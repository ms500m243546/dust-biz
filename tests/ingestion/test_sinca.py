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
        station_code="424",
        station_name="Cuncumén",
        region="Coquimbo",
        commune="Salamanca",
        longitude=-70.701,
        latitude=-31.971,
        tier="EMRPM",
        parameters=("pm10", "pm25"),
    )


def test_parse_yields_full_week_of_hourly_records() -> None:
    payload = (FIXTURES / "sinca_cuncumen_pm10.csv").read_text(encoding="utf-8")
    rows = parse_sinca_csv(payload, station_code="424", parameter="pm10")
    # Captured window: 2026-04-25 01:00 → 2026-05-02 00:00, 168 hours
    # nominal. Cuncumén had a real sensor outage 2026-04-29 17:00 →
    # 2026-04-30 00:00 (8 consecutive empty hours), so the parser
    # retains 160 rows.
    assert len(rows) == 160
    assert all(isinstance(r["value_ugm3"], float) for r in rows)


def test_parse_drops_all_empty_outage_rows() -> None:
    payload = (FIXTURES / "sinca_cuncumen_pm10.csv").read_text(encoding="utf-8")
    rows = parse_sinca_csv(payload, station_code="424", parameter="pm10")
    timestamps = {r["timestamp"] for r in rows}
    # The 8-hour outage window must NOT appear.
    for h in range(17, 24):
        assert datetime(2026, 4, 29, h, 0) not in timestamps
    assert datetime(2026, 4, 30, 0, 0) not in timestamps
    # Boundary hours immediately around the outage must be present.
    assert datetime(2026, 4, 29, 16, 0) in timestamps
    assert datetime(2026, 4, 30, 1, 0) in timestamps


def test_parse_first_and_last_rows_match_captured_data() -> None:
    payload = (FIXTURES / "sinca_cuncumen_pm10.csv").read_text(encoding="utf-8")
    rows = parse_sinca_csv(payload, station_code="424", parameter="pm10")
    first = rows[0]
    assert first["timestamp"] == datetime(2026, 4, 25, 1, 0)
    assert first["value_ugm3"] == 24.0
    last = rows[-1]
    assert last["timestamp"] == datetime(2026, 5, 2, 0, 0)
    assert last["value_ugm3"] == 15.0


def test_parse_uses_col2_prevalidated_when_col3_empty() -> None:
    """SINCA's QA pipeline parks recent (~1 year) values at col 2
    until they're promoted to col 3. Verified empirically against
    Cuncumén's 2025-05-01 → 2026-05-01 export. The parser must read
    col 2 when col 3 is empty, and mark the row as not-validated.
    """
    payload = (
        "FECHA (YYMMDD);HORA (HHMM);\n"
        "250501;0100;16;;;\n"      # col 2 only -> pre-validated
        "260425;0100;;24;;\n"      # col 3 only -> validated
        "260425;0400;;;0;\n"       # col 4 only -> raw fallback
        "260429;1700;;;;\n"        # all empty -> outage, dropped
    )
    rows = parse_sinca_csv(payload, station_code="424", parameter="pm10")
    assert len(rows) == 3
    by_ts = {r["timestamp"]: r for r in rows}
    assert by_ts[datetime(2025, 5, 1, 1, 0)]["value_ugm3"] == 16.0
    assert by_ts[datetime(2025, 5, 1, 1, 0)]["validated"] is False
    assert by_ts[datetime(2026, 4, 25, 1, 0)]["value_ugm3"] == 24.0
    assert by_ts[datetime(2026, 4, 25, 1, 0)]["validated"] is True
    assert by_ts[datetime(2026, 4, 25, 4, 0)]["value_ugm3"] == 0.0
    assert by_ts[datetime(2026, 4, 25, 4, 0)]["validated"] is False


def test_parse_falls_back_to_raw_when_validated_column_empty() -> None:
    # Two rows in the captured week (260425 04:00 and 260427 03:00)
    # have col 3 empty and col 4 = 0 — i.e., raw fallback path.
    payload = (FIXTURES / "sinca_cuncumen_pm10.csv").read_text(encoding="utf-8")
    rows = parse_sinca_csv(payload, station_code="424", parameter="pm10")
    fallback_rows = [r for r in rows if not r["validated"]]
    assert len(fallback_rows) == 2
    assert {r["timestamp"] for r in fallback_rows} == {
        datetime(2026, 4, 25, 4, 0),
        datetime(2026, 4, 27, 3, 0),
    }
    assert all(r["value_ugm3"] == 0.0 for r in fallback_rows)


def test_to_raw_sensor_payload_uses_pm10_ugm3_key() -> None:
    payload = (FIXTURES / "sinca_cuncumen_pm10.csv").read_text(encoding="utf-8")
    rec = parse_sinca_csv(payload, station_code="424", parameter="pm10")[0]
    raw = to_raw_sensor_payload(rec, station=_cuncumen())
    assert raw["source"] == SOURCE_NAME
    assert raw["station_code"] == "424"
    assert raw["pm10_ugm3"] == 24.0
    assert raw["region"] == "Coquimbo"


def test_quality_hint_tiers() -> None:
    assert quality_hint_for_tier("EMRPM") == 0.9
    assert quality_hint_for_tier("indicative") == 0.7
    assert quality_hint_for_tier("unknown-tier") == 0.5


def test_build_url_matches_verified_sinca_macro_pattern() -> None:
    # Verified live against Cuncumén station 424 on 2026-05-02.
    url = build_url(
        station_code="424",
        parameter="pm10",
        window_from=datetime(2026, 4, 25, 0, 0),
        window_to=datetime(2026, 5, 1, 0, 0),
        region_path="RIV",
    )
    assert "tsindico2.cgi" in url
    assert "outtype=xcl" in url
    # Macro path is URL-encoded; check decoded form for clarity.
    from urllib.parse import unquote
    assert "./RIV/424/Cal/PM10/PM10.horario.horario.ic" in unquote(url)
    # Date format is YYMMDDHH — from anchored 00, to anchored 23.
    assert "from=26042500" in url
    assert "to=26050123" in url


def test_build_url_default_region_is_rm() -> None:
    url = build_url(
        station_code="D14",
        parameter="pm25",
        window_from=datetime(2026, 5, 1, 0, 0),
        window_to=datetime(2026, 5, 2, 0, 0),
    )
    from urllib.parse import unquote
    decoded = unquote(url)
    assert "/RM/D14/Cal/PM2.5/PM2.5.horario.horario.ic" in decoded


def test_build_url_supports_daily_resolution() -> None:
    url = build_url(
        station_code="424",
        parameter="pm10",
        window_from=datetime(2026, 4, 25, 0, 0),
        window_to=datetime(2026, 5, 1, 0, 0),
        region_path="RIV",
        resolution="diario",
    )
    from urllib.parse import unquote
    assert "PM10.diario.diario.ic" in unquote(url)


def test_connector_fetch_from_payload_yields_typed_records() -> None:
    payload = (FIXTURES / "sinca_cuncumen_pm10.csv").read_text(encoding="utf-8")
    conn = SincaConnector(cache_dir=Path("/nonexistent"))
    rows = list(
        conn.fetch_from_payload(
            station=_cuncumen(), parameter="pm10", payload=payload
        )
    )
    assert len(rows) == 160
    assert rows[0]["pm10_ugm3"] == 24.0


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
