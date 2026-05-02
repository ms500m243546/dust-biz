"""Shadow-mode evaluation endpoint (Phase K.4).

POST /api/v1/shadow-mode/evaluate  - compare candidate vs production model.

Role-gated (admin / operations_manager / environmental_manager) because
the result feeds promotion decisions. Returns the structured comparison;
the caller is the one who acts on the recommendation by calling
`app.models.registry.set_current` (kept explicit per G13).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_role
from app.api.deps import get_session
from app.domain.shadow_mode import evaluate_shadow
from app.schemas.shadow_mode import (
    ShadowEvaluationRequest,
    ShadowEvaluationResponse,
)
from app.storage.models import User

router = APIRouter(prefix="/shadow-mode", tags=["shadow-mode"])

SessionDep = Annotated[Session, Depends(get_session)]

_EVALUATOR_ROLES = ("environmental_manager", "operations_manager", "admin")


@router.post("/evaluate", response_model=ShadowEvaluationResponse)
def evaluate(
    payload: ShadowEvaluationRequest,
    session: SessionDep,
    _user: Annotated[User, Depends(require_role(*_EVALUATOR_ROLES))],
) -> ShadowEvaluationResponse:
    window_from = payload.window_from
    if window_from.tzinfo is not None:
        window_from = window_from.replace(tzinfo=None)
    window_to = payload.window_to
    if window_to.tzinfo is not None:
        window_to = window_to.replace(tzinfo=None)

    result = evaluate_shadow(
        session=session,
        candidate_version=payload.candidate_version,
        production_version=payload.production_version,
        window_from=window_from,
        window_to=window_to,
        observation_window=timedelta(minutes=payload.observation_window_minutes),
    )
    return ShadowEvaluationResponse(
        candidate_version=result.candidate_version,
        production_version=result.production_version,
        window_from=result.window_from,
        window_to=result.window_to,
        candidate_metrics=result.candidate_metrics,
        production_metrics=result.production_metrics,
        delta=result.delta,
        recommendation=result.recommendation,
        recommendation_reason=result.recommendation_reason,
    )
