"""PopulatedPlaceRepository tests (Phase L.1)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.storage.models import Mine, PopulatedPlace
from app.storage.repositories.receptor import PopulatedPlaceRepository


def _seed_mine(session: Session) -> None:
    session.add(Mine(mine_id="los-pelambres", name="Los Pelambres"))
    session.commit()


def _row(
    place_id: str = "place-cuncumen",
    distance: float | None = 22000.0,
) -> PopulatedPlace:
    return PopulatedPlace(
        place_id=place_id,
        mine_id="los-pelambres",
        name="Cuncumén",
        kind="town",
        longitude=-70.701,
        latitude=-31.971,
        population=600,
        distance_to_mine_m=distance,
        bearing_from_mine_deg=250.0,
        source="ine",
    )


def test_add_and_get_for_mine_orders_by_distance(session: Session) -> None:
    _seed_mine(session)
    repo = PopulatedPlaceRepository(session)
    repo.add(_row("place-far", distance=40000.0))
    repo.add(_row("place-near", distance=8000.0))
    session.commit()

    rows = repo.get_for_mine("los-pelambres")
    assert [r.place_id for r in rows] == ["place-near", "place-far"]


def test_upsert_overwrites_existing(session: Session) -> None:
    _seed_mine(session)
    repo = PopulatedPlaceRepository(session)
    repo.add(_row("place-cuncumen", distance=22000.0))
    session.commit()
    repo.upsert(_row("place-cuncumen", distance=18500.0))
    session.commit()
    fetched = repo.get("place-cuncumen")
    assert fetched is not None
    assert fetched.distance_to_mine_m == 18500.0
