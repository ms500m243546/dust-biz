"""Schema-level guardrail tests.

These mirror what `scripts/checks/validate-safety.js` enforces
structurally (G2/G15) plus the field-level constraints the scanner
cannot see (ranges, source enum, defaults).
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.forecasts import DustForecastSchema, ForecastTargetSchema


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "issued_at": datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        "target_kind": "zone",
        "target_id": "haul_c",
        "forecast_horizon": "60min",
        "predicted_pm10": 142.0,
        "predicted_pm25": 48.0,
        "breach_probability": 0.74,
        "confidence": 0.82,
        "main_risk_window": "12:00-13:00",
        "main_uncertainty": "wind variability",
        "model_version": "dust_forecast_heuristic_v0.1.0",
        "feature_pipeline_version": "feature_pipeline_v0.1.0",
        "input_data_quality_score": 0.9,
    }
    base.update(overrides)
    return base


def test_minimal_round_trip_includes_all_guardrail_fields() -> None:
    f = DustForecastSchema(**_payload())  # type: ignore[arg-type]
    # G2
    assert hasattr(f, "confidence")
    # G15
    assert hasattr(f, "model_version")
    assert hasattr(f, "feature_pipeline_version")
    assert hasattr(f, "input_data_quality_score")
    # G5
    assert hasattr(f, "data_quality_warnings")
    assert f.data_quality_warnings == []
    # G11
    assert f.source == "model"
    # Audit (data-contracts.md line 147)
    assert f.input_record_ids == []


def test_breach_probability_must_be_in_unit_interval() -> None:
    with pytest.raises(ValidationError):
        DustForecastSchema(**_payload(breach_probability=1.4))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        DustForecastSchema(**_payload(breach_probability=-0.1))  # type: ignore[arg-type]


def test_confidence_must_be_in_unit_interval() -> None:
    with pytest.raises(ValidationError):
        DustForecastSchema(**_payload(confidence=1.5))  # type: ignore[arg-type]


def test_source_enum_accepts_only_documented_values() -> None:
    DustForecastSchema(**_payload(source="model"))  # type: ignore[arg-type]
    DustForecastSchema(**_payload(source="heuristic_fallback"))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        DustForecastSchema(**_payload(source="oracle"))  # type: ignore[arg-type]


def test_horizon_enum_matches_data_contract() -> None:
    for h in ("15min", "30min", "60min", "120min", "24h"):
        DustForecastSchema(**_payload(forecast_horizon=h))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        DustForecastSchema(**_payload(forecast_horizon="90min"))  # type: ignore[arg-type]


def test_target_schema_round_trip() -> None:
    t = ForecastTargetSchema(target_kind="sensor", target_id="cs1")
    assert t.target_kind == "sensor"
    assert t.target_id == "cs1"
