"""Optimization engine schemas (Phase H, S11).

Per docs/model-contracts.md `OptimizationEngine`. The engine ranks
intervention candidates and tells the recommendation orchestrator
whether compliance-priority logic kicked in (G7).

`RankedCandidate` is the per-row output; `RankedRecommendations` is
the engine's full return object. Both stay schema-shaped (not ORM-
shaped) because the engine is a pure function and its output is
joined into the persisted `Recommendation` by the orchestrator.

Note on safety scanner: this file is intentionally NOT named
"Recommendation*" - those names belong to `app/schemas/recommendations.py`.
The optimizer is upstream of persistence; its output is internal.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ProductionLossLabel = Literal["low", "medium", "high"]
# Phase AA — plan-relative cost label. Reflects whether the action's
# tonnes_delayed fits within the shift's remaining slack.
PlanRelativeLossLabel = Literal["absorbable", "partial", "blocking"]


class RiskClassDerivation(BaseModel):
    """Phase AB — audit trail for context-derived risk class.

    `base` is the catalog floor; `derived` is the class the ranker
    actually surfaced (escalation only — never below base). `reasons`
    is the human-readable list of why escalation fired. Empty reasons
    + base == derived means the catalog floor was unchanged.
    """

    model_config = ConfigDict(from_attributes=True)

    base: str
    derived: str
    reasons: list[str] = Field(default_factory=list)


class RankedCandidate(BaseModel):
    """One ranked candidate from the optimizer."""

    rank: int = Field(ge=1)
    intervention_id: str
    simulation_id: str
    score: float  # higher = better (lower cost-adjusted breach reduction)
    breach_probability_after: float = Field(ge=0.0, le=1.0)
    estimated_tonnes_delayed: float = Field(ge=0.0)
    production_loss: ProductionLossLabel
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    risk_class: str  # Phase AB: this is the *derived* class (post-escalation).
    requires_human_approval: bool
    # Phase AB — the catalog floor and the audit trail for any
    # context-driven escalation. None on degraded / pre-AB call sites.
    risk_derivation: RiskClassDerivation | None = None
    # Phase Z — true when the active source attribution names a cause
    # class in this candidate's target_cause_classes. Surfaced by the
    # recommendation orchestrator as a "Cause-targeted" badge.
    cause_targeted: bool = False
    # Phase AA — plan-relative production loss label. None when no
    # shift_progress was supplied (degraded / pre-AA call sites).
    plan_relative_loss: PlanRelativeLossLabel | None = None


class RankedRecommendations(BaseModel):
    """Full optimizer output for one (forecast, candidate-set) call."""

    target_zone_id: str
    candidates: list[RankedCandidate] = Field(default_factory=list)
    target_probability: float = Field(ge=0.0, le=1.0)
    compliance_priority_triggered: bool
    requires_human_review: bool
    overall_confidence: float = Field(ge=0.0, le=1.0)
    overall_reason: str
    model_version: str
    # Phase Z — the cause class (zone_type) the optimizer used to apply
    # the cause-match boost. None when no attribution was available or
    # the attributed source has no resolvable zone_type.
    cause_class: str | None = None
    # Phase AA — slack_ratio (tonnes_done / expected_done) used to
    # rescale w_production. 1.0 = on plan; >1 = ahead; <1 = behind.
    # None means no shift_progress was supplied and the rescale was
    # skipped.
    shift_slack_ratio: float | None = None
