"""Model-performance aggregation tests (Phase K)."""

from __future__ import annotations

from datetime import datetime

from app.domain.model_performance import compute_metric_payload
from app.schemas.model_performance import TrainingRecordSchema


def _record(
    *,
    breach_prob: float,
    breach_actual: bool | None,
    predicted_pm10: float = 120.0,
    actual_pm10: float | None = 110.0,
    human_action: str = "approved",
    outcome_status: str = "observed",
    production_loss: float | None = 200.0,
) -> TrainingRecordSchema:
    return TrainingRecordSchema(
        prediction_id="PRED-X",
        issued_at=datetime(2026, 5, 1, 10, 0),
        target_kind="zone",
        target_id="Z-1",
        forecast_horizon="30m",
        predicted_pm10=predicted_pm10,
        predicted_pm25=42.0,
        predicted_breach_probability=breach_prob,
        confidence=0.6,
        model_version="df-0.1.0",
        human_action=human_action,  # type: ignore[arg-type]
        actual_pm10_peak=actual_pm10,
        breach_occurred=breach_actual,
        intervention_effectiveness="successful" if breach_actual is False else "partial",
        production_loss_tonnes_actual=production_loss,
        outcome_status=outcome_status,  # type: ignore[arg-type]
    )


def test_all_unobserved_returns_nulls() -> None:
    records = [
        _record(breach_prob=0.6, breach_actual=None, outcome_status="unobserved")
    ]
    payload = compute_metric_payload(records)
    assert payload["sample_count"] == 1
    assert payload["observed_count"] == 0
    assert payload["unobserved_count"] == 1
    assert payload["mae_pm10"] is None
    assert payload["breach_precision"] is None
    assert payload["avoided_shutdowns_estimate"] == 0


def test_perfect_predictions_yield_high_precision() -> None:
    # Two correctly-flagged breaches, two correctly-flagged non-breaches.
    records = [
        _record(breach_prob=0.9, breach_actual=True, actual_pm10=125),
        _record(breach_prob=0.85, breach_actual=True, actual_pm10=130),
        _record(breach_prob=0.2, breach_actual=False, actual_pm10=80),
        _record(breach_prob=0.1, breach_actual=False, actual_pm10=70),
    ]
    payload = compute_metric_payload(records)
    assert payload["breach_precision"] == 1.0
    assert payload["breach_recall"] == 1.0
    assert payload["false_positive_rate"] == 0.0
    assert payload["false_negative_rate"] == 0.0
    assert payload["avoided_shutdowns_estimate"] == 0  # no FPs


def test_avoided_shutdown_only_counts_approved_false_positives() -> None:
    records = [
        # FP + approved -> counts as avoided
        _record(
            breach_prob=0.8,
            breach_actual=False,
            human_action="approved",
        ),
        # FP + rejected -> does not count
        _record(
            breach_prob=0.8,
            breach_actual=False,
            human_action="rejected",
        ),
        # FP + overridden -> counts
        _record(
            breach_prob=0.8,
            breach_actual=False,
            human_action="overridden",
        ),
    ]
    payload = compute_metric_payload(records)
    assert payload["avoided_shutdowns_estimate"] == 2


def test_mae_and_calibration_computed_only_over_observed() -> None:
    records = [
        _record(
            breach_prob=0.6,
            breach_actual=True,
            predicted_pm10=120.0,
            actual_pm10=110.0,
        ),
        _record(
            breach_prob=0.4,
            breach_actual=False,
            predicted_pm10=80.0,
            actual_pm10=85.0,
        ),
        _record(
            breach_prob=0.7,
            breach_actual=None,
            actual_pm10=None,
            outcome_status="unobserved",
        ),
    ]
    payload = compute_metric_payload(records)
    assert payload["mae_pm10"] == (10 + 5) / 2
    # |0.6 - 1| + |0.4 - 0| = 0.4 + 0.4 -> mean 0.4
    assert payload["calibration_error"] == 0.4
    assert payload["unobserved_count"] == 1
    assert payload["production_loss_tonnes_total"] == 400.0


def test_empty_input() -> None:
    payload = compute_metric_payload([])
    assert payload["sample_count"] == 0
    assert payload["mae_pm10"] is None
