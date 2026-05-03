"""Recommendation schemas (Phase H, S12).

Per docs/data-contracts.md `recommendations` and
docs/subsystem-contracts.md S12. Recommendation-named schemas are
safety-relevant: `validate-safety` enforces presence of `confidence`,
`reason`, and `model_version` on every Recommendation* class. The
ranked actions array carries per-action `confidence` + `reason` so
G3 holds at the action level too; the wrapper carries the overall
`confidence` and the human-readable `reason` aimed at a shift
supervisor.

Per Guardrail 1, every action declares `requires_human_approval` (the
S8 catalog flag, copied through). Per Guardrail 7, the wrapper carries
`compliance_priority_triggered` so the dashboard can render the
"compliance prioritized" banner. Per Guardrail 15, the wrapper carries
`model_version`, `feature_pipeline_version`,
`input_data_quality_score`, and `linked_prediction_ids` sufficient to
reconstruct what the engine saw.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.simulations import ProductionImpact

ProductionLossLabel = Literal["low", "medium", "high"]


class RecommendationActionSchema(BaseModel):
    """One ranked action inside a Recommendation."""

    rank: int = Field(ge=1)
    intervention_id: str
    action: str  # human-readable phrase, e.g. "Water Haul_Road_C"
    breach_probability_after: float = Field(ge=0.0, le=1.0)
    production_loss: ProductionLossLabel
    estimated_tonnes_delayed: float = Field(ge=0.0)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str  # G3 at the per-action level
    requires_human_approval: bool  # G1
    risk_class: str  # low / medium / high (from S8 catalog)
    simulation_id: str  # link back to the persisted InterventionSimulation


class RecommendationSchema(BaseModel):
    """Wire format for a persisted recommendation."""

    model_config = ConfigDict(from_attributes=True)

    recommendation_id: str
    issued_at: datetime
    target_zone_id: str
    risk_event: str  # human-readable description of the risk
    current_breach_probability: float = Field(ge=0.0, le=1.0)
    target_probability: float = Field(ge=0.0, le=1.0)
    recommended_actions: list[RecommendationActionSchema] = Field(default_factory=list)
    requires_human_review: bool  # G6
    compliance_priority_triggered: bool  # G7
    confidence: float = Field(ge=0.0, le=1.0)  # G2 (overall)
    reason: str  # G3 (overall, rendered text for the supervisor)
    model_version: str  # G15 (optimization engine version)
    feature_pipeline_version: str  # G15
    input_data_quality_score: float = Field(ge=0.0, le=1.0)  # G15
    data_quality_warnings: list[str] = Field(default_factory=list)  # G5
    linked_prediction_ids: list[str] = Field(default_factory=list)  # G15
    linked_attribution_id: str | None = None
    automation_level: str  # L0..L4 active at issuance time

    # Aggregate production-impact bucket of the top-ranked action.
    # Convenience field for the dashboard; derivable from
    # `recommended_actions[0]` if needed.
    top_production_impact: ProductionImpact | None = None
    # M.3.1 — causal-protocol confidence (penalty-adjusted relative to
    # predictive `confidence`). The dashboard shows both side-by-side
    # so a supervisor can see the gap between "the model thinks this
    # will work" and "the model has causal evidence it will work."
    causal_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
