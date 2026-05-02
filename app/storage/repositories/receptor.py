"""PopulatedPlace repository (Phase L.1)."""

from __future__ import annotations

from sqlalchemy import select

from app.storage.models import PopulatedPlace
from app.storage.repositories.base import BaseRepository


class PopulatedPlaceRepository(BaseRepository):
    def add(self, row: PopulatedPlace) -> PopulatedPlace:
        self.session.add(row)
        self.session.flush()
        return row

    def get(self, place_id: str) -> PopulatedPlace | None:
        return self.session.get(PopulatedPlace, place_id)

    def get_for_mine(self, mine_id: str) -> list[PopulatedPlace]:
        stmt = (
            select(PopulatedPlace)
            .where(PopulatedPlace.mine_id == mine_id)
            .order_by(PopulatedPlace.distance_to_mine_m.asc().nullslast())
        )
        return list(self.session.execute(stmt).scalars())

    def upsert(self, row: PopulatedPlace) -> PopulatedPlace:
        existing = self.session.get(PopulatedPlace, row.place_id)
        if existing is None:
            return self.add(row)
        for col in (
            "mine_id",
            "name",
            "kind",
            "longitude",
            "latitude",
            "population",
            "distance_to_mine_m",
            "bearing_from_mine_deg",
            "source",
            "source_url",
            "notes",
        ):
            setattr(existing, col, getattr(row, col))
        self.session.flush()
        return existing
