"""Recommendation ORM (Phase H).

Per docs/data-contracts.md `recommendations`. Append-only audit
table: every issued recommendation lands here regardless of whether
it was approved, rejected, overridden, or expired (G8). Approvals
land in a separate table in Phase I.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.models.base import Base


def _default_labeled_at_from_issued(context: Any) -> datetime:
    issued_at: datetime = context.get_current_parameters()["issued_at"]
    return issued_at


class Recommendation(Base):
    __tablename__ = "recommendations"

    recommendation_id: Mapped[str] = mapped_column(String, primary_key=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    target_zone_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    risk_event: Mapped[str] = mapped_column(String, nullable=False)
    current_breach_probability: Mapped[float] = mapped_column(Float, nullable=False)
    target_probability: Mapped[float] = mapped_column(Float, nullable=False)
    recommended_actions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    requires_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False)
    compliance_priority_triggered: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    model_version: Mapped[str] = mapped_column(String, nullable=False, index=True)
    feature_pipeline_version: Mapped[str] = mapped_column(String, nullable=False)
    input_data_quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    data_quality_warnings: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    linked_prediction_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    linked_attribution_id: Mapped[str | None] = mapped_column(String, nullable=True)
    automation_level: Mapped[str] = mapped_column(String, nullable=False)
    top_production_impact: Mapped[str | None] = mapped_column(String, nullable=True)
    # M.2: anti-hindsight rule 3. Default `labeled_at = issued_at`
    # (context-aware) for system-generated recommendations; manual
    # human edits override.
    labeled_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_default_labeled_at_from_issued,
        index=True,
    )
    # M.3: causal-protocol — separate the *causal* claim's confidence
    # from the *predictive* one. Default = `confidence` (no causal
    # downgrade); domain logic that builds Recommendations from a
    # naive_correlation simulation downgrades this explicitly.
    causal_confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.5
    )
