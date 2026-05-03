"""Phase P.3 — promotion-decision tests.

Pure-function tests over `decide_promotion`. The registry-level
auto-promote is exercised by the API smoke + the GBM in-memory
training tests; this file focuses on the criterion logic.
"""

from __future__ import annotations

from app.training.dust_forecast_training import (
    PROMOTION_MAX_MAE_PM10,
    PROMOTION_MIN_TEST_SAMPLES,
    decide_promotion,
)


def _payload(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "ece": 0.01,
        "mae_pm10": 9.5,
        "observed_count": 500,
        "protocol": {"max_ece": 0.05},
    }
    base.update(over)
    return base


def test_promotion_passes_with_clean_metrics() -> None:
    decision = decide_promotion(_payload())
    assert decision.passed
    assert decision.reasons == ()


def test_promotion_blocks_when_ece_above_gate() -> None:
    decision = decide_promotion(_payload(ece=0.07))
    assert not decision.passed
    assert any("ece=" in r for r in decision.reasons)


def test_promotion_blocks_when_mae_above_threshold() -> None:
    decision = decide_promotion(_payload(mae_pm10=PROMOTION_MAX_MAE_PM10 + 1))
    assert not decision.passed
    assert any("mae_pm10=" in r for r in decision.reasons)


def test_promotion_blocks_when_thin_test_sample() -> None:
    decision = decide_promotion(
        _payload(observed_count=PROMOTION_MIN_TEST_SAMPLES - 1)
    )
    assert not decision.passed
    assert any("observed_count" in r for r in decision.reasons)


def test_promotion_passes_when_breach_recall_none_due_to_class_imbalance() -> None:
    # breach_recall is None when no positive class exists in the test
    # window (rare-event case). decide_promotion should NOT block.
    decision = decide_promotion(_payload(breach_recall=None))
    assert decision.passed


def test_promotion_blocks_when_mae_missing() -> None:
    decision = decide_promotion(_payload(mae_pm10=None))
    assert not decision.passed
    assert any("mae_pm10 missing" in r for r in decision.reasons)


def test_promotion_uses_protocol_max_ece_not_default() -> None:
    # If protocol carries a stricter max_ece, the comparison uses it.
    decision = decide_promotion(
        _payload(ece=0.04, protocol={"max_ece": 0.03})
    )
    assert not decision.passed
    assert any("ece=" in r and "max_ece=0.0300" in r for r in decision.reasons)
