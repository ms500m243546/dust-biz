from datetime import UTC, datetime, timedelta

from app.ingestion.mock_streams import (
    generate_equipment_activity,
    generate_sensor_readings,
    generate_weather_readings,
)


def test_sensor_stream_count_matches_duration_and_interval() -> None:
    start = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    readings = list(
        generate_sensor_readings(
            "PM10_BOUNDARY", start, timedelta(minutes=10), interval_seconds=60
        )
    )
    assert len(readings) == 10


def test_sensor_stream_is_reproducible_for_same_seed() -> None:
    start = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    a = list(generate_sensor_readings("S1", start, timedelta(minutes=5), seed=99))
    b = list(generate_sensor_readings("S1", start, timedelta(minutes=5), seed=99))
    assert [r.raw_value for r in a] == [r.raw_value for r in b]


def test_sensor_stream_pm10_is_non_negative_and_realistic() -> None:
    start = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    readings = list(generate_sensor_readings("S1", start, timedelta(hours=1)))
    pm10s = [r.raw_value["pm10_ugm3"] for r in readings]
    assert all(p >= 0 for p in pm10s)
    # Baseline 80 ug/m^3 with diurnal swing - all values should land in
    # an obviously-PM10 range, not e.g. 1e6.
    assert all(0 <= p < 1000 for p in pm10s)


def test_sensor_stream_spikes_are_reachable_with_high_probability() -> None:
    start = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    readings = list(
        generate_sensor_readings(
            "S1",
            start,
            timedelta(hours=2),
            spike_probability=1.0,
            spike_magnitude=(200.0, 200.0),
            seed=7,
        )
    )
    # Every reading was spiked; max should be well above the noisy baseline
    assert max(r.raw_value["pm10_ugm3"] for r in readings) > 200


def test_weather_stream_basic_shape() -> None:
    start = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    readings = list(
        generate_weather_readings(
            "onsite_station_1",
            start,
            timedelta(hours=1),
            interval_seconds=600,
        )
    )
    assert len(readings) == 6
    for r in readings:
        assert r.wind_speed_ms is not None and r.wind_speed_ms >= 0
        assert r.wind_direction_deg is not None and 0 <= r.wind_direction_deg < 360
        assert r.humidity_pct is not None and 0 <= r.humidity_pct <= 100


def test_equipment_stream_emits_only_allowed_activity_types() -> None:
    start = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    activities = list(
        generate_equipment_activity(
            "Truck_17",
            start,
            timedelta(hours=1),
            interval_seconds=300,
        )
    )
    assert len(activities) == 12
    types = {a.activity_type for a in activities}
    assert types.issubset({"hauling", "loading", "idle"})


def test_equipment_stream_speed_is_non_negative() -> None:
    start = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    activities = list(
        generate_equipment_activity("Truck_17", start, timedelta(hours=1))
    )
    for a in activities:
        if a.speed_kmh is not None:
            assert a.speed_kmh >= 0
