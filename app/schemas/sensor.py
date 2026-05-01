"""Sensor schemas.

Static entity (Sensor) + raw event (RawSensorReading) + S2 health
status. Per docs/data-contracts.md and docs/subsystem-contracts.md.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SensorType = Literal[
    "pm10",
    "pm25",
    "pm1",
    "wind",
    "humidity",
    "temperature",
    "pressure",
    "rainfall",
    "solar",
    "visibility",
    "multi",
]
SensorStatus = Literal["healthy", "degraded", "offline", "unknown"]


class SensorSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sensor_id: str
    mine_id: str
    sensor_type: SensorType
    zone_id: str | None = None
    is_compliance_station: bool = False


class RawSensorReadingSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sensor_id: str
    timestamp: datetime
    raw_value: dict[str, Any]
    received_at: datetime
    source_quality_hint: float | None = Field(default=None, ge=0.0, le=1.0)


class SensorHealthStatusSchema(BaseModel):
    """S2 output. Downstream consumers must apply
    `downstream_confidence_multiplier` to their confidence.
    """

    sensor_id: str
    status: SensorStatus
    quality_score: float = Field(ge=0.0, le=1.0)
    issues: tuple[str, ...] = Field(default_factory=tuple)
    downstream_confidence_multiplier: float = Field(ge=0.0, le=1.0)
