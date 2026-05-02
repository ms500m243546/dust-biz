"""HaulRoadSegmentSilt repository (Phase L.7)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.storage.models import HaulRoadSegmentSilt
from app.storage.repositories.base import BaseRepository


class HaulRoadSegmentSiltRepository(BaseRepository):
    def add(self, row: HaulRoadSegmentSilt) -> HaulRoadSegmentSilt:
        self.session.add(row)
        self.session.flush()
        return row

    def latest_for_segment(
        self, segment_id: str
    ) -> HaulRoadSegmentSilt | None:
        stmt = (
            select(HaulRoadSegmentSilt)
            .where(HaulRoadSegmentSilt.segment_id == segment_id)
            .order_by(HaulRoadSegmentSilt.sampled_at.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def for_segment(
        self, segment_id: str, *, since: datetime | None = None
    ) -> list[HaulRoadSegmentSilt]:
        stmt = (
            select(HaulRoadSegmentSilt)
            .where(HaulRoadSegmentSilt.segment_id == segment_id)
            .order_by(HaulRoadSegmentSilt.sampled_at.desc())
        )
        if since is not None:
            stmt = stmt.where(HaulRoadSegmentSilt.sampled_at >= since)
        return list(self.session.execute(stmt).scalars())
