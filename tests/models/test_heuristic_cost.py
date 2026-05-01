"""Heuristic production cost model tests."""

from app.models.cost.heuristic_baseline import (
    HEURISTIC_VERSION,
    HeuristicProductionCost,
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


def test_water_road_low_impact() -> None:
    m = HeuristicProductionCost()
    out = m.estimate_cost(
        intervention=_opt("water_road"),
        target_zone_id="haul_c",
        production_rate_tph=1000.0,
    )
    assert out.production_impact == "low"
    assert out.cycle_time_increase_percent <= 5.0
    assert out.estimated_tonnes_delayed > 0
    assert out.model_version == HEURISTIC_VERSION


def test_reroute_higher_cost_than_water() -> None:
    m = HeuristicProductionCost()
    water = m.estimate_cost(
        intervention=_opt("water_road"),
        target_zone_id="z",
        production_rate_tph=1000.0,
    )
    reroute = m.estimate_cost(
        intervention=_opt("reroute_trucks"),
        target_zone_id="z",
        production_rate_tph=1000.0,
    )
    assert reroute.estimated_tonnes_delayed > water.estimated_tonnes_delayed
    assert reroute.cycle_time_increase_percent > water.cycle_time_increase_percent


def test_pause_loading_full_throughput_loss() -> None:
    m = HeuristicProductionCost()
    out = m.estimate_cost(
        intervention=_opt("pause_loading", estimated_time_to_effect_minutes=15),
        target_zone_id="pit_n",
        production_rate_tph=1200.0,
    )
    # 15min * 2 capped at 30 -> 0.5 hr * 1200 * 1.0 = 600 tonnes
    assert abs(out.estimated_tonnes_delayed - 600.0) < 1.0
    assert out.production_impact == "high"


def test_unknown_production_rate_degrades_confidence() -> None:
    m = HeuristicProductionCost()
    known = m.estimate_cost(
        intervention=_opt("reduce_speed"),
        target_zone_id="z",
        production_rate_tph=800.0,
    )
    unknown = m.estimate_cost(
        intervention=_opt("reduce_speed"),
        target_zone_id="z",
        production_rate_tph=None,
    )
    assert unknown.estimated_tonnes_delayed == 0.0
    assert unknown.confidence < known.confidence


def test_unknown_intervention_uses_default_coefficients() -> None:
    m = HeuristicProductionCost()
    out = m.estimate_cost(
        intervention=_opt("dance_for_rain"),
        target_zone_id="z",
        production_rate_tph=500.0,
    )
    assert out.production_impact == "low"
    assert out.estimated_tonnes_delayed > 0


def test_caller_supplied_duration_overrides_default() -> None:
    m = HeuristicProductionCost()
    short = m.estimate_cost(
        intervention=_opt("reduce_speed"),
        target_zone_id="z",
        production_rate_tph=600.0,
        duration_minutes=10,
    )
    long = m.estimate_cost(
        intervention=_opt("reduce_speed"),
        target_zone_id="z",
        production_rate_tph=600.0,
        duration_minutes=60,
    )
    assert long.estimated_tonnes_delayed > short.estimated_tonnes_delayed


def test_do_nothing_zero_tonnage_high_confidence() -> None:
    m = HeuristicProductionCost()
    out = m.estimate_cost(
        intervention=_opt(DO_NOTHING_INTERVENTION_ID, risk_class="low"),
        target_zone_id="z",
        production_rate_tph=1000.0,
    )
    assert out.estimated_tonnes_delayed == 0.0
    assert out.confidence >= 0.95
