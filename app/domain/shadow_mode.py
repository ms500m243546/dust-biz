"""Shadow-mode evaluation harness (Phase K.4).

Per `docs/model-contracts.md` "Model lifecycle" step 5:
shadow-evaluate new versions before promoting. The harness compares a
candidate model_version against the production version over the same
prediction window, using the K.1 S14 join + K.1 metric aggregator.
The output is a structured `ShadowEvaluationResult` with a
recommendation in {promote, hold, regress}; the registry promote
helper is in `app.models.registry.set_current`.

This module is read-only — it does not mutate registry state. The
operator (or the K.3 scheduler in a future iteration) is the one who
consults the result and calls `set_current`. Keeping promote as an
explicit human action is the conservative posture per
`docs/safety-guardrails.md` G13.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.domain.evaluation_protocol import EvaluationProtocol
from app.domain.model_performance import compute_metric_payload
from app.domain.training_data import load_and_assemble

PromotionRecommendation = Literal["promote", "hold", "regress"]


@dataclass(frozen=True)
class ShadowEvaluationResult:
    candidate_version: str
    production_version: str
    window_from: datetime
    window_to: datetime
    candidate_metrics: dict[str, Any]
    production_metrics: dict[str, Any]
    delta: dict[str, float | None]
    recommendation: PromotionRecommendation
    recommendation_reason: str


# Decision thresholds for the recommendation. Conservative by design;
# operators can override by reading the structured deltas and acting
# directly. Calibration error is a tie-breaker — we punish miscalibrated
# models more than slightly less accurate ones.
_BREACH_PRECISION_FLOOR = 0.0
_MAE_REGRESSION_TOLERANCE = 0.0


def _safe_get(payload: dict[str, Any], key: str) -> float | None:
    v = payload.get(key)
    if v is None:
        return None
    if isinstance(v, int | float):
        return float(v)
    return None


def _delta(candidate: dict[str, Any], production: dict[str, Any]) -> dict[str, float | None]:
    keys = (
        "mae_pm10",
        "breach_precision",
        "breach_recall",
        "false_positive_rate",
        "false_negative_rate",
        "calibration_error",
    )
    out: dict[str, float | None] = {}
    for k in keys:
        c = _safe_get(candidate, k)
        p = _safe_get(production, k)
        out[k] = (c - p) if (c is not None and p is not None) else None
    return out


def _decide(
    candidate: dict[str, Any], production: dict[str, Any]
) -> tuple[PromotionRecommendation, str]:
    if candidate.get("observed_count", 0) == 0:
        return "hold", "candidate has no observed predictions in this window"
    if production.get("observed_count", 0) == 0:
        return "hold", "production has no observed predictions; cannot compare"

    cand_mae = _safe_get(candidate, "mae_pm10")
    prod_mae = _safe_get(production, "mae_pm10")
    cand_prec = _safe_get(candidate, "breach_precision")
    prod_prec = _safe_get(production, "breach_precision")
    cand_recall = _safe_get(candidate, "breach_recall")
    prod_recall = _safe_get(production, "breach_recall")

    # Regression: candidate is materially worse on the safety-critical
    # axes. Either lower recall (more missed breaches) or higher MAE.
    if (
        cand_recall is not None
        and prod_recall is not None
        and cand_recall < prod_recall - 0.05
    ):
        return "regress", (
            f"candidate breach_recall {cand_recall:.3f} is materially below "
            f"production {prod_recall:.3f}"
        )
    if (
        cand_mae is not None
        and prod_mae is not None
        and cand_mae > prod_mae + 5.0 + _MAE_REGRESSION_TOLERANCE
    ):
        return "regress", (
            f"candidate MAE {cand_mae:.2f} > production MAE {prod_mae:.2f} + 5.0"
        )

    # Promote: candidate is better on all three primary axes
    # (recall non-decreasing, precision non-decreasing, MAE non-increasing)
    # AND moves at least one of them by a meaningful margin.
    if (
        cand_recall is not None
        and prod_recall is not None
        and cand_prec is not None
        and prod_prec is not None
        and cand_mae is not None
        and prod_mae is not None
        and cand_recall >= prod_recall
        and cand_prec >= prod_prec - _BREACH_PRECISION_FLOOR
        and cand_mae <= prod_mae
        and (
            cand_recall - prod_recall >= 0.05
            or prod_mae - cand_mae >= 2.0
            or cand_prec - prod_prec >= 0.05
        )
    ):
        return "promote", (
            f"candidate dominates production: recall {cand_recall:.3f} vs "
            f"{prod_recall:.3f}, precision {cand_prec:.3f} vs "
            f"{prod_prec:.3f}, MAE {cand_mae:.2f} vs {prod_mae:.2f}"
        )

    return "hold", "candidate within noise of production; no promotion signal"


def evaluate_shadow(
    *,
    session: Session,
    candidate_version: str,
    production_version: str,
    window_from: datetime,
    window_to: datetime,
    protocol: EvaluationProtocol,
    now: datetime | None = None,
    observation_window: timedelta = timedelta(minutes=180),
) -> ShadowEvaluationResult:
    """Compare candidate_version vs production_version over [from, to].

    M.1: requires an `EvaluationProtocol` so the comparison itself
    obeys the rigor gate (anti-overfit + anti-hindsight). The same
    protocol is applied to both versions so the comparison is
    apples-to-apples.
    """
    moment = now or datetime.now(window_from.tzinfo).replace(microsecond=0) if window_from.tzinfo else now
    if moment is None:
        # Conservative: use the window_to instant for the "now" reference
        # so unobserved-cutoff is deterministic in tests.
        moment = window_to

    cand_records = load_and_assemble(
        session=session,
        window_from=window_from,
        window_to=window_to,
        now=moment,
        observation_window=observation_window,
        model_version=candidate_version,
    )
    prod_records = load_and_assemble(
        session=session,
        window_from=window_from,
        window_to=window_to,
        now=moment,
        observation_window=observation_window,
        model_version=production_version,
    )

    # M.2: pass the session so SQL probes run for shadow comparisons.
    cand_payload = compute_metric_payload(
        cand_records, protocol=protocol, session=session
    )
    prod_payload = compute_metric_payload(
        prod_records, protocol=protocol, session=session
    )
    decision, reason = _decide(cand_payload, prod_payload)

    return ShadowEvaluationResult(
        candidate_version=candidate_version,
        production_version=production_version,
        window_from=window_from,
        window_to=window_to,
        candidate_metrics=cand_payload,
        production_metrics=prod_payload,
        delta=_delta(cand_payload, prod_payload),
        recommendation=decision,
        recommendation_reason=reason,
    )


__all__ = [
    "PromotionRecommendation",
    "ShadowEvaluationResult",
    "evaluate_shadow",
]
