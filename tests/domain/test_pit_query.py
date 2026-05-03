"""Phase M.2: pit_query helper tests."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.domain.pit_query import (
    labels_as_of,
    sensor_readings_as_of,
    weather_readings_as_of,
)
from app.storage.models import (
    DustEvent,
    SensorReading,
    WeatherReading,
)


def test_sensor_readings_as_of_filters_pre_promoted_value(
    session: Session,
) -> None:
    """col-2 (pre-validated) is visible during [hour, hour+7d)."""
    hour = datetime(2026, 1, 1, 12, 0)
    pre = SensorReading(
        sensor_id="lp-em05-cuncumen",
        timestamp=hour,
        raw_value={"v": "pre"},
        valid_from=hour,
        valid_to=datetime(2026, 1, 8, 12, 0),
    )
    val = SensorReading(
        sensor_id="lp-em05-cuncumen",
        timestamp=hour,
        raw_value={"v": "validated"},
        valid_from=datetime(2026, 1, 8, 12, 0),
        valid_to=None,
    )
    session.add_all([pre, val])
    session.commit()

    # As of `hour + 1 day`: only the pre-validated row is legal.
    rows = list(
        session.execute(
            sensor_readings_as_of(datetime(2026, 1, 2, 12, 0))
        ).scalars()
    )
    assert len(rows) == 1
    assert rows[0].raw_value["v"] == "pre"

    # As of `hour + 14 days`: only the validated row is legal.
    rows = list(
        session.execute(
            sensor_readings_as_of(datetime(2026, 1, 15, 12, 0))
        ).scalars()
    )
    assert len(rows) == 1
    assert rows[0].raw_value["v"] == "validated"


def test_weather_readings_as_of_filters_realtime_proxy(
    session: Session,
) -> None:
    open_meteo = WeatherReading(
        source="open_meteo",
        zone_id=None,
        timestamp=datetime(2026, 1, 1, 12, 0),
        weather_target_id="lp-cuncumen-met",
        realtime_proxy=True,
        wind_speed_ms=4.0,
    )
    era5 = WeatherReading(
        source="era5",
        zone_id=None,
        timestamp=datetime(2026, 1, 1, 12, 0),
        weather_target_id="lp-cuncumen-met-era5",
        realtime_proxy=False,
        wind_speed_ms=3.5,
    )
    session.add_all([open_meteo, era5])
    session.commit()

    # Default: realtime_only=True drops ERA5.
    rows = list(
        session.execute(
            weather_readings_as_of(datetime(2026, 1, 2, 0, 0))
        ).scalars()
    )
    assert len(rows) == 1
    assert rows[0].source == "open_meteo"

    # realtime_only=False includes both.
    rows = list(
        session.execute(
            weather_readings_as_of(
                datetime(2026, 1, 2, 0, 0), realtime_only=False
            )
        ).scalars()
    )
    assert len(rows) == 2


def test_labels_as_of_filters_future_labels(session: Session) -> None:
    # Need a Sensor row for the FK on dust_events.affected_station.
    from app.storage.models import Sensor
    session.add(Sensor(sensor_id="lp-em05-cuncumen", mine_id="los-pelambres", sensor_type="pm10"))
    session.commit()

    early = DustEvent(
        event_id="EVT-1",
        detected_at=datetime(2026, 1, 1, 12, 0),
        affected_station="lp-em05-cuncumen",
        peak_pm10=160.0,
        peak_pm25=50.0,
        breach_occurred=True,
        event_source="auto",
        linked_prediction_ids=[],
        labeled_at=datetime(2026, 1, 1, 12, 0),
    )
    late = DustEvent(
        event_id="EVT-2",
        detected_at=datetime(2026, 1, 1, 12, 0),
        affected_station="lp-em05-cuncumen",
        peak_pm10=160.0,
        peak_pm25=50.0,
        breach_occurred=True,
        event_source="auto",
        linked_prediction_ids=[],
        labeled_at=datetime(2026, 6, 1, 12, 0),  # labeled 5 months later
    )
    session.add_all([early, late])
    session.commit()

    # As of Feb 1, only the early-labeled event is visible.
    rows = list(
        session.execute(
            labels_as_of(DustEvent, datetime(2026, 2, 1, 12, 0))
        ).scalars()
    )
    assert len(rows) == 1
    assert rows[0].event_id == "EVT-1"


def test_labels_as_of_rejects_non_pit_models() -> None:
    from app.storage.models import Sensor

    with pytest.raises(ValueError):
        labels_as_of(Sensor, datetime(2026, 1, 1))


# Pull in the engine + session fixtures from tests/conftest.py
__all__: list[str] = []
_ = Engine  # silence unused-import lint
