"""Phase BC.4 — STL validator tests."""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest

from scripts.cfd.dem_to_stl import write_binary_stl
from scripts.cfd.validate_stl import (
    DEFAULT_BLOCKMESH_HALF_X_M,
    DEFAULT_BUFFER_M,
    validate_binary_stl,
)


def _grid_stl(tmp_path: Path, *, half_extent_m: float = 6_000.0) -> Path:
    """Build a synthetic STL covering [-half, +half] in x + y, flat z.

    32x32 grid -> 1,922 triangles, comfortably above the validator's
    1000-triangle sanity floor.
    """
    n = 32
    coords = np.zeros((n, n, 3), dtype=np.float32)
    span = np.linspace(-half_extent_m, half_extent_m, n, dtype=np.float32)
    coords[..., 0] = span.reshape(1, -1)
    coords[..., 1] = span.reshape(-1, 1)
    p = tmp_path / "synth.stl"
    write_binary_stl(coords, p, name="synth")
    return p


def test_passes_on_clean_stl_covering_blockmesh(tmp_path: Path) -> None:
    p = _grid_stl(tmp_path, half_extent_m=DEFAULT_BLOCKMESH_HALF_X_M + DEFAULT_BUFFER_M + 100)
    report = validate_binary_stl(p)
    assert report.passed, report.failures
    assert report.triangle_count > 0
    assert report.degenerate_triangles == 0
    assert report.nan_vertices == 0


def test_fails_when_bbox_too_small(tmp_path: Path) -> None:
    # Tiny STL — covers only ±100 m, way less than the blockMesh.
    p = _grid_stl(tmp_path, half_extent_m=100.0)
    report = validate_binary_stl(p)
    assert not report.passed
    assert any("blockMesh" in f for f in report.failures)


def test_fails_on_truncated_file(tmp_path: Path) -> None:
    p = _grid_stl(tmp_path, half_extent_m=DEFAULT_BLOCKMESH_HALF_X_M + 600)
    raw = p.read_bytes()
    # Lop off the last 200 bytes -> file size won't match header count.
    p.write_bytes(raw[:-200])
    report = validate_binary_stl(p)
    assert not report.passed
    assert any("file size" in f for f in report.failures)


def test_detects_degenerate_triangles(tmp_path: Path) -> None:
    # Hand-craft an STL with one degenerate triangle (3 colinear points)
    # plus one valid triangle to clear the min-count bound? No — the
    # min-count is 1000, so we use the synth then poke a triangle.
    p = _grid_stl(tmp_path, half_extent_m=DEFAULT_BLOCKMESH_HALF_X_M + 600)
    raw = bytearray(p.read_bytes())
    # Overwrite the first triangle's vertices to be colinear at origin.
    # Triangle layout in the file: 12 bytes normal + 36 bytes (v0,v1,v2) + 2 attr.
    offset = 84  # past 80-byte header + 4-byte count
    # Skip the 12-byte normal, then write 9 floats of zero for v0,v1,v2.
    zero_vert = struct.pack("<9f", *([0.0] * 9))
    raw[offset + 12 : offset + 12 + 36] = zero_vert
    p.write_bytes(bytes(raw))
    report = validate_binary_stl(p)
    assert report.degenerate_triangles >= 1
    assert any("degenerate" in f for f in report.failures)


def test_detects_nan_vertices(tmp_path: Path) -> None:
    p = _grid_stl(tmp_path, half_extent_m=DEFAULT_BLOCKMESH_HALF_X_M + 600)
    raw = bytearray(p.read_bytes())
    # Write a NaN into the first vertex's x-coordinate.
    nan_bytes = struct.pack("<f", float("nan"))
    # First vertex starts at offset 84 + 12 (normal).
    raw[96:100] = nan_bytes
    p.write_bytes(bytes(raw))
    report = validate_binary_stl(p)
    assert report.nan_vertices >= 1
    assert any("NaN" in f for f in report.failures)


def test_real_terrain_stl_passes_if_present() -> None:
    p = Path("cfd/los_pelambres/template/constant/triSurface/terrain.stl")
    if not p.exists():
        pytest.skip("real Los Pelambres STL not present (BB.2 not run)")
    report = validate_binary_stl(p)
    # Print before assert so CI surfaces the report on failure.
    if not report.passed:
        print(f"Real STL failures: {report.failures}")
    assert report.passed
