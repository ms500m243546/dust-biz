"""Multi-zone joint optimization (Phase AD, Tension 3).

When N zones cross the breach threshold simultaneously, the prior
recommendation orchestrator emitted N independent recommendations
that could double-spend shared resources (one water truck assigned
to two haul roads, etc.). Phase AD adds a *joint* solver that
respects shared-resource constraints declared on the catalog
(`InterventionOption.resource_classes`).

Algorithm — first implementation: **greedy with conflict back-off**.

  1. Order zones by per-zone breach probability (highest first); ties
     broken by alphabetical zone_id for determinism.
  2. For each zone, walk its ranked candidates top-down. Pick the
     first one whose `resource_classes` don't overlap any resource
     already claimed by an earlier-ranked zone.
  3. If every candidate conflicts, fall back to the do-nothing
     baseline for that zone (always present, always resource-free
     by construction). Record a `conflict_resolution` audit row.

Greedy is the right first choice: cheap, deterministic, audit-
readable, and no solver dependency. MIP via PuLP / cvxpy can replace
this once we measure the optimality gap on real multi-zone data.

The solver is pure: takes per-zone ranked candidates + a resource
map, returns a JointResolution dataclass. Persistence is the
caller's job (matching the universal model rule from
`docs/model-contracts.md`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.optimization import RankedCandidate


@dataclass(frozen=True)
class ZoneCandidates:
    """Ranked candidate set for one zone, plus its breach probability.

    Mirrors the shape `WeightedOptimizationEngine.rank_actions` returns
    per-zone; the joint solver doesn't re-rank, it picks among already-
    ranked candidates.
    """

    zone_id: str
    breach_probability: float
    candidates: list[RankedCandidate]
    do_nothing_intervention_id: str = "do_nothing"


@dataclass(frozen=True)
class JointConflict:
    """Audit row for one zone whose top candidate was demoted."""

    zone_id: str
    preferred_intervention_id: str
    chosen_intervention_id: str
    conflicting_resource_classes: tuple[str, ...]
    conflicting_zone_id: str


@dataclass(frozen=True)
class JointResolution:
    """Final assignment + audit trail."""

    assignments: dict[str, RankedCandidate]
    conflicts: list[JointConflict] = field(default_factory=list)
    claimed_resources: dict[str, str] = field(default_factory=dict)


def solve_joint_recommendations(
    *,
    zone_candidates: list[ZoneCandidates],
    candidate_resource_classes: dict[str, list[str]],
) -> JointResolution:
    """Greedy joint assignment.

    `candidate_resource_classes` maps `intervention_id -> list of
    resource classes the action consumes`. Empty / missing entries
    mean no shared-resource constraint (the action can always run).
    """
    # Sort highest-breach-probability zones first so they get first
    # claim on shared resources. Ties broken by zone_id for
    # determinism.
    order = sorted(
        zone_candidates,
        key=lambda z: (-z.breach_probability, z.zone_id),
    )
    assignments: dict[str, RankedCandidate] = {}
    conflicts: list[JointConflict] = []
    claimed: dict[str, str] = {}  # resource_class -> zone_id

    for zone in order:
        chosen, conflict = _choose_for_zone(
            zone=zone,
            candidate_resource_classes=candidate_resource_classes,
            claimed=claimed,
        )
        if chosen is None:
            # No candidates at all (catalog empty for this zone). Skip
            # — there's nothing to assign.
            continue
        assignments[zone.zone_id] = chosen
        # Claim this candidate's resources.
        for cls in candidate_resource_classes.get(chosen.intervention_id, []):
            claimed.setdefault(cls, zone.zone_id)
        if conflict is not None:
            conflicts.append(conflict)
    return JointResolution(
        assignments=assignments,
        conflicts=conflicts,
        claimed_resources=dict(claimed),
    )


def _choose_for_zone(
    *,
    zone: ZoneCandidates,
    candidate_resource_classes: dict[str, list[str]],
    claimed: dict[str, str],
) -> tuple[RankedCandidate | None, JointConflict | None]:
    """Walk this zone's candidates top-down; pick the first non-conflict.

    Returns (chosen_candidate, conflict) where `conflict` is non-None
    iff the top-ranked candidate was demoted in favour of a
    non-conflicting alternative.
    """
    if not zone.candidates:
        return None, None

    preferred = zone.candidates[0]
    do_nothing_fallback: RankedCandidate | None = None
    for cand in zone.candidates:
        if cand.intervention_id == zone.do_nothing_intervention_id:
            do_nothing_fallback = cand
        resources = candidate_resource_classes.get(cand.intervention_id, []) or []
        conflicting = [c for c in resources if c in claimed]
        if conflicting:
            continue
        if cand is preferred:
            return cand, None
        # Demoted: surface the conflict that bumped the preferred pick.
        preferred_resources = candidate_resource_classes.get(
            preferred.intervention_id, []
        ) or []
        first_conflict = next(
            (c for c in preferred_resources if c in claimed), ""
        )
        conflict = JointConflict(
            zone_id=zone.zone_id,
            preferred_intervention_id=preferred.intervention_id,
            chosen_intervention_id=cand.intervention_id,
            conflicting_resource_classes=tuple(
                c for c in preferred_resources if c in claimed
            ),
            conflicting_zone_id=claimed.get(first_conflict, ""),
        )
        return cand, conflict

    # Every candidate conflicted. Fall back to the do-nothing baseline
    # if it was in the list (it always is, in normal flow); otherwise
    # surface no assignment.
    if do_nothing_fallback is not None:
        preferred_resources = candidate_resource_classes.get(
            preferred.intervention_id, []
        ) or []
        first_conflict = next(
            (c for c in preferred_resources if c in claimed), ""
        )
        conflict = JointConflict(
            zone_id=zone.zone_id,
            preferred_intervention_id=preferred.intervention_id,
            chosen_intervention_id=do_nothing_fallback.intervention_id,
            conflicting_resource_classes=tuple(
                c for c in preferred_resources if c in claimed
            ),
            conflicting_zone_id=claimed.get(first_conflict, ""),
        )
        return do_nothing_fallback, conflict
    return None, None


__all__ = [
    "JointConflict",
    "JointResolution",
    "ZoneCandidates",
    "solve_joint_recommendations",
]
