"""Operator-real adapter tests (Phase L.5)."""

from __future__ import annotations

from app.ingestion.fleet_specs import CATERPILLAR_793F, KOMATSU_930E, get_spec
from app.ingestion.operator_real import (
    SOURCE_NAME,
    FieldMap,
    to_equipment_activity,
    to_sensor_readings,
    to_weather_readings,
)


def test_default_field_map_parses_modular_dispatch_shape() -> None:
    rows = [
        {
            "timestamp": "2026-05-01T10:00:00",
            "equipment_id": "T-101",
            "activity": "hauling",
            "speed_kmh": 32.5,
            "tonnage": 218.0,
            "zone_id": "haul_road_a",
        },
        {
            "timestamp": "2026-05-01T10:02:00",
            "equipment_id": "T-101",
            "activity": "idle",
            "speed_kmh": 0.0,
            "zone_id": "loading_area",
        },
    ]
    out = list(to_equipment_activity(rows))
    assert len(out) == 2
    assert out[0].activity_type == "hauling"
    assert out[0].tonnage == 218.0
    assert out[1].speed_kmh == 0.0


def test_pm_rows_get_source_quality_one() -> None:
    rows = [
        {
            "timestamp": "2026-05-01T10:00:00+00:00",
            "sensor_id": "lp-faena-pm10-01",
            "pm10_ugm3": 145.6,
            "pm25_ugm3": 41.2,
        }
    ]
    out = list(to_sensor_readings(rows))
    assert len(out) == 1
    assert out[0].source_quality_hint == 1.0
    assert out[0].raw_value["source"] == SOURCE_NAME
    assert out[0].raw_value["pm10_ugm3"] == 145.6


def test_dotted_path_field_map_pulls_nested_columns() -> None:
    rows = [
        {
            "ts": "2026-05-01T10:00:00",
            "ident": {"truck": "T-101"},
            "telemetry": {
                "speed": 28.0,
                "tonnes": 215.0,
                "activity": "hauling",
            },
            "loc": {"zone": "haul_road_b"},
        }
    ]
    field_map = FieldMap(
        timestamp="ts",
        equipment_id="ident.truck",
        activity_type="telemetry.activity",
        speed_kmh="telemetry.speed",
        tonnage="telemetry.tonnes",
        zone_id="loc.zone",
    )
    out = list(to_equipment_activity(rows, field_map=field_map))
    assert len(out) == 1
    assert out[0].equipment_id == "T-101"
    assert out[0].speed_kmh == 28.0


def test_drops_rows_with_missing_required_fields() -> None:
    rows: list[dict[str, object]] = [
        {"timestamp": "2026-05-01T10:00:00"},  # no sensor_id
        {"sensor_id": "x", "pm10_ugm3": 100.0},  # no timestamp
        {
            "timestamp": "not-a-time",
            "sensor_id": "x",
            "pm10_ugm3": 100.0,
        },  # bad timestamp
    ]
    assert list(to_sensor_readings(rows)) == []


def test_drops_pm_rows_without_any_pm_value() -> None:
    rows: list[dict[str, object]] = [
        {
            "timestamp": "2026-05-01T10:00:00",
            "sensor_id": "x",
            # no pm10 / pm25 -> dropped
        }
    ]
    assert list(to_sensor_readings(rows)) == []


def test_weather_passthrough() -> None:
    rows = [
        {
            "timestamp": "2026-05-01T10:00:00",
            "wind_speed_ms": 4.5,
            "wind_direction_deg": 200,
            "temperature_c": 12.0,
            "humidity_pct": 35.0,
            "zone_id": "pit-north",
        }
    ]
    out = list(to_weather_readings(rows))
    assert len(out) == 1
    assert out[0].source == SOURCE_NAME
    assert out[0].wind_speed_ms == 4.5
    assert out[0].zone_id == "pit-north"


def test_fleet_spec_lookup_matches_published_payloads() -> None:
    assert CATERPILLAR_793F.payload_tonnes == 218.0
    assert KOMATSU_930E.payload_tonnes == 290.0
    assert get_spec("cat-793f") is CATERPILLAR_793F


def test_fleet_spec_unknown_model_raises() -> None:
    import pytest

    with pytest.raises(KeyError):
        get_spec("not-a-model")
