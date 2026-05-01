"""FeatureRecord ORM.

Per docs/data-contracts.md `features` (Phase E). Append-only:
each compute pass writes a new row. Derived from raw readings +
mine state; raw readings are never mutated (data-contracts.md
"Separation rules").
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.models.base import Base


class FeatureRecord(Base):
    __tablename__ = "features"

    feature_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.zone_id"), nullable=False, index=True)
    feature_pipeline_version: Mapped[str] = mapped_column(String, nullable=False, index=True)
    feature_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    missing_inputs: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
