"""Phase BA.2 — DEM-to-STL pipeline tests.

Synthetic SRTM tiles (small, in-memory) exercise the parser, mosaic
assembly, void filling, projection, and STL writer. No actual SRTM
downloads.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest

from scripts.cfd.dem_to_stl import (
    SRTM_VOID,
    assemble_mosaic,
    crop_to_bbox,
    fill_voids_nearest,
    parse_tile_filename,
    project_to_local_xyz,
    read_tile,
    write_binary_stl,
)


def _write_synthetic_tile(
    path: Path,
    samples: int = 9,
    base_elevation: int = 1000,
) -> None:
    """Write a synthetic .hgt with a smooth elevation gradient."""
    grid = np.full((samples, samples), base_elevation, dtype=">i2")
    # Add a NS gradient so we can verify orientation later.
    for r in range(samples):
        grid[r, :] = base_elevation + r * 10
    path.write_bytes(grid.tobytes())


def test_parse_tile_filename_southwest() -> None:
    meta = parse_tile_filename(Path("S32W071.hgt"))
    assert meta.lat_sw == -32
    assert meta.lon_sw == -71


def test_parse_tile_filename_northeast() -> None:
    meta = parse_tile_filename(Path("N48E123.hgt"))
    assert meta.lat_sw == 48
    assert meta.lon_sw == 123


def test_parse_tile_filename_rejects_bad() -> None:
    with pytest.raises(ValueError):
        parse_tile_filename(Path("bogus.hgt"))


def test_read_tile_replaces_voids_with_nan(tmp_path: Path) -> None:
    samples = 9
    p = tmp_path / "S32W071.hgt"
    grid = np.full((samples, samples), 100, dtype=">i2")
    grid[3, 3] = SRTM_VOID
    p.write_bytes(grid.tobytes())
    out = read_tile(parse_tile_filename(p), samples=samples)
    assert np.isnan(out[3, 3])
    assert out[0, 0] == 100.0


def test_assemble_mosaic_two_horizontally_adjacent_tiles(tmp_path: Path) -> None:
    samples = 5
    a = tmp_path / "S32W071.hgt"
    b = tmp_path / "S32W070.hgt"
    _write_synthetic_tile(a, samples=samples, base_elevation=100)
    _write_synthetic_tile(b, samples=samples, base_elevation=200)
    tiles = [parse_tile_filename(a), parse_tile_filename(b)]
    mosaic, lat_n, lon_w, dpp = assemble_mosaic(tiles, samples=samples)
    # Two tiles span 2 longitudes (W071 and W070, both covering lat -32 to -31).
    # Rows = (samples - 1) + 1 = 5; cols = 2 * (samples - 1) + 1 = 9.
    assert mosaic.shape == (5, 9)
    assert lat_n == -31.0
    assert lon_w == -71.0
    # Western tile fills cols 0..4; eastern fills cols 4..8.
    # Boundary col (4) is shared; both tiles wrote there. Last tile wins (eastern, base=200).


def test_crop_to_bbox_inside_mosaic(tmp_path: Path) -> None:
    samples = 9
    a = tmp_path / "S32W071.hgt"
    _write_synthetic_tile(a, samples=samples, base_elevation=500)
    tiles = [parse_tile_filename(a)]
    mosaic, lat_n, lon_w, dpp = assemble_mosaic(tiles, samples=samples)
    # bbox = (-70.75, -31.75, -70.25, -31.25) — middle half of the tile.
    cropped, _, _ = crop_to_bbox(mosaic, lat_n, lon_w, dpp, (-70.75, -31.75, -70.25, -31.25))
    assert cropped.shape[0] >= 3 and cropped.shape[1] >= 3
    # Same elevation gradient as the synthetic source.
    assert not np.isnan(cropped).any()


def test_crop_to_bbox_rejects_outside() -> None:
    mosaic = np.zeros((10, 10), dtype=np.float32)
    with pytest.raises(ValueError):
        crop_to_bbox(mosaic, -31.0, -71.0, 0.1, (-60.0, -20.0, -55.0, -15.0))


def test_fill_voids_nearest_recovers_isolated_nan() -> None:
    grid = np.full((5, 5), 100.0, dtype=np.float32)
    grid[2, 2] = np.nan
    out = fill_voids_nearest(grid)
    assert not np.isnan(out).any()
    assert abs(out[2, 2] - 100.0) < 1e-3


def test_fill_voids_nearest_handles_fully_void(capsys: pytest.CaptureFixture[str]) -> None:
    grid = np.full((4, 4), 50.0, dtype=np.float32)
    grid[:] = np.nan
    grid[0, 0] = 50.0  # one valid pixel
    out = fill_voids_nearest(grid)
    assert not np.isnan(out).any()


def test_project_to_local_xyz_centroid_origin() -> None:
    # 3x3 elevation grid centred at lat -31.5, lon -70.5.
    grid = np.zeros((3, 3), dtype=np.float32)
    coords = project_to_local_xyz(grid, lat_north=-31.0, lon_west=-71.0, deg_per_pixel=0.5)
    # Centre cell should be at (0, 0, 0).
    assert abs(coords[1, 1, 0]) < 1.0  # x ~ 0 m
    assert abs(coords[1, 1, 1]) < 1.0  # y ~ 0 m
    assert coords[1, 1, 2] == 0.0  # z = elevation


def test_write_binary_stl_emits_correct_triangle_count(tmp_path: Path) -> None:
    coords = np.zeros((3, 3, 3), dtype=np.float32)
    coords[..., 0] = np.arange(3).reshape(1, -1)
    coords[..., 1] = np.arange(3).reshape(-1, 1)
    out = tmp_path / "terrain.stl"
    n = write_binary_stl(coords, out, name="test")
    # 2 triangles per cell, (3-1) x (3-1) cells = 4 cells -> 8 triangles.
    assert n == 8
    raw = out.read_bytes()
    # 80-byte header + 4-byte tri count + 50 bytes per triangle.
    assert len(raw) == 80 + 4 + 50 * 8
    assert struct.unpack("<I", raw[80:84])[0] == 8


def test_end_to_end_synthetic(tmp_path: Path) -> None:
    samples = 9
    a = tmp_path / "S32W071.hgt"
    b = tmp_path / "S32W070.hgt"
    _write_synthetic_tile(a, samples=samples, base_elevation=100)
    _write_synthetic_tile(b, samples=samples, base_elevation=200)
    tiles = [parse_tile_filename(a), parse_tile_filename(b)]
    mosaic, lat_n, lon_w, dpp = assemble_mosaic(tiles, samples=samples)
    cropped, lat_n_c, lon_w_c = crop_to_bbox(
        mosaic, lat_n, lon_w, dpp, (-70.7, -31.7, -70.3, -31.3)
    )
    filled = fill_voids_nearest(cropped)
    coords = project_to_local_xyz(filled, lat_n_c, lon_w_c, dpp)
    out = tmp_path / "out.stl"
    n = write_binary_stl(coords, out)
    assert n > 0
    assert out.stat().st_size > 84
