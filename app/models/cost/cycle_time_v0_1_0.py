"""Cycle-time-aware production cost model (Phase U.1).

Replaces the heuristic-only `HeuristicProductionCost` for the two
interventions where physics applies cleanly:

  reduce_speed   → `speed_reduction_cycle_impact` from
                   production_cost_physics. Cycle time scales
                   inversely with speed; tonnes delayed follows.
  water_road     → `watering_one_time_cycle_hit` — small one-time
                   cycle hit during the watering window.

All other intervention IDs fall through to heuristic-baseline
coefficients tagged via `confidence` reduction so the operator sees
which path produced the estimate.

The simulate-time signature is fixed (`production_rate_tph` +
`duration_minutes`); fleet-spec inputs (truck count, speed defaults)
use documented defaults pending Phase U.3 site-config integration.
"""

from __future__ import annotations

from app.domain.production_cost_physics import (
    DEFAULT_CYCLE_BASELINE_SEC,
    DEFAULT_WATERING_WINDOW_MIN,
    speed_reduction_cycle_impact,
    tonnes_delayed_from_cycle,
    watering_one_time_cycle_hit,
)
from app.models.cost.heuristic_baseline import (
    COEFFICIENTS,
    DEFAULT_COEFFS,
    _as_bottleneck,
    _as_impact,
)
from app.schemas.interventions import InterventionOptionSchema
from app.schemas.simulations import (
    DO_NOTHING_INTERVENTION_ID,
    ProductionCostEstimateSchema,
)

CYCLE_TIME_VERSION = "production_cost_cycle_time_v0.1.0"
MODEL_KIND = "production_cost"

# Phase U.1 documented defaults — site config integration is U.3+.
DEFAULT_SPEED_BEFORE_KMH = 50.0
DEFAULT_SPEED_AFTER_KMH = 25.0
DEFAULT_FLEET_SIZE = 8


class CycleTimeProductionCost:
    """Phase U.1 physics-informed `ProductionCostModel`.

    Same Protocol shape as the heuristic baseline; the difference is
    in *how* the (cycle_time_increase, tonnes_delayed) pair is derived
    for the two physics-applicable interventions.
    """

    model_kind: str = MODEL_KIND

    def __init__(self, model_version: str = CYCLE_TIME_VERSION) -> None:
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

        coeffs = COEFFICIENTS.get(intervention.intervention_id, DEFAULT_COEFFS)
        bottleneck = _as_bottleneck(coeffs["bottleneck_risk"])
        impact_bucket = _as_impact(coeffs["production_impact"])
        base_conf = coeffs["base_confidence"]

        effective_min = duration_minutes
        if effective_min is None:
            effective_min = min(
                60, max(0, intervention.estimated_time_to_effect_minutes * 2)
            )

        cycle_increase_frac, source_note = self._cycle_increase(intervention)

        if production_rate_tph is None or production_rate_tph <= 0:
            tonnes = 0.0
            confidence = max(0.10, round(base_conf - 0.30, 3))
        else:
            tonnes = tonnes_delayed_from_cycle(
                production_rate_tph=production_rate_tph,
                duration_minutes=effective_min,
                cycle_increase_frac=cycle_increase_frac,
            )
            # Physics path: small confidence boost. Heuristic fallback:
            # match heuristic baseline confidence.
            confidence = (
                round(min(0.95, base_conf + 0.05), 3)
                if source_note != "heuristic_fallback"
                else base_conf
            )

        return ProductionCostEstimateSchema(
            intervention_id=intervention.intervention_id,
            target_zone_id=target_zone_id,
            estimated_tonnes_delayed=round(tonnes, 1),
            cycle_time_increase_percent=round(cycle_increase_frac * 100.0, 2),
            bottleneck_risk=bottleneck,
            production_impact=impact_bucket,
            confidence=confidence,
            model_version=self.model_version,
        )

    def _cycle_increase(
        self, intervention: InterventionOptionSchema
    ) -> tuple[float, str]:
        if intervention.intervention_id == "reduce_speed":
            return (
                speed_reduction_cycle_impact(
                    speed_before_kmh=DEFAULT_SPEED_BEFORE_KMH,
                    speed_after_kmh=DEFAULT_SPEED_AFTER_KMH,
                ),
                "speed_reduction_cycle_impact",
            )
        if intervention.intervention_id == "water_road":
            return (
                watering_one_time_cycle_hit(
                    watering_window_min=DEFAULT_WATERING_WINDOW_MIN,
                    cycle_baseline_sec=DEFAULT_CYCLE_BASELINE_SEC,
                    fleet_size=DEFAULT_FLEET_SIZE,
                ),
                "watering_one_time_cycle_hit",
            )
        # Fallback: convert heuristic cycle_time_pct (whole percent)
        # back to a fraction so the pipeline shape is uniform.
        coeffs = COEFFICIENTS.get(intervention.intervention_id, DEFAULT_COEFFS)
        return float(coeffs["cycle_time_pct"]) / 100.0, "heuristic_fallback"


__all__ = [
    "CYCLE_TIME_VERSION",
    "DEFAULT_FLEET_SIZE",
    "DEFAULT_SPEED_AFTER_KMH",
    "DEFAULT_SPEED_BEFORE_KMH",
    "MODEL_KIND",
    "CycleTimeProductionCost",
]
