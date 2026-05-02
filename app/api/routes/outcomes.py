"""Action outcome endpoints (Phase I, S14 feeder).

POST /api/v1/action-outcomes              - record an outcome (manual)
GET  /api/v1/action-outcomes              - recent outcomes
GET  /api/v1/action-outcomes/for-recommendation/{id}  - history for one rec

Roles allowed:
- POST: environmental_manager, operations_manager, admin
- GET:  any authenticated user

Per safety-guardrails.md, this file should trigger the safety reviewer
before merge.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies.auth import current_user, require_role
from app.api.deps import get_session
from app.domain.outcomes import (
    UnknownPredictionError,
    UnknownRecommendationError,
    record_outcome,
)
from app.schemas.outcomes import ActionOutcomeCreate, ActionOutcomeSchema
from app.storage.models import User
from app.storage.repositories.outcomes import ActionOutcomeRepository

router = APIRouter(prefix="/action-outcomes", tags=["outcomes"])

SessionDep = Annotated[Session, Depends(get_session)]

_RECORDER_ROLES = ("environmental_manager", "operations_manager", "admin")


@router.post("", response_model=ActionOutcomeSchema, status_code=201)
def post_outcome(
    payload: ActionOutcomeCreate,
    session: SessionDep,
    user: Annotated[User, Depends(require_role(*_RECORDER_ROLES))],
) -> ActionOutcomeSchema:
    try:
        return record_outcome(
            session=session, payload=payload, actor_username=user.username
        )
    except UnknownRecommendationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnknownPredictionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("", response_model=list[ActionOutcomeSchema])
def list_recent(
    session: SessionDep,
    _user: Annotated[User, Depends(current_user)],
    since_minutes: Annotated[int, Query(ge=1, le=24 * 60 * 30)] = 24 * 60,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[ActionOutcomeSchema]:
    since = (datetime.now(UTC) - timedelta(minutes=since_minutes)).replace(tzinfo=None)
    rows = ActionOutcomeRepository(session).get_recent(since=since, limit=limit)
    return [ActionOutcomeSchema.model_validate(r) for r in rows]


@router.get(
    "/for-recommendation/{recommendation_id}",
    response_model=list[ActionOutcomeSchema],
)
def list_for_recommendation(
    recommendation_id: str,
    session: SessionDep,
    _user: Annotated[User, Depends(current_user)],
) -> list[ActionOutcomeSchema]:
    rows = ActionOutcomeRepository(session).for_recommendation(recommendation_id)
    return [ActionOutcomeSchema.model_validate(r) for r in rows]
