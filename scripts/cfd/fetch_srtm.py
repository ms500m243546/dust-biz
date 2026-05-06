"""Phase BB.2 — SRTM 30 m tile fetcher.

Public-domain SRTM v3 1-arc-second tiles from AWS Open Data
(`elevation-tiles-prod` bucket). 3601 x 3601 int16 big-endian
elevation grids, gzipped.

Default tile set covers Los Pelambres (S32W071, S32W072, S33W071,
S33W072). Tiles drop into `cfd/<mine>/dem/<TILE>.hgt`. Already-
present tiles are skipped (idempotent).

Bytes per uncompressed tile: 3601 * 3601 * 2 = ~26 MB. Compressed
download ~12 MB. 4 tiles ≈ 50 MB on disk.
"""

from __future__ import annotations

import argparse
import gzip
import io
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

LOS_PELAMBRES_TILES = ("S32W071", "S32W072", "S33W071", "S33W072")

S3_BUCKET = "https://elevation-tiles-prod.s3.amazonaws.com/skadi"


def _tile_url(tile_name: str) -> str:
    """elevation-tiles-prod uses skadi/<lat>/<file>.hgt.gz layout."""
    lat_band = tile_name[:3]   # e.g. "S32" or "N48"
    return f"{S3_BUCKET}/{lat_band}/{tile_name}.hgt.gz"


def fetch_tile(tile_name: str, out_dir: Path, timeout: float = 60.0) -> Path:
    """Download + decompress one tile. Returns the local .hgt path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{tile_name}.hgt"
    if target.exists() and target.stat().st_size > 0:
        return target
    url = _tile_url(tile_name)
    print(f"  fetching {url}")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "DustOps-AI/0.1 (+SRTM tile fetch)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    decompressed = gzip.decompress(data)
    target.write_bytes(decompressed)
    print(f"  -> {target} ({len(decompressed):,} bytes)")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch public-domain SRTM tiles.")
    parser.add_argument(
        "--tiles", nargs="+", default=list(LOS_PELAMBRES_TILES),
        help="Tile names like S32W071. Default: Los Pelambres bbox.",
    )
    parser.add_argument(
        "--out-dir", default=str(ROOT / "cfd" / "los_pelambres" / "dem"),
        help="Output directory for .hgt files.",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    print(f"Fetching {len(args.tiles)} SRTM tiles -> {out_dir}")
    paths: list[Path] = []
    for tile in args.tiles:
        try:
            p = fetch_tile(tile, out_dir)
            paths.append(p)
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED {tile}: {exc}", file=sys.stderr)
    print(f"Done: {len(paths)}/{len(args.tiles)} tiles available")
    return 0 if len(paths) == len(args.tiles) else 1


if __name__ == "__main__":
    sys.exit(main())
