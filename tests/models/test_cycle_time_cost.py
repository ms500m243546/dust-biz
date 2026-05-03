"""Phase U.1 — CycleTimeProductionCost model tests."""

from __future__ import annotations

import pytest

from app.models.cost.cycle_time_v0_1_0 import (
    CYCLE_TIME_VERSION,
    CycleTimeProductionCost,
)
from app.schemas.interventions import InterventionOptionSchema
from app.schemas.simulations import DO_NOTHING_INTERVENTION_ID


def _option(intervention_id: str) -> InterventionOptionSchema:
    return InterventionOptionSchema(
        intervention_id=intervention_id,
        name=intervention_id.replace("_", " "),
        description="test",
        risk_class="low",
        requires_human_approval=False,
        automation_eligible_levels=["L1"],
        estimated_time_to_effect_minutes=10,
        allowed_zone_types=["haul_road"],
    )


def test_kind_and_version() -> None:
    m = CycleTimeProductionCost()
    assert m.model_kind == "production_cost"
    assert m.model_version == CYCLE_TIME_VERSION


def test_reduce_speed_uses_physics_cycle_increase() -> None:
    m = CycleTimeProductionCost()
    out = m.estimate_cost(
        intervention=_option("reduce_speed"),
        target_zone_id="z",
        production_rate_tph=1000.0,
        duration_minutes=60,
    )
    # 50→25 km/h doubles cycle → 100% cycle_time_increase_percent
    assert out.cycle_time_increase_percent == pytest.approx(100.0, rel=1e-3)
    assert out.estimated_tonnes_delayed > 0


def test_water_road_uses_physics_cycle_increase() -> None:
    m = CycleTimeProductionCost()
    out = m.estimate_cost(
        intervention=_option("water_road"),
        target_zone_id="z",
        production_rate_tph=1000.0,
        duration_minutes=60,
    )
    # Default fleet=8 trucks, window=8 min, baseline=180s
    # → 8*60/(180*8) = 0.333... → 33.33%
    assert out.cycle_time_increase_percent > 0
    assert out.cycle_time_increase_percent < 100  # smaller than reduce_speed


def test_unknown_intervention_falls_back_to_heuristic_coeff() -> None:
    m = CycleTimeProductionCost()
    out = m.estimate_cost(
        intervention=_option("throttle_crusher"),
        target_zone_id="z",
        production_rate_tph=1000.0,
        duration_minutes=60,
    )
    # Heuristic baseline says throttle_crusher cycle_time_pct = 0
    # (it's a throughput effect, not a cycle effect).
    assert out.cycle_time_increase_percent == 0.0


def test_do_nothing_returns_zero() -> None:
    m = CycleTimeProductionCost()
    out = m.estimate_cost(
        intervention=_option(DO_NOTHING_INTERVENTION_ID),
        target_zone_id="z",
        production_rate_tph=1000.0,
        duration_minutes=60,
    )
    assert out.estimated_tonnes_delayed == 0.0
    assert out.cycle_time_increase_percent == 0.0
    assert out.confidence == 0.99


def test_no_production_rate_zeroes_tonnes_and_lowers_confidence() -> None:
    m = CycleTimeProductionCost()
    out = m.estimate_cost(
        intervention=_option("reduce_speed"),
        target_zone_id="z",
        production_rate_tph=None,
        duration_minutes=60,
    )
    assert out.estimated_tonnes_delayed == 0.0
    assert out.confidence < 0.5  # baseline reduced by 0.30


def test_tonnes_scale_with_production_rate() -> None:
    m = CycleTimeProductionCost()
    low = m.estimate_cost(
        intervention=_option("reduce_speed"),
        target_zone_id="z",
        production_rate_tph=500.0,
        duration_minutes=60,
    )
    high = m.estimate_cost(
        intervention=_option("reduce_speed"),
        target_zone_id="z",
        production_rate_tph=2000.0,
        duration_minutes=60,
    )
    assert high.estimated_tonnes_delayed > low.estimated_tonnes_delayed
