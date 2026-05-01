from datetime import UTC, datetime

import pytest

from app.models.forecasting.heuristic_baseline import (
    HEURISTIC_VERSION,
    HeuristicBaselineForecaster,
)
from app.schemas.features import FeatureRecordSchema
from app.schemas.forecasts import ForecastTargetSchema

NOW = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def _features(payload: dict[str, object], missing: list[str] | None = None) -> FeatureRecordSchema:
    return FeatureRecordSchema(
        timestamp=NOW,
        zone_id="haul_c",
        feature_pipeline_version="feature_pipeline_v0.1.0",
        feature_payload=payload,
        missing_inputs=missing or [],
    )


def _target() -> ForecastTargetSchema:
    return ForecastTargetSchema(target_kind="zone", target_id="haul_c")


def _stable_payload() -> dict[str, object]:
    return {
        "pm.pm10_avg_15min": 60.0,
        "pm.pm25_avg_15min": 25.0,
        "pm.pm10_trend_per_min": 0.2,
        "pm.pm25_trend_per_min": 0.1,
        "wind.speed_ms": 4.0,
        "wind.humidity_pct": 50.0,
        "state.wind_exposure": "medium",
        "state.dust_generation_potential": "medium",
    }


def test_predict_returns_forecast_with_required_safety_fields() -> None:
    model = HeuristicBaselineForecaster()
    out = model.predict(
        features=_features(_stable_payload()),
        target=_target(),
        horizon="60min",
        now=NOW,
    )
    # Guardrail fields
    assert out.confidence > 0.0
    assert out.model_version == HEURISTIC_VERSION
    assert out.feature_pipeline_version == "feature_pipeline_v0.1.0"
    assert out.source == "model"
    # Output shape
    assert out.forecast_horizon == "60min"
    assert out.target_id == "haul_c"
    assert 0.0 <= out.breach_probability <= 1.0
    assert out.predicted_pm10 > 0


def test_predict_is_deterministic_for_fixed_inputs() -> None:
    model = HeuristicBaselineForecaster()
    a = model.predict(features=_features(_stable_payload()), target=_target(), horizon="30min", now=NOW)
    b = model.predict(features=_features(_stable_payload()), target=_target(), horizon="30min", now=NOW)
    assert a.predicted_pm10 == b.predicted_pm10
    assert a.predicted_pm25 == b.predicted_pm25
    assert a.breach_probability == b.breach_probability
    assert a.confidence == b.confidence


def test_quality_multiplier_scales_confidence(monkeypatch: pytest.MonkeyPatch) -> None:
    model = HeuristicBaselineForecaster()
    full = model.predict(
        features=_features(_stable_payload()),
        target=_target(),
        horizon="30min",
        input_data_quality_score=1.0,
        now=NOW,
    )
    half = model.predict(
        features=_features(_stable_payload()),
        target=_target(),
        horizon="30min",
        input_data_quality_score=0.5,
        now=NOW,
    )
    # Guardrail 4: confidence cannot exceed raw * multiplier
    assert half.confidence <= full.confidence * 0.5 + 1e-6


def test_high_pm_with_dry_windy_conditions_raises_breach_probability() -> None:
    model = HeuristicBaselineForecaster()
    elevated = _stable_payload()
    elevated.update(
        {
            "pm.pm10_avg_15min": 130.0,
            "pm.pm10_trend_per_min": 1.5,
            "wind.speed_ms": 8.5,
            "wind.humidity_pct": 18.0,
            "state.wind_exposure": "high",
            "state.dust_generation_potential": "high",
        }
    )
    out = model.predict(features=_features(elevated), target=_target(), horizon="60min", now=NOW)
    baseline = model.predict(
        features=_features(_stable_payload()), target=_target(), horizon="60min", now=NOW
    )
    assert out.breach_probability > baseline.breach_probability
    assert out.predicted_pm10 > baseline.predicted_pm10


def test_missing_pm_features_trigger_heuristic_fallback() -> None:
    model = HeuristicBaselineForecaster()
    out = model.predict(
        features=_features(
            payload={"wind.speed_ms": 4.0},
            missing=["pm10_readings_missing", "pm25_readings_missing"],
        ),
        target=_target(),
        horizon="30min",
        now=NOW,
    )
    assert out.source == "heuristic_fallback"
    assert out.confidence < 0.3
    assert "fallback" in out.main_uncertainty.lower()


def test_horizons_emit_distinct_risk_windows() -> None:
    model = HeuristicBaselineForecaster()
    a = model.predict(features=_features(_stable_payload()), target=_target(), horizon="15min", now=NOW)
    b = model.predict(features=_features(_stable_payload()), target=_target(), horizon="60min", now=NOW)
    assert a.main_risk_window != b.main_risk_window


def test_input_record_ids_are_passed_through_for_audit() -> None:
    model = HeuristicBaselineForecaster()
    out = model.predict(
        features=_features(_stable_payload()),
        target=_target(),
        horizon="30min",
        input_record_ids=["sr-1", "sr-2", "wr-1"],
        now=NOW,
    )
    assert out.input_record_ids == ["sr-1", "sr-2", "wr-1"]
