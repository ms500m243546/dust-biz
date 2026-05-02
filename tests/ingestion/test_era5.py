"""ERA5 connector tests (Phase L.3)."""

from __future__ import annotations

from app.ingestion.public.era5 import parse_era5_payload

_PAYLOAD = {
    "time": [
        "2026-05-01T00:00",
        "2026-05-01T01:00",
    ],
    # Eastward + northward 10m wind components, m/s.
    # u=3, v=4 -> speed 5 m/s, blowing toward 36.87° (NE), so "from" 216.87°
    "u10": [3.0, 0.0],
    "v10": [4.0, -2.0],
    "t2m": [12.0, 11.5],  # already °C after pre-extract
    "sp": [810.0, 811.0],  # hPa after pre-extract
    "rh2m": [42.0, 45.0],
    "tp": [0.0, 0.0],
    "ssrd": [None, 50.0],
}


def test_parse_combines_uv_into_speed_and_direction() -> None:
    rows = parse_era5_payload(_PAYLOAD, zone_id="los-bronces")
    assert len(rows) == 2
    r0 = rows[0]
    assert r0["wind_speed_ms"] == 5.0
    # u=3, v=4 -> direction "to" 36.87°; "from" = (36.87+180) mod 360 = 216.87°
    assert abs(r0["wind_direction_deg"] - 216.87) < 0.1
    assert r0["temperature_c"] == 12.0
    assert r0["zone_id"] == "los-bronces"


def test_parse_handles_negative_v_component() -> None:
    rows = parse_era5_payload(_PAYLOAD)
    r1 = rows[1]
    # u=0, v=-2 -> wind blows southward, "from" = 360°
    assert r1["wind_speed_ms"] == 2.0
    assert abs(r1["wind_direction_deg"] - 360.0) < 0.1 or abs(r1["wind_direction_deg"]) < 0.1


def test_parse_preserves_solar_none_then_value() -> None:
    rows = parse_era5_payload(_PAYLOAD)
    assert rows[0]["solar_wm2"] is None
    assert rows[1]["solar_wm2"] == 50.0


def test_parse_returns_empty_for_no_time_array() -> None:
    assert parse_era5_payload({"u10": [1.0]}) == []
