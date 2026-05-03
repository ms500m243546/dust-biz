"""Raw immutable readings: sensor, weather, equipment activity.

Per docs/data-contracts.md and the "Separation rules (enforced)"
section: raw readings are never overwritten or deleted.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.storage.models.base import Base


class SensorReading(Base):
    __tablename__ = "sensor_readings"
    # L.M.1: idempotent ingest — the same (sensor, hour) only persists once.
    # M.2: Point-in-time discipline — `valid_from` / `valid_to` carry the
    # availability interval for *this version* of the reading. SINCA's
    # col-2 (pre-validated, immediate) and col-3 (validated, ~7d lag)
    # both persist as separate rows for the same (sensor, hour),
    # discriminated by `valid_from`. Anti-hindsight rule 1
    # (docs/anti-hindsight-protocol.md) is enforced via PIT-aware
    # SQL filters in app/domain/pit_query.py.
    __table_args__ = (
        UniqueConstraint(
            "sensor_id",
            "timestamp",
            "valid_from",
            name="uq_sensor_readings_sensor_ts_validfrom",
        ),
    )

    reading_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sensor_id: Mapped[str] = mapped_column(ForeignKey("sensors.sensor_id"), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    raw_value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    source_quality_hint: Mapped[float | None] = mapped_column(Float, nullable=True)
    # M.2 PIT — see __table_args__ comment. Server default = now() so
    # tests + legacy callers that don't supply valid_from get a
    # sensible value; orchestrator path always sets it explicitly via
    # expand_to_pit_records.
    valid_from: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )
    valid_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    pit_version: Mapped[str] = mapped_column(String, nullable=False, default="v1")


class WeatherReading(Base):
    __tablename__ = "weather_readings"
    # M.2: idempotent ingest + anti-hindsight rule 2.
    # `weather_target_id` carries the target identity from
    # data_seed/<mine>.yaml `weather_targets:` (e.g., `lp-mine-centroid`,
    # `lp-cuncumen-met`). The unique constraint
    # (source, weather_target_id, timestamp) prevents duplicate ingest;
    # `zone_id` (FK→zones) stays nullable for the future case of true
    # per-zone weather but routine ingest writes `weather_target_id`.
    # `realtime_proxy=True` for sources that approximate the realtime
    # regime (Open-Meteo, DGA, NASA POWER); `False` for post-hoc
    # reanalysis (ERA5, MERRA-2). Models flagged
    # `intended_for_realtime=True` must filter `WHERE realtime_proxy=True`.
    __table_args__ = (
        UniqueConstraint(
            "source",
            "weather_target_id",
            "timestamp",
            name="uq_weather_readings_source_target_ts",
        ),
    )

    reading_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String, nullable=False, index=True)
    zone_id: Mapped[str | None] = mapped_column(ForeignKey("zones.zone_id"), nullable=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    # M.2 PIT additions. `weather_target_id` defaults to 'test-default'
    # so legacy / test callers don't break; orchestrator sets it from
    # the YAML target spec. `realtime_proxy` defaults to True (matches
    # the realistic ingest source — Open-Meteo); ERA5 ingest sets False
    # explicitly.
    weather_target_id: Mapped[str] = mapped_column(
        String, nullable=False, default="test-default", index=True
    )
    realtime_proxy: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    wind_speed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_direction_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    gust_speed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    pressure_hpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    rainfall_mm_15min: Mapped[float | None] = mapped_column(Float, nullable=True)
    solar_wm2: Mapped[float | None] = mapped_column(Float, nullable=True)
    visibility_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Phase L.7: dispersion-modelling inputs.
    cloud_cover_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    mixing_height_m: Mapped[float | None] = mapped_column(Float, nullable=True)


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
