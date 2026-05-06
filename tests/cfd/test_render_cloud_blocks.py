"""Phase BC.1 — cloud-block renderer tests."""

from __future__ import annotations

import pytest

from app.cfd.projection import LOS_PELAMBRES_CENTROID, CentroidProjection
from scripts.cfd.render_cloud_blocks import (
    render_injection_sites,
    render_receptor_samplers,
    render_topo_set_cellzones,
)


def _zone(zone_id: str, ring: list[list[float]]) -> dict[str, object]:
    return {
        "zone_id": zone_id,
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }


def _haul_road(seg_id: str, coords: list[list[float]], length_m: float) -> dict[str, object]:
    return {
        "segment_id": seg_id,
        "length_m": length_m,
        "geometry": {"type": "LineString", "coordinates": coords},
    }


def test_projection_origin_maps_to_zero_zero() -> None:
    p = LOS_PELAMBRES_CENTROID
    x, y, _ = p.project(lon=p.centroid_lon, lat=p.centroid_lat)
    assert abs(x) < 1e-6
    assert abs(y) < 1e-6


def test_projection_east_is_positive_x() -> None:
    p = LOS_PELAMBRES_CENTROID
    x_east, y_east, _ = p.project(lon=p.centroid_lon + 0.05, lat=p.centroid_lat)
    assert x_east > 0
    assert abs(y_east) < 50  # tiny lat-residual from sphere; should be near 0
    x_north, y_north, _ = p.project(lon=p.centroid_lon, lat=p.centroid_lat + 0.05)
    assert y_north > 0
    assert abs(x_north) < 50


def test_render_injection_sites_includes_cone_keys() -> None:
    z = _zone("zone-A", [[-70.5, -31.7], [-70.49, -31.7], [-70.49, -31.69], [-70.5, -31.69], [-70.5, -31.7]])
    out = render_injection_sites(zones=[z], haul_roads=[], proj=LOS_PELAMBRES_CENTROID)
    assert "src_zone_A" in out
    assert "coneInjection" in out
    assert "thetaOuter" in out
    # Must contain a fixed sizeDistribution with the 5e-6 m default.
    assert "5.00e-06" in out


def test_render_injection_sites_haul_road_top_n_caps_count() -> None:
    z = _zone("zone-A", [[-70.5, -31.7], [-70.49, -31.7], [-70.49, -31.69], [-70.5, -31.7]])
    haul_roads = [
        _haul_road(f"hr-{i:03d}", [[-70.55 + 0.0001 * i, -31.72]] * 2, length_m=float(50 + i))
        for i in range(50)
    ]
    out = render_injection_sites(
        zones=[z], haul_roads=haul_roads, proj=LOS_PELAMBRES_CENTROID,
        haul_road_top_n=5,
    )
    # 1 zone + 5 longest haul-road segments = 6 src_ keys.
    assert out.count("src_") == 6
    # Longest is hr-049; it must appear, hr-000 (shortest) must not.
    assert "src_hr_049" in out
    assert "src_hr_000" not in out


def test_render_injection_sites_skips_empty_polygons() -> None:
    bad = {"zone_id": "empty", "geometry": {"coordinates": []}}
    out = render_injection_sites(zones=[bad], haul_roads=[], proj=LOS_PELAMBRES_CENTROID)
    assert out == ""


def test_render_receptor_samplers_emits_void_fraction() -> None:
    out = render_receptor_samplers()
    assert "voidFraction" in out


def test_render_topo_set_cellzones_emits_cylinder_per_receptor() -> None:
    receptors = [
        {"place_id": "rec-A", "longitude": -70.5208, "latitude": -31.7300},
        {"place_id": "rec-B", "longitude": -70.7010, "latitude": -31.9710},
    ]
    out = render_topo_set_cellzones(
        receptors=receptors, proj=LOS_PELAMBRES_CENTROID,
    )
    assert "rcv_rec_A" in out
    assert "rcv_rec_B" in out
    assert "cylinderToCell" in out
    assert "setToCellZone" in out
    # rec-A is the centroid -> projected to (0,0).
    assert "(0.00 0.00 2.00)" in out


def test_render_topo_set_cellzones_skips_invalid_coords() -> None:
    bad = [{"place_id": "x", "longitude": "TODO", "latitude": "TODO"}]
    out = render_topo_set_cellzones(receptors=bad, proj=LOS_PELAMBRES_CENTROID)
    assert out == ""


def test_centroid_projection_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        CentroidProjection(centroid_lon=200.0, centroid_lat=0.0)
    with pytest.raises(ValueError):
        CentroidProjection(centroid_lon=0.0, centroid_lat=-100.0)
