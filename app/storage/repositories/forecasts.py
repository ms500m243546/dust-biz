"""DustPrediction repository.

Append-only writes; reads return latest-per-target or windowed
history. Prediction IDs follow `data-contracts.md` line 132 format
`PRED-YYYYMMDD-NNNN`; the orchestrator generates them per
issued_at-day and ascending sequence.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, select

from app.storage.models import DustPrediction
from app.storage.repositories.base import BaseRepository


class DustPredictionRepository(BaseRepository):
    def add(self, prediction: DustPrediction) -> DustPrediction:
        self.session.add(prediction)
        self.session.flush()
        return prediction

    def latest_for_target(
        self, target_kind: str, target_id: str, horizon: str | None = None
    ) -> DustPrediction | None:
        stmt = (
            select(DustPrediction)
            .where(DustPrediction.target_kind == target_kind)
            .where(DustPrediction.target_id == target_id)
            .order_by(DustPrediction.issued_at.desc())
            .limit(1)
        )
        if horizon is not None:
            stmt = stmt.where(DustPrediction.forecast_horizon == horizon)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_recent(
        self,
        target_kind: str,
        target_id: str,
        since: datetime,
        limit: int = 200,
    ) -> list[DustPrediction]:
        stmt = (
            select(DustPrediction)
            .where(DustPrediction.target_kind == target_kind)
            .where(DustPrediction.target_id == target_id)
            .where(DustPrediction.issued_at >= since)
            .order_by(DustPrediction.issued_at.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars())

    def next_prediction_id(self, on_date: date) -> str:
        """`PRED-YYYYMMDD-NNNN` per data-contracts.md line 132.

        Sequence resets per UTC day. SQLite-friendly count via a
        pattern match on the date portion of `prediction_id`.
        """
        prefix = f"PRED-{on_date.strftime('%Y%m%d')}-"
        stmt = select(func.count()).where(DustPrediction.prediction_id.like(prefix + "%"))
        n = self.session.execute(stmt).scalar_one() or 0
        return f"{prefix}{n + 1:04d}"
