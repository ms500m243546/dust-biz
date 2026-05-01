"""Heuristic intervention impact baseline (S9 first implementation).

Per docs/model-contracts.md "First implementation: heuristic per
intervention class (e.g. watering reduces dust generation in zone by
X% for Y minutes; speed reduction reduces road dust by Z%)."

Coefficients are intentionally simple and uncalibrated; this is the
cold-start model that lets the rest of the platform exercise the S9
contract. Trained variants plug into the same Protocol later via
`app.models.registry`.

Per the universal model rules in `docs/model-contracts.md`:
- Pure function: no DB writes, no session.
- Returns `model_version` and `confidence` on every call.
- Returns `source = "heuristic"` (Guardrail 11 spirit; this isn't a
  fallback path, but it tells the caller this output was not produced
  by a trained model).
"""

from __future__ import annotations

from app.schemas.interventions import InterventionOptionSchema
from app.schemas.simulations import (
    DO_NOTHING_INTERVENTION_ID,
    InterventionImpactSchema,
)

HEURISTIC_VERSION = "intervention_impact_heuristic_v0.1.0"

# PM10 reduction fractions per intervention_id. Tuned conservatively;
# operational reductions in the field rarely exceed ~50% even for the
# heaviest interventions.
PM10_REDUCTION_FRACTION: dict[str, float] = {
    "increase_monitoring": 0.0,
    "raise_alert": 0.0,
    "water_road": 0.35,
    "reduce_speed": 0.20,
    "reroute_trucks": 0.50,
    "throttle_crusher": 0.40,
    "pause_loading": 0.60,
}

# Per-intervention base confidence. Watering and speed reduction are
# well understood operationally so they get higher base confidence;
# reroute is harder to predict because it shifts dust to a new zone.
BASE_CONFIDENCE: dict[str, float] = {
    "increase_monitoring": 0.9,
    "raise_alert": 0.9,
    "water_road": 0.75,
    "reduce_speed": 0.70,
    "reroute_trucks": 0.55,
    "throttle_crusher": 0.65,
    "pause_loading": 0.80,
}

DEFAULT_REDUCTION = 0.10
DEFAULT_CONFIDENCE = 0.50


class HeuristicInterventionImpact:
    """First implementation of `InterventionImpactModel`.

    `model_kind` is `str` (not `Literal[...]`) for Protocol-compatibility
    with the registry; the assigned value enforces the kind at runtime.
    """

    model_kind: str = "intervention_impact"

    def __init__(self, model_version: str = HEURISTIC_VERSION) -> None:
        self.model_version = model_version

    def simulate(
        self,
        *,
        intervention: InterventionOptionSchema,
        target_zone_id: str,
        predicted_pm10: float,
        predicted_pm25: float | None,
        breach_probability_before: float,
    ) -> InterventionImpactSchema:
        if intervention.intervention_id == DO_NOTHING_INTERVENTION_ID:
            return self._do_nothing(
                target_zone_id=target_zone_id,
                predicted_pm10=predicted_pm10,
                breach_probability_before=breach_probability_before,
            )

        reduction_frac = PM10_REDUCTION_FRACTION.get(
            intervention.intervention_id, DEFAULT_REDUCTION
        )
        # Risk-class downscales confidence because high-risk levers have
        # more variable outcomes when actually executed.
        base_conf = BASE_CONFIDENCE.get(intervention.intervention_id, DEFAULT_CONFIDENCE)
        risk_penalty = {"low": 0.0, "medium": 0.05, "high": 0.10}.get(
            intervention.risk_class, 0.0
        )
        confidence = max(0.05, round(base_conf - risk_penalty, 3))

        pm10_reduction = max(0.0, predicted_pm10) * reduction_frac
        pm25_reduction: float | None
        if predicted_pm25 is not None:
            # PM2.5 typically responds proportionally to PM10 from
            # mechanical-source dust, slightly less for fine fractions.
            pm25_reduction = max(0.0, predicted_pm25) * reduction_frac * 0.85
        else:
            pm25_reduction = None

        # Linear-scaling breach probability map: a fractional PM10
        # reduction translates roughly into the same fractional breach-
        # probability reduction, capped at 0.0. This is intentionally
        # simple - a calibrated mapping arrives in K.
        breach_after = max(
            0.0,
            min(
                1.0,
                round(breach_probability_before * (1.0 - reduction_frac), 4),
            ),
        )

        main_uncertainty: str | None = None
        if intervention.intervention_id == "reroute_trucks":
            main_uncertainty = (
                "Reroute may shift dust generation to the alternate haul road"
            )
        elif intervention.risk_class == "high":
            main_uncertainty = "High-risk intervention; outcome variance is wider"

        return InterventionImpactSchema(
            intervention_id=intervention.intervention_id,
            target_zone_id=target_zone_id,
            predicted_pm10_reduction=round(pm10_reduction, 3),
            predicted_pm25_reduction=(
                round(pm25_reduction, 3) if pm25_reduction is not None else None
            ),
            breach_probability_before=round(breach_probability_before, 4),
            breach_probability_after_action=breach_after,
            time_to_effect_minutes=intervention.estimated_time_to_effect_minutes,
            confidence=confidence,
            model_version=self.model_version,
            source="heuristic",
            main_uncertainty=main_uncertainty,
        )

    def _do_nothing(
        self,
        *,
        target_zone_id: str,
        predicted_pm10: float,
        breach_probability_before: float,
    ) -> InterventionImpactSchema:
        """Counterfactual: nothing changes.

        Used by the recommendation engine (Phase H) so the "no-op"
        option is comparable on the same axis. Confidence is high
        because predicting the status quo is trivial.
        """
        return InterventionImpactSchema(
            intervention_id=DO_NOTHING_INTERVENTION_ID,
            target_zone_id=target_zone_id,
            predicted_pm10_reduction=0.0,
            predicted_pm25_reduction=0.0,
            breach_probability_before=round(breach_probability_before, 4),
            breach_probability_after_action=round(breach_probability_before, 4),
            time_to_effect_minutes=0,
            confidence=0.95,
            model_version=self.model_version,
            source="heuristic",
            main_uncertainty=None,
        )


__all__ = ["HEURISTIC_VERSION", "HeuristicInterventionImpact"]
