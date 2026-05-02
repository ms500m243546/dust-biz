"""ModelPerformanceMetric repository (Phase K, S14)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.storage.models import ModelPerformanceMetric
from app.storage.repositories.base import BaseRepository


class ModelPerformanceMetricRepository(BaseRepository):
    def add(self, row: ModelPerformanceMetric) -> ModelPerformanceMetric:
        self.session.add(row)
        self.session.flush()
        return row

    def latest_for_version(
        self, model_version: str
    ) -> ModelPerformanceMetric | None:
        stmt = (
            select(ModelPerformanceMetric)
            .where(ModelPerformanceMetric.model_version == model_version)
            .order_by(ModelPerformanceMetric.evaluated_at.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_recent(
        self,
        since: datetime,
        limit: int = 200,
        model_version: str | None = None,
        model_kind: str | None = None,
    ) -> list[ModelPerformanceMetric]:
        stmt = (
            select(ModelPerformanceMetric)
            .where(ModelPerformanceMetric.evaluated_at >= since)
            .order_by(ModelPerformanceMetric.evaluated_at.desc())
            .limit(limit)
        )
        if model_version is not None:
            stmt = stmt.where(
                ModelPerformanceMetric.model_version == model_version
            )
        if model_kind is not None:
            stmt = stmt.where(ModelPerformanceMetric.model_kind == model_kind)
        return list(self.session.execute(stmt).scalars())
