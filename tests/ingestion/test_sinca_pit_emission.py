"""Phase M.2: SINCA col-2 / col-3 PIT emission tests."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.ingestion.public.sinca import (
    SINCA_VALIDATION_DELAY,
    expand_to_pit_records,
    parse_sinca_csv,
)


def test_emit_all_versions_returns_two_rows_when_both_set() -> None:
    csv_body = (
        "FECHA (YYMMDD);HORA (HHMM);;;;\n"
        "260101;0100;42;38;;\n"  # both col-2 (42) and col-3 (38) set
    )
    rows = parse_sinca_csv(
        csv_body, station_code="424", parameter="pm10", emit_all_versions=True
    )
    assert len(rows) == 2
    values = sorted(r["value_ugm3"] for r in rows)
    assert values == [38.0, 42.0]
    validated_flags = sorted(r["validated"] for r in rows)
    assert validated_flags == [False, True]


def test_emit_all_versions_returns_one_row_when_only_one_set() -> None:
    csv_body = (
        "FECHA (YYMMDD);HORA (HHMM);;;;\n"
        "260101;0100;;38;;\n"  # only col-3
    )
    rows = parse_sinca_csv(
        csv_body, station_code="424", parameter="pm10", emit_all_versions=True
    )
    assert len(rows) == 1
    assert rows[0]["validated"] is True
    assert rows[0]["value_ugm3"] == 38.0


def test_legacy_single_pick_unchanged() -> None:
    """The default (emit_all_versions=False) preserves K-phase behavior."""
    csv_body = (
        "FECHA (YYMMDD);HORA (HHMM);;;;\n"
        "260101;0100;42;38;;\n"
    )
    rows = parse_sinca_csv(
        csv_body, station_code="424", parameter="pm10"
    )
    assert len(rows) == 1
    # Priority col-3 → col-2; col-3=38 wins.
    assert rows[0]["validated"] is True
    assert rows[0]["value_ugm3"] == 38.0


def test_expand_validated_record_has_no_valid_to() -> None:
    parsed = [
        {
            "station_code": "424",
            "timestamp": datetime(2026, 1, 1, 12, 0),
            "parameter": "pm10",
            "value_ugm3": 42.0,
            "validated": True,
        }
    ]
    pit = expand_to_pit_records(parsed)
    assert len(pit) == 1
    rec = pit[0]
    assert rec["valid_from"] == datetime(2026, 1, 1, 12, 0) + SINCA_VALIDATION_DELAY
    assert rec["valid_to"] is None


def test_expand_pre_validated_has_seven_day_validity() -> None:
    parsed = [
        {
            "station_code": "424",
            "timestamp": datetime(2026, 1, 1, 12, 0),
            "parameter": "pm10",
            "value_ugm3": 42.0,
            "validated": False,
        }
    ]
    pit = expand_to_pit_records(parsed)
    assert pit[0]["valid_from"] == datetime(2026, 1, 1, 12, 0)
    assert pit[0]["valid_to"] == datetime(2026, 1, 1, 12, 0) + SINCA_VALIDATION_DELAY


def test_expand_two_versions_yield_two_pit_rows() -> None:
    parsed = [
        {
            "station_code": "424",
            "timestamp": datetime(2026, 1, 1, 12, 0),
            "parameter": "pm10",
            "value_ugm3": 42.0,
            "validated": False,
        },
        {
            "station_code": "424",
            "timestamp": datetime(2026, 1, 1, 12, 0),
            "parameter": "pm10",
            "value_ugm3": 38.0,
            "validated": True,
        },
    ]
    pit = expand_to_pit_records(parsed)
    assert len(pit) == 2
    pre, val = pit
    # Pre-validated covers [hour, hour+7d).
    assert pre["valid_from"] == datetime(2026, 1, 1, 12, 0)
    assert pre["valid_to"] == datetime(2026, 1, 1, 12, 0) + timedelta(days=7)
    # Validated covers [hour+7d, ∞).
    assert val["valid_from"] == datetime(2026, 1, 1, 12, 0) + timedelta(days=7)
    assert val["valid_to"] is None


def test_custom_validation_delay() -> None:
    parsed = [
        {
            "station_code": "424",
            "timestamp": datetime(2026, 1, 1, 12, 0),
            "parameter": "pm10",
            "value_ugm3": 42.0,
            "validated": True,
        }
    ]
    pit = expand_to_pit_records(parsed, validation_delay=timedelta(days=14))
    assert pit[0]["valid_from"] == datetime(2026, 1, 15, 12, 0)
