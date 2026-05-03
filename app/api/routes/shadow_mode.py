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

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_role
from app.api.deps import get_session
from app.domain.evaluation_protocol import (
    EvaluationProtocol,
    ProtocolViolation,
)
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

    protocol = EvaluationProtocol(
        split_strategy=payload.protocol.split_strategy,
        train_window_from=payload.protocol.train_window_from,
        train_window_to=payload.protocol.train_window_to,
        validation_window_from=payload.protocol.validation_window_from,
        validation_window_to=payload.protocol.validation_window_to,
        test_window_from=payload.protocol.test_window_from,
        test_window_to=payload.protocol.test_window_to,
        embargo_days=payload.protocol.embargo_days,
        sealed_test_used=payload.protocol.sealed_test_used,
        baselines_named=tuple(payload.protocol.baselines_named),
        sinca_validated_legal_only_after_days=(
            payload.protocol.sinca_validated_legal_only_after_days
        ),
        realtime_proxy_required=payload.protocol.realtime_proxy_required,
        protocol_version=payload.protocol.protocol_version,
        intended_for_realtime=payload.protocol.intended_for_realtime,
        causal_intent=payload.protocol.causal_intent,
        feature_set=tuple(payload.protocol.feature_set),
        required_covariates=tuple(payload.protocol.required_covariates),
        forbidden_covariates=tuple(payload.protocol.forbidden_covariates),
        max_ece=payload.protocol.max_ece,
        ece_override_reason=payload.protocol.ece_override_reason,
        notes=payload.protocol.notes,
    )
    try:
        result = evaluate_shadow(
            session=session,
            candidate_version=payload.candidate_version,
            production_version=payload.production_version,
            window_from=window_from,
            window_to=window_to,
            protocol=protocol,
            observation_window=timedelta(
                minutes=payload.observation_window_minutes
            ),
        )
    except ProtocolViolation as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
