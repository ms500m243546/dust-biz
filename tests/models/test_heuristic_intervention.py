"""Heuristic intervention impact model tests.

Pin per-intervention reduction fractions and the safety invariants the
scanner can't enforce on a behavioral output (e.g. confidence stays in
range under high-risk penalty).
"""

from app.models.intervention.heuristic_baseline import (
    HEURISTIC_VERSION,
    HeuristicInterventionImpact,
)
from app.schemas.interventions import InterventionOptionSchema
from app.schemas.simulations import DO_NOTHING_INTERVENTION_ID


def _opt(intervention_id: str, **overrides: object) -> InterventionOptionSchema:
    base: dict[str, object] = {
        "intervention_id": intervention_id,
        "name": intervention_id,
        "description": "test",
        "risk_class": "medium",
        "requires_human_approval": True,
        "automation_eligible_levels": [],
        "estimated_time_to_effect_minutes": 10,
        "allowed_zone_types": ["haul_road"],
    }
    base.update(overrides)
    return InterventionOptionSchema(**base)  # type: ignore[arg-type]


def test_water_road_reduces_pm10_about_35_percent() -> None:
    m = HeuristicInterventionImpact()
    out = m.simulate(
        intervention=_opt("water_road"),
        target_zone_id="haul_c",
        predicted_pm10=200.0,
        predicted_pm25=80.0,
        breach_probability_before=0.8,
    )
    assert abs(out.predicted_pm10_reduction - 70.0) < 0.01
    assert out.breach_probability_after_action < out.breach_probability_before
    assert out.model_version == HEURISTIC_VERSION
    assert out.source == "heuristic"


def test_reduce_speed_lower_reduction_than_water() -> None:
    m = HeuristicInterventionImpact()
    water = m.simulate(
        intervention=_opt("water_road"),
        target_zone_id="haul_c",
        predicted_pm10=100.0,
        predicted_pm25=None,
        breach_probability_before=0.5,
    )
    speed = m.simulate(
        intervention=_opt("reduce_speed"),
        target_zone_id="haul_c",
        predicted_pm10=100.0,
        predicted_pm25=None,
        breach_probability_before=0.5,
    )
    assert speed.predicted_pm10_reduction < water.predicted_pm10_reduction


def test_reroute_carries_main_uncertainty_note() -> None:
    m = HeuristicInterventionImpact()
    out = m.simulate(
        intervention=_opt("reroute_trucks", risk_class="high"),
        target_zone_id="haul_c",
        predicted_pm10=140.0,
        predicted_pm25=None,
        breach_probability_before=0.6,
    )
    assert out.main_uncertainty is not None
    assert "alternate" in out.main_uncertainty.lower()


def test_high_risk_class_lowers_confidence() -> None:
    m = HeuristicInterventionImpact()
    medium = m.simulate(
        intervention=_opt("water_road", risk_class="medium"),
        target_zone_id="z",
        predicted_pm10=100.0,
        predicted_pm25=None,
        breach_probability_before=0.5,
    )
    high = m.simulate(
        intervention=_opt("water_road", risk_class="high"),
        target_zone_id="z",
        predicted_pm10=100.0,
        predicted_pm25=None,
        breach_probability_before=0.5,
    )
    assert high.confidence < medium.confidence


def test_unknown_intervention_falls_back_to_default_reduction() -> None:
    m = HeuristicInterventionImpact()
    out = m.simulate(
        intervention=_opt("dance_for_rain", risk_class="low"),
        target_zone_id="z",
        predicted_pm10=100.0,
        predicted_pm25=None,
        breach_probability_before=0.5,
    )
    # Default 10% reduction.
    assert abs(out.predicted_pm10_reduction - 10.0) < 0.01


def test_pm25_reduction_proportional_when_provided() -> None:
    m = HeuristicInterventionImpact()
    out = m.simulate(
        intervention=_opt("water_road"),
        target_zone_id="z",
        predicted_pm10=100.0,
        predicted_pm25=40.0,
        breach_probability_before=0.4,
    )
    assert out.predicted_pm25_reduction is not None
    # 40 * 0.35 * 0.85 = 11.9
    assert abs(out.predicted_pm25_reduction - 11.9) < 0.05


def test_do_nothing_returns_zero_reduction_and_high_confidence() -> None:
    m = HeuristicInterventionImpact()
    out = m.simulate(
        intervention=_opt(DO_NOTHING_INTERVENTION_ID, risk_class="low"),
        target_zone_id="z",
        predicted_pm10=120.0,
        predicted_pm25=None,
        breach_probability_before=0.7,
    )
    assert out.predicted_pm10_reduction == 0.0
    assert out.breach_probability_after_action == out.breach_probability_before
    assert out.confidence >= 0.9


def test_breach_after_clamped_to_unit_interval() -> None:
    m = HeuristicInterventionImpact()
    out = m.simulate(
        intervention=_opt("pause_loading"),
        target_zone_id="z",
        predicted_pm10=180.0,
        predicted_pm25=None,
        breach_probability_before=0.99,
    )
    assert 0.0 <= out.breach_probability_after_action <= 1.0
