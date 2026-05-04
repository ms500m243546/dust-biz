"""DispersionMatrix ORM (Phase BA.5).

Append-only: each calibration run lands a new row. The current matrix
for a mine is whatever has the latest `created_at` and matches the
`current` `dispersion` model_version in the registry.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.storage.models.base import Base


class DispersionMatrix(Base):
    __tablename__ = "dispersion_matrices"

    matrix_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    mine_id: Mapped[str] = mapped_column(
        ForeignKey("mines.mine_id"), nullable=False, index=True
    )
    model_version: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )
    # JSON blob: {"regime_grid": {...}, "coefficients": {...},
    # "source_run_dir": str | None, "notes": str | None}.
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
