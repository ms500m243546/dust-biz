"""Recommendation repository.

Append-only writes per G8. IDs follow `REC-YYYYMMDD-NNNNN` per
docs/data-contracts.md line 191; the orchestrator generates them.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, select

from app.storage.models import Recommendation
from app.storage.repositories.base import BaseRepository


class RecommendationRepository(BaseRepository):
    def add(self, rec: Recommendation) -> Recommendation:
        self.session.add(rec)
        self.session.flush()
        return rec

    def get(self, recommendation_id: str) -> Recommendation | None:
        return self.session.get(Recommendation, recommendation_id)

    def latest_for_zone(self, target_zone_id: str) -> Recommendation | None:
        stmt = (
            select(Recommendation)
            .where(Recommendation.target_zone_id == target_zone_id)
            .order_by(Recommendation.issued_at.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_recent(
        self,
        since: datetime,
        limit: int = 200,
        target_zone_id: str | None = None,
    ) -> list[Recommendation]:
        stmt = (
            select(Recommendation)
            .where(Recommendation.issued_at >= since)
            .order_by(Recommendation.issued_at.desc())
            .limit(limit)
        )
        if target_zone_id is not None:
            stmt = stmt.where(Recommendation.target_zone_id == target_zone_id)
        return list(self.session.execute(stmt).scalars())

    def next_recommendation_id(self, on_date: date) -> str:
        prefix = f"REC-{on_date.strftime('%Y%m%d')}-"
        stmt = select(func.count()).where(Recommendation.recommendation_id.like(prefix + "%"))
        n = self.session.execute(stmt).scalar_one() or 0
        return f"{prefix}{n + 1:05d}"
