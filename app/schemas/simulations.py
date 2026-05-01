"""Intervention simulation schemas (Phase G, S9 + S10).

Per docs/data-contracts.md `intervention_simulations`,
docs/subsystem-contracts.md S9, and docs/model-contracts.md
`InterventionImpactModel` / `ProductionCostModel` return contracts.

The simulation schema is deliberately Simulation-named so the
`validate-safety` scanner picks it up: G2 (`confidence`) is enforced
structurally on every Simulation-named class.

Two related shapes live here:
- `InterventionImpactSchema`  - what the impact model returns
  (predicted dust reduction + breach probability after action +
  time-to-effect + confidence + model_version + source). Pure
  output of the impact model; the orchestrator joins it with cost.
- `ProductionCostEstimateSchema` - what the cost model returns
  (tonnes delayed, cycle time bump, qualitative impact, confidence,
  model_version). Pure output of the cost model.
- `InterventionSimulationSchema` - the persisted, joined view that
  the API exposes. Wraps both above in a single record keyed by
  `simulation_id`. This is what the recommendation engine (Phase H)
  consumes per intervention candidate.

A `do_nothing` counterfactual lives in this same schema with
`intervention_id = "_do_nothing_"` reserved and `predicted_pm10_reduction = 0`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DO_NOTHING_INTERVENTION_ID = "_do_nothing_"

SimulationSource = Literal["model", "heuristic"]
ProductionImpact = Literal["low", "medium", "high"]
BottleneckRisk = Literal["low", "medium", "high"]


class InterventionImpactSchema(BaseModel):
    """S9 model output shape.

    `breach_probability_after_action` carries the post-intervention
    estimate in [0, 1] alongside the original (pre-action) value the
    caller asked us to evaluate. Both are stored so the dashboard can
    show the delta directly.
    """

    intervention_id: str
    target_zone_id: str
    predicted_pm10_reduction: float = Field(ge=0.0)
    predicted_pm25_reduction: float | None = None
    breach_probability_before: float = Field(ge=0.0, le=1.0)
    breach_probability_after_action: float = Field(ge=0.0, le=1.0)
    time_to_effect_minutes: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    model_version: str
    source: SimulationSource = "heuristic"
    main_uncertainty: str | None = None


class ProductionCostEstimateSchema(BaseModel):
    """S10 model output shape."""

    intervention_id: str
    target_zone_id: str
    estimated_tonnes_delayed: float = Field(ge=0.0)
    cycle_time_increase_percent: float = Field(ge=0.0)
    bottleneck_risk: BottleneckRisk
    production_impact: ProductionImpact
    confidence: float = Field(ge=0.0, le=1.0)
    model_version: str


class InterventionSimulationSchema(BaseModel):
    """Persisted, joined simulation row.

    Combines impact + cost so a single record fully describes one
    candidate scenario. `source` reflects the impact model's path
    (`model` or `heuristic`); the cost model's source is implicit.
    """

    model_config = ConfigDict(from_attributes=True)

    simulation_id: str
    requested_at: datetime
    intervention_id: str
    target_zone_id: str
    scenario: str  # human-readable summary, e.g. "Reduce truck speed on Haul_Road_C"
    # Impact
    predicted_pm10_reduction: float = Field(ge=0.0)
    predicted_pm25_reduction: float | None = None
    breach_probability_before: float = Field(ge=0.0, le=1.0)
    breach_probability_after: float = Field(ge=0.0, le=1.0)
    time_to_effect_minutes: int = Field(ge=0)
    # Cost
    production_loss_tonnes: float = Field(ge=0.0)
    cycle_time_increase_percent: float = Field(ge=0.0)
    production_impact: ProductionImpact
    # Combined provenance
    confidence: float = Field(ge=0.0, le=1.0)
    model_version: str
    cost_model_version: str
    source: SimulationSource = "heuristic"
    main_uncertainty: str | None = None
