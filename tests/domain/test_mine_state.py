from datetime import UTC, datetime, timedelta

from app.domain.mine_state import compute_zone_state
from app.storage.models import EquipmentActivity, WeatherReading, Zone

NOW = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def _haul_road_zone(zone_id: str = "haul_c") -> Zone:
    return Zone(
        zone_id=zone_id,
        mine_id="m1",
        zone_type="haul_road",
        operational_importance="high",
        dust_generation_baseline="medium",
    )


def _activity(equipment_id: str, kind: str, mins_ago: float, tonnage: float | None = None) -> EquipmentActivity:
    return EquipmentActivity(
        equipment_id=equipment_id,
        timestamp=NOW - timedelta(minutes=mins_ago),
        zone_id="haul_c",
        activity_type=kind,
        speed_kmh=None,
        tonnage=tonnage,
        raw_payload={},
    )


def _weather(speed: float | None, gust: float | None, direction: float | None, mins_ago: float) -> WeatherReading:
    return WeatherReading(
        source="onsite",
        zone_id=None,
        timestamp=NOW - timedelta(minutes=mins_ago),
        wind_speed_ms=speed,
        wind_direction_deg=direction,
        gust_speed_ms=gust,
    )


def test_no_activity_no_weather_yields_unknown_with_staleness() -> None:
    state = compute_zone_state(
        zone=_haul_road_zone(),
        now=NOW,
        window_minutes=15,
        recent_activity=[],
        recent_weather=[],
        downwind_candidates=[],
    )
    assert state.activity == "unknown"
    assert state.dust_generation_potential == "unknown"
    assert state.wind_exposure == "unknown"
    assert "equipment_activity_missing" in state.staleness_flags
    assert "weather_missing" in state.staleness_flags
    assert state.downwind_assets == []


def test_hauling_with_high_wind_marks_high_dust_and_high_exposure() -> None:
    activity = [_activity(f"truck_{i}", "hauling", mins_ago=2.0, tonnage=120.0) for i in range(6)]
    weather = [_weather(speed=8.5, gust=11.0, direction=270.0, mins_ago=1.0)]
    state = compute_zone_state(
        zone=_haul_road_zone(),
        now=NOW,
        window_minutes=15,
        recent_activity=activity,
        recent_weather=weather,
        downwind_candidates=[],
    )
    assert state.activity == "hauling"
    assert state.wind_exposure == "high"
    assert state.dust_generation_potential == "high"
    assert state.staleness_flags == []
    assert state.production_rate_tph is not None and state.production_rate_tph > 0


def test_stale_weather_falls_back_to_unknown_exposure() -> None:
    activity = [_activity("truck_1", "hauling", mins_ago=2.0)]
    # 60 minutes old, window is 15 -> stale
    weather = [_weather(speed=5.0, gust=None, direction=90.0, mins_ago=60.0)]
    state = compute_zone_state(
        zone=_haul_road_zone(),
        now=NOW,
        window_minutes=15,
        recent_activity=activity,
        recent_weather=weather,
        downwind_candidates=[],
    )
    assert "weather_stale" in state.staleness_flags
    assert state.wind_exposure == "unknown"
    assert state.dust_generation_potential == "unknown"


def test_downwind_assets_returns_boundary_and_critical_zones() -> None:
    boundary = Zone(
        zone_id="boundary_n",
        mine_id="m1",
        zone_type="boundary",
        operational_importance="high",
        dust_generation_baseline="low",
    )
    critical_loading = Zone(
        zone_id="loading_a",
        mine_id="m1",
        zone_type="loading_area",
        operational_importance="critical",
        dust_generation_baseline="medium",
    )
    irrelevant = Zone(
        zone_id="stockpile",
        mine_id="m1",
        zone_type="stockpile",
        operational_importance="medium",
        dust_generation_baseline="medium",
    )
    activity = [_activity("truck_1", "hauling", mins_ago=2.0)]
    weather = [_weather(speed=5.0, gust=None, direction=45.0, mins_ago=1.0)]
    state = compute_zone_state(
        zone=_haul_road_zone(),
        now=NOW,
        window_minutes=15,
        recent_activity=activity,
        recent_weather=weather,
        downwind_candidates=[boundary, critical_loading, irrelevant],
    )
    assert "boundary_n" in state.downwind_assets
    assert "loading_a" in state.downwind_assets
    assert "stockpile" not in state.downwind_assets


def test_mixed_activity_label() -> None:
    activity = [
        _activity("truck_1", "hauling", mins_ago=2.0),
        _activity("shovel_1", "loading", mins_ago=1.0),
        _activity("truck_2", "dumping", mins_ago=3.0),
    ]
    weather = [_weather(speed=2.0, gust=None, direction=180.0, mins_ago=1.0)]
    state = compute_zone_state(
        zone=_haul_road_zone(),
        now=NOW,
        window_minutes=15,
        recent_activity=activity,
        recent_weather=weather,
        downwind_candidates=[],
    )
    assert state.activity == "mixed"
    assert state.wind_exposure == "low"
