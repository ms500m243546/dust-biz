"""Phase Z — attribution-coupled ranking tests.

Pure-function tests over the optimizer extension. The recommendation
orchestrator wiring is exercised by the existing recommendation
integration suite.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.models.optimization.heuristic_baseline import (
    WeightedOptimizationEngine,
)
from app.schemas.simulations import InterventionSimulationSchema
from app.schemas.site_config import OptimizationWeightsSchema


def _sim(
    *,
    intervention_id: str,
    breach_after: float,
    tonnes: float = 100.0,
    confidence: float = 0.8,
) -> InterventionSimulationSchema:
    return InterventionSimulationSchema(
        simulation_id=f"SIM-{intervention_id}",
        requested_at=datetime(2026, 5, 3, 12, 0, tzinfo=UTC),
        intervention_id=intervention_id,
        target_zone_id="zone-A",
        scenario=f"run {intervention_id}",
        predicted_pm10_reduction=20.0,
        breach_probability_before=0.7,
        breach_probability_after=breach_after,
        time_to_effect_minutes=10,
        production_loss_tonnes=tonnes,
        cycle_time_increase_percent=5.0,
        production_impact="medium",
        confidence=confidence,
        model_version="ap42_test",
        cost_model_version="cost_test",
    )


def _weights(*, w_cause_match: float = 0.3) -> OptimizationWeightsSchema:
    return OptimizationWeightsSchema(
        w_breach=1.0,
        w_production=1.0,
        w_disruption=0.5,
        w_low_confidence=0.5,
        w_compliance=1.0,
        w_cause_match=w_cause_match,
    )


def _engine() -> WeightedOptimizationEngine:
    return WeightedOptimizationEngine()


def test_cause_match_flips_rank_between_two_otherwise_tied_candidates() -> None:
    # A and B simulate to identical breach reductions and identical cost.
    # Without a cause class, they tie. With cause_class="haul_road" and
    # only A targeting haul_road, A must win.
    a = _sim(intervention_id="water_road", breach_after=0.4)
    b = _sim(intervention_id="throttle_crusher", breach_after=0.4)
    cause_classes = {
        "water_road": ["haul_road"],
        "throttle_crusher": ["crusher"],
    }
    engine = _engine()
    no_cause = engine.rank_actions(
        target_zone_id="zone-A",
        breach_probability_before=0.7,
        candidates=[a, b],
        candidate_risk_classes={"water_road": "medium", "throttle_crusher": "high"},
        candidate_requires_approval={"water_road": True, "throttle_crusher": True},
        weights=_weights(),
        candidate_target_cause_classes=cause_classes,
    )
    with_cause = engine.rank_actions(
        target_zone_id="zone-A",
        breach_probability_before=0.7,
        candidates=[a, b],
        candidate_risk_classes={"water_road": "medium", "throttle_crusher": "high"},
        candidate_requires_approval={"water_road": True, "throttle_crusher": True},
        weights=_weights(),
        cause_class="haul_road",
        candidate_target_cause_classes=cause_classes,
    )
    # Without cause: top is whichever sort happens to surface first
    # (deterministic but not the assertion's interest). With cause:
    # water_road must be top and tagged cause_targeted.
    assert with_cause.candidates[0].intervention_id == "water_road"
    assert with_cause.candidates[0].cause_targeted is True
    assert with_cause.candidates[1].intervention_id == "throttle_crusher"
    assert with_cause.candidates[1].cause_targeted is False
    assert with_cause.cause_class == "haul_road"
    assert no_cause.cause_class is None


def test_cause_match_does_not_boost_when_no_breach_drop() -> None:
    # A "cause-targeted" candidate that doesn't actually reduce breach
    # must NOT outscore a non-targeted candidate that does. Otherwise
    # the boost becomes a backdoor for ineffective do-nothing actions.
    a_targeted_no_drop = _sim(intervention_id="water_road", breach_after=0.7)
    b_untargeted_drop = _sim(
        intervention_id="throttle_crusher", breach_after=0.4
    )
    cause_classes = {
        "water_road": ["haul_road"],
        "throttle_crusher": [],
    }
    engine = _engine()
    out = engine.rank_actions(
        target_zone_id="zone-A",
        breach_probability_before=0.7,
        candidates=[a_targeted_no_drop, b_untargeted_drop],
        candidate_risk_classes={"water_road": "medium", "throttle_crusher": "high"},
        candidate_requires_approval={"water_road": True, "throttle_crusher": True},
        weights=_weights(w_cause_match=10.0),  # large boost — must still lose
        cause_class="haul_road",
        candidate_target_cause_classes=cause_classes,
    )
    assert out.candidates[0].intervention_id == "throttle_crusher"


def test_no_cause_class_means_no_boost_for_anyone() -> None:
    a = _sim(intervention_id="water_road", breach_after=0.4)
    b = _sim(intervention_id="throttle_crusher", breach_after=0.4)
    cause_classes = {
        "water_road": ["haul_road"],
        "throttle_crusher": ["crusher"],
    }
    out = _engine().rank_actions(
        target_zone_id="zone-A",
        breach_probability_before=0.7,
        candidates=[a, b],
        candidate_risk_classes={"water_road": "medium", "throttle_crusher": "high"},
        candidate_requires_approval={"water_road": True, "throttle_crusher": True},
        weights=_weights(),
        cause_class=None,
        candidate_target_cause_classes=cause_classes,
    )
    assert all(c.cause_targeted is False for c in out.candidates)


def test_w_cause_match_zero_disables_cause_coupling() -> None:
    # Operators can switch cause-coupling off per-site by zeroing the
    # weight; the boost must vanish even when target classes match.
    a = _sim(intervention_id="water_road", breach_after=0.4)
    b = _sim(intervention_id="throttle_crusher", breach_after=0.39)
    out = _engine().rank_actions(
        target_zone_id="zone-A",
        breach_probability_before=0.7,
        candidates=[a, b],
        candidate_risk_classes={"water_road": "medium", "throttle_crusher": "high"},
        candidate_requires_approval={"water_road": True, "throttle_crusher": True},
        weights=_weights(w_cause_match=0.0),
        cause_class="haul_road",
        candidate_target_cause_classes={
            "water_road": ["haul_road"],
            "throttle_crusher": [],
        },
    )
    # throttle_crusher has the larger breach drop; with the boost off,
    # it must beat water_road.
    assert out.candidates[0].intervention_id == "throttle_crusher"


def test_cause_match_reason_line_surfaces_class() -> None:
    a = _sim(intervention_id="water_road", breach_after=0.4)
    out = _engine().rank_actions(
        target_zone_id="zone-A",
        breach_probability_before=0.7,
        candidates=[a],
        candidate_risk_classes={"water_road": "medium"},
        candidate_requires_approval={"water_road": True},
        weights=_weights(),
        cause_class="haul_road",
        candidate_target_cause_classes={"water_road": ["haul_road"]},
    )
    top = out.candidates[0]
    assert top.cause_targeted
    assert "cause-targeted (haul_road)" in top.reason


def test_unmatched_cause_class_leaves_everyone_neutral() -> None:
    a = _sim(intervention_id="water_road", breach_after=0.4)
    b = _sim(intervention_id="throttle_crusher", breach_after=0.4)
    out = _engine().rank_actions(
        target_zone_id="zone-A",
        breach_probability_before=0.7,
        candidates=[a, b],
        candidate_risk_classes={"water_road": "medium", "throttle_crusher": "high"},
        candidate_requires_approval={"water_road": True, "throttle_crusher": True},
        weights=_weights(),
        cause_class="dump",  # nothing in catalog targets dump
        candidate_target_cause_classes={
            "water_road": ["haul_road"],
            "throttle_crusher": ["crusher"],
        },
    )
    assert all(c.cause_targeted is False for c in out.candidates)
    assert out.cause_class == "dump"
