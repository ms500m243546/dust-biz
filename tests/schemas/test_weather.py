from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.weather import RawWeatherReadingSchema


def test_weather_basic() -> None:
    w = RawWeatherReadingSchema(
        source="onsite_station_1",
        timestamp=datetime.now(UTC),
        wind_speed_ms=14.2,
        wind_direction_deg=72.0,
        humidity_pct=38.0,
    )
    assert w.wind_speed_ms == 14.2


def test_weather_rejects_out_of_range_humidity() -> None:
    with pytest.raises(ValidationError):
        RawWeatherReadingSchema(
            source="onsite_station_1",
            timestamp=datetime.now(UTC),
            humidity_pct=120.0,
        )


def test_weather_rejects_negative_wind_speed() -> None:
    with pytest.raises(ValidationError):
        RawWeatherReadingSchema(
            source="onsite_station_1",
            timestamp=datetime.now(UTC),
            wind_speed_ms=-1.0,
        )


def test_weather_all_optional_fields_default_to_none() -> None:
    w = RawWeatherReadingSchema(
        source="onsite_station_1", timestamp=datetime.now(UTC)
    )
    assert w.wind_speed_ms is None
    assert w.humidity_pct is None
    assert w.zone_id is None
