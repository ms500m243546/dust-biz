"""Static spatial + equipment entities.

Per docs/data-contracts.md: mines, zones, sensors, equipment,
haul_road_segments.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.storage.models.base import Base


class Mine(Base):
    __tablename__ = "mines"

    mine_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    default_automation_level: Mapped[str] = mapped_column(String, default="L1", nullable=False)
    default_risk_thresholds: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    zones: Mapped[list[Zone]] = relationship(back_populates="mine", cascade="all, delete-orphan")
    sensors: Mapped[list[Sensor]] = relationship(back_populates="mine", cascade="all, delete-orphan")
    equipment: Mapped[list[Equipment]] = relationship(
        back_populates="mine", cascade="all, delete-orphan"
    )
    haul_road_segments: Mapped[list[HaulRoadSegment]] = relationship(
        back_populates="mine", cascade="all, delete-orphan"
    )


class Zone(Base):
    __tablename__ = "zones"

    zone_id: Mapped[str] = mapped_column(String, primary_key=True)
    mine_id: Mapped[str] = mapped_column(ForeignKey("mines.mine_id"), nullable=False)
    zone_type: Mapped[str] = mapped_column(String, nullable=False)
    operational_importance: Mapped[str] = mapped_column(String, nullable=False)
    dust_generation_baseline: Mapped[str] = mapped_column(String, nullable=False)
    allowed_interventions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    requires_approval_for: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    mine: Mapped[Mine] = relationship(back_populates="zones")


class Sensor(Base):
    __tablename__ = "sensors"

    sensor_id: Mapped[str] = mapped_column(String, primary_key=True)
    mine_id: Mapped[str] = mapped_column(ForeignKey("mines.mine_id"), nullable=False)
    zone_id: Mapped[str | None] = mapped_column(ForeignKey("zones.zone_id"), nullable=True)
    sensor_type: Mapped[str] = mapped_column(String, nullable=False)
    is_compliance_station: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    installed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decommissioned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    mine: Mapped[Mine] = relationship(back_populates="sensors")


class Equipment(Base):
    __tablename__ = "equipment"

    equipment_id: Mapped[str] = mapped_column(String, primary_key=True)
    mine_id: Mapped[str] = mapped_column(ForeignKey("mines.mine_id"), nullable=False)
    equipment_type: Mapped[str] = mapped_column(String, nullable=False)
    nominal_capacity_t: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    mine: Mapped[Mine] = relationship(back_populates="equipment")


class HaulRoadSegment(Base):
    __tablename__ = "haul_road_segments"

    segment_id: Mapped[str] = mapped_column(String, primary_key=True)
    mine_id: Mapped[str] = mapped_column(ForeignKey("mines.mine_id"), nullable=False)
    from_node: Mapped[str] = mapped_column(String, nullable=False)
    to_node: Mapped[str] = mapped_column(String, nullable=False)
    length_m: Mapped[float] = mapped_column(Float, nullable=False)
    surface_type: Mapped[str] = mapped_column(String, nullable=False)
    last_watered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_graded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    mine: Mapped[Mine] = relationship(back_populates="haul_road_segments")
