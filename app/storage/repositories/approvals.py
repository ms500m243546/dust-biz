"""RecommendationApproval repository (Phase I)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from app.storage.models import RecommendationApproval
from app.storage.repositories.base import BaseRepository


class RecommendationApprovalRepository(BaseRepository):
    def add(self, row: RecommendationApproval) -> RecommendationApproval:
        self.session.add(row)
        self.session.flush()
        return row

    def latest_for_recommendation(
        self, recommendation_id: str
    ) -> RecommendationApproval | None:
        stmt = (
            select(RecommendationApproval)
            .where(RecommendationApproval.recommendation_id == recommendation_id)
            .order_by(RecommendationApproval.decided_at.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get(self, approval_id: str) -> RecommendationApproval | None:
        return self.session.get(RecommendationApproval, approval_id)

    def get_recent(
        self,
        since: datetime,
        limit: int = 200,
    ) -> list[RecommendationApproval]:
        stmt = (
            select(RecommendationApproval)
            .where(RecommendationApproval.decided_at >= since)
            .order_by(RecommendationApproval.decided_at.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars())

    def next_approval_id(self, on_date: datetime) -> str:
        prefix = f"APR-{on_date.strftime('%Y%m%d')}-"
        stmt = select(func.count()).where(
            RecommendationApproval.approval_id.like(prefix + "%")
        )
        n = self.session.execute(stmt).scalar_one() or 0
        return f"{prefix}{n + 1:05d}"
