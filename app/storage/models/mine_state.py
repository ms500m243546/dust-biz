"""MineStateSnapshot ORM.

Per docs/data-contracts.md `mine_state_snapshots` (Phase D). Snapshots
are append-only: each compute writes a new row rather than mutating an
existing one, mirroring the separation rules at the bottom of
data-contracts.md ("Derived data lives in separate tables").
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.models.base import Base


class MineStateSnapshot(Base):
    __tablename__ = "mine_state_snapshots"

    snapshot_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.zone_id"), nullable=False, index=True)
    activity: Mapped[str] = mapped_column(String, nullable=False)
    equipment_active: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    production_rate_tph: Mapped[float | None] = mapped_column(Float, nullable=True)
    dust_generation_potential: Mapped[str] = mapped_column(String, nullable=False)
    wind_exposure: Mapped[str] = mapped_column(String, nullable=False)
    downwind_assets: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    operational_importance: Mapped[str] = mapped_column(String, nullable=False)
    staleness_flags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
