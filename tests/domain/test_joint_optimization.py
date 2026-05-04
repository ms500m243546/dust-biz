"""Phase AD — joint optimization tests."""

from __future__ import annotations

from app.domain.joint_optimization import (
    ZoneCandidates,
    solve_joint_recommendations,
)
from app.schemas.optimization import RankedCandidate


def _cand(
    *,
    rank: int,
    intervention_id: str,
    score: float = 1.0,
    breach_after: float = 0.3,
) -> RankedCandidate:
    return RankedCandidate(
        rank=rank,
        intervention_id=intervention_id,
        simulation_id=f"SIM-{intervention_id}",
        score=score,
        breach_probability_after=breach_after,
        estimated_tonnes_delayed=10.0,
        production_loss="low",
        confidence=0.8,
        reason="x",
        risk_class="low",
        requires_human_approval=False,
    )


def test_no_conflict_each_zone_gets_top_pick() -> None:
    z1 = ZoneCandidates(
        zone_id="zone-A",
        breach_probability=0.7,
        candidates=[
            _cand(rank=1, intervention_id="water_road_A"),
            _cand(rank=2, intervention_id="do_nothing"),
        ],
    )
    z2 = ZoneCandidates(
        zone_id="zone-B",
        breach_probability=0.6,
        candidates=[
            _cand(rank=1, intervention_id="throttle_crusher_B"),
            _cand(rank=2, intervention_id="do_nothing"),
        ],
    )
    out = solve_joint_recommendations(
        zone_candidates=[z1, z2],
        candidate_resource_classes={
            "water_road_A": ["water_truck_fleet"],
            "throttle_crusher_B": ["primary_crusher"],
        },
    )
    assert out.assignments["zone-A"].intervention_id == "water_road_A"
    assert out.assignments["zone-B"].intervention_id == "throttle_crusher_B"
    assert out.conflicts == []


def test_conflicting_resource_demotes_lower_priority_zone() -> None:
    # Both zones want water_road; only one water_truck_fleet exists.
    # Higher breach_probability wins; loser falls back to do_nothing.
    z_high = ZoneCandidates(
        zone_id="zone-high",
        breach_probability=0.9,
        candidates=[
            _cand(rank=1, intervention_id="water_road_high"),
            _cand(rank=2, intervention_id="do_nothing"),
        ],
    )
    z_low = ZoneCandidates(
        zone_id="zone-low",
        breach_probability=0.6,
        candidates=[
            _cand(rank=1, intervention_id="water_road_low"),
            _cand(rank=2, intervention_id="do_nothing"),
        ],
    )
    out = solve_joint_recommendations(
        zone_candidates=[z_low, z_high],
        candidate_resource_classes={
            "water_road_high": ["water_truck_fleet"],
            "water_road_low": ["water_truck_fleet"],
        },
    )
    assert out.assignments["zone-high"].intervention_id == "water_road_high"
    assert out.assignments["zone-low"].intervention_id == "do_nothing"
    assert len(out.conflicts) == 1
    conflict = out.conflicts[0]
    assert conflict.zone_id == "zone-low"
    assert conflict.preferred_intervention_id == "water_road_low"
    assert conflict.chosen_intervention_id == "do_nothing"
    assert conflict.conflicting_zone_id == "zone-high"
    assert "water_truck_fleet" in conflict.conflicting_resource_classes


def test_demotes_to_non_conflicting_alternative_not_do_nothing() -> None:
    # Zone-low's top conflicts on a resource, but its second option is
    # resource-free → should pick that, not jump straight to do_nothing.
    z_high = ZoneCandidates(
        zone_id="zone-high",
        breach_probability=0.9,
        candidates=[_cand(rank=1, intervention_id="water_road_high")],
    )
    z_low = ZoneCandidates(
        zone_id="zone-low",
        breach_probability=0.6,
        candidates=[
            _cand(rank=1, intervention_id="water_road_low"),
            _cand(rank=2, intervention_id="reduce_speed_low"),
            _cand(rank=3, intervention_id="do_nothing"),
        ],
    )
    out = solve_joint_recommendations(
        zone_candidates=[z_high, z_low],
        candidate_resource_classes={
            "water_road_high": ["water_truck_fleet"],
            "water_road_low": ["water_truck_fleet"],
            "reduce_speed_low": [],  # resource-free
        },
    )
    assert out.assignments["zone-low"].intervention_id == "reduce_speed_low"
    assert len(out.conflicts) == 1
    assert out.conflicts[0].chosen_intervention_id == "reduce_speed_low"


def test_higher_breach_probability_gets_priority_regardless_of_input_order() -> None:
    # Input order should not change the result — deterministic via
    # breach_probability sort.
    z_high = ZoneCandidates(
        zone_id="zone-high",
        breach_probability=0.85,
        candidates=[_cand(rank=1, intervention_id="x_high")],
    )
    z_low = ZoneCandidates(
        zone_id="zone-low",
        breach_probability=0.55,
        candidates=[_cand(rank=1, intervention_id="x_low"), _cand(rank=2, intervention_id="do_nothing")],
    )
    res_map = {
        "x_high": ["pool"],
        "x_low": ["pool"],
    }
    a = solve_joint_recommendations(
        zone_candidates=[z_low, z_high], candidate_resource_classes=res_map
    )
    b = solve_joint_recommendations(
        zone_candidates=[z_high, z_low], candidate_resource_classes=res_map
    )
    assert a.assignments["zone-high"].intervention_id == "x_high"
    assert b.assignments["zone-high"].intervention_id == "x_high"
    assert a.assignments["zone-low"].intervention_id == "do_nothing"
    assert b.assignments["zone-low"].intervention_id == "do_nothing"


def test_resource_free_actions_never_conflict() -> None:
    # Two zones both running do_nothing (resource-free) — both succeed
    # with no conflict noise.
    z1 = ZoneCandidates(
        zone_id="zone-A",
        breach_probability=0.7,
        candidates=[_cand(rank=1, intervention_id="do_nothing")],
    )
    z2 = ZoneCandidates(
        zone_id="zone-B",
        breach_probability=0.6,
        candidates=[_cand(rank=1, intervention_id="do_nothing")],
    )
    out = solve_joint_recommendations(
        zone_candidates=[z1, z2],
        candidate_resource_classes={"do_nothing": []},
    )
    assert out.conflicts == []
    assert "zone-A" in out.assignments and "zone-B" in out.assignments


def test_empty_input_returns_empty_resolution() -> None:
    out = solve_joint_recommendations(
        zone_candidates=[], candidate_resource_classes={}
    )
    assert out.assignments == {}
    assert out.conflicts == []
    assert out.claimed_resources == {}
