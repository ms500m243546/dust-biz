"""SINCA connector tests (Phase L.2).

No live network. All tests run against the captured fixture in
tests/ingestion/fixtures/.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.ingestion.public.sinca import (
    SOURCE_NAME,
    SincaConnector,
    SincaStation,
    build_url,
    parse_sinca_csv,
    quality_hint_for_tier,
    to_raw_sensor_payload,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _cuncumen() -> SincaStation:
    return SincaStation(
        station_code="EM05",
        station_name="Cuncumén",
        region="Coquimbo",
        commune="Salamanca",
        longitude=-70.701,
        latitude=-31.971,
        tier="EMRPM",
        parameters=("pm10", "pm25"),
    )


def test_parse_drops_si_and_na_rows() -> None:
    payload = (FIXTURES / "sinca_cuncumen_pm10.csv").read_text(encoding="utf-8")
    rows = parse_sinca_csv(payload, station_code="EM05", parameter="pm10")
    # 10 input rows; 2 are non-numeric (S/I, NA) so 8 remain.
    assert len(rows) == 8
    assert all(isinstance(r["value_ugm3"], float) for r in rows)


def test_parse_handles_european_decimal_comma() -> None:
    payload = (FIXTURES / "sinca_cuncumen_pm10.csv").read_text(encoding="utf-8")
    rows = parse_sinca_csv(payload, station_code="EM05", parameter="pm10")
    last = rows[-1]
    assert last["value_ugm3"] == 108.5
    assert last["timestamp"] == datetime(2026, 5, 1, 7, 0)


def test_parse_preserves_validated_flag() -> None:
    payload = (FIXTURES / "sinca_cuncumen_pm10.csv").read_text(encoding="utf-8")
    rows = parse_sinca_csv(payload, station_code="EM05", parameter="pm10")
    assert all(r["validated"] is True for r in rows)


def test_to_raw_sensor_payload_uses_pm10_ugm3_key() -> None:
    payload = (FIXTURES / "sinca_cuncumen_pm10.csv").read_text(encoding="utf-8")
    rec = parse_sinca_csv(payload, station_code="EM05", parameter="pm10")[0]
    raw = to_raw_sensor_payload(rec, station=_cuncumen())
    assert raw["source"] == SOURCE_NAME
    assert raw["station_code"] == "EM05"
    assert raw["pm10_ugm3"] == 112.4
    assert raw["region"] == "Coquimbo"


def test_quality_hint_tiers() -> None:
    assert quality_hint_for_tier("EMRPM") == 0.9
    assert quality_hint_for_tier("indicative") == 0.7
    assert quality_hint_for_tier("unknown-tier") == 0.5


def test_build_url_includes_station_param_and_dates() -> None:
    url = build_url(
        station_code="EM05",
        parameter="pm10",
        window_from=datetime(2026, 4, 30, 0, 0),
        window_to=datetime(2026, 5, 2, 0, 0),
    )
    assert "EM05" in url
    assert "PM10" in url
    assert "20260430" in url
    assert "20260502" in url


def test_connector_fetch_from_payload_yields_typed_records() -> None:
    payload = (FIXTURES / "sinca_cuncumen_pm10.csv").read_text(encoding="utf-8")
    conn = SincaConnector(cache_dir=Path("/nonexistent"))
    rows = list(
        conn.fetch_from_payload(
            station=_cuncumen(), parameter="pm10", payload=payload
        )
    )
    assert len(rows) == 8
    assert rows[0]["pm10_ugm3"] == 112.4


def test_connector_fetch_returns_empty_when_cache_miss(tmp_path: Path) -> None:
    conn = SincaConnector(cache_dir=tmp_path)
    out = list(
        conn.fetch(
            window_from=datetime(2026, 4, 30, 0, 0),
            window_to=datetime(2026, 5, 2, 0, 0),
            station=_cuncumen(),
            parameter="pm10",
        )
    )
    assert out == []
