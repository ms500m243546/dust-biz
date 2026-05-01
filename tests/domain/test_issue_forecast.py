from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.domain.forecasting import TargetNotFoundError, issue_forecast
from app.models import registry
from app.models.forecasting.heuristic_baseline import HeuristicBaselineForecaster
from app.schemas.forecasts import DustForecastSchema, ForecastTargetSchema
from app.storage.models import (
    DustPrediction,
    EquipmentActivity,
    FeatureRecord,
    Mine,
    Sensor,
    SensorReading,
    WeatherReading,
    Zone,
)

NOW = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _reset_registry() -> Iterator[None]:
    registry.reset()
    registry.register(HeuristicBaselineForecaster())
    yield
    registry.reset()


def _seed(session: Session, *, with_pm: bool = True, with_weather: bool = True) -> None:
    session.add(Mine(mine_id="m1", name="Demo"))
    session.add(
        Zone(
            zone_id="haul_c",
            mine_id="m1",
            zone_type="haul_road",
            operational_importance="high",
            dust_generation_baseline="medium",
        )
    )
    session.add(Sensor(sensor_id="cs1", mine_id="m1", zone_id="haul_c", sensor_type="pm10"))
    session.flush()

    # Equipment activity at t-2 min
    from app.storage.models import Equipment

    session.add(Equipment(equipment_id="truck_1", mine_id="m1", equipment_type="truck"))
    session.flush()
    session.add(
        EquipmentActivity(
            equipment_id="truck_1",
            timestamp=(NOW - timedelta(minutes=2)).replace(tzinfo=None),
            zone_id="haul_c",
            activity_type="hauling",
            tonnage=140.0,
            raw_payload={},
        )
    )

    if with_pm:
        for mins_ago, pm10 in [(2.0, 80.0), (10.0, 60.0), (25.0, 50.0)]:
            session.add(
                SensorReading(
                    sensor_id="cs1",
                    timestamp=(NOW - timedelta(minutes=mins_ago)).replace(tzinfo=None),
                    raw_value={"pm10_ugm3": pm10, "pm25_ugm3": pm10 * 0.4},
                )
            )

    if with_weather:
        session.add(
            WeatherReading(
                source="onsite",
                zone_id=None,
                timestamp=(NOW - timedelta(minutes=1)).replace(tzinfo=None),
                wind_speed_ms=4.0,
                wind_direction_deg=180.0,
                gust_speed_ms=6.0,
                humidity_pct=45.0,
                temperature_c=21.0,
            )
        )
    session.flush()


def test_issue_forecast_returns_schema_with_safety_fields(session: Session) -> None:
    _seed(session)
    out = issue_forecast(
        session=session,
        target=ForecastTargetSchema(target_kind="zone", target_id="haul_c"),
        horizon="60min",
        now=NOW,
    )
    assert isinstance(out, DustForecastSchema)
    assert out.confidence > 0.0
    assert out.model_version.startswith("dust_forecast_heuristic_")
    assert out.feature_pipeline_version == "feature_pipeline_v0.1.0"
    assert out.source == "model"
    assert out.target_id == "haul_c"


def test_issue_forecast_persists_feature_and_prediction(session: Session) -> None:
    _seed(session)
    out = issue_forecast(
        session=session,
        target=ForecastTargetSchema(target_kind="zone", target_id="haul_c"),
        horizon="30min",
        now=NOW,
    )

    features = list(session.query(FeatureRecord).all())
    assert len(features) == 1
    assert features[0].zone_id == "haul_c"
    assert features[0].feature_pipeline_version == "feature_pipeline_v0.1.0"

    predictions = list(session.query(DustPrediction).all())
    assert len(predictions) == 1
    p = predictions[0]
    assert p.prediction_id == "PRED-20260501-0001"
    assert p.confidence == out.confidence
    assert p.target_id == "haul_c"
    assert p.input_record_ids  # at least the seeded sensor + weather rows


def test_unknown_zone_raises_forecast_input_error(session: Session) -> None:
    _seed(session)
    with pytest.raises(TargetNotFoundError):
        issue_forecast(
            session=session,
            target=ForecastTargetSchema(target_kind="zone", target_id="nope"),
            horizon="30min",
            now=NOW,
        )


def test_no_pm_sensors_lowers_quality_score_and_adds_warning(session: Session) -> None:
    # Seed mine + zone + weather but no sensors / PM readings
    session.add(Mine(mine_id="m1", name="Demo"))
    session.add(
        Zone(
            zone_id="haul_c",
            mine_id="m1",
            zone_type="haul_road",
            operational_importance="high",
            dust_generation_baseline="medium",
        )
    )
    session.add(
        WeatherReading(
            source="onsite",
            zone_id=None,
            timestamp=(NOW - timedelta(minutes=1)).replace(tzinfo=None),
            wind_speed_ms=4.0,
            wind_direction_deg=180.0,
        )
    )
    session.flush()

    out = issue_forecast(
        session=session,
        target=ForecastTargetSchema(target_kind="zone", target_id="haul_c"),
        horizon="60min",
        now=NOW,
    )
    assert out.input_data_quality_score == 0.5
    assert "no_pm_sensors_for_zone" in out.data_quality_warnings
    # Without PM features the heuristic falls back
    assert out.source == "heuristic_fallback"


def test_sensor_target_resolves_to_zone(session: Session) -> None:
    _seed(session)
    out = issue_forecast(
        session=session,
        target=ForecastTargetSchema(target_kind="sensor", target_id="cs1"),
        horizon="60min",
        now=NOW,
    )
    # Forecast keeps the sensor target identity but uses the zone's
    # features / activity for the prediction.
    assert out.target_kind == "sensor"
    assert out.target_id == "cs1"


def test_quality_multiplier_passed_through_to_prediction(session: Session) -> None:
    """G4 - low PM sensor health must propagate into confidence."""
    # Seed everything but make the PM sensor look stale: only one
    # reading 25 minutes ago.
    session.add(Mine(mine_id="m1", name="Demo"))
    session.add(
        Zone(
            zone_id="haul_c",
            mine_id="m1",
            zone_type="haul_road",
            operational_importance="high",
            dust_generation_baseline="medium",
        )
    )
    session.add(Sensor(sensor_id="cs1", mine_id="m1", zone_id="haul_c", sensor_type="pm10"))
    session.add(
        SensorReading(
            sensor_id="cs1",
            timestamp=(NOW - timedelta(minutes=25)).replace(tzinfo=None),
            raw_value={"pm10_ugm3": 60.0, "pm25_ugm3": 25.0},
        )
    )
    session.add(
        WeatherReading(
            source="onsite",
            zone_id=None,
            timestamp=(NOW - timedelta(minutes=1)).replace(tzinfo=None),
            wind_speed_ms=4.0,
            wind_direction_deg=180.0,
        )
    )
    session.flush()

    out = issue_forecast(
        session=session,
        target=ForecastTargetSchema(target_kind="zone", target_id="haul_c"),
        horizon="60min",
        now=NOW,
    )
    assert out.input_data_quality_score < 1.0
    assert any("cs1" in w for w in out.data_quality_warnings)
