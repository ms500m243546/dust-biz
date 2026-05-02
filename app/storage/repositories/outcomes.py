"""ActionOutcome repository (Phase I)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.storage.models import ActionOutcome
from app.storage.repositories.base import BaseRepository


class ActionOutcomeRepository(BaseRepository):
    def add(self, row: ActionOutcome) -> ActionOutcome:
        self.session.add(row)
        self.session.flush()
        return row

    def get(self, outcome_id: int) -> ActionOutcome | None:
        return self.session.get(ActionOutcome, outcome_id)

    def for_recommendation(self, recommendation_id: str) -> list[ActionOutcome]:
        stmt = (
            select(ActionOutcome)
            .where(ActionOutcome.recommendation_id == recommendation_id)
            .order_by(ActionOutcome.recorded_at.asc())
        )
        return list(self.session.execute(stmt).scalars())

    def get_recent(
        self, since: datetime, limit: int = 200
    ) -> list[ActionOutcome]:
        stmt = (
            select(ActionOutcome)
            .where(ActionOutcome.recorded_at >= since)
            .order_by(ActionOutcome.recorded_at.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars())
