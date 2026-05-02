"""Approval endpoints (Phase I, S13).

POST /api/v1/recommendations/{id}/approve   - approve one ranked action
POST /api/v1/recommendations/{id}/reject    - reject all actions
POST /api/v1/recommendations/{id}/override  - override with off-catalog action
GET  /api/v1/recommendations/{id}/approval  - current decision
GET  /api/v1/approvals                      - recent decision history
POST /api/v1/approvals/sweep-expired        - manual expiry sweep

Roles allowed (per docs/data-contracts.md `users, roles`):
- approve / reject:  shift_supervisor, environmental_manager,
                     operations_manager, admin
- override:          environmental_manager, operations_manager, admin
                     (not shift_supervisor: an off-catalog action carries
                     more accountability per G9)
- sweep-expired:     admin (operational tool only)

Per safety-guardrails.md "Safety-reviewer subagent triggers", changes
to this file should trigger the safety reviewer before merge.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import current_user, require_role
from app.api.deps import get_session
from app.domain.approvals import (
    AlreadyDecidedError,
    HighRiskAutoExecutionError,
    InvalidActionRankError,
    RecommendationNotFoundError,
    approve_recommendation,
    latest_for_recommendation,
    override_recommendation,
    reject_recommendation,
    sweep_expired,
)
from app.schemas.approvals import (
    ApproveRequest,
    OverrideRequest,
    RecommendationApprovalSchema,
    RejectRequest,
)
from app.storage.models import User
from app.storage.repositories.approvals import RecommendationApprovalRepository

router = APIRouter(tags=["approvals"])

SessionDep = Annotated[Session, Depends(get_session)]

_DECIDER_ROLES = (
    "shift_supervisor",
    "environmental_manager",
    "operations_manager",
    "admin",
)
_OVERRIDE_ROLES = ("environmental_manager", "operations_manager", "admin")


def _to_409(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post(
    "/recommendations/{recommendation_id}/approve",
    response_model=RecommendationApprovalSchema,
)
def approve(
    recommendation_id: str,
    payload: ApproveRequest,
    session: SessionDep,
    user: Annotated[User, Depends(require_role(*_DECIDER_ROLES))],
) -> RecommendationApprovalSchema:
    try:
        return approve_recommendation(
            session=session,
            recommendation_id=recommendation_id,
            chosen_action_rank=payload.chosen_action_rank,
            human_reason=payload.human_reason,
            actor_username=user.username,
            actor_role=user.role,
        )
    except RecommendationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AlreadyDecidedError as exc:
        raise _to_409(exc) from exc
    except InvalidActionRankError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HighRiskAutoExecutionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post(
    "/recommendations/{recommendation_id}/reject",
    response_model=RecommendationApprovalSchema,
)
def reject(
    recommendation_id: str,
    payload: RejectRequest,
    session: SessionDep,
    user: Annotated[User, Depends(require_role(*_DECIDER_ROLES))],
) -> RecommendationApprovalSchema:
    try:
        return reject_recommendation(
            session=session,
            recommendation_id=recommendation_id,
            human_reason=payload.human_reason,
            actor_username=user.username,
            actor_role=user.role,
        )
    except RecommendationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AlreadyDecidedError as exc:
        raise _to_409(exc) from exc


@router.post(
    "/recommendations/{recommendation_id}/override",
    response_model=RecommendationApprovalSchema,
)
def override(
    recommendation_id: str,
    payload: OverrideRequest,
    session: SessionDep,
    user: Annotated[User, Depends(require_role(*_OVERRIDE_ROLES))],
) -> RecommendationApprovalSchema:
    try:
        return override_recommendation(
            session=session,
            recommendation_id=recommendation_id,
            override_action=payload.override_action,
            human_reason=payload.human_reason,
            actor_username=user.username,
            actor_role=user.role,
        )
    except RecommendationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AlreadyDecidedError as exc:
        raise _to_409(exc) from exc


@router.get(
    "/recommendations/{recommendation_id}/approval",
    response_model=RecommendationApprovalSchema | None,
)
def get_latest_decision(
    recommendation_id: str,
    session: SessionDep,
    _user: Annotated[User, Depends(current_user)],
) -> RecommendationApprovalSchema | None:
    return latest_for_recommendation(
        session=session, recommendation_id=recommendation_id
    )


@router.get("/approvals", response_model=list[RecommendationApprovalSchema])
def list_recent_approvals(
    session: SessionDep,
    _user: Annotated[User, Depends(current_user)],
    since_minutes: Annotated[int, Query(ge=1, le=24 * 60 * 7)] = 24 * 60,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[RecommendationApprovalSchema]:
    since = (datetime.now(UTC) - timedelta(minutes=since_minutes)).replace(tzinfo=None)
    repo = RecommendationApprovalRepository(session)
    rows = repo.get_recent(since=since, limit=limit)
    out: list[RecommendationApprovalSchema] = []
    from app.storage.repositories.recommendations import RecommendationRepository

    rec_repo = RecommendationRepository(session)
    for row in rows:
        rec = rec_repo.get(row.recommendation_id)
        if rec is None:
            continue
        out.append(
            RecommendationApprovalSchema(
                approval_id=row.approval_id,
                recommendation_id=row.recommendation_id,
                approved_by=row.approved_by,
                approver_role=row.approver_role,
                decided_at=row.decided_at,
                approval_status=row.approval_status,  # type: ignore[arg-type]
                chosen_action_rank=row.chosen_action_rank,
                override_action=row.override_action,
                human_reason=row.human_reason,
                automation_level_at_decision=row.automation_level_at_decision,
                confidence=rec.confidence,
                reason=rec.reason,
                model_version=rec.model_version,
            )
        )
    return out


@router.post(
    "/approvals/sweep-expired",
    response_model=list[RecommendationApprovalSchema],
)
def sweep(
    session: SessionDep,
    _user: Annotated[User, Depends(require_role("admin"))],
) -> list[RecommendationApprovalSchema]:
    return sweep_expired(session=session)
