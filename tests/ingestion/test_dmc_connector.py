"""Phase BA.1 — DMC connector tests."""

from __future__ import annotations

import pytest

from app.ingestion.public.dmc import (
    SOURCE_NAME,
    fetch_live,
    parse_dmc_payload,
)


def test_source_name_is_stable() -> None:
    # The discriminator is wire-visible (RawWeatherReading.source)
    # and ends up in audit trails — it should never silently change.
    assert SOURCE_NAME == "dmc"


def test_parse_dmc_payload_basic_shape() -> None:
    payload = {
        "station_code": "330020",
        "time": ["2026-05-01T00:00", "2026-05-01T01:00"],
        "temperature_c": [12.3, 11.8],
        "humidity_pct": [55.0, 58.0],
        "wind_speed_ms": [3.2, 2.7],
        "wind_direction_deg": [240.0, 245.0],
        "pressure_hpa": [882.0, 881.5],
    }
    rows = parse_dmc_payload(payload, weather_target_id="lp-salamanca-met")
    assert len(rows) == 2
    assert rows[0]["source"] == "dmc"
    assert rows[0]["weather_target_id"] == "lp-salamanca-met"
    assert rows[0]["timestamp"] == "2026-05-01T00:00"
    assert rows[0]["temperature_c"] == 12.3
    assert rows[0]["wind_direction_deg"] == 240.0
    assert rows[0]["raw_value"]["station_code"] == "330020"
    assert rows[0]["realtime_proxy"] is True


def test_parse_dmc_payload_empty_times_yields_empty() -> None:
    rows = parse_dmc_payload({"time": []}, weather_target_id="x")
    assert rows == []


def test_parse_dmc_payload_missing_optional_field_skipped() -> None:
    # rainfall_mm_15min isn't always populated. Missing keys must not
    # produce KeyError; the row just lacks that field.
    payload = {
        "time": ["2026-05-01T00:00"],
        "temperature_c": [10.0],
    }
    rows = parse_dmc_payload(payload, weather_target_id="x")
    assert len(rows) == 1
    assert "rainfall_mm_15min" not in rows[0]
    assert rows[0]["temperature_c"] == 10.0


def test_parse_dmc_payload_none_value_skipped() -> None:
    payload = {
        "time": ["2026-05-01T00:00"],
        "temperature_c": [None],
        "humidity_pct": [50.0],
    }
    rows = parse_dmc_payload(payload, weather_target_id="x")
    assert "temperature_c" not in rows[0]
    assert rows[0]["humidity_pct"] == 50.0


def test_fetch_live_is_deferred() -> None:
    with pytest.raises(NotImplementedError, match="DMC live mode is deferred"):
        fetch_live()
