"""AP-42 physics-informed intervention impact model (Phase R.1).

Replaces the heuristic-only `HeuristicInterventionImpact` for the two
interventions where the EPA AP-42 §13.2.2 unpaved-haul-road formula
applies:

  water_road     → `watering_decay_curve` predicts the reduction
                   based on time since last watering + meteorology.
  reduce_speed   → `speed_reduction_factor` from the AP-42 speed
                   exponent.

All other intervention IDs fall through to the heuristic baseline
fractions so the registry can swap atomically — no per-intervention
gap.

Phase R.1 ships *with documented defaults* for the physics inputs the
simulate() Protocol does not currently surface (silt content, vehicle
weight, time since watering, meteorology). The defaults reflect typical
Chilean copper-mine haul roads + Komatsu 930E fleet + moderate Andean
afternoon. Calibration against real `ActionOutcome` rows is Phase R.2.

The model is registered alongside the heuristic but *not* promoted to
current — operator decides per `docs/intervention-physics.md`.
"""

from __future__ import annotations

from app.domain.ap42_emission import (
    speed_reduction_factor,
    watering_decay_curve,
)
from app.models.intervention.heuristic_baseline import (
    BASE_CONFIDENCE,
    DEFAULT_CONFIDENCE,
    DEFAULT_REDUCTION,
    PM10_REDUCTION_FRACTION,
)
from app.schemas.interventions import InterventionOptionSchema
from app.schemas.simulations import (
    DO_NOTHING_INTERVENTION_ID,
    InterventionImpactSchema,
)

AP42_VERSION = "intervention_impact_ap42_v0.1.0"
MODEL_KIND = "intervention_impact"

# Physics-default inputs. R.1 documents these as conservative pending
# Phase R.2 calibration. R.2 will plumb real silt samples, fleet
# specs, and meteorology through a richer calling convention.
DEFAULT_MINUTES_SINCE_WATERING = 0.0  # immediately after a watering action
DEFAULT_WIND_SPEED_MS = 5.0
DEFAULT_HUMIDITY_PCT = 50.0
DEFAULT_TEMPERATURE_C = 15.0
DEFAULT_SPEED_BEFORE_KMH = 50.0
DEFAULT_SPEED_AFTER_KMH = 25.0


class AP42InterventionImpact:
    """Phase R.1 physics-informed `InterventionImpactModel`.

    Same Protocol shape as the heuristic baseline; the difference is
    in *how* the reduction fraction is derived for the two AP-42-
    applicable interventions.
    """

    model_kind: str = MODEL_KIND

    def __init__(self, model_version: str = AP42_VERSION) -> None:
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
                breach_probability_before=breach_probability_before,
            )

        reduction_frac, source_note = self._reduction_fraction(intervention)

        base_conf = BASE_CONFIDENCE.get(
            intervention.intervention_id, DEFAULT_CONFIDENCE
        )
        risk_penalty = {"low": 0.0, "medium": 0.05, "high": 0.10}.get(
            intervention.risk_class, 0.0
        )
        # Physics-informed paths get a small confidence boost over the
        # heuristic since the reduction fraction is grounded in a
        # published EPA model rather than a hand-tuned constant.
        physics_boost = 0.05 if source_note != "heuristic_fallback" else 0.0
        confidence = max(0.05, min(0.95, round(base_conf - risk_penalty + physics_boost, 3)))

        pm10_reduction = max(0.0, predicted_pm10) * reduction_frac
        pm25_reduction: float | None = (
            max(0.0, predicted_pm25) * reduction_frac * 0.85
            if predicted_pm25 is not None
            else None
        )

        breach_after = max(
            0.0,
            min(
                1.0,
                round(breach_probability_before * (1.0 - reduction_frac), 4),
            ),
        )

        main_uncertainty = (
            f"AP-42 physics ({source_note}); "
            "R.1 uses documented defaults for silt + vehicle weight + "
            "meteorology pending Phase R.2 calibration."
            if source_note != "heuristic_fallback"
            else "Heuristic fallback — AP-42 not applicable to this intervention"
        )

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
            source="model" if source_note != "heuristic_fallback" else "heuristic",
            main_uncertainty=main_uncertainty,
        )

    def _reduction_fraction(
        self, intervention: InterventionOptionSchema
    ) -> tuple[float, str]:
        if intervention.intervention_id == "water_road":
            frac = watering_decay_curve(
                minutes_since_watering=DEFAULT_MINUTES_SINCE_WATERING,
                wind_speed_ms=DEFAULT_WIND_SPEED_MS,
                humidity_pct=DEFAULT_HUMIDITY_PCT,
                temperature_c=DEFAULT_TEMPERATURE_C,
            )
            return frac, "watering_decay_curve"
        if intervention.intervention_id == "reduce_speed":
            frac = speed_reduction_factor(
                speed_before_kmh=DEFAULT_SPEED_BEFORE_KMH,
                speed_after_kmh=DEFAULT_SPEED_AFTER_KMH,
            )
            return frac, "speed_reduction_factor"
        # All other interventions: defer to heuristic baseline values
        # so the model gives a sensible answer for the full menu.
        frac = PM10_REDUCTION_FRACTION.get(
            intervention.intervention_id, DEFAULT_REDUCTION
        )
        return frac, "heuristic_fallback"

    def _do_nothing(
        self,
        *,
        target_zone_id: str,
        breach_probability_before: float,
    ) -> InterventionImpactSchema:
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
            source="model",
            main_uncertainty=None,
        )


__all__ = ["AP42_VERSION", "MODEL_KIND", "AP42InterventionImpact"]
