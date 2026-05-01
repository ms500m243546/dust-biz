"""Weather reading schema.

Per docs/data-contracts.md `weather_readings`.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RawWeatherReadingSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    timestamp: datetime
    zone_id: str | None = None
    wind_speed_ms: float | None = Field(default=None, ge=0.0)
    wind_direction_deg: float | None = Field(default=None, ge=0.0, le=360.0)
    gust_speed_ms: float | None = Field(default=None, ge=0.0)
    humidity_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    temperature_c: float | None = None
    pressure_hpa: float | None = Field(default=None, ge=0.0)
    rainfall_mm_15min: float | None = Field(default=None, ge=0.0)
    solar_wm2: float | None = Field(default=None, ge=0.0)
    visibility_m: float | None = Field(default=None, ge=0.0)
