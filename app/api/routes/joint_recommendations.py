"""Phase BD.4 — multi-zone joint-recommendation endpoint.

POST /api/v1/recommendations/joint
    body: { target_zone_ids: [zone_a, zone_b, ...] }
    response: {
        recommendations: [...],         # one per zone, the standard schema
        conflicts: [...],               # which zone got demoted on which resource
        claimed_resources: {...}        # resource_class -> winning zone
    }

When two or more zones cross the breach threshold simultaneously, the
solver respects the catalog's `resource_classes` so a single water
truck cannot be assigned to two haul roads in the same call. Phase AD
shipped the solver; BD.4 wires the route.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies.auth import current_user
from app.api.deps import get_session
from app.domain.joint_optimization import (
    JointConflict,
    ZoneCandidates,
    solve_joint_recommendations,
)
from app.domain.recommendations import (
    NoForecastError,
    ZoneNotFoundError,
    generate_recommendation,
)
from app.domain.site_config_resolver import MissingSiteConfigError
from app.schemas.joint_recommendations import (
    JointConflictSchema,
    JointSolveRequest,
    JointSolveResponse,
)
from app.schemas.optimization import RankedCandidate
from app.schemas.recommendations import (
    RecommendationActionSchema,
    RecommendationSchema,
)
from app.storage.repositories.interventions import InterventionOptionRepository

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

SessionDep = Annotated[Session, Depends(get_session)]


def _action_to_ranked_candidate(
    action: RecommendationActionSchema,
    *,
    breach_before: float,
) -> RankedCandidate:
    """Re-pack a per-zone RecommendationAction as a RankedCandidate.

    The joint solver only reads `intervention_id`, `simulation_id`,
    `risk_class`, and `requires_human_approval`; the other fields are
    populated for completeness so the dataclass round-trips cleanly.
    """
    drop = max(0.0, breach_before - action.breach_probability_after)
    return RankedCandidate(
        rank=action.rank,
        intervention_id=action.intervention_id,
        simulation_id=action.simulation_id,
        score=drop,  # proxy; the solver doesn't re-rank
        breach_probability_after=action.breach_probability_after,
        estimated_tonnes_delayed=action.estimated_tonnes_delayed,
        production_loss=action.production_loss,
        confidence=action.confidence,
        reason=action.reason,
        risk_class=action.risk_class,
        requires_human_approval=action.requires_human_approval,
    )


def _build_zone_candidates(
    rec: RecommendationSchema,
) -> ZoneCandidates:
    return ZoneCandidates(
        zone_id=rec.target_zone_id,
        breach_probability=rec.current_breach_probability,
        candidates=[
            _action_to_ranked_candidate(
                a, breach_before=rec.current_breach_probability,
            )
            for a in rec.recommended_actions
        ],
    )


def _conflict_to_schema(c: JointConflict) -> JointConflictSchema:
    return JointConflictSchema(
        zone_id=c.zone_id,
        preferred_intervention_id=c.preferred_intervention_id,
        chosen_intervention_id=c.chosen_intervention_id,
        conflicting_resource_classes=list(c.conflicting_resource_classes),
        conflicting_zone_id=c.conflicting_zone_id,
    )


@router.post(
    "/joint",
    response_model=JointSolveResponse,
    dependencies=[Depends(current_user)],
)
def issue_joint_recommendations(
    payload: JointSolveRequest,
    session: SessionDep,
) -> JointSolveResponse:
    """Compute one recommendation per zone, then resolve resource conflicts."""
    if len(set(payload.target_zone_ids)) != len(payload.target_zone_ids):
        raise HTTPException(
            status_code=400, detail="target_zone_ids must be unique",
        )

    recommendations: list[RecommendationSchema] = []
    for zone_id in payload.target_zone_ids:
        try:
            rec = generate_recommendation(session=session, target_zone_id=zone_id)
        except ZoneNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except NoForecastError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except MissingSiteConfigError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        recommendations.append(rec)

    # Build the resource-classes map by looking up each candidate
    # intervention's catalog entry once.
    repo = InterventionOptionRepository(session)
    resource_map: dict[str, list[str]] = {}
    for rec in recommendations:
        for action in rec.recommended_actions:
            if action.intervention_id in resource_map:
                continue
            opt = repo.get(action.intervention_id)
            resource_map[action.intervention_id] = (
                list(getattr(opt, "resource_classes", None) or [])
                if opt is not None
                else []
            )

    zone_candidates = [_build_zone_candidates(r) for r in recommendations]
    resolution = solve_joint_recommendations(
        zone_candidates=zone_candidates,
        candidate_resource_classes=resource_map,
    )

    return JointSolveResponse(
        recommendations=recommendations,
        conflicts=[_conflict_to_schema(c) for c in resolution.conflicts],
        claimed_resources=resolution.claimed_resources,
    )
