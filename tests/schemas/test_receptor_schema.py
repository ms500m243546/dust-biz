"""PopulatedPlaceSchema tests (Phase L.1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.receptor import PopulatedPlaceSchema


def _make(**overrides: object) -> PopulatedPlaceSchema:
    base: dict[str, object] = {
        "place_id": "place-cuncumen",
        "mine_id": "los-pelambres",
        "name": "Cuncumén",
        "kind": "town",
        "longitude": -70.701,
        "latitude": -31.971,
        "population": 600,
        "distance_to_mine_m": 22000.0,
        "bearing_from_mine_deg": 250.0,
    }
    base.update(overrides)
    return PopulatedPlaceSchema(**base)  # type: ignore[arg-type]


def test_minimum_fields_round_trip() -> None:
    p = _make()
    assert p.kind == "town"
    assert p.distance_to_mine_m == 22000.0


def test_rejects_bad_kind() -> None:
    with pytest.raises(ValidationError):
        _make(kind="not-a-receptor-kind")


def test_rejects_out_of_range_coordinates() -> None:
    with pytest.raises(ValidationError):
        _make(longitude=-200.0)
    with pytest.raises(ValidationError):
        _make(latitude=99.9)


def test_rejects_negative_population() -> None:
    with pytest.raises(ValidationError):
        _make(population=-1)


def test_optional_fields_default_to_none() -> None:
    p = PopulatedPlaceSchema(
        place_id="x",
        mine_id="m",
        name="X",
        kind="town",
        longitude=-70.0,
        latitude=-31.0,
    )
    assert p.population is None
    assert p.distance_to_mine_m is None
    assert p.source == "ine"
