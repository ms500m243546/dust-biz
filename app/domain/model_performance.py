"""Model performance aggregation (Phase K, S14; M.1 protocol gate).

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

M.1 — `compute_metric_payload(records, *, protocol)` requires an
`EvaluationProtocol`. The protocol's pre-registered hash, split
strategy, baselines, and warnings are persisted on the metric row
under the `protocol` namespace so audit and the agent-check gate can
verify obedience after the fact. Calls that violate the protocol
raise `ProtocolViolation` and persist nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.domain.evaluation_protocol import (
    EvaluationProtocol,
    ProtocolViolation,
    protocol_to_payload_keys,
    validate_protocol_obeyed,
)
from app.schemas.model_performance import TrainingRecordSchema

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

BREACH_DECISION_THRESHOLD = 0.5

# M.4.1 — reliability-table bin count. 10 equal-width bins is standard
# for ECE / reliability-diagram reporting (Niculescu-Mizil & Caruana
# 2005). Independent of the operational decision threshold.
CALIBRATION_BIN_COUNT = 10


def _safe_div(num: float, den: float) -> float | None:
    return None if den == 0 else num / den


# M.4.2 — Goodhart canary pairs. Each "deployable KPI" is paired with a
# counter-metric whose movement the wrong way reveals gaming. The pairs
# are encoded once here so every metric_payload carries the same shape;
# the validator scans for these key names.
GOODHART_CANARY_PAIRS: dict[str, str] = {
    # Maximizing precision by under-firing → recall craters. Pair them.
    "breach_precision": "breach_recall",
    # Minimizing FPR by under-firing → recall craters too.
    "false_positive_rate": "breach_recall",
    # Inflating "avoided shutdowns" by missing real breaches → FNR rises.
    "avoided_shutdowns_estimate": "false_negative_rate",
    # Minimizing production-loss by ignoring breaches → recall craters.
    "production_loss_tonnes_total": "breach_recall",
}


def _per_receptor_breakdown(
    observed: list[TrainingRecordSchema],
) -> dict[str, dict[str, Any]]:
    """B-32 mitigation — split metrics by `target_id` (the receptor).

    Returns a dict keyed by `target_id`. For each receptor, the same
    breach-precision / recall / FPR / FNR / mae as the aggregate, plus
    `target_kind` and the sample count. Missing data (no observed
    records for that receptor in the window) → empty dict for that key.

    Why per-receptor: Cuncumén-vs-Caimanes asymmetry. A model that
    optimizes "average" PM10 may disproportionately allow high readings
    at less-visible receptors. Splitting the metrics surfaces the gap.
    """
    by_id: dict[str, list[TrainingRecordSchema]] = {}
    for r in observed:
        by_id.setdefault(r.target_id, []).append(r)

    out: dict[str, dict[str, Any]] = {}
    for target_id, group in by_id.items():
        tp = fp = tn = fn = 0
        abs_errors: list[float] = []
        for r in group:
            breach_actual = bool(r.breach_occurred)
            breach_predicted = (
                r.predicted_breach_probability >= BREACH_DECISION_THRESHOLD
            )
            if r.actual_pm10_peak is not None:
                abs_errors.append(abs(r.predicted_pm10 - r.actual_pm10_peak))
            if breach_predicted and breach_actual:
                tp += 1
            elif breach_predicted and not breach_actual:
                fp += 1
            elif not breach_predicted and breach_actual:
                fn += 1
            else:
                tn += 1
        out[target_id] = {
            "target_kind": group[0].target_kind,
            "sample_count": len(group),
            "mae_pm10": (
                sum(abs_errors) / len(abs_errors) if abs_errors else None
            ),
            "breach_precision": _safe_div(tp, tp + fp),
            "breach_recall": _safe_div(tp, tp + fn),
            "false_positive_rate": _safe_div(fp, fp + tn),
            "false_negative_rate": _safe_div(fn, fn + tp),
        }
    return out


def _calibration_breakdown(
    pairs: list[tuple[float, bool]],
    *,
    bin_count: int = CALIBRATION_BIN_COUNT,
) -> tuple[list[dict[str, float | int]], float, float]:
    """Compute reliability bins, expected calibration error, and Brier score.

    `pairs` is a list of `(predicted_breach_probability, breach_actual)`
    over observed records only. Returns:
      - `bins`: list of one dict per bin with keys
        `lower`, `upper`, `count`, `avg_predicted`, `actual_frequency`.
        Empty bins are emitted with `count=0` and null-but-numeric
        averages (0.0) so the wire shape stays stable for the UI.
      - `ece`: weighted absolute deviation across bins.
      - `brier`: mean squared error on (probability vs realized).
    """
    if not pairs:
        return [], 0.0, 0.0

    width = 1.0 / bin_count
    buckets: list[list[tuple[float, bool]]] = [[] for _ in range(bin_count)]
    for prob, actual in pairs:
        idx = min(int(prob / width), bin_count - 1)
        buckets[idx].append((prob, actual))

    bins: list[dict[str, float | int]] = []
    total = len(pairs)
    ece_terms = 0.0
    for i, bucket in enumerate(buckets):
        lower = i * width
        upper = (i + 1) * width
        count = len(bucket)
        if count:
            avg_pred = sum(p for p, _ in bucket) / count
            actual_freq = sum(1 for _, a in bucket if a) / count
            ece_terms += (count / total) * abs(avg_pred - actual_freq)
        else:
            avg_pred = 0.0
            actual_freq = 0.0
        bins.append(
            {
                "lower": lower,
                "upper": upper,
                "count": count,
                "avg_predicted": avg_pred,
                "actual_frequency": actual_freq,
            }
        )

    brier = sum((p - (1.0 if a else 0.0)) ** 2 for p, a in pairs) / total
    return bins, ece_terms, brier


def compute_metric_payload(
    records: list[TrainingRecordSchema],
    *,
    protocol: EvaluationProtocol,
    station_count: int = 1,
    prior_metric_protocol_hashes: tuple[str, ...] = (),
    session: Session | None = None,
) -> dict[str, Any]:
    """Aggregate observed records into the metric_payload JSON blob.

    Required `protocol` (M.1+): the binding evaluation contract. If the
    protocol fails `validate_protocol_obeyed`, raises `ProtocolViolation`
    — caller persists nothing.

    M.2 `session` (optional): when provided, runs SQL-level
    anti-hindsight probes against `sensor_readings`, `weather_readings`,
    and label tables. Probe violations become hard errors. When None,
    those rules emit warnings only (useful for unit tests). The API
    route always supplies the session so the gate is fully enforced
    in production paths.
    """
    validation = validate_protocol_obeyed(
        protocol,
        station_count=station_count,
        prior_metric_protocol_hashes=prior_metric_protocol_hashes,
        session=session,
    )
    if validation.errors:
        raise ProtocolViolation(
            "evaluation rejected: " + "; ".join(validation.errors)
        )

    protocol_block: dict[str, Any] = {
        **protocol_to_payload_keys(protocol),
        "warnings": list(validation.warnings),
    }

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
            "calibration_bins": [],
            "ece": None,
            "brier_score": None,
            "avoided_shutdowns_estimate": 0,
            "production_loss_tonnes_total": 0.0,
            "per_receptor": {},
            "canary_metrics": {},
            "protocol": protocol_block,
        }

    abs_errors_pm10: list[float] = []
    cal_terms: list[float] = []
    calibration_pairs: list[tuple[float, bool]] = []
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
        calibration_pairs.append((r.predicted_breach_probability, breach_actual))
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

    calibration_bins, ece, brier = _calibration_breakdown(calibration_pairs)

    # M.4.1 — calibration acceptance gate. ECE > max_ece blocks
    # evaluation unless the protocol carries a non-empty
    # `ece_override_reason` (logged on the metric row).
    if ece > protocol.max_ece:
        if not protocol.ece_override_reason.strip():
            raise ProtocolViolation(
                f"calibration acceptance gate (anti-overfit rule 8): "
                f"ECE={ece:.4f} > max_ece={protocol.max_ece:.4f}. "
                "Either recalibrate the model (Platt / isotonic) or set "
                "`ece_override_reason` with explicit operator sign-off."
            )
        protocol_block["warnings"].append(
            f"calibration acceptance gate overridden: ECE={ece:.4f} "
            f"> max_ece={protocol.max_ece:.4f}; "
            f"reason={protocol.ece_override_reason!r}"
        )

    breach_precision = _safe_div(tp, tp + fp)
    breach_recall = _safe_div(tp, tp + fn)
    false_positive_rate = _safe_div(fp, fp + tn)
    false_negative_rate = _safe_div(fn, fn + tp)

    # M.4.2 — Goodhart canary pairs. Persisted alongside the headline
    # KPIs so any deployment threshold based on those KPIs has its
    # paired counter-metric available for review (per
    # docs/safety-guardrails.md). The numeric values are the canary
    # metric's value, not the KPI itself.
    available: dict[str, float | int | None] = {
        "breach_precision": breach_precision,
        "breach_recall": breach_recall,
        "false_positive_rate": false_positive_rate,
        "false_negative_rate": false_negative_rate,
        "avoided_shutdowns_estimate": avoided,
        "production_loss_tonnes_total": production_loss_total,
    }
    canary_metrics = {
        kpi: available[canary]
        for kpi, canary in GOODHART_CANARY_PAIRS.items()
        if canary in available
    }

    return {
        "sample_count": len(records),
        "observed_count": len(observed),
        "unobserved_count": unobserved_count,
        "mae_pm10": (
            sum(abs_errors_pm10) / len(abs_errors_pm10)
            if abs_errors_pm10
            else None
        ),
        "breach_precision": breach_precision,
        "breach_recall": breach_recall,
        "false_positive_rate": false_positive_rate,
        "false_negative_rate": false_negative_rate,
        "calibration_error": (
            sum(cal_terms) / len(cal_terms) if cal_terms else None
        ),
        "calibration_bins": calibration_bins,
        "ece": ece,
        "brier_score": brier,
        "avoided_shutdowns_estimate": avoided,
        "production_loss_tonnes_total": production_loss_total,
        "per_receptor": _per_receptor_breakdown(observed),
        "canary_metrics": canary_metrics,
        "protocol": protocol_block,
    }


__all__ = [
    "BREACH_DECISION_THRESHOLD",
    "CALIBRATION_BIN_COUNT",
    "GOODHART_CANARY_PAIRS",
    "compute_metric_payload",
]
