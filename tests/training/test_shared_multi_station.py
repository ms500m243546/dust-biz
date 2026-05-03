"""Phase Q.2 — shared multi-station training tests."""

from __future__ import annotations

import math
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.forecasting.gbm_shared_v0_1_0 import (
    GBM_SHARED_VERSION,
    GBMSharedForecaster,
    shared_artifact_path,
)
from app.schemas.features import FeatureRecordSchema
from app.schemas.forecasts import ForecastTargetSchema
from app.storage.models import Base, ModelPerformanceMetric, SensorReading, WeatherReading
from app.training.dust_forecast_training import (
    build_p1_protocol,
    train_shared_multi_station,
)

STATION_A = "test-shared-a"
STATION_B = "test-shared-b"
TARGET_A = "test-shared-a-met"
TARGET_B = "test-shared-b-met"


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
    mod.STATION_WEATHER_TARGETS.update({STATION_A: TARGET_A, STATION_B: TARGET_B})
    yield
    mod.STATION_WEATHER_TARGETS.clear()
    mod.STATION_WEATHER_TARGETS.update(original)


def _seed(session: Session, *, station: str, target: str, seed: int) -> None:
    import random

    rng = random.Random(seed)
    start = datetime(2025, 5, 3)
    for hour in range(200 * 24):
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


def test_shared_trainer_persists_one_artifact_for_two_stations(
    session: Session, tmp_path: Path
) -> None:
    _seed(session, station=STATION_A, target=TARGET_A, seed=1)
    _seed(session, station=STATION_B, target=TARGET_B, seed=2)
    result = train_shared_multi_station(
        station_ids=(STATION_A, STATION_B),
        session=session,
        protocol=_protocol(),  # type: ignore[arg-type]
        artifact_root=tmp_path,
    )
    assert result.model_version == GBM_SHARED_VERSION
    assert STATION_A in result.station_vocab
    assert STATION_B in result.station_vocab
    # Single artifact file (not one per station).
    assert result.artifact_path is not None
    assert result.artifact_path.exists()
    expected = shared_artifact_path(artifact_root=tmp_path, horizon="60min")
    assert result.artifact_path == expected
    # Single metric row carrying per_receptor breakdown.
    rows = session.query(ModelPerformanceMetric).all()
    assert len(rows) == 1
    payload = rows[0].metric_payload or {}
    per_receptor = payload.get("per_receptor", {}) or {}
    assert STATION_A in per_receptor
    assert STATION_B in per_receptor


def test_shared_predict_uses_per_station_one_hot(
    session: Session, tmp_path: Path
) -> None:
    _seed(session, station=STATION_A, target=TARGET_A, seed=1)
    _seed(session, station=STATION_B, target=TARGET_B, seed=2)
    train_shared_multi_station(
        station_ids=(STATION_A, STATION_B),
        session=session,
        protocol=_protocol(),  # type: ignore[arg-type]
        artifact_root=tmp_path,
    )
    forecaster = GBMSharedForecaster(artifact_root=tmp_path)
    features = FeatureRecordSchema(
        timestamp=datetime(2025, 11, 1, 12, 0),
        zone_id="z",
        feature_pipeline_version="feature_pipeline_p1_v0.1.0",
        feature_payload={
            "pm10_lag_1h": 40.0,
            "pm10_lag_3h": 38.0,
            "pm10_lag_24h": 35.0,
            "pm10_rolling_mean_24h": 36.0,
            "wind_speed_ms": 5.0,
            "wind_direction_deg": 180.0,
            "humidity_pct": 50.0,
            "temperature_c": 15.0,
            "pressure_hpa": 1013.0,
            "rainfall_mm_15min": 0.0,
            "hour_of_day": 12.0,
            "month": 11.0,
        },
        missing_inputs=[],
    )
    target_a = ForecastTargetSchema(target_kind="sensor", target_id=STATION_A)
    target_b = ForecastTargetSchema(target_kind="sensor", target_id=STATION_B)
    fa = forecaster.predict(features=features, target=target_a, horizon="60min")
    fb = forecaster.predict(features=features, target=target_b, horizon="60min")
    # Same feature payload, different stations — predictions should
    # differ if the one-hot is being honoured.
    assert (fa.predicted_pm10 != fb.predicted_pm10) or (
        fa.breach_probability != fb.breach_probability
    )
    assert "shared_model_unknown_station" not in " ".join(fa.data_quality_warnings)


def test_shared_predict_warns_on_unknown_station(
    session: Session, tmp_path: Path
) -> None:
    _seed(session, station=STATION_A, target=TARGET_A, seed=1)
    _seed(session, station=STATION_B, target=TARGET_B, seed=2)
    train_shared_multi_station(
        station_ids=(STATION_A, STATION_B),
        session=session,
        protocol=_protocol(),  # type: ignore[arg-type]
        artifact_root=tmp_path,
    )
    forecaster = GBMSharedForecaster(artifact_root=tmp_path)
    features = FeatureRecordSchema(
        timestamp=datetime(2025, 11, 1, 12, 0),
        zone_id="z",
        feature_pipeline_version="feature_pipeline_p1_v0.1.0",
        feature_payload={
            "pm10_lag_1h": 40.0,
            "pm10_lag_3h": 38.0,
            "pm10_lag_24h": 35.0,
            "pm10_rolling_mean_24h": 36.0,
            "wind_speed_ms": 5.0,
            "wind_direction_deg": 180.0,
            "humidity_pct": 50.0,
            "temperature_c": 15.0,
            "pressure_hpa": 1013.0,
            "rainfall_mm_15min": 0.0,
            "hour_of_day": 12.0,
            "month": 11.0,
        },
        missing_inputs=[],
    )
    f = forecaster.predict(
        features=features,
        target=ForecastTargetSchema(target_kind="sensor", target_id="ghost"),
        horizon="60min",
    )
    assert any(
        "shared_model_unknown_station" in w for w in f.data_quality_warnings
    )
