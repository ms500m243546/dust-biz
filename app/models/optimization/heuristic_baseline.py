"""Weighted-scoring optimization engine (S11 first implementation).

Per docs/model-contracts.md "First implementation: weighted scoring
against the objective in safety-guardrails.md". Per
docs/safety-guardrails.md "compliance-priority logic" (rule 7
expanded), three regimes:

  breach_prob < 0.5            balanced
  0.5 <= breach_prob < 0.85    w_production *= 0.7
  breach_prob >= 0.85          w_production *= 0.3, w_compliance *= 2.0
                                AND mark compliance_priority_triggered

The engine is a pure function: it consumes typed inputs (a list of
`InterventionSimulationSchema` candidates plus the active site config
weights) and returns a `RankedRecommendations`. Persistence is the
orchestrator's job (universal model rule 5).

Score per candidate (higher = better):

  score =   w_breach * (breach_before - breach_after)
          - w_production * (tonnes_delayed / 1000.0)
          - w_disruption * (cycle_time_pct / 100.0)
          - w_low_confidence_penalty
          + w_compliance_bump (if compliance triggered AND action
                               actually reduces breach)

`w_low_confidence_penalty` activates when joined simulation
confidence < `low_confidence_threshold`; it pushes the candidate
down without removing it, so the orchestrator can still surface it
under `requires_human_review` if nothing else qualifies.
"""

from __future__ import annotations

from app.schemas.optimization import (
    ProductionLossLabel,
    RankedCandidate,
    RankedRecommendations,
)
from app.schemas.simulations import (
    DO_NOTHING_INTERVENTION_ID,
    InterventionSimulationSchema,
)
from app.schemas.site_config import OptimizationWeightsSchema

OPTIMIZER_VERSION = "optimization_weighted_v0.1.0"

EXTREME_BREACH_DEFAULT = 0.85
ELEVATED_BREACH_DEFAULT = 0.5
LOW_CONFIDENCE_DEFAULT = 0.5

# Cost-class catalog cross-check; we don't import the catalog here
# (would create a Domain->Model upward import). The orchestrator hands
# us the catalog IDs and risk classes when it builds candidates.


class WeightedOptimizationEngine:
    """First implementation of OptimizationEngine.

    `model_kind` is `str` (not `Literal[...]`) for Protocol-compatibility
    with the registry; the assigned value enforces the kind at runtime.
    """

    model_kind: str = "optimization"

    def __init__(self, model_version: str = OPTIMIZER_VERSION) -> None:
        self.model_version = model_version

    def rank_actions(
        self,
        *,
        target_zone_id: str,
        breach_probability_before: float,
        candidates: list[InterventionSimulationSchema],
        candidate_risk_classes: dict[str, str],
        candidate_requires_approval: dict[str, bool],
        weights: OptimizationWeightsSchema,
        extreme_breach_threshold: float = EXTREME_BREACH_DEFAULT,
        low_confidence_threshold: float = LOW_CONFIDENCE_DEFAULT,
    ) -> RankedRecommendations:
        """Rank candidates by weighted score.

        `candidate_risk_classes` and `candidate_requires_approval` come
        from the S8 catalog at orchestrator time; the optimizer doesn't
        re-query the DB. This keeps the engine a pure function.
        """
        active_weights, regime, compliance_triggered = _resolve_weights(
            weights=weights,
            breach_probability_before=breach_probability_before,
            extreme_breach_threshold=extreme_breach_threshold,
        )

        scored: list[tuple[InterventionSimulationSchema, float, bool]] = []
        for cand in candidates:
            low_conf = cand.confidence < low_confidence_threshold
            score = _score_candidate(
                cand=cand,
                breach_probability_before=breach_probability_before,
                weights=active_weights,
                low_confidence=low_conf,
                compliance_triggered=compliance_triggered,
            )
            scored.append((cand, score, low_conf))

        scored.sort(key=lambda t: t[1], reverse=True)

        ranked = [
            _to_ranked(
                rank=i + 1,
                cand=cand,
                score=score,
                low_confidence=low_conf,
                breach_before=breach_probability_before,
                risk_class=candidate_risk_classes.get(cand.intervention_id, "low"),
                requires_approval=candidate_requires_approval.get(
                    cand.intervention_id, True
                ),
            )
            for i, (cand, score, low_conf) in enumerate(scored)
        ]

        # G6: when no candidate clears the low-confidence threshold,
        # the orchestrator gets requires_human_review=True. The engine
        # surfaces the signal; the orchestrator decides what to do with
        # high-risk actions in that state.
        any_confident = any(c.confidence >= low_confidence_threshold for c in candidates)
        requires_human_review = not any_confident

        # Overall confidence: top candidate's confidence, but capped by
        # the regime - extreme-breach decisions are inherently uncertain.
        overall_conf = ranked[0].confidence if ranked else 0.0
        if compliance_triggered:
            overall_conf = round(min(overall_conf, 0.85), 3)

        target_probability = _target_probability(
            breach_probability_before=breach_probability_before,
            extreme_breach_threshold=extreme_breach_threshold,
        )

        overall_reason = _overall_reason(
            regime=regime,
            ranked=ranked,
            breach_before=breach_probability_before,
            target_probability=target_probability,
            requires_human_review=requires_human_review,
        )

        return RankedRecommendations(
            target_zone_id=target_zone_id,
            candidates=ranked,
            target_probability=target_probability,
            compliance_priority_triggered=compliance_triggered,
            requires_human_review=requires_human_review,
            overall_confidence=overall_conf,
            overall_reason=overall_reason,
            model_version=self.model_version,
        )


def _resolve_weights(
    *,
    weights: OptimizationWeightsSchema,
    breach_probability_before: float,
    extreme_breach_threshold: float,
) -> tuple[OptimizationWeightsSchema, str, bool]:
    """Apply the three-regime compliance-priority logic from G7."""
    if breach_probability_before >= extreme_breach_threshold:
        adjusted = weights.model_copy(
            update={
                "w_production": weights.w_production * 0.3,
                "w_compliance": weights.w_compliance * 2.0,
            }
        )
        return adjusted, "extreme", True
    if breach_probability_before >= ELEVATED_BREACH_DEFAULT:
        adjusted = weights.model_copy(
            update={"w_production": weights.w_production * 0.7}
        )
        return adjusted, "elevated", False
    return weights, "balanced", False


def _score_candidate(
    *,
    cand: InterventionSimulationSchema,
    breach_probability_before: float,
    weights: OptimizationWeightsSchema,
    low_confidence: bool,
    compliance_triggered: bool,
) -> float:
    breach_drop = max(0.0, breach_probability_before - cand.breach_probability_after)

    score = (
        weights.w_breach * breach_drop
        - weights.w_production * (cand.production_loss_tonnes / 1000.0)
        - weights.w_disruption * (cand.cycle_time_increase_percent / 100.0)
    )
    if low_confidence:
        score -= weights.w_low_confidence
    if compliance_triggered and breach_drop > 0:
        # The compliance bump is proportional to the breach reduction so
        # a "do nothing" candidate doesn't get inflated under extreme
        # risk just because the bonus exists.
        score += weights.w_compliance * breach_drop
    return round(score, 4)


def _to_ranked(
    *,
    rank: int,
    cand: InterventionSimulationSchema,
    score: float,
    low_confidence: bool,
    breach_before: float,
    risk_class: str,
    requires_approval: bool,
) -> RankedCandidate:
    breach_drop = max(0.0, breach_before - cand.breach_probability_after)
    parts: list[str] = []
    if cand.intervention_id == DO_NOTHING_INTERVENTION_ID:
        parts.append("counterfactual baseline (no operational change)")
    if breach_drop >= 0.30:
        parts.append("strong breach reduction")
    elif breach_drop >= 0.10:
        parts.append("moderate breach reduction")
    elif breach_drop > 0:
        parts.append("small breach reduction")
    else:
        parts.append("no breach reduction")
    if cand.production_impact == "low":
        parts.append("low production impact")
    elif cand.production_impact == "medium":
        parts.append("medium production impact")
    else:
        parts.append("high production impact")
    if low_confidence:
        parts.append("low simulation confidence")

    return RankedCandidate(
        rank=rank,
        intervention_id=cand.intervention_id,
        simulation_id=cand.simulation_id,
        score=score,
        breach_probability_after=cand.breach_probability_after,
        estimated_tonnes_delayed=cand.production_loss_tonnes,
        production_loss=_loss_label(cand.production_impact),
        confidence=cand.confidence,
        reason="; ".join(parts),
        risk_class=risk_class,
        requires_human_approval=requires_approval,
    )


def _loss_label(impact: str) -> ProductionLossLabel:
    if impact in ("low", "medium", "high"):
        return impact  # type: ignore[return-value]
    return "low"


def _target_probability(
    *,
    breach_probability_before: float,
    extreme_breach_threshold: float,
) -> float:
    """Heuristic target the engine tries to achieve.

    Under extreme breach we aim for 0.25 (well below the warning band).
    Otherwise we aim for max(0.25, breach_before - 0.30).
    """
    if breach_probability_before >= extreme_breach_threshold:
        return 0.25
    return round(max(0.25, breach_probability_before - 0.30), 3)


def _overall_reason(
    *,
    regime: str,
    ranked: list[RankedCandidate],
    breach_before: float,
    target_probability: float,
    requires_human_review: bool,
) -> str:
    if not ranked:
        return "No actionable interventions in the catalog for this zone."
    top = ranked[0]
    parts: list[str] = []
    if regime == "extreme":
        parts.append(
            "Extreme breach risk - compliance prioritized over production."
        )
    elif regime == "elevated":
        parts.append("Elevated breach risk; production weight reduced.")
    parts.append(
        f"Recommend {top.intervention_id}: breach probability {breach_before:.0%} -> "
        f"{top.breach_probability_after:.0%} (target {target_probability:.0%})."
    )
    if requires_human_review:
        parts.append(
            "All candidates below low-confidence threshold; flagged for human review."
        )
    return " ".join(parts)


__all__ = [
    "ELEVATED_BREACH_DEFAULT",
    "EXTREME_BREACH_DEFAULT",
    "LOW_CONFIDENCE_DEFAULT",
    "OPTIMIZER_VERSION",
    "WeightedOptimizationEngine",
]
