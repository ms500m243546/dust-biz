"""SiteConfiguration ORM.

Per docs/data-contracts.md `site_configurations`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.storage.models.base import Base


class SiteConfiguration(Base):
    __tablename__ = "site_configurations"

    site_id: Mapped[str] = mapped_column(String, primary_key=True)
    mine_id: Mapped[str] = mapped_column(ForeignKey("mines.mine_id"), nullable=False, index=True)
    automation_level: Mapped[str] = mapped_column(String, default="L1", nullable=False)
    pm10_thresholds: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False)
    pm25_thresholds: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False)
    extreme_breach_threshold: Mapped[float] = mapped_column(Float, default=0.85, nullable=False)
    low_confidence_threshold: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    optimization_weights: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False)
    intervention_constraints: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)
