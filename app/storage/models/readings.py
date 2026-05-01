"""Raw immutable readings: sensor, weather, equipment activity.

Per docs/data-contracts.md and the "Separation rules (enforced)"
section: raw readings are never overwritten or deleted.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.storage.models.base import Base


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    reading_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sensor_id: Mapped[str] = mapped_column(ForeignKey("sensors.sensor_id"), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    raw_value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    source_quality_hint: Mapped[float | None] = mapped_column(Float, nullable=True)


class WeatherReading(Base):
    __tablename__ = "weather_readings"

    reading_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String, nullable=False, index=True)
    zone_id: Mapped[str | None] = mapped_column(ForeignKey("zones.zone_id"), nullable=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    wind_speed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_direction_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    gust_speed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    pressure_hpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    rainfall_mm_15min: Mapped[float | None] = mapped_column(Float, nullable=True)
    solar_wm2: Mapped[float | None] = mapped_column(Float, nullable=True)
    visibility_m: Mapped[float | None] = mapped_column(Float, nullable=True)


class EquipmentActivity(Base):
    __tablename__ = "equipment_activity"

    activity_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equipment_id: Mapped[str] = mapped_column(
        ForeignKey("equipment.equipment_id"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    zone_id: Mapped[str | None] = mapped_column(ForeignKey("zones.zone_id"), nullable=True, index=True)
    activity_type: Mapped[str] = mapped_column(String, nullable=False)
    speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    tonnage: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
