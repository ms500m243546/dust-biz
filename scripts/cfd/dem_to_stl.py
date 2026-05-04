"""SRTM `.hgt` -> STL terrain pipeline (Phase BA.2).

Reads NASA SRTM 30 m / 1-arc-second `.hgt` files (1201 x 1201 big-
endian int16 elevation grids; void = -32768), assembles them into a
contiguous lat/lon grid, crops to the operator-supplied bounding
box, projects to a local Cartesian frame (UTM-equivalent
equirectangular projection at the bbox centroid), and emits a
binary STL surface ready for OpenFOAM `snappyHexMesh`.

No GDAL / rasterio dependency. Pure-Python + numpy. Matches the
deferred-mode pattern used elsewhere in the codebase: heavy
spatial libraries stay out of CI; the operator runs this once
per campaign to materialise the terrain STL.

Tile naming: SRTM follows `{N|S}{lat}{E|W}{lon}.hgt` where lat/lon
are the southwest corner. So `S32W071.hgt` covers (-32, -71) to
(-31, -70) (lat increasing north, lon increasing east).
"""

from __future__ import annotations

import argparse
import math
import struct
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SRTM_TILE_SAMPLES = 1201  # 1-arc-second tiles are 1201x1201 (3601 for SRTM 30m v3, but
# the legacy SRTM3 format we use is 1201). If your tiles are 3601,
# pass --tile-samples 3601.
SRTM_VOID = -32768
EARTH_RADIUS_M = 6_378_137.0


@dataclass(frozen=True)
class TileMeta:
    """Parsed SRTM tile filename: SW corner lat/lon."""

    lat_sw: int  # integer degrees, north-positive
    lon_sw: int  # integer degrees, east-positive
    path: Path


def parse_tile_filename(path: Path) -> TileMeta:
    """E.g. `S32W071.hgt` -> TileMeta(lat_sw=-32, lon_sw=-71, ...)."""
    stem = path.stem.upper()
    if len(stem) != 7 or stem[0] not in {"N", "S"} or stem[3] not in {"E", "W"}:
        raise ValueError(
            f"unrecognised SRTM tile name {path.name!r}; expected like S32W071.hgt"
        )
    lat = int(stem[1:3])
    lon = int(stem[4:7])
    if stem[0] == "S":
        lat = -lat
    if stem[3] == "W":
        lon = -lon
    return TileMeta(lat_sw=lat, lon_sw=lon, path=path)


def read_tile(meta: TileMeta, samples: int = SRTM_TILE_SAMPLES) -> np.ndarray:
    """Return a (samples, samples) float32 grid in metres.

    Row 0 is the *northernmost* row (lat = lat_sw + 1 - row/samples * 1°).
    Column 0 is the *westernmost* col (lon = lon_sw + col/samples * 1°).
    Voids are replaced by NaN; downstream code should fill via
    nearest-neighbour or skip those triangles.
    """
    expected_bytes = samples * samples * 2
    raw = meta.path.read_bytes()
    if len(raw) != expected_bytes:
        raise ValueError(
            f"{meta.path.name}: expected {expected_bytes} bytes "
            f"({samples}x{samples} int16), got {len(raw)}. "
            f"If your tiles are 3601-sample, pass --tile-samples 3601."
        )
    # Big-endian int16; numpy handles this natively.
    arr = np.frombuffer(raw, dtype=">i2").reshape(samples, samples).astype(np.float32)
    arr[arr == SRTM_VOID] = np.nan
    return arr


def assemble_mosaic(
    tiles: list[TileMeta],
    samples: int = SRTM_TILE_SAMPLES,
) -> tuple[np.ndarray, float, float, float]:
    """Stitch tiles into a single grid covering the union bbox.

    Returns (elevation, lat_north, lon_west, deg_per_pixel).
    `elevation[r, c]` corresponds to lat_north - r * deg_per_pixel,
    lon_west + c * deg_per_pixel.
    """
    if not tiles:
        raise ValueError("no tiles supplied")
    lat_min = min(t.lat_sw for t in tiles)
    lat_max = max(t.lat_sw for t in tiles) + 1
    lon_min = min(t.lon_sw for t in tiles)
    lon_max = max(t.lon_sw for t in tiles) + 1

    rows = (lat_max - lat_min) * (samples - 1) + 1
    cols = (lon_max - lon_min) * (samples - 1) + 1
    deg_per_pixel = 1.0 / (samples - 1)
    out = np.full((rows, cols), np.nan, dtype=np.float32)

    for tile in tiles:
        grid = read_tile(tile, samples=samples)
        # Tile spans lat [lat_sw, lat_sw+1] and lon [lon_sw, lon_sw+1].
        # In the mosaic, north -> small row index.
        row_offset = (lat_max - (tile.lat_sw + 1)) * (samples - 1)
        col_offset = (tile.lon_sw - lon_min) * (samples - 1)
        out[
            row_offset : row_offset + samples,
            col_offset : col_offset + samples,
        ] = grid
    return out, float(lat_max), float(lon_min), deg_per_pixel


def crop_to_bbox(
    elevation: np.ndarray,
    lat_north: float,
    lon_west: float,
    deg_per_pixel: float,
    bbox: tuple[float, float, float, float],
) -> tuple[np.ndarray, float, float]:
    """Crop the mosaic to (lon_min, lat_min, lon_max, lat_max).

    Returns (cropped_elevation, lat_north_cropped, lon_west_cropped).
    """
    lon_min_b, lat_min_b, lon_max_b, lat_max_b = bbox
    if not (lon_min_b < lon_max_b and lat_min_b < lat_max_b):
        raise ValueError(f"degenerate bbox {bbox}")
    # Convert bbox corners to row/col in the mosaic.
    row_top = max(0, int(round((lat_north - lat_max_b) / deg_per_pixel)))
    row_bot = min(
        elevation.shape[0],
        int(round((lat_north - lat_min_b) / deg_per_pixel)) + 1,
    )
    col_lft = max(0, int(round((lon_min_b - lon_west) / deg_per_pixel)))
    col_rht = min(
        elevation.shape[1],
        int(round((lon_max_b - lon_west) / deg_per_pixel)) + 1,
    )
    if row_bot <= row_top or col_rht <= col_lft:
        raise ValueError(
            f"bbox {bbox} doesn't overlap mosaic "
            f"(lat_north={lat_north}, lon_west={lon_west})"
        )
    cropped = elevation[row_top:row_bot, col_lft:col_rht].copy()
    new_lat_north = lat_north - row_top * deg_per_pixel
    new_lon_west = lon_west + col_lft * deg_per_pixel
    return cropped, new_lat_north, new_lon_west


def fill_voids_nearest(elevation: np.ndarray) -> np.ndarray:
    """Replace NaN voids with the nearest non-NaN neighbour.

    Cheap iterative dilation rather than scipy's distance transform
    (no scipy dep). For small void counts (typical SRTM) this is
    fast enough.
    """
    out = elevation.copy()
    nan_mask = np.isnan(out)
    if not nan_mask.any():
        return out
    # Iteratively propagate from non-NaN neighbours. Capped iterations
    # so a fully-NaN region doesn't loop forever.
    for _ in range(64):
        if not nan_mask.any():
            break
        # Replace each NaN with the mean of its non-NaN neighbours
        # in a 3x3 stencil.
        padded = np.pad(out, 1, mode="edge")
        neigh_sum = (
            padded[:-2, :-2] + padded[:-2, 1:-1] + padded[:-2, 2:]
            + padded[1:-1, :-2] + padded[1:-1, 2:]
            + padded[2:, :-2] + padded[2:, 1:-1] + padded[2:, 2:]
        )
        neigh_count = (
            (~np.isnan(padded[:-2, :-2])).astype(np.float32)
            + (~np.isnan(padded[:-2, 1:-1])).astype(np.float32)
            + (~np.isnan(padded[:-2, 2:])).astype(np.float32)
            + (~np.isnan(padded[1:-1, :-2])).astype(np.float32)
            + (~np.isnan(padded[1:-1, 2:])).astype(np.float32)
            + (~np.isnan(padded[2:, :-2])).astype(np.float32)
            + (~np.isnan(padded[2:, 1:-1])).astype(np.float32)
            + (~np.isnan(padded[2:, 2:])).astype(np.float32)
        )
        # Guard: where neigh_sum is itself NaN (everything around was
        # NaN), keep NaN — the next iteration will reach further.
        with np.errstate(invalid="ignore"):
            avg = neigh_sum / np.where(neigh_count > 0, neigh_count, 1)
        out = np.where(nan_mask & (neigh_count > 0), avg, out)
        nan_mask = np.isnan(out)
    if nan_mask.any():
        # Failure to fill: backfill remaining NaNs with global mean
        # so downstream code never sees NaN. Surface a warning to stderr.
        global_mean = float(np.nanmean(elevation))
        out[np.isnan(out)] = global_mean
        print(
            f"warning: {nan_mask.sum()} NaN voids could not be neighbour-filled; "
            f"set to global mean {global_mean:.1f} m",
            file=sys.stderr,
        )
    return out


def project_to_local_xyz(
    elevation: np.ndarray,
    lat_north: float,
    lon_west: float,
    deg_per_pixel: float,
) -> np.ndarray:
    """Equirectangular projection at the bbox centroid.

    Output is (rows, cols, 3) float32 with x = east metres, y = north
    metres, z = elevation metres. Origin (0, 0, 0) is the centroid of
    the bbox at z = sea level. Adequate for mine-scale (10s of km);
    proper UTM projection deferred until a domain breaks the
    flat-earth approximation (won't happen at Los Pelambres scale).
    """
    rows, cols = elevation.shape
    lat_centre = lat_north - (rows - 1) / 2 * deg_per_pixel
    lon_centre = lon_west + (cols - 1) / 2 * deg_per_pixel
    deg_to_rad = math.pi / 180.0
    metres_per_deg_lat = EARTH_RADIUS_M * deg_to_rad
    metres_per_deg_lon = metres_per_deg_lat * math.cos(lat_centre * deg_to_rad)

    row_idx = np.arange(rows, dtype=np.float32).reshape(-1, 1)
    col_idx = np.arange(cols, dtype=np.float32).reshape(1, -1)
    lat_grid = lat_north - row_idx * deg_per_pixel  # (rows, 1)
    lon_grid = lon_west + col_idx * deg_per_pixel  # (1, cols)

    x = (lon_grid - lon_centre) * metres_per_deg_lon  # east metres
    y = (lat_grid - lat_centre) * metres_per_deg_lat  # north metres
    x_b, y_b = np.broadcast_arrays(x, y)
    coords = np.stack([x_b, y_b, elevation], axis=-1).astype(np.float32)
    return coords


def write_binary_stl(
    coords: np.ndarray,
    out_path: Path,
    name: str = "terrain",
) -> int:
    """Triangulate the (rows, cols, 3) grid and write an 80-byte-header binary STL.

    Each grid cell becomes 2 triangles (NW/SE and NE/SW). Returns the
    number of triangles written.
    """
    rows, cols, _ = coords.shape
    if rows < 2 or cols < 2:
        raise ValueError(f"need a >=2x2 grid to triangulate, got {rows}x{cols}")
    n_tris: int = int((rows - 1) * (cols - 1) * 2)

    # Vertex layout per cell (r, c):
    #   v00 = (r, c)         v01 = (r, c+1)
    #   v10 = (r+1, c)       v11 = (r+1, c+1)
    # Triangle 1: v00, v11, v10  (CCW from above when y increases northward)
    # Triangle 2: v00, v01, v11
    v00 = coords[:-1, :-1]
    v01 = coords[:-1, 1:]
    v10 = coords[1:, :-1]
    v11 = coords[1:, 1:]

    tri1 = np.stack([v00, v11, v10], axis=-2)  # (rows-1, cols-1, 3, 3)
    tri2 = np.stack([v00, v01, v11], axis=-2)

    triangles = np.concatenate(
        [tri1.reshape(-1, 3, 3), tri2.reshape(-1, 3, 3)], axis=0
    )

    # Compute facet normals.
    e1 = triangles[:, 1] - triangles[:, 0]
    e2 = triangles[:, 2] - triangles[:, 0]
    normals = np.cross(e1, e2)
    norms = np.linalg.norm(normals, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normals = (normals / norms).astype(np.float32)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as fh:
        # 80-byte header (binary STL).
        header = name.encode("utf-8")[:80].ljust(80, b"\x00")
        fh.write(header)
        fh.write(struct.pack("<I", n_tris))
        for i in range(n_tris):
            fh.write(struct.pack("<fff", *normals[i]))
            for v in triangles[i]:
                fh.write(struct.pack("<fff", *v.astype(np.float32)))
            fh.write(b"\x00\x00")  # attribute byte count
    return n_tris


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert SRTM .hgt tiles into a binary STL terrain surface."
    )
    parser.add_argument(
        "--tiles",
        nargs="+",
        required=True,
        help="One or more .hgt SRTM tiles (filenames must follow N|S<lat>E|W<lon>.hgt).",
    )
    parser.add_argument(
        "--bbox",
        required=True,
        help="lon_min,lat_min,lon_max,lat_max (decimal degrees, WGS84).",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output STL path.",
    )
    parser.add_argument(
        "--tile-samples",
        type=int,
        default=SRTM_TILE_SAMPLES,
        help="Tile resolution; 1201 for SRTM3 (default), 3601 for SRTM 30m v3.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    bbox = tuple(float(x) for x in args.bbox.split(","))
    if len(bbox) != 4:
        parser.error("--bbox must be lon_min,lat_min,lon_max,lat_max (4 floats)")
    bbox_t: tuple[float, float, float, float] = (bbox[0], bbox[1], bbox[2], bbox[3])

    tiles = [parse_tile_filename(Path(p)) for p in args.tiles]
    print(f"Parsing {len(tiles)} tiles...")
    mosaic, lat_n, lon_w, dpp = assemble_mosaic(tiles, samples=args.tile_samples)
    print(f"Mosaic: {mosaic.shape}, lat_north={lat_n:.4f}, lon_west={lon_w:.4f}, dpp={dpp:.6f}")

    cropped, lat_n_c, lon_w_c = crop_to_bbox(mosaic, lat_n, lon_w, dpp, bbox_t)
    print(f"Cropped: {cropped.shape}")

    filled = fill_voids_nearest(cropped)
    coords = project_to_local_xyz(filled, lat_n_c, lon_w_c, dpp)
    print(f"Projected: {coords.shape}; x range {coords[..., 0].min():.0f}..{coords[..., 0].max():.0f} m")

    n = write_binary_stl(coords, Path(args.out))
    print(f"Wrote {n} triangles -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
