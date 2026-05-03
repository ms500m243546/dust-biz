"""ActionOutcome ORM (Phase I, S14 feeder).

Per docs/data-contracts.md `action_outcomes` (lines 219-229). Phase I
delivers the storage shape and the manual-entry endpoint; the join
logic that tracks predicted vs. actual lands in Phase K.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.models.base import Base


def _default_labeled_at_from_recorded(context: Any) -> datetime:
    recorded_at: datetime = context.get_current_parameters()["recorded_at"]
    return recorded_at


class ActionOutcome(Base):
    __tablename__ = "action_outcomes"

    outcome_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    recommendation_id: Mapped[str | None] = mapped_column(
        ForeignKey("recommendations.recommendation_id"), nullable=True, index=True
    )
    prediction_id: Mapped[str | None] = mapped_column(
        ForeignKey("dust_predictions.prediction_id"), nullable=True, index=True
    )
    actual_pm10_peak: Mapped[float] = mapped_column(Float, nullable=False)
    actual_pm25_peak: Mapped[float | None] = mapped_column(Float, nullable=True)
    breach_occurred: Mapped[bool] = mapped_column(Boolean, nullable=False)
    production_loss_tonnes_actual: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    intervention_effectiveness: Mapped[str] = mapped_column(String, nullable=False)
    model_error: Mapped[str | None] = mapped_column(String, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    recorded_by: Mapped[str] = mapped_column(String, nullable=False)
    # M.2: anti-hindsight rule 3. Default `labeled_at = recorded_at`
    # (context-aware).
    labeled_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_default_labeled_at_from_recorded,
        index=True,
    )
