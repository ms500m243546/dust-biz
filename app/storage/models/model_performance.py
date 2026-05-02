"""ModelPerformanceMetric ORM (Phase K, S14).

Per docs/data-contracts.md `model_performance_metrics` (lines 241-248).
Append-only: each row is one evaluation of one model_version over one
window. The metric_payload is a JSON blob carrying MAE, breach
precision/recall, false-positive/negative rates, calibration error,
avoided-shutdowns estimate, and any other window-level aggregates
computed by `app.domain.model_performance`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.models.base import Base


class ModelPerformanceMetric(Base):
    __tablename__ = "model_performance_metrics"

    metric_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    model_version: Mapped[str] = mapped_column(String, nullable=False, index=True)
    model_kind: Mapped[str] = mapped_column(String, nullable=False, index=True)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True
    )
    window_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    window_to: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metric_payload: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
