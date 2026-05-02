"""RecommendationApproval ORM (Phase I, S13).

Per docs/data-contracts.md `recommendation_approvals` (lines 207-217).
Append-only: every decision (approve / reject / override / expire) is
recorded as its own row. Recommendations remain immutable on issue
(separation rule); the latest approval row defines the active state of
a recommendation.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.models.base import Base


class RecommendationApproval(Base):
    __tablename__ = "recommendation_approvals"

    approval_id: Mapped[str] = mapped_column(String, primary_key=True)
    recommendation_id: Mapped[str] = mapped_column(
        ForeignKey("recommendations.recommendation_id"),
        nullable=False,
        index=True,
    )
    approved_by: Mapped[str] = mapped_column(String, nullable=False, index=True)
    approver_role: Mapped[str] = mapped_column(String, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    approval_status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    chosen_action_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    override_action: Mapped[str | None] = mapped_column(String, nullable=True)
    human_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    automation_level_at_decision: Mapped[str] = mapped_column(String, nullable=False)
