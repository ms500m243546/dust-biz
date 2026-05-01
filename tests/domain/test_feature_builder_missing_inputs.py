from datetime import UTC, datetime

from app.domain.features import build_feature_record
from app.schemas.mine_state import MineStateZoneSchema

NOW = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def _zone_state(staleness: list[str] | None = None) -> MineStateZoneSchema:
    return MineStateZoneSchema(
        timestamp=NOW,
        zone_id="haul_c",
        activity="unknown",
        equipment_active=[],
        production_rate_tph=None,
        dust_generation_potential="unknown",
        wind_exposure="unknown",
        downwind_assets=[],
        operational_importance="high",
        staleness_flags=staleness or [],
    )


def test_missing_pm_and_weather_annotated_not_fabricated() -> None:
    out = build_feature_record(
        zone_state=_zone_state(),
        pm_readings=[],
        weather_readings=[],
        as_of=NOW,
    )
    assert "pm10_readings_missing" in out.missing_inputs
    assert "pm25_readings_missing" in out.missing_inputs
    assert "weather_readings_missing" in out.missing_inputs
    assert out.feature_payload["pm.pm10_avg_15min"] is None
    assert out.feature_payload["wind.speed_ms"] is None
    assert out.feature_payload["wind.direction_deg"] is None


def test_zone_state_staleness_flags_propagate_into_missing_inputs() -> None:
    out = build_feature_record(
        zone_state=_zone_state(staleness=["weather_stale", "equipment_activity_missing"]),
        pm_readings=[],
        weather_readings=[],
        as_of=NOW,
    )
    assert "weather_stale" in out.missing_inputs
    assert "equipment_activity_missing" in out.missing_inputs


def test_missing_inputs_are_deduplicated() -> None:
    # weather_readings_missing comes from both the weather check and any
    # propagation; ensure it is not duplicated.
    out = build_feature_record(
        zone_state=_zone_state(staleness=["weather_readings_missing"]),
        pm_readings=[],
        weather_readings=[],
        as_of=NOW,
    )
    assert out.missing_inputs.count("weather_readings_missing") == 1
