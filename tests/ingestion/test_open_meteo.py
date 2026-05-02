"""Open-Meteo connector tests (Phase L.3)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.ingestion.public.open_meteo import (
    OpenMeteoConnector,
    parse_open_meteo_payload,
)

_PAYLOAD = {
    "latitude": -31.971,
    "longitude": -70.701,
    "hourly": {
        "time": [
            "2026-05-01T00:00",
            "2026-05-01T01:00",
            "2026-05-01T02:00",
        ],
        "temperature_2m": [10.5, 9.8, 8.2],
        "wind_speed_10m": [3.4, 5.1, 7.8],
        "wind_direction_10m": [210, 230, 245],
        "wind_gusts_10m": [6.2, 8.0, 10.5],
        "relative_humidity_2m": [40, 38, 35],
        "surface_pressure": [851.0, 851.5, 852.0],
        "rain": [0.0, 0.0, 0.0],
        "shortwave_radiation": [0, 0, 0],
    },
}


def test_parse_yields_hourly_records() -> None:
    rows = parse_open_meteo_payload(_PAYLOAD, zone_id="cuncumen-zone")
    assert len(rows) == 3
    assert rows[0]["timestamp"] == datetime(2026, 5, 1, 0, 0)
    assert rows[0]["temperature_c"] == 10.5
    assert rows[0]["wind_speed_ms"] == 3.4
    assert rows[0]["wind_direction_deg"] == 210.0
    assert rows[0]["zone_id"] == "cuncumen-zone"


def test_parse_handles_missing_variable_arrays() -> None:
    payload = {"hourly": {"time": ["2026-05-01T00:00"], "temperature_2m": [12.0]}}
    rows = parse_open_meteo_payload(payload)
    assert len(rows) == 1
    assert rows[0]["temperature_c"] == 12.0
    assert "wind_speed_ms" not in rows[0]


def test_parse_returns_empty_for_malformed_payload() -> None:
    assert parse_open_meteo_payload({}) == []
    assert parse_open_meteo_payload({"hourly": "not a dict"}) == []


def test_connector_fetch_returns_empty_when_cache_miss(tmp_path: Path) -> None:
    conn = OpenMeteoConnector(cache_dir=tmp_path)
    out = list(
        conn.fetch(
            window_from=datetime(2026, 5, 1, 0, 0),
            window_to=datetime(2026, 5, 2, 0, 0),
            latitude=-31.971,
            longitude=-70.701,
        )
    )
    assert out == []
