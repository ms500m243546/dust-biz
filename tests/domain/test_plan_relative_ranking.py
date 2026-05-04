"""Phase AA — plan-relative cost ranking tests.

Pure-function tests: same simulations, different shift_progress, must
yield different rankings. The shift_progress live-mode + recommendation
orchestrator wiring is exercised by the integration suite.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.models.optimization.heuristic_baseline import (
    PLAN_RELATIVE_ABSORBABLE_FRAC,
    PLAN_RELATIVE_BLOCKING_FRAC,
    SHIFT_SLACK_MAX,
    SHIFT_SLACK_MIN,
    WeightedOptimizationEngine,
)
from app.schemas.shift_progress import ShiftProgressSchema
from app.schemas.simulations import InterventionSimulationSchema
from app.schemas.site_config import OptimizationWeightsSchema


def _sim(
    *,
    intervention_id: str,
    breach_after: float,
    tonnes: float,
) -> InterventionSimulationSchema:
    return InterventionSimulationSchema(
        simulation_id=f"SIM-{intervention_id}",
        requested_at=datetime(2026, 5, 3, 12, 0, tzinfo=UTC),
        intervention_id=intervention_id,
        target_zone_id="zone-A",
        scenario=intervention_id,
        predicted_pm10_reduction=20.0,
        breach_probability_before=0.7,
        breach_probability_after=breach_after,
        time_to_effect_minutes=10,
        production_loss_tonnes=tonnes,
        cycle_time_increase_percent=5.0,
        production_impact="medium",
        confidence=0.8,
        model_version="ap42_test",
        cost_model_version="cost_test",
    )


def _progress(*, slack_ratio: float) -> ShiftProgressSchema:
    return ShiftProgressSchema(
        mine_id="aa-mine",
        shift_start=datetime(2026, 5, 3, 0, 0),
        now=datetime(2026, 5, 3, 6, 0),
        hours_elapsed=6.0,
        hours_remaining=6.0,
        target_tonnes_per_hour=200.0,
        shift_target_tonnes=2400.0,
        tonnes_done=200.0 * 6.0 * slack_ratio,
        expected_done=1200.0,
        slack_ratio=slack_ratio,
        source="synthetic",
    )


def _engine() -> WeightedOptimizationEngine:
    return WeightedOptimizationEngine()


def _weights() -> OptimizationWeightsSchema:
    return OptimizationWeightsSchema()


def test_behind_plan_inflates_production_weight() -> None:
    # cheap_small: small breach drop, tiny cost.
    # expensive_big: big breach drop, sizeable cost.
    # On plan, expensive_big wins via w_breach. Behind plan (slack=0.3),
    # production weight is multiplied by ~3.3 — cheap_small overtakes.
    # Keep breach_before in the balanced regime (<0.5) so the elevated/
    # extreme compliance multipliers don't muddy the slack-rescale signal.
    cheap_small = _sim(
        intervention_id="cheap_small", breach_after=0.32, tonnes=10.0
    )
    expensive_big = _sim(
        intervention_id="expensive_big", breach_after=0.05, tonnes=200.0
    )
    on_plan = _engine().rank_actions(
        target_zone_id="zone-A",
        breach_probability_before=0.40,
        candidates=[cheap_small, expensive_big],
        candidate_risk_classes={"cheap_small": "low", "expensive_big": "high"},
        candidate_requires_approval={"cheap_small": False, "expensive_big": True},
        weights=_weights(),
        shift_progress=_progress(slack_ratio=1.0),
    )
    behind = _engine().rank_actions(
        target_zone_id="zone-A",
        breach_probability_before=0.40,
        candidates=[cheap_small, expensive_big],
        candidate_risk_classes={"cheap_small": "low", "expensive_big": "high"},
        candidate_requires_approval={"cheap_small": False, "expensive_big": True},
        weights=_weights(),
        shift_progress=_progress(slack_ratio=0.3),
    )
    assert on_plan.candidates[0].intervention_id == "expensive_big"
    assert behind.candidates[0].intervention_id == "cheap_small"
    assert behind.shift_slack_ratio == 0.3


def test_ahead_of_plan_deflates_production_weight() -> None:
    # cheap: small breach drop, tiny cost — wins on plan.
    # big_drop: bigger breach drop but enough cost to lose on plan.
    # Way ahead of plan (slack=2.5), production cost matters less; the
    # ranker should now prefer big_drop.
    cheap = _sim(intervention_id="cheap", breach_after=0.30, tonnes=10.0)
    big_drop = _sim(intervention_id="big_drop", breach_after=0.10, tonnes=400.0)
    on_plan = _engine().rank_actions(
        target_zone_id="zone-A",
        breach_probability_before=0.40,
        candidates=[cheap, big_drop],
        candidate_risk_classes={"cheap": "low", "big_drop": "medium"},
        candidate_requires_approval={"cheap": False, "big_drop": True},
        weights=_weights(),
        shift_progress=_progress(slack_ratio=1.0),
    )
    ahead = _engine().rank_actions(
        target_zone_id="zone-A",
        breach_probability_before=0.40,
        candidates=[cheap, big_drop],
        candidate_risk_classes={"cheap": "low", "big_drop": "medium"},
        candidate_requires_approval={"cheap": False, "big_drop": True},
        weights=_weights(),
        shift_progress=_progress(slack_ratio=2.5),
    )
    assert on_plan.candidates[0].intervention_id == "cheap"
    assert ahead.candidates[0].intervention_id == "big_drop"
    assert ahead.shift_slack_ratio == 2.5


def test_plan_relative_loss_label_thresholds() -> None:
    # absorbable: relative ≤ 0.03; partial: 0.03..0.10; blocking: ≥ 0.10
    # at slack_ratio=1.0 the multiplier is 1, so relative = tonnes / 2400.
    absorbable = _sim(
        intervention_id="absorbable",
        breach_after=0.60,
        tonnes=2400.0 * (PLAN_RELATIVE_ABSORBABLE_FRAC - 0.005),
    )
    partial = _sim(
        intervention_id="partial",
        breach_after=0.55,
        tonnes=2400.0 * 0.06,
    )
    blocking = _sim(
        intervention_id="blocking",
        breach_after=0.50,
        tonnes=2400.0 * (PLAN_RELATIVE_BLOCKING_FRAC + 0.005),
    )
    out = _engine().rank_actions(
        target_zone_id="zone-A",
        breach_probability_before=0.7,
        candidates=[absorbable, partial, blocking],
        candidate_risk_classes={
            "absorbable": "low", "partial": "medium", "blocking": "high"
        },
        candidate_requires_approval={
            "absorbable": False, "partial": True, "blocking": True
        },
        weights=_weights(),
        shift_progress=_progress(slack_ratio=1.0),
    )
    by_id = {c.intervention_id: c for c in out.candidates}
    assert by_id["absorbable"].plan_relative_loss == "absorbable"
    assert by_id["partial"].plan_relative_loss == "partial"
    assert by_id["blocking"].plan_relative_loss == "blocking"


def test_no_shift_progress_disables_rescale_and_label() -> None:
    sim = _sim(intervention_id="x", breach_after=0.5, tonnes=200.0)
    out = _engine().rank_actions(
        target_zone_id="zone-A",
        breach_probability_before=0.7,
        candidates=[sim],
        candidate_risk_classes={"x": "low"},
        candidate_requires_approval={"x": False},
        weights=_weights(),
        shift_progress=None,
    )
    assert out.shift_slack_ratio is None
    assert out.candidates[0].plan_relative_loss is None


def test_extreme_slack_ratios_clamped() -> None:
    # slack=0.001 must NOT inflate w_production by 1000x. Clamps cap
    # the multiplier at 1/SHIFT_SLACK_MIN.
    sim = _sim(intervention_id="x", breach_after=0.5, tonnes=200.0)
    out = _engine().rank_actions(
        target_zone_id="zone-A",
        breach_probability_before=0.7,
        candidates=[sim],
        candidate_risk_classes={"x": "low"},
        candidate_requires_approval={"x": False},
        weights=_weights(),
        shift_progress=_progress(slack_ratio=0.001),
    )
    # The rescale ran but did not blow up — the candidate still has a
    # finite score and a label assigned. (We don't assert on the
    # multiplier value directly; we assert the system stayed sane.)
    assert out.candidates[0].plan_relative_loss is not None
    # Sanity-check the constants haven't drifted:
    assert SHIFT_SLACK_MIN > 0
    assert SHIFT_SLACK_MAX > SHIFT_SLACK_MIN
