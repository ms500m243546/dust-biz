"""Model-performance aggregation tests (Phase K + M.4.1 calibration gate)."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.domain.evaluation_protocol import (
    REQUIRED_BASELINES,
    EvaluationProtocol,
    ProtocolViolation,
)
from app.domain.model_performance import (
    CALIBRATION_BIN_COUNT,
    compute_metric_payload,
)
from app.schemas.model_performance import TrainingRecordSchema


def _good_protocol(**overrides: object) -> EvaluationProtocol:
    """Minimal valid protocol for unit tests of compute_metric_payload.

    Defaults `max_ece=1.0` so legacy tests that weren't built around
    calibrated probabilities don't trip the M.4.1 acceptance gate.
    Calibration-specific tests override `max_ece` and provide an
    `ece_override_reason` (or honest probabilities).
    """
    base: dict[str, object] = dict(
        split_strategy="walk_forward",
        train_window_from=datetime(2025, 1, 1),
        train_window_to=datetime(2025, 6, 1),
        validation_window_from=datetime(2025, 6, 8),
        validation_window_to=datetime(2025, 9, 1),
        test_window_from=datetime(2025, 9, 8),
        test_window_to=datetime(2026, 3, 1),
        baselines_named=REQUIRED_BASELINES,
        max_ece=1.0,  # disable gate for legacy fixtures
    )
    base.update(overrides)
    return EvaluationProtocol(**base)  # type: ignore[arg-type]


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
    payload = compute_metric_payload(records, protocol=_good_protocol())
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
    payload = compute_metric_payload(records, protocol=_good_protocol())
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
    payload = compute_metric_payload(records, protocol=_good_protocol())
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
    payload = compute_metric_payload(records, protocol=_good_protocol())
    assert payload["mae_pm10"] == (10 + 5) / 2
    # |0.6 - 1| + |0.4 - 0| = 0.4 + 0.4 -> mean 0.4
    assert payload["calibration_error"] == 0.4
    assert payload["unobserved_count"] == 1
    assert payload["production_loss_tonnes_total"] == 400.0


def test_empty_input() -> None:
    payload = compute_metric_payload([], protocol=_good_protocol())
    assert payload["sample_count"] == 0
    assert payload["mae_pm10"] is None
    assert payload["protocol"]["protocol_version"] == "M.4"


# ---------------------------------------------------------------------------
# M.4.1 — calibration acceptance gate (anti-overfit rule 8).
# ---------------------------------------------------------------------------


def test_calibration_bins_emitted_with_stable_shape() -> None:
    records = [
        _record(breach_prob=0.95, breach_actual=True),
        _record(breach_prob=0.05, breach_actual=False),
    ]
    payload = compute_metric_payload(records, protocol=_good_protocol())
    bins = payload["calibration_bins"]
    assert isinstance(bins, list)
    # Always 10 bins, even when most are empty — wire shape is stable.
    assert len(bins) == CALIBRATION_BIN_COUNT
    # Bin 0 (0.0-0.1) holds prob=0.05; bin 9 (0.9-1.0) holds prob=0.95.
    assert bins[0]["count"] == 1
    assert bins[9]["count"] == 1
    assert sum(b["count"] for b in bins) == 2


def test_perfectly_calibrated_yields_zero_ece() -> None:
    # All predictions match outcomes exactly at the bin centre.
    records = [
        _record(breach_prob=1.0, breach_actual=True, actual_pm10=130),
        _record(breach_prob=0.0, breach_actual=False, actual_pm10=70),
    ]
    payload = compute_metric_payload(records, protocol=_good_protocol())
    assert payload["ece"] == pytest.approx(0.0)
    assert payload["brier_score"] == pytest.approx(0.0)


def test_uncalibrated_blocks_evaluation_without_override() -> None:
    """An over-confident model with no override reason raises 422."""
    # Predict 0.9 every time, but breach only half the time → ECE = 0.4.
    records = [
        _record(breach_prob=0.9, breach_actual=True, actual_pm10=130),
        _record(breach_prob=0.9, breach_actual=False, actual_pm10=80),
    ]
    strict = _good_protocol(max_ece=0.05)
    with pytest.raises(ProtocolViolation, match="calibration acceptance gate"):
        compute_metric_payload(records, protocol=strict)


def test_uncalibrated_with_override_reason_persists_warning() -> None:
    records = [
        _record(breach_prob=0.9, breach_actual=True),
        _record(breach_prob=0.9, breach_actual=False),
    ]
    overridden = _good_protocol(
        max_ece=0.05,
        ece_override_reason="diagnostic run only — not promoted",
    )
    payload = compute_metric_payload(records, protocol=overridden)
    assert any(
        "calibration acceptance gate overridden" in w
        for w in payload["protocol"]["warnings"]
    )


def test_brier_score_squared_error_arithmetic() -> None:
    # Two records: pred 0.8 vs actual 1 (err 0.04), pred 0.3 vs actual 0 (err 0.09).
    records = [
        _record(breach_prob=0.8, breach_actual=True),
        _record(breach_prob=0.3, breach_actual=False),
    ]
    payload = compute_metric_payload(records, protocol=_good_protocol())
    assert payload["brier_score"] == pytest.approx((0.04 + 0.09) / 2)
