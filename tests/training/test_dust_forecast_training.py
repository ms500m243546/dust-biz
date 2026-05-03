"""Phase P.2 — training-pipeline tests.

Synthetic in-memory dataset rather than the full dev DB so tests
run < 5 s and don't depend on operator-pulled data being present.
The synthetic generator emits a noisy seasonal PM10 series + a
correlated weather signal so the GBM has something learnable.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.storage.models import Base, SensorReading, WeatherReading
from app.training.dust_forecast_training import (
    DEFAULT_HORIZON,
    GBM_VERSION,
    PM10_BREACH,
    build_p1_protocol,
    train_one,
)

STATION = "lp-em05-cuncumen"
WEATHER_TARGET = "lp-cuncumen-met"


@pytest.fixture()
def session() -> Iterator[Session]:
    """Fresh in-memory SQLite per test."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    with SessionLocal() as s:
        yield s


def _seed(session: Session, *, days: int = 200, seed: int = 0) -> None:
    """Inject a deterministic synthetic series for `days` worth of hours."""
    import random

    rng = random.Random(seed)
    start = datetime(2025, 5, 3, 0, 0, 0)
    for hour in range(days * 24):
        ts = start + timedelta(hours=hour)
        # Synthetic PM10: diurnal + weekly seasonality + noise + a
        # weather-driven excursion (when humidity is low + wind high,
        # PM10 spikes). Generates enough breach events to fit a
        # classifier.
        diurnal = 30 + 25 * math.sin(2 * math.pi * (hour % 24) / 24)
        humidity = 50 + 30 * math.sin(2 * math.pi * (hour % 168) / 168) + rng.uniform(-5, 5)
        wind_speed = 4 + 5 * math.cos(2 * math.pi * (hour % 24) / 24) + rng.uniform(-1, 1)
        excursion = max(0.0, 80.0 * (1 - humidity / 100) * (wind_speed / 8))
        pm10 = diurnal + excursion + rng.uniform(-15, 15)
        pm10 = max(5.0, pm10)

        session.add(
            SensorReading(
                sensor_id=STATION,
                timestamp=ts,
                raw_value={
                    "source": "sinca",
                    "station_code": "424",
                    "parameter": "pm10",
                    "validated": True,
                    "pm10_ugm3": round(pm10, 2),
                },
                source_quality_hint=0.9,
                valid_from=ts,
                pit_version="v1",
            )
        )
        session.add(
            WeatherReading(
                source="open_meteo",
                timestamp=ts,
                weather_target_id=WEATHER_TARGET,
                realtime_proxy=True,
                wind_speed_ms=round(wind_speed, 2),
                wind_direction_deg=round((hour * 13) % 360, 1),
                humidity_pct=round(humidity, 2),
                temperature_c=round(15 + 10 * math.sin(2 * math.pi * (hour % 24) / 24), 2),
                pressure_hpa=1013.0,
                rainfall_mm_15min=0.0,
            )
        )
    session.flush()


def _protocol_over_seeded(start: datetime = datetime(2025, 5, 3)) -> object:
    return build_p1_protocol(
        train_window_from=start,
        train_window_to=start + timedelta(days=140),
        validation_window_from=start + timedelta(days=147),
        validation_window_to=start + timedelta(days=170),
        test_window_from=start + timedelta(days=177),
        test_window_to=start + timedelta(days=200),
    )


def test_train_one_persists_artifact_and_metric_row(
    session: Session, tmp_path: Path
) -> None:
    _seed(session, days=200)
    protocol = _protocol_over_seeded()
    result = train_one(
        station_id=STATION,
        session=session,
        horizon=DEFAULT_HORIZON,
        protocol=protocol,  # type: ignore[arg-type]
        artifact_root=tmp_path,
        persist=True,
    )
    assert result.model_version == GBM_VERSION
    assert result.station_id == STATION
    assert result.train_record_count > 0
    assert result.test_record_count > 0
    # Artifact file exists on disk and contains the bundle.
    assert result.artifact_path is not None
    assert result.artifact_path.exists()
    assert result.artifact_path.is_file()
    # Metric row was persisted with M.4 protocol fields.
    assert result.metric_row_id is not None


def test_train_one_writes_protocol_block_into_metric_payload(
    session: Session, tmp_path: Path
) -> None:
    _seed(session, days=200)
    protocol = _protocol_over_seeded()
    train_one(
        station_id=STATION,
        session=session,
        horizon=DEFAULT_HORIZON,
        protocol=protocol,  # type: ignore[arg-type]
        artifact_root=tmp_path,
        persist=True,
    )
    from app.storage.models import ModelPerformanceMetric

    rows = session.query(ModelPerformanceMetric).all()
    assert len(rows) == 1
    payload = rows[0].metric_payload
    block = payload.get("protocol", {})
    assert block.get("protocol_version") == "M.4"
    assert "max_ece" in block
    assert payload.get("calibration_bins") is not None
    assert payload.get("ece") is not None


def test_train_one_no_persist_skips_artifact_and_metric_row(
    session: Session, tmp_path: Path
) -> None:
    _seed(session, days=200)
    protocol = _protocol_over_seeded()
    result = train_one(
        station_id=STATION,
        session=session,
        horizon=DEFAULT_HORIZON,
        protocol=protocol,  # type: ignore[arg-type]
        artifact_root=tmp_path,
        persist=False,
    )
    assert result.artifact_path is None
    assert result.metric_row_id is None
    # But ECE/MAE were still computed for the caller's review.
    assert result.ece is not None or result.mae_pm10 is not None


def test_train_one_raises_with_insufficient_data(
    session: Session, tmp_path: Path
) -> None:
    # Only ~10 days = ~240 PM rows; below the 200-each floor.
    _seed(session, days=8)
    protocol = _protocol_over_seeded()
    with pytest.raises(ValueError, match="insufficient"):
        train_one(
            station_id=STATION,
            session=session,
            horizon=DEFAULT_HORIZON,
            protocol=protocol,  # type: ignore[arg-type]
            artifact_root=tmp_path,
            persist=False,
        )


def test_breach_threshold_constant_matches_heuristic_baseline() -> None:
    # If these drift, the predicted_breach_probability target
    # construction in the trainer no longer matches the gate the
    # heuristic baseline was built against.
    from app.models.forecasting.gbm_v0_1_0 import PM10_BREACH_THRESHOLD

    assert PM10_BREACH == PM10_BREACH_THRESHOLD == 150.0
