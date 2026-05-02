"""Model performance aggregation (Phase K, S14).

Reduces a list of `TrainingRecordSchema` rows into the
`metric_payload` JSON blob persisted on `model_performance_metrics`
per docs/data-contracts.md lines 241-248.

Heuristics-first per CLAUDE.md rule 13. The metric set is the minimum
needed to drive the reports in S15 + the shadow-mode evaluation
harness:

- `mae_pm10` — mean absolute error on observed PM10 peaks
- `breach_precision`, `breach_recall` — at the operational
  `breach_probability >= 0.5` decision threshold
- `false_positive_rate`, `false_negative_rate`
- `calibration_error` — mean abs(predicted breach probability minus
  realised breach indicator); flat-bin proxy for Brier reliability
- `avoided_shutdowns_estimate` — count of records where the model
  predicted breach, the operator approved an action, and the breach
  did not occur. Lower bound, not causal — kept conservative.
- `production_loss_tonnes_total` — sum of recorded production loss

Records with `outcome_status="unobserved"` are excluded from
accuracy metrics but counted under `unobserved_count` so callers
can see coverage.
"""

from __future__ import annotations

from typing import Any

from app.schemas.model_performance import TrainingRecordSchema

BREACH_DECISION_THRESHOLD = 0.5


def _safe_div(num: float, den: float) -> float | None:
    return None if den == 0 else num / den


def compute_metric_payload(
    records: list[TrainingRecordSchema],
) -> dict[str, Any]:
    observed = [r for r in records if r.outcome_status == "observed"]
    unobserved_count = len(records) - len(observed)

    if not observed:
        return {
            "sample_count": len(records),
            "observed_count": 0,
            "unobserved_count": unobserved_count,
            "mae_pm10": None,
            "breach_precision": None,
            "breach_recall": None,
            "false_positive_rate": None,
            "false_negative_rate": None,
            "calibration_error": None,
            "avoided_shutdowns_estimate": 0,
            "production_loss_tonnes_total": 0.0,
        }

    abs_errors_pm10: list[float] = []
    cal_terms: list[float] = []
    tp = fp = tn = fn = 0
    avoided = 0
    production_loss_total = 0.0

    for r in observed:
        if r.actual_pm10_peak is not None:
            abs_errors_pm10.append(abs(r.predicted_pm10 - r.actual_pm10_peak))
        breach_actual = bool(r.breach_occurred)
        breach_predicted = r.predicted_breach_probability >= BREACH_DECISION_THRESHOLD
        cal_terms.append(
            abs(r.predicted_breach_probability - (1.0 if breach_actual else 0.0))
        )
        if breach_predicted and breach_actual:
            tp += 1
        elif breach_predicted and not breach_actual:
            fp += 1
            if r.human_action in {"approved", "overridden"}:
                avoided += 1
        elif not breach_predicted and breach_actual:
            fn += 1
        else:
            tn += 1
        if r.production_loss_tonnes_actual is not None:
            production_loss_total += r.production_loss_tonnes_actual

    return {
        "sample_count": len(records),
        "observed_count": len(observed),
        "unobserved_count": unobserved_count,
        "mae_pm10": (
            sum(abs_errors_pm10) / len(abs_errors_pm10)
            if abs_errors_pm10
            else None
        ),
        "breach_precision": _safe_div(tp, tp + fp),
        "breach_recall": _safe_div(tp, tp + fn),
        "false_positive_rate": _safe_div(fp, fp + tn),
        "false_negative_rate": _safe_div(fn, fn + tp),
        "calibration_error": (
            sum(cal_terms) / len(cal_terms) if cal_terms else None
        ),
        "avoided_shutdowns_estimate": avoided,
        "production_loss_tonnes_total": production_loss_total,
    }


__all__ = ["BREACH_DECISION_THRESHOLD", "compute_metric_payload"]
