"""INE populated-places connector tests (Phase L.4)."""

from __future__ import annotations

from app.ingestion.public.ine_populated_places import parse_ine_payload

# Los Pelambres pit centroid (approx).
_MINE_LON = -70.5208
_MINE_LAT = -31.7300

_PAYLOAD = {
    "places": [
        {
            "name": "Cuncumén",
            "kind": "town",
            "longitude": -70.701,
            "latitude": -31.971,
            "population": 600,
        },
        {
            "name": "Caimanes",
            "kind": "town",
            "longitude": -71.135,
            "latitude": -32.020,
            "population": 1300,
        },
        {
            "name": "Salamanca",
            "kind": "town",
            "longitude": -70.967,
            "latitude": -31.778,
            "population": 25000,
        },
        # An entry with bad kind should fall back to "other".
        {
            "name": "Random",
            "kind": "alien-base",
            "longitude": -70.0,
            "latitude": -31.5,
        },
    ]
}


def test_parse_computes_distance_and_bearing() -> None:
    rows = parse_ine_payload(
        _PAYLOAD, mine_id="los-pelambres", mine_lon=_MINE_LON, mine_lat=_MINE_LAT
    )
    assert len(rows) == 4
    cuncumen = rows[0]
    assert cuncumen["name"] == "Cuncumén"
    # Distance ~30km; loose tolerance.
    assert 20_000 < cuncumen["distance_to_mine_m"] < 40_000
    assert 0.0 <= cuncumen["bearing_from_mine_deg"] <= 360.0


def test_parse_normalises_unknown_kind_to_other() -> None:
    rows = parse_ine_payload(
        _PAYLOAD, mine_id="los-pelambres", mine_lon=_MINE_LON, mine_lat=_MINE_LAT
    )
    rogue = next(r for r in rows if r["name"] == "Random")
    assert rogue["kind"] == "other"


def test_parse_drops_records_with_bad_coords() -> None:
    payload = {
        "places": [
            {"name": "ok", "longitude": -70.0, "latitude": -31.0},
            {"name": "bad-lon", "longitude": "x", "latitude": -31.0},
            {"longitude": -70.0, "latitude": -31.0},  # missing name
        ]
    }
    rows = parse_ine_payload(payload, mine_id="m", mine_lon=-70.0, mine_lat=-31.0)
    assert len(rows) == 1
    assert rows[0]["name"] == "ok"


def test_parse_assigns_source_ine() -> None:
    rows = parse_ine_payload(
        _PAYLOAD, mine_id="los-pelambres", mine_lon=_MINE_LON, mine_lat=_MINE_LAT
    )
    assert all(r["source"] == "ine" for r in rows)


def test_parse_records_pass_populated_place_schema() -> None:
    """Every output row must validate against PopulatedPlaceSchema."""
    from app.schemas.receptor import PopulatedPlaceSchema

    rows = parse_ine_payload(
        _PAYLOAD, mine_id="los-pelambres", mine_lon=_MINE_LON, mine_lat=_MINE_LAT
    )
    for r in rows:
        PopulatedPlaceSchema(**dict(r))  # raises on validation failure
