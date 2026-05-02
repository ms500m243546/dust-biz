"""GeoJSON geometry validation on Zone + HaulRoadSegment (Phase K.3)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.mine import HaulRoadSegmentSchema, ZoneSchema


def _zone(geom: dict[str, Any] | None = None) -> ZoneSchema:
    return ZoneSchema(
        zone_id="Z-1",
        mine_id="m1",
        zone_type="haul_road",
        operational_importance="high",
        dust_generation_baseline="medium",
        geometry=geom,
    )


def test_zone_accepts_closed_polygon() -> None:
    poly = {
        "type": "Polygon",
        "coordinates": [
            [
                [0.0, 0.0],
                [0.0, 1.0],
                [1.0, 1.0],
                [1.0, 0.0],
                [0.0, 0.0],
            ]
        ],
    }
    z = _zone(poly)
    assert z.geometry is not None
    assert z.geometry["type"] == "Polygon"


def test_zone_accepts_none_geometry() -> None:
    assert _zone(None).geometry is None


def test_zone_rejects_unclosed_ring() -> None:
    poly = {
        "type": "Polygon",
        "coordinates": [
            [
                [0.0, 0.0],
                [0.0, 1.0],
                [1.0, 1.0],
                [1.0, 0.0],
            ]
        ],
    }
    with pytest.raises(ValidationError):
        _zone(poly)


def test_zone_rejects_wrong_type() -> None:
    with pytest.raises(ValidationError):
        _zone({"type": "Point", "coordinates": [0.0, 0.0]})


def test_haul_road_accepts_linestring() -> None:
    seg = HaulRoadSegmentSchema(
        segment_id="HRS-1",
        mine_id="m1",
        from_node="A",
        to_node="B",
        length_m=120.0,
        surface_type="dirt",
        geometry={
            "type": "LineString",
            "coordinates": [[0.0, 0.0], [1.0, 1.0]],
        },
    )
    assert seg.geometry is not None


def test_haul_road_rejects_one_position_linestring() -> None:
    with pytest.raises(ValidationError):
        HaulRoadSegmentSchema(
            segment_id="HRS-1",
            mine_id="m1",
            from_node="A",
            to_node="B",
            length_m=120.0,
            surface_type="dirt",
            geometry={"type": "LineString", "coordinates": [[0.0, 0.0]]},
        )
