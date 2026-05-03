"""Phase Q.1 — multi-station batch training tests.

Synthetic in-memory dataset with 3 stations so we exercise both the
happy path and the partial-success path (one station with thin data
gets a placeholder TrainingResult instead of raising).
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.storage.models import Base, ModelPerformanceMetric, SensorReading, WeatherReading
from app.training.dust_forecast_training import (
    GBM_VERSION,
    build_p1_protocol,
    train_many,
)

STATION_DENSE_A = "test-station-a"
STATION_DENSE_B = "test-station-b"
STATION_THIN = "test-station-c"
TARGET_A = "test-station-a-met"
TARGET_B = "test-station-b-met"
TARGET_C = "test-station-c-met"

# Override the per-station weather mapping for the test stations.
# We mutate the module dict in a fixture and restore on teardown so
# we don't leak into the rest of the test suite.


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    with SessionLocal() as s:
        yield s


@pytest.fixture(autouse=True)
def _patch_weather_targets() -> Iterator[None]:
    from app.training import dust_forecast_training as mod

    original = dict(mod.STATION_WEATHER_TARGETS)
    mod.STATION_WEATHER_TARGETS.update(
        {
            STATION_DENSE_A: TARGET_A,
            STATION_DENSE_B: TARGET_B,
            STATION_THIN: TARGET_C,
        }
    )
    yield
    mod.STATION_WEATHER_TARGETS.clear()
    mod.STATION_WEATHER_TARGETS.update(original)


def _seed(
    session: Session, *, station: str, target: str, days: int, seed: int
) -> None:
    """Inject `days` worth of hourly synthetic PM10 + weather rows."""
    import random

    rng = random.Random(seed)
    start = datetime(2025, 5, 3)
    for hour in range(days * 24):
        ts = start + timedelta(hours=hour)
        diurnal = 30 + 25 * math.sin(2 * math.pi * (hour % 24) / 24)
        humidity = 50 + 30 * math.sin(2 * math.pi * (hour % 168) / 168) + rng.uniform(-5, 5)
        wind_speed = 4 + 5 * math.cos(2 * math.pi * (hour % 24) / 24) + rng.uniform(-1, 1)
        pm10 = max(5.0, diurnal + 80.0 * (1 - humidity / 100) * (wind_speed / 8) + rng.uniform(-15, 15))
        session.add(
            SensorReading(
                sensor_id=station,
                timestamp=ts,
                raw_value={"parameter": "pm10", "validated": False, "pm10_ugm3": round(pm10, 2)},
                source_quality_hint=0.9,
                valid_from=ts,
                pit_version="v1",
            )
        )
        session.add(
            WeatherReading(
                source="open_meteo",
                timestamp=ts,
                weather_target_id=target,
                realtime_proxy=True,
                wind_speed_ms=round(wind_speed, 2),
                wind_direction_deg=round((hour * 13) % 360, 1),
                humidity_pct=round(humidity, 2),
                temperature_c=15.0,
                pressure_hpa=1013.0,
                rainfall_mm_15min=0.0,
            )
        )
    session.flush()


def _protocol(start: datetime = datetime(2025, 5, 3)) -> object:
    return build_p1_protocol(
        train_window_from=start,
        train_window_to=start + timedelta(days=140),
        validation_window_from=start + timedelta(days=147),
        validation_window_to=start + timedelta(days=170),
        test_window_from=start + timedelta(days=177),
        test_window_to=start + timedelta(days=200),
    )


def test_train_many_fits_each_station_under_one_model_version(
    session: Session, tmp_path: Path
) -> None:
    _seed(session, station=STATION_DENSE_A, target=TARGET_A, days=200, seed=1)
    _seed(session, station=STATION_DENSE_B, target=TARGET_B, days=200, seed=2)
    results = train_many(
        station_ids=(STATION_DENSE_A, STATION_DENSE_B),
        session=session,
        protocol=_protocol(),  # type: ignore[arg-type]
        artifact_root=tmp_path,
        persist=True,
    )
    assert len(results) == 2
    assert all(r.model_version == GBM_VERSION for r in results)
    assert all(r.metric_row_id is not None for r in results)
    # One artifact file per station, all under the same model_version dir.
    paths = [r.artifact_path for r in results if r.artifact_path is not None]
    assert len(paths) == 2
    parents = {p.parent for p in paths}
    assert len(parents) == 1, "all per-station artifacts share one version dir"
    # And one metric_payload row per station (Q.3 fairness audit
    # consumes these).
    rows = session.query(ModelPerformanceMetric).all()
    assert len(rows) == 2


def test_train_many_returns_placeholder_for_thin_station(
    session: Session, tmp_path: Path
) -> None:
    # A only seeded; C is empty; B has very thin data.
    _seed(session, station=STATION_DENSE_A, target=TARGET_A, days=200, seed=1)
    _seed(session, station=STATION_THIN, target=TARGET_C, days=5, seed=3)
    results = train_many(
        station_ids=(STATION_DENSE_A, STATION_THIN),
        session=session,
        protocol=_protocol(),  # type: ignore[arg-type]
        artifact_root=tmp_path,
        persist=True,
    )
    assert len(results) == 2
    assert results[0].metric_row_id is not None  # A succeeded
    assert results[1].metric_row_id is None  # C captured-as-placeholder
    assert results[1].train_record_count == 0
    assert results[1].artifact_path is None
