"""Phase BC.4 — STL pre-flight validator.

Catches mesh-killing corruption before committing 60-72 h of OpenFOAM
compute to a bad terrain. Validates a binary STL on these axes:

* File size matches the declared triangle count (header field).
* Triangle count is non-zero and bounded (sanity bounds: 1k..50M).
* No degenerate triangles (zero area within float epsilon).
* No NaN / Inf vertex coordinates.
* Bounding box covers a domain at least as large as the OpenFOAM
  blockMesh, with a configurable buffer.

Designed to fail fast and loudly: the moment a check trips, the
script prints the failure + non-zero exits. CI calls this with
`--strict`; the operator can run it without `--strict` to inspect a
case under construction.
"""

from __future__ import annotations

import argparse
import struct
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import numpy as np

# Default bounds aligned with cfd/los_pelambres/template/system/blockMeshDict
# (10 km x 10 km x 3 km centred on 0,0,0). The STL must extend at
# least to these bounds (with a small buffer) for snappyHexMesh to
# refine the terrain everywhere it matters.
DEFAULT_BLOCKMESH_HALF_X_M = 5_000.0
DEFAULT_BLOCKMESH_HALF_Y_M = 5_000.0
DEFAULT_BUFFER_M = 500.0
DEGENERATE_AREA_EPS = 1e-6

MIN_TRIANGLES = 1_000
MAX_TRIANGLES = 50_000_000


@dataclass(frozen=True)
class STLReport:
    path: Path
    file_size_bytes: int
    triangle_count: int
    degenerate_triangles: int
    nan_vertices: int
    bbox_min: tuple[float, float, float]
    bbox_max: tuple[float, float, float]
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


def _read_header(fh: BinaryIO) -> tuple[bytes, int]:
    header = fh.read(80)
    if len(header) != 80:
        raise ValueError("STL truncated: header < 80 bytes")
    raw_count = fh.read(4)
    if len(raw_count) != 4:
        raise ValueError("STL truncated: missing triangle-count field")
    n_tris: int = struct.unpack("<I", raw_count)[0]
    return header, n_tris


def validate_binary_stl(
    path: Path,
    *,
    expected_half_x_m: float = DEFAULT_BLOCKMESH_HALF_X_M,
    expected_half_y_m: float = DEFAULT_BLOCKMESH_HALF_Y_M,
    buffer_m: float = DEFAULT_BUFFER_M,
) -> STLReport:
    """Parse + validate. Always returns a report; failures listed inside."""
    failures: list[str] = []
    file_size = path.stat().st_size
    with path.open("rb") as fh:
        _, n_tris = _read_header(fh)
        # 50 bytes per triangle: 12 normal + 36 vertex coords + 2 attr.
        expected_size = 80 + 4 + 50 * n_tris
        if file_size != expected_size:
            failures.append(
                f"file size {file_size} != header_count*50+84 = {expected_size}"
            )
        if n_tris < MIN_TRIANGLES:
            failures.append(
                f"triangle_count={n_tris} below sanity floor {MIN_TRIANGLES}"
            )
        if n_tris > MAX_TRIANGLES:
            failures.append(
                f"triangle_count={n_tris} above sanity ceiling {MAX_TRIANGLES}"
            )

        # Read all vertex data; degenerate detection + bbox.
        # 50 bytes per tri = (3 normal + 9 vertex) floats + 2 byte tail.
        chunk_dtype = np.dtype([
            ("normal", "<f4", 3),
            ("v0", "<f4", 3),
            ("v1", "<f4", 3),
            ("v2", "<f4", 3),
            ("attr", "<u2"),
        ])
        # If declared count overruns the file, clamp so we don't
        # request bytes we don't have.
        readable_n = min(n_tris, max(0, (file_size - 84) // 50))
        if readable_n > 0:
            buf = np.frombuffer(fh.read(readable_n * 50), dtype=chunk_dtype)
        else:
            buf = np.empty(0, dtype=chunk_dtype)

    if buf.size == 0:
        return STLReport(
            path=path, file_size_bytes=file_size, triangle_count=n_tris,
            degenerate_triangles=0, nan_vertices=0,
            bbox_min=(0.0, 0.0, 0.0), bbox_max=(0.0, 0.0, 0.0),
            failures=tuple(failures + ["no triangles readable"]),
        )

    verts = np.stack([buf["v0"], buf["v1"], buf["v2"]], axis=1)  # (N,3,3)
    nan_mask = np.isnan(verts) | np.isinf(verts)
    nan_count = int(nan_mask.any(axis=(1, 2)).sum())
    if nan_count:
        failures.append(f"{nan_count} triangles contain NaN/Inf vertices")

    e1 = verts[:, 1] - verts[:, 0]
    e2 = verts[:, 2] - verts[:, 0]
    cross = np.cross(e1, e2)
    areas = 0.5 * np.linalg.norm(cross, axis=1)
    degenerate_count = int((areas < DEGENERATE_AREA_EPS).sum())
    if degenerate_count > 0:
        failures.append(
            f"{degenerate_count} degenerate triangles (area < {DEGENERATE_AREA_EPS})"
        )

    flat = verts.reshape(-1, 3)
    finite_flat = flat[np.isfinite(flat).all(axis=1)]
    if finite_flat.size:
        bbox_min = tuple(float(x) for x in finite_flat.min(axis=0))
        bbox_max = tuple(float(x) for x in finite_flat.max(axis=0))
    else:
        bbox_min = (0.0, 0.0, 0.0)
        bbox_max = (0.0, 0.0, 0.0)

    required_x = expected_half_x_m + buffer_m
    required_y = expected_half_y_m + buffer_m
    if bbox_min[0] > -required_x:
        failures.append(
            f"bbox xmin {bbox_min[0]:.0f} > -{required_x:.0f}; "
            f"STL doesn't cover the western blockMesh face + buffer"
        )
    if bbox_max[0] < required_x:
        failures.append(
            f"bbox xmax {bbox_max[0]:.0f} < {required_x:.0f}; "
            f"STL doesn't cover the eastern blockMesh face + buffer"
        )
    if bbox_min[1] > -required_y:
        failures.append(
            f"bbox ymin {bbox_min[1]:.0f} > -{required_y:.0f}; "
            f"STL doesn't cover the southern blockMesh face + buffer"
        )
    if bbox_max[1] < required_y:
        failures.append(
            f"bbox ymax {bbox_max[1]:.0f} < {required_y:.0f}; "
            f"STL doesn't cover the northern blockMesh face + buffer"
        )

    bbox_min_t: tuple[float, float, float] = (bbox_min[0], bbox_min[1], bbox_min[2])
    bbox_max_t: tuple[float, float, float] = (bbox_max[0], bbox_max[1], bbox_max[2])
    return STLReport(
        path=path,
        file_size_bytes=file_size,
        triangle_count=n_tris,
        degenerate_triangles=degenerate_count,
        nan_vertices=nan_count,
        bbox_min=bbox_min_t,
        bbox_max=bbox_max_t,
        failures=tuple(failures),
    )


def _print_report(r: STLReport) -> None:
    print(f"STL: {r.path}")
    print(f"  size      : {r.file_size_bytes:,} bytes")
    print(f"  triangles : {r.triangle_count:,}")
    print(f"  bbox min  : ({r.bbox_min[0]:.1f}, {r.bbox_min[1]:.1f}, {r.bbox_min[2]:.1f}) m")
    print(f"  bbox max  : ({r.bbox_max[0]:.1f}, {r.bbox_max[1]:.1f}, {r.bbox_max[2]:.1f}) m")
    print(f"  degenerate: {r.degenerate_triangles}")
    print(f"  NaN/Inf   : {r.nan_vertices}")
    if r.failures:
        print("  FAILURES:")
        for f in r.failures:
            print(f"    - {f}")
    else:
        print("  OK")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an OpenFOAM-bound STL.")
    parser.add_argument("--stl", required=True, help="Path to binary STL.")
    parser.add_argument("--half-x-m", type=float, default=DEFAULT_BLOCKMESH_HALF_X_M)
    parser.add_argument("--half-y-m", type=float, default=DEFAULT_BLOCKMESH_HALF_Y_M)
    parser.add_argument("--buffer-m", type=float, default=DEFAULT_BUFFER_M)
    parser.add_argument(
        "--strict", action="store_true",
        help="Exit non-zero on any failure (CI mode).",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = validate_binary_stl(
        Path(args.stl),
        expected_half_x_m=args.half_x_m,
        expected_half_y_m=args.half_y_m,
        buffer_m=args.buffer_m,
    )
    _print_report(report)
    if args.strict and not report.passed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
