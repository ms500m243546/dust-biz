"""DGA connector tests (Phase L.3)."""

from __future__ import annotations

from datetime import datetime

from app.ingestion.public.dga import parse_dga_payload

_PAYLOAD = {
    "station_code": "CUNCUMEN_DGA",
    "observations": [
        {
            "timestamp": "2026-05-01T00:00",
            "wind_speed_ms": 2.1,
            "wind_direction_deg": 200.0,
            "temperature_c": 11.0,
            "humidity_pct": 60.0,
            "rainfall_mm": 0.0,
        },
        {
            "timestamp": "2026-05-01T01:00",
            "wind_speed_ms": 3.4,
            "wind_direction_deg": 215.0,
            "temperature_c": 10.2,
            "humidity_pct": 65.0,
            "rainfall_mm": 0.2,
        },
    ],
}


def test_parse_yields_one_record_per_observation() -> None:
    rows = parse_dga_payload(_PAYLOAD, zone_id="cuncumen-zone")
    assert len(rows) == 2
    assert rows[0]["timestamp"] == datetime(2026, 5, 1, 0, 0)
    assert rows[0]["wind_speed_ms"] == 2.1
    assert rows[0]["station_code"] == "CUNCUMEN_DGA"


def test_parse_preserves_zone_id_when_provided() -> None:
    rows = parse_dga_payload(_PAYLOAD, zone_id="cuncumen-zone")
    assert all(r["zone_id"] == "cuncumen-zone" for r in rows)


def test_parse_drops_observations_with_bad_timestamp() -> None:
    payload = {
        "station_code": "X",
        "observations": [
            {"timestamp": "not-a-date", "temperature_c": 12.0},
            {"timestamp": "2026-05-01T00:00", "temperature_c": 13.0},
        ],
    }
    rows = parse_dga_payload(payload)
    assert len(rows) == 1


def test_parse_empty_for_no_observations() -> None:
    assert parse_dga_payload({}) == []
    assert parse_dga_payload({"observations": "not a list"}) == []
