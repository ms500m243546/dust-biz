"""OSM mine-geometry connector tests (Phase L.4)."""

from __future__ import annotations

from app.ingestion.public.osm_mine import (
    parse_overpass_response,
)

# A trimmed Overpass JSON example: 4 nodes forming a closed pit polygon
# + 2 nodes for a haul-road LineString.
_PAYLOAD = {
    "elements": [
        {"type": "node", "id": 1, "lon": -70.520, "lat": -31.730},
        {"type": "node", "id": 2, "lon": -70.515, "lat": -31.730},
        {"type": "node", "id": 3, "lon": -70.515, "lat": -31.735},
        {"type": "node", "id": 4, "lon": -70.520, "lat": -31.735},
        {"type": "node", "id": 10, "lon": -70.522, "lat": -31.732},
        {"type": "node", "id": 11, "lon": -70.524, "lat": -31.733},
        {
            "type": "way",
            "id": 100,
            "nodes": [1, 2, 3, 4, 1],
            "tags": {"landuse": "quarry", "name": "Los Pelambres pit"},
        },
        {
            "type": "way",
            "id": 200,
            "nodes": [10, 11],
            "tags": {"highway": "service", "service": "mine", "surface": "dirt"},
        },
        # A non-mine way that should be ignored.
        {
            "type": "way",
            "id": 300,
            "nodes": [1, 2],
            "tags": {"highway": "residential"},
        },
    ]
}


def test_parse_extracts_one_pit_polygon() -> None:
    result = parse_overpass_response(_PAYLOAD, mine_id="los-pelambres")
    assert len(result.zones) == 1
    z = result.zones[0]
    assert z["mine_id"] == "los-pelambres"
    assert z["zone_type"] == "pit"
    assert z["geometry"]["type"] == "Polygon"
    ring = z["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1]  # closed


def test_parse_closes_unclosed_polygon() -> None:
    payload = {
        "elements": [
            {"type": "node", "id": 1, "lon": 0.0, "lat": 0.0},
            {"type": "node", "id": 2, "lon": 1.0, "lat": 0.0},
            {"type": "node", "id": 3, "lon": 1.0, "lat": 1.0},
            {"type": "node", "id": 4, "lon": 0.0, "lat": 1.0},
            {
                "type": "way",
                "id": 100,
                "nodes": [1, 2, 3, 4],  # not closed
                "tags": {"landuse": "quarry"},
            },
        ]
    }
    result = parse_overpass_response(payload, mine_id="m")
    ring = result.zones[0]["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1]


def test_parse_extracts_haul_road_linestring() -> None:
    result = parse_overpass_response(_PAYLOAD, mine_id="los-pelambres")
    assert len(result.haul_roads) == 1
    seg = result.haul_roads[0]
    assert seg["geometry"]["type"] == "LineString"
    assert seg["surface_type"] == "dirt"
    assert seg["length_m"] > 100  # >100m between the two test nodes


def test_parse_ignores_non_mine_ways() -> None:
    result = parse_overpass_response(_PAYLOAD, mine_id="los-pelambres")
    assert len(result.zones) + len(result.haul_roads) == 2  # not 3


def test_parse_handles_empty_response() -> None:
    result = parse_overpass_response({}, mine_id="m")
    assert result.zones == []
    assert result.haul_roads == []
