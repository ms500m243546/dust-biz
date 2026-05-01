from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.sensor import (
    RawSensorReadingSchema,
    SensorHealthStatusSchema,
    SensorSchema,
)


def test_sensor_schema_basic() -> None:
    s = SensorSchema(sensor_id="PM10_STATION_2", mine_id="m1", sensor_type="pm10")
    assert s.sensor_id == "PM10_STATION_2"
    assert s.is_compliance_station is False


def test_sensor_schema_invalid_type() -> None:
    with pytest.raises(ValidationError):
        SensorSchema(sensor_id="x", mine_id="m1", sensor_type="laser")  # type: ignore[arg-type]


def test_raw_sensor_reading_round_trip() -> None:
    now = datetime.now(UTC)
    r = RawSensorReadingSchema(
        sensor_id="PM10_STATION_2",
        timestamp=now,
        raw_value={"pm10_ugm3": 118},
        received_at=now,
        source_quality_hint=0.92,
    )
    dumped = r.model_dump_json()
    restored = RawSensorReadingSchema.model_validate_json(dumped)
    assert restored.raw_value == {"pm10_ugm3": 118}


def test_sensor_health_status_multiplier_bounds() -> None:
    h = SensorHealthStatusSchema(
        sensor_id="PM10_STATION_2",
        status="degraded",
        quality_score=0.71,
        issues=("missing_readings_last_10min",),
        downstream_confidence_multiplier=0.75,
    )
    assert h.status == "degraded"
    with pytest.raises(ValidationError):
        SensorHealthStatusSchema(
            sensor_id="x",
            status="healthy",
            quality_score=1.5,
            downstream_confidence_multiplier=0.5,
        )
