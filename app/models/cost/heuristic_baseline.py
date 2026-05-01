"""Heuristic production cost baseline (S10 first implementation).

Per docs/model-contracts.md: "First implementation: heuristic using
current production rate and intervention duration. Financial conversion
deferred until `site_config.cost_curves` is populated."

Inputs are kept narrow on purpose: we don't take a full MineState here,
just the figures the heuristic actually consumes (current production
rate at the target zone, plus the InterventionOption itself). This
mirrors the impact model's pure-function shape and keeps the
orchestrator's job clear.

Per the universal model rules:
- Pure function: no DB, no session.
- Returns `model_version` and `confidence`.
- Conservative: when production rate is unknown we degrade confidence
  rather than fabricate a tonnage.
"""

from __future__ import annotations

from typing import TypedDict

from app.schemas.interventions import InterventionOptionSchema
from app.schemas.simulations import (
    DO_NOTHING_INTERVENTION_ID,
    BottleneckRisk,
    ProductionCostEstimateSchema,
    ProductionImpact,
)

HEURISTIC_VERSION = "production_cost_heuristic_v0.1.0"


class _Coeffs(TypedDict):
    throughput_loss_fraction: float
    cycle_time_pct: float
    bottleneck_risk: str
    production_impact: str
    base_confidence: float


# Per-intervention coefficients. `bottleneck_risk` and
# `production_impact` are qualitative buckets; the rest are floats.
COEFFICIENTS: dict[str, _Coeffs] = {
    "increase_monitoring": {
        "throughput_loss_fraction": 0.0,
        "cycle_time_pct": 0.0,
        "bottleneck_risk": "low",
        "production_impact": "low",
        "base_confidence": 0.95,
    },
    "raise_alert": {
        "throughput_loss_fraction": 0.0,
        "cycle_time_pct": 0.0,
        "bottleneck_risk": "low",
        "production_impact": "low",
        "base_confidence": 0.95,
    },
    "water_road": {
        "throughput_loss_fraction": 0.05,
        "cycle_time_pct": 2.0,
        "bottleneck_risk": "low",
        "production_impact": "low",
        "base_confidence": 0.80,
    },
    "reduce_speed": {
        "throughput_loss_fraction": 0.10,
        "cycle_time_pct": 8.5,
        "bottleneck_risk": "low",
        "production_impact": "low",
        "base_confidence": 0.75,
    },
    "reroute_trucks": {
        "throughput_loss_fraction": 0.20,
        "cycle_time_pct": 18.0,
        "bottleneck_risk": "medium",
        "production_impact": "medium",
        "base_confidence": 0.65,
    },
    "throttle_crusher": {
        "throughput_loss_fraction": 0.40,
        "cycle_time_pct": 0.0,  # crusher throttle shows up as throughput, not cycle time
        "bottleneck_risk": "high",
        "production_impact": "high",
        "base_confidence": 0.70,
    },
    "pause_loading": {
        "throughput_loss_fraction": 1.0,
        "cycle_time_pct": 0.0,
        "bottleneck_risk": "high",
        "production_impact": "high",
        "base_confidence": 0.85,
    },
}

DEFAULT_COEFFS: _Coeffs = {
    "throughput_loss_fraction": 0.05,
    "cycle_time_pct": 5.0,
    "bottleneck_risk": "low",
    "production_impact": "low",
    "base_confidence": 0.50,
}


class HeuristicProductionCost:
    """First implementation of `ProductionCostModel`."""

    model_kind: str = "production_cost"

    def __init__(self, model_version: str = HEURISTIC_VERSION) -> None:
        self.model_version = model_version

    def estimate_cost(
        self,
        *,
        intervention: InterventionOptionSchema,
        target_zone_id: str,
        production_rate_tph: float | None,
        duration_minutes: int | None = None,
    ) -> ProductionCostEstimateSchema:
        if intervention.intervention_id == DO_NOTHING_INTERVENTION_ID:
            return self._do_nothing(target_zone_id=target_zone_id)

        coeffs = COEFFICIENTS.get(intervention.intervention_id, DEFAULT_COEFFS)
        loss_frac = coeffs["throughput_loss_fraction"]
        cycle_pct = coeffs["cycle_time_pct"]
        bottleneck = coeffs["bottleneck_risk"]
        impact_bucket = coeffs["production_impact"]
        base_conf = coeffs["base_confidence"]

        # Effective duration: caller may pass an explicit duration
        # (e.g. site_config.intervention_constraints.max_duration_min);
        # otherwise we use the intervention's time-to-effect doubled, on
        # the rule of thumb that an action needs to run at least as long
        # as it took to take effect to be useful. Capped at 60 min so a
        # zero-effect action like raise_alert doesn't generate phantom
        # tonnage.
        effective_min = duration_minutes
        if effective_min is None:
            effective_min = min(
                60, max(0, intervention.estimated_time_to_effect_minutes * 2)
            )

        if production_rate_tph is None or production_rate_tph <= 0:
            # No production rate => no tonnes figure; degrade confidence.
            tonnes_delayed = 0.0
            confidence = max(0.10, round(base_conf - 0.30, 3))
        else:
            tonnes_delayed = round(
                production_rate_tph * (effective_min / 60.0) * loss_frac, 1
            )
            confidence = base_conf

        return ProductionCostEstimateSchema(
            intervention_id=intervention.intervention_id,
            target_zone_id=target_zone_id,
            estimated_tonnes_delayed=tonnes_delayed,
            cycle_time_increase_percent=cycle_pct,
            bottleneck_risk=_as_bottleneck(bottleneck),
            production_impact=_as_impact(impact_bucket),
            confidence=confidence,
            model_version=self.model_version,
        )

    def _do_nothing(self, *, target_zone_id: str) -> ProductionCostEstimateSchema:
        return ProductionCostEstimateSchema(
            intervention_id=DO_NOTHING_INTERVENTION_ID,
            target_zone_id=target_zone_id,
            estimated_tonnes_delayed=0.0,
            cycle_time_increase_percent=0.0,
            bottleneck_risk="low",
            production_impact="low",
            confidence=0.99,
            model_version=self.model_version,
        )


def _as_bottleneck(value: str) -> BottleneckRisk:
    if value not in ("low", "medium", "high"):
        return "low"
    return value  # type: ignore[return-value]


def _as_impact(value: str) -> ProductionImpact:
    if value not in ("low", "medium", "high"):
        return "low"
    return value  # type: ignore[return-value]


__all__ = ["HEURISTIC_VERSION", "HeuristicProductionCost"]
