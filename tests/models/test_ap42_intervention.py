"""Phase R.1 — AP-42 intervention impact model tests."""

from __future__ import annotations

import pytest

from app.models.intervention.ap42_v0_1_0 import (
    AP42_VERSION,
    AP42InterventionImpact,
)
from app.models.intervention.heuristic_baseline import (
    PM10_REDUCTION_FRACTION,
)
from app.schemas.interventions import InterventionOptionSchema
from app.schemas.simulations import DO_NOTHING_INTERVENTION_ID


def _option(intervention_id: str, *, risk: str = "low") -> InterventionOptionSchema:
    return InterventionOptionSchema(
        intervention_id=intervention_id,
        name=intervention_id.replace("_", " "),
        description="test",
        risk_class=risk,  # type: ignore[arg-type]
        requires_human_approval=False,
        automation_eligible_levels=["L1"],
        estimated_time_to_effect_minutes=10,
        allowed_zone_types=["haul_road"],
    )


def test_model_kind_and_version() -> None:
    m = AP42InterventionImpact()
    assert m.model_kind == "intervention_impact"
    assert m.model_version == AP42_VERSION


def test_water_road_uses_physics_path_source_model() -> None:
    m = AP42InterventionImpact()
    out = m.simulate(
        intervention=_option("water_road"),
        target_zone_id="z",
        predicted_pm10=100.0,
        predicted_pm25=40.0,
        breach_probability_before=0.4,
    )
    assert out.source == "model"
    assert out.predicted_pm10_reduction > 0
    # Physics-informed reduction should be in the watering empirical
    # range — at t=0 with default meteo, ~55% per WATERING_BASE_REDUCTION.
    assert 0.40 <= (out.predicted_pm10_reduction / 100.0) <= 0.60


def test_reduce_speed_uses_physics_path_source_model() -> None:
    m = AP42InterventionImpact()
    out = m.simulate(
        intervention=_option("reduce_speed"),
        target_zone_id="z",
        predicted_pm10=100.0,
        predicted_pm25=40.0,
        breach_probability_before=0.4,
    )
    assert out.source == "model"
    # 50 → 25 km/h cuts ~29% of emission per AP-42 speed exponent.
    assert 0.25 <= (out.predicted_pm10_reduction / 100.0) <= 0.32


def test_unknown_intervention_falls_back_to_heuristic_source() -> None:
    m = AP42InterventionImpact()
    out = m.simulate(
        intervention=_option("throttle_crusher"),
        target_zone_id="z",
        predicted_pm10=100.0,
        predicted_pm25=40.0,
        breach_probability_before=0.4,
    )
    assert out.source == "heuristic"
    expected = PM10_REDUCTION_FRACTION["throttle_crusher"] * 100.0
    assert pytest.approx(out.predicted_pm10_reduction, rel=1e-6) == expected


def test_do_nothing_returns_zero_reduction() -> None:
    m = AP42InterventionImpact()
    out = m.simulate(
        intervention=_option(DO_NOTHING_INTERVENTION_ID),
        target_zone_id="z",
        predicted_pm10=100.0,
        predicted_pm25=40.0,
        breach_probability_before=0.4,
    )
    assert out.predicted_pm10_reduction == 0.0
    assert out.predicted_pm25_reduction == 0.0
    assert out.breach_probability_after_action == out.breach_probability_before
    assert out.confidence == 0.95


def test_pm25_scales_with_pm10_reduction() -> None:
    m = AP42InterventionImpact()
    out = m.simulate(
        intervention=_option("water_road"),
        target_zone_id="z",
        predicted_pm10=100.0,
        predicted_pm25=40.0,
        breach_probability_before=0.4,
    )
    # PM2.5 reduction should be slightly less than PM10 reduction
    # (scaled by 0.85 per the heuristic-baseline contract).
    assert out.predicted_pm25_reduction is not None
    expected_pm25 = out.predicted_pm10_reduction / 100.0 * 40.0 * 0.85
    assert pytest.approx(out.predicted_pm25_reduction, rel=1e-3) == round(expected_pm25, 3)


def test_breach_probability_scales_with_reduction() -> None:
    m = AP42InterventionImpact()
    out = m.simulate(
        intervention=_option("water_road"),
        target_zone_id="z",
        predicted_pm10=100.0,
        predicted_pm25=40.0,
        breach_probability_before=0.6,
    )
    assert out.breach_probability_after_action < out.breach_probability_before
