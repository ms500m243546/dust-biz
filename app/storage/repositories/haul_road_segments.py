"""HaulRoadSegment repository.

Segments are the unit S4 uses to compute truck density and surface
dryness. `last_watered_at` and `last_graded_at` are mutable timestamps
that Phase G interventions (watering, grading) will update; the helper
methods exist now so S4 / S9 callers don't reach into ORM internals.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.storage.models import HaulRoadSegment
from app.storage.repositories.base import BaseRepository


class HaulRoadSegmentRepository(BaseRepository):
    def get(self, segment_id: str) -> HaulRoadSegment | None:
        return self.session.get(HaulRoadSegment, segment_id)

    def get_for_mine(self, mine_id: str) -> list[HaulRoadSegment]:
        stmt = select(HaulRoadSegment).where(HaulRoadSegment.mine_id == mine_id)
        return list(self.session.execute(stmt).scalars())

    def upsert(
        self,
        segment_id: str,
        mine_id: str,
        from_node: str,
        to_node: str,
        length_m: float,
        surface_type: str,
        last_watered_at: datetime | None = None,
        last_graded_at: datetime | None = None,
    ) -> HaulRoadSegment:
        existing = self.session.get(HaulRoadSegment, segment_id)
        if existing is None:
            seg = HaulRoadSegment(
                segment_id=segment_id,
                mine_id=mine_id,
                from_node=from_node,
                to_node=to_node,
                length_m=length_m,
                surface_type=surface_type,
                last_watered_at=last_watered_at,
                last_graded_at=last_graded_at,
            )
            self.session.add(seg)
        else:
            existing.mine_id = mine_id
            existing.from_node = from_node
            existing.to_node = to_node
            existing.length_m = length_m
            existing.surface_type = surface_type
            if last_watered_at is not None:
                existing.last_watered_at = last_watered_at
            if last_graded_at is not None:
                existing.last_graded_at = last_graded_at
            seg = existing
        self.session.flush()
        return seg

    def mark_watered(self, segment_id: str, at: datetime) -> HaulRoadSegment | None:
        seg = self.session.get(HaulRoadSegment, segment_id)
        if seg is None:
            return None
        seg.last_watered_at = at
        self.session.flush()
        return seg

    def mark_graded(self, segment_id: str, at: datetime) -> HaulRoadSegment | None:
        seg = self.session.get(HaulRoadSegment, segment_id)
        if seg is None:
            return None
        seg.last_graded_at = at
        self.session.flush()
        return seg
