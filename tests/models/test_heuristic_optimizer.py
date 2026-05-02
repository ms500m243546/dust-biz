"""Weighted optimization engine tests.

Pin compliance-priority logic (G7), low-confidence handling (G6), and
production-vs-compliance trade-off behavior at all three breach
regimes from `safety-guardrails.md`.
"""

from datetime import UTC, datetime

from app.models.optimization.heuristic_baseline import (
    OPTIMIZER_VERSION,
    WeightedOptimizationEngine,
)
from app.schemas.simulations import (
    DO_NOTHING_INTERVENTION_ID,
    InterventionSimulationSchema,
)
from app.schemas.site_config import OptimizationWeightsSchema


def _sim(
    intervention_id: str,
    *,
    breach_after: float,
    tonnes: float = 200.0,
    cycle_pct: float = 5.0,
    impact: str = "low",
    confidence: float = 0.7,
) -> InterventionSimulationSchema:
    return InterventionSimulationSchema(
        simulation_id=f"SIM-{intervention_id}",
        requested_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        intervention_id=intervention_id,
        target_zone_id="haul_c",
        scenario=intervention_id,
        predicted_pm10_reduction=10.0,
        predicted_pm25_reduction=4.0,
        breach_probability_before=0.7,
        breach_probability_after=breach_after,
        time_to_effect_minutes=10,
        production_loss_tonnes=tonnes,
        cycle_time_increase_percent=cycle_pct,
        production_impact=impact,  # type: ignore[arg-type]
        confidence=confidence,
        model_version="intervention_impact_heuristic_v0.1.0",
        cost_model_version="production_cost_heuristic_v0.1.0",
        source="heuristic",
    )


def _weights(**overrides: float) -> OptimizationWeightsSchema:
    return OptimizationWeightsSchema(**overrides)


def test_top_pick_is_strongest_breach_reduction_at_low_cost() -> None:
    eng = WeightedOptimizationEngine()
    cands = [
        _sim("water_road", breach_after=0.45, tonnes=50, impact="low"),
        _sim("reroute_trucks", breach_after=0.30, tonnes=520, impact="medium"),
        _sim(DO_NOTHING_INTERVENTION_ID, breach_after=0.7, tonnes=0, impact="low"),
    ]
    out = eng.rank_actions(
        target_zone_id="haul_c",
        breach_probability_before=0.7,
        candidates=cands,
        candidate_risk_classes={
            "water_road": "medium",
            "reroute_trucks": "high",
            DO_NOTHING_INTERVENTION_ID: "low",
        },
        candidate_requires_approval={
            "water_road": True,
            "reroute_trucks": True,
            DO_NOTHING_INTERVENTION_ID: False,
        },
        weights=_weights(),
    )
    # water_road is the production-cheap moderate-breach winner.
    assert out.candidates[0].intervention_id == "water_road"
    assert out.model_version == OPTIMIZER_VERSION


def test_compliance_priority_kicks_in_above_extreme_threshold() -> None:
    eng = WeightedOptimizationEngine()
    cands = [
        _sim("water_road", breach_after=0.50, tonnes=50, impact="low"),
        _sim("pause_loading", breach_after=0.20, tonnes=900, impact="high"),
    ]
    out = eng.rank_actions(
        target_zone_id="haul_c",
        breach_probability_before=0.92,
        candidates=cands,
        candidate_risk_classes={"water_road": "medium", "pause_loading": "high"},
        candidate_requires_approval={"water_road": True, "pause_loading": True},
        weights=_weights(),
    )
    assert out.compliance_priority_triggered is True
    assert "compliance prioritized over production" in out.overall_reason.lower()
    # Under extreme breach, the heavier action wins despite cost.
    assert out.candidates[0].intervention_id == "pause_loading"


def test_compliance_not_triggered_below_extreme() -> None:
    eng = WeightedOptimizationEngine()
    cands = [_sim("water_road", breach_after=0.40, tonnes=50)]
    out = eng.rank_actions(
        target_zone_id="haul_c",
        breach_probability_before=0.6,
        candidates=cands,
        candidate_risk_classes={"water_road": "medium"},
        candidate_requires_approval={"water_road": True},
        weights=_weights(),
    )
    assert out.compliance_priority_triggered is False


def test_low_confidence_threshold_marks_review() -> None:
    eng = WeightedOptimizationEngine()
    cands = [
        _sim("water_road", breach_after=0.45, confidence=0.30),
        _sim("reduce_speed", breach_after=0.50, confidence=0.40),
    ]
    out = eng.rank_actions(
        target_zone_id="haul_c",
        breach_probability_before=0.7,
        candidates=cands,
        candidate_risk_classes={"water_road": "medium", "reduce_speed": "medium"},
        candidate_requires_approval={"water_road": True, "reduce_speed": True},
        weights=_weights(),
    )
    assert out.requires_human_review is True


def test_one_high_confidence_candidate_clears_review_flag() -> None:
    eng = WeightedOptimizationEngine()
    cands = [
        _sim("water_road", breach_after=0.45, confidence=0.30),  # below threshold
        _sim("reduce_speed", breach_after=0.50, confidence=0.80),
    ]
    out = eng.rank_actions(
        target_zone_id="haul_c",
        breach_probability_before=0.7,
        candidates=cands,
        candidate_risk_classes={"water_road": "medium", "reduce_speed": "medium"},
        candidate_requires_approval={"water_road": True, "reduce_speed": True},
        weights=_weights(),
    )
    assert out.requires_human_review is False


def test_target_probability_drops_to_025_under_extreme() -> None:
    eng = WeightedOptimizationEngine()
    out = eng.rank_actions(
        target_zone_id="haul_c",
        breach_probability_before=0.95,
        candidates=[_sim("water_road", breach_after=0.5)],
        candidate_risk_classes={"water_road": "medium"},
        candidate_requires_approval={"water_road": True},
        weights=_weights(),
    )
    assert out.target_probability == 0.25


def test_target_probability_relaxes_below_extreme() -> None:
    eng = WeightedOptimizationEngine()
    out = eng.rank_actions(
        target_zone_id="haul_c",
        breach_probability_before=0.6,
        candidates=[_sim("water_road", breach_after=0.4)],
        candidate_risk_classes={"water_road": "medium"},
        candidate_requires_approval={"water_road": True},
        weights=_weights(),
    )
    # 0.6 - 0.30 = 0.30
    assert abs(out.target_probability - 0.30) < 0.01


def test_no_candidates_returns_no_actions_message() -> None:
    eng = WeightedOptimizationEngine()
    out = eng.rank_actions(
        target_zone_id="haul_c",
        breach_probability_before=0.7,
        candidates=[],
        candidate_risk_classes={},
        candidate_requires_approval={},
        weights=_weights(),
    )
    assert out.candidates == []
    assert "no actionable" in out.overall_reason.lower()


def test_extreme_regime_caps_overall_confidence_at_085() -> None:
    eng = WeightedOptimizationEngine()
    out = eng.rank_actions(
        target_zone_id="haul_c",
        breach_probability_before=0.92,
        candidates=[_sim("water_road", breach_after=0.5, confidence=0.95)],
        candidate_risk_classes={"water_road": "medium"},
        candidate_requires_approval={"water_road": True},
        weights=_weights(),
    )
    assert out.overall_confidence <= 0.85
