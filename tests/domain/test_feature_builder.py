from datetime import UTC, datetime, timedelta

from app.domain.features import FEATURE_PIPELINE_VERSION, build_feature_record
from app.schemas.mine_state import MineStateZoneSchema
from app.storage.models import SensorReading, WeatherReading

NOW = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def _zone_state(zone_id: str = "haul_c") -> MineStateZoneSchema:
    return MineStateZoneSchema(
        timestamp=NOW,
        zone_id=zone_id,
        activity="hauling",
        equipment_active=["truck_1", "truck_2"],
        production_rate_tph=480.0,
        dust_generation_potential="high",
        wind_exposure="high",
        downwind_assets=["boundary_n"],
        operational_importance="high",
        staleness_flags=[],
    )


def _pm(sensor_id: str, mins_ago: float, pm10: float, pm25: float) -> SensorReading:
    return SensorReading(
        sensor_id=sensor_id,
        timestamp=NOW - timedelta(minutes=mins_ago),
        raw_value={"pm10_ugm3": pm10, "pm25_ugm3": pm25},
    )


def _weather(
    mins_ago: float,
    *,
    speed: float = 5.0,
    gust: float = 7.0,
    direction: float = 180.0,
) -> WeatherReading:
    return WeatherReading(
        source="onsite",
        timestamp=NOW - timedelta(minutes=mins_ago),
        wind_speed_ms=speed,
        gust_speed_ms=gust,
        wind_direction_deg=direction,
        humidity_pct=40.0,
        temperature_c=22.0,
    )


def test_happy_path_builds_payload_with_pm_wind_and_state_namespaces() -> None:
    pm = [_pm("s1", mins_ago=m, pm10=80 + m, pm25=30 + m) for m in (1, 5, 10, 20, 45)]
    weather = [_weather(mins_ago=2.0)]
    out = build_feature_record(
        zone_state=_zone_state(),
        pm_readings=pm,
        weather_readings=weather,
        as_of=NOW,
    )
    assert out.feature_pipeline_version == FEATURE_PIPELINE_VERSION
    assert out.zone_id == "haul_c"
    assert out.timestamp == NOW
    assert out.feature_payload["pm.pm10_avg_5min"] is not None
    assert out.feature_payload["pm.pm10_avg_60min"] is not None
    assert out.feature_payload["wind.speed_ms"] == 5.0
    assert out.feature_payload["wind.direction_deg"] == 180.0
    assert out.feature_payload["activity.label"] == "hauling"
    assert out.feature_payload["activity.equipment_count"] == 2
    assert out.feature_payload["state.dust_generation_potential"] == "high"
    assert out.feature_payload["state.downwind_asset_count"] == 1
    assert out.missing_inputs == []


def test_leakage_guard_excludes_readings_strictly_after_as_of() -> None:
    # readings 5 min in the future relative to as_of must not contribute
    future_reading = SensorReading(
        sensor_id="s1",
        timestamp=NOW + timedelta(minutes=5),
        raw_value={"pm10_ugm3": 9999.0, "pm25_ugm3": 9999.0},
    )
    valid = _pm("s1", mins_ago=2.0, pm10=50.0, pm25=20.0)
    out = build_feature_record(
        zone_state=_zone_state(),
        pm_readings=[valid, future_reading],
        weather_readings=[_weather(mins_ago=1.0)],
        as_of=NOW,
    )
    pm10_avg = out.feature_payload["pm.pm10_avg_5min"]
    assert pm10_avg is not None
    assert pm10_avg < 9999.0  # future poison reading excluded


def test_pm_trend_is_positive_when_concentrations_rising() -> None:
    # older readings low, recent readings high -> positive trend
    pm = [
        _pm("s1", mins_ago=25, pm10=40.0, pm25=15.0),
        _pm("s1", mins_ago=20, pm10=50.0, pm25=20.0),
        _pm("s1", mins_ago=10, pm10=80.0, pm25=30.0),
        _pm("s1", mins_ago=2, pm10=120.0, pm25=50.0),
    ]
    out = build_feature_record(
        zone_state=_zone_state(),
        pm_readings=pm,
        weather_readings=[_weather(mins_ago=1.0)],
        as_of=NOW,
    )
    trend = out.feature_payload["pm.pm10_trend_per_min"]
    assert trend is not None
    assert trend > 0


def test_meta_fields_record_input_counts() -> None:
    pm = [_pm("s1", mins_ago=2.0, pm10=42.0, pm25=18.0)]
    weather = [_weather(mins_ago=1.0), _weather(mins_ago=10.0)]
    out = build_feature_record(
        zone_state=_zone_state(),
        pm_readings=pm,
        weather_readings=weather,
        as_of=NOW,
        lookback_minutes=45,
    )
    assert out.feature_payload["meta.lookback_minutes"] == 45
    assert out.feature_payload["meta.weather_reading_count"] == 2
    assert out.feature_payload["meta.pm_reading_count"] == 1
