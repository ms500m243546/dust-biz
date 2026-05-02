"""Per-station PM threshold override schema (Phase L.6).

Per docs/rca-seed.md. Used by the K.2 compliance report to look up
per-station limits before falling back to the site defaults.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StationThresholdOverrideSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    override_id: int | None = None
    sensor_id: str
    site_id: str | None = None
    pm10_warning_ugm3: float | None = Field(default=None, ge=0.0)
    pm10_breach_ugm3: float | None = Field(default=None, ge=0.0)
    pm25_warning_ugm3: float | None = Field(default=None, ge=0.0)
    pm25_breach_ugm3: float | None = Field(default=None, ge=0.0)
    rca_reference: str | None = None
    source_url: str | None = None
    notes: str | None = None
    updated_at: datetime | None = None


__all__ = ["StationThresholdOverrideSchema"]
