"""Per-station threshold override tests for build_compliance_report (Phase L.6)."""

from __future__ import annotations

from datetime import datetime

from app.domain.reports import _bucket_readings, build_compliance_report
from app.storage.models import SensorReading


def _readings(sensor_id: str, values: list[float]) -> list[SensorReading]:
    return [
        SensorReading(
            sensor_id=sensor_id,
            timestamp=datetime(2026, 5, 1, 10, i),
            raw_value={"pm10_ugm3": v, "pm25_ugm3": v / 4.0},
        )
        for i, v in enumerate(values)
    ]


def test_override_lowers_threshold_for_one_station_only() -> None:
    # Site default: pm10 breach=150
    # Override at "EM05-CUNCUMEN": pm10 breach=100 (RCA-mandated stricter
    # community receptor).
    readings = _readings("EM05-CUNCUMEN", [80, 110, 140]) + _readings(
        "FENCE-01", [80, 110, 140]
    )
    rep = build_compliance_report(
        sensor_ids=["EM05-CUNCUMEN", "FENCE-01"],
        readings_by_sensor=_bucket_readings(readings),
        pm10_thresholds={"warning": 100.0, "breach": 150.0},
        pm25_thresholds={"warning": 25.0, "breach": 35.0},
        dust_events=[],
        generated_at=datetime(2026, 5, 1, 11, 0),
        window_from=datetime(2026, 5, 1, 9, 0),
        window_to=datetime(2026, 5, 1, 11, 0),
        station_overrides={
            "EM05-CUNCUMEN": {"pm10_breach_ugm3": 100.0, "pm10_warning_ugm3": 80.0},
        },
    )
    cuncumen = next(s for s in rep.stations if s.sensor_id == "EM05-CUNCUMEN")
    fence = next(s for s in rep.stations if s.sensor_id == "FENCE-01")

    # Cuncumén uses stricter threshold: 110 + 140 are both >= 100 -> 2 breaches
    assert cuncumen.pm10_breach_count == 2
    assert cuncumen.pm10_breach_threshold == 100.0
    # Fence uses site default: only readings >= 150 count -> 0 breaches
    assert fence.pm10_breach_count == 0
    assert fence.pm10_breach_threshold == 150.0


def test_override_falls_back_when_value_is_none() -> None:
    """An override row that's missing a particular threshold reverts to site default."""
    readings = _readings("EM05-CUNCUMEN", [80, 140, 160])
    rep = build_compliance_report(
        sensor_ids=["EM05-CUNCUMEN"],
        readings_by_sensor=_bucket_readings(readings),
        pm10_thresholds={"warning": 100.0, "breach": 150.0},
        pm25_thresholds={"warning": 25.0, "breach": 35.0},
        dust_events=[],
        generated_at=datetime(2026, 5, 1, 11, 0),
        window_from=datetime(2026, 5, 1, 9, 0),
        window_to=datetime(2026, 5, 1, 11, 0),
        station_overrides={
            # Only PM2.5 breach overridden; PM10 should still use site 150.
            "EM05-CUNCUMEN": {
                "pm25_breach_ugm3": 25.0,
                "pm10_breach_ugm3": None,
            },
        },
    )
    e = rep.stations[0]
    assert e.pm10_breach_threshold == 150.0
    assert e.pm25_breach_threshold == 25.0
