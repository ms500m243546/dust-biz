"""Per-station PM threshold overrides (Phase L.6).

Per docs/rca-seed.md: RCAs sometimes impose stricter PM thresholds at
named community-receptor stations than the site default. The K.2
compliance report logic uses this table to look up per-station limits
when scoring exceedances; missing entries fall back to the
`SiteConfiguration` defaults.

Append-only audit pattern is NOT applied here — this is a config
table, not an event log. Updates overwrite via upsert; the source
URL on every row preserves provenance.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.storage.models.base import Base


class StationThresholdOverride(Base):
    __tablename__ = "station_threshold_overrides"

    override_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    sensor_id: Mapped[str] = mapped_column(
        ForeignKey("sensors.sensor_id"), nullable=False, index=True
    )
    site_id: Mapped[str | None] = mapped_column(
        ForeignKey("site_configurations.site_id"), nullable=True, index=True
    )
    pm10_warning_ugm3: Mapped[float | None] = mapped_column(Float, nullable=True)
    pm10_breach_ugm3: Mapped[float | None] = mapped_column(Float, nullable=True)
    pm25_warning_ugm3: Mapped[float | None] = mapped_column(Float, nullable=True)
    pm25_breach_ugm3: Mapped[float | None] = mapped_column(Float, nullable=True)
    rca_reference: Mapped[str | None] = mapped_column(String, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
