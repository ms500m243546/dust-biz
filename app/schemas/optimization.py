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

from pydantic import BaseModel, Field

ProductionLossLabel = Literal["low", "medium", "high"]


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
    risk_class: str
    requires_human_approval: bool
    # Phase Z — true when the active source attribution names a cause
    # class in this candidate's target_cause_classes. Surfaced by the
    # recommendation orchestrator as a "Cause-targeted" badge.
    cause_targeted: bool = False


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
