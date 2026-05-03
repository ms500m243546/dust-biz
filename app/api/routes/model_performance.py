"""Model-performance endpoints (Phase K, S14).

GET  /api/v1/model-performance           - recent persisted metric rows
POST /api/v1/model-performance/evaluate  - compute + persist a metric row
                                           over an explicit window

The POST is role-gated: only operations_manager / environmental_manager /
admin can trigger an evaluation, because the row becomes part of the
audit trail used for shadow-mode promotion decisions.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies.auth import current_user, require_role
from app.api.deps import get_session
from app.domain.evaluation_protocol import (
    EvaluationProtocol,
    ProtocolViolation,
)
from app.domain.model_performance import compute_metric_payload
from app.domain.training_data import load_and_assemble
from app.schemas.model_performance import (
    EvaluateModelRequest,
    ModelPerformanceMetricSchema,
)
from app.storage.models import ModelPerformanceMetric, User
from app.storage.repositories.model_performance import (
    ModelPerformanceMetricRepository,
)

router = APIRouter(prefix="/model-performance", tags=["model-performance"])

SessionDep = Annotated[Session, Depends(get_session)]

_EVALUATOR_ROLES = ("environmental_manager", "operations_manager", "admin")


@router.get("", response_model=list[ModelPerformanceMetricSchema])
def list_recent(
    session: SessionDep,
    _user: Annotated[User, Depends(current_user)],
    since_minutes: Annotated[int, Query(ge=1, le=24 * 60 * 90)] = 7 * 24 * 60,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    model_version: Annotated[str | None, Query()] = None,
    model_kind: Annotated[str | None, Query()] = None,
) -> list[ModelPerformanceMetricSchema]:
    since = (datetime.now(UTC) - timedelta(minutes=since_minutes)).replace(
        tzinfo=None
    )
    rows = ModelPerformanceMetricRepository(session).get_recent(
        since=since,
        limit=limit,
        model_version=model_version,
        model_kind=model_kind,
    )
    return [ModelPerformanceMetricSchema.model_validate(r) for r in rows]


@router.post(
    "/evaluate",
    response_model=ModelPerformanceMetricSchema,
    status_code=201,
)
def evaluate(
    payload: EvaluateModelRequest,
    session: SessionDep,
    _user: Annotated[User, Depends(require_role(*_EVALUATOR_ROLES))],
) -> ModelPerformanceMetricSchema:
    now = datetime.now(UTC).replace(tzinfo=None)
    window_from = payload.window_from
    if window_from.tzinfo is not None:
        window_from = window_from.replace(tzinfo=None)
    window_to = payload.window_to
    if window_to.tzinfo is not None:
        window_to = window_to.replace(tzinfo=None)

    records = load_and_assemble(
        session=session,
        window_from=window_from,
        window_to=window_to,
        now=now,
        observation_window=timedelta(
            minutes=payload.outcome_observation_minutes
        ),
        model_version=payload.model_version,
    )
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
        notes=payload.protocol.notes,
    )
    repo = ModelPerformanceMetricRepository(session)
    prior_hashes = tuple(
        (r.metric_payload or {})
        .get("protocol", {})
        .get("protocol_hash", "")
        for r in repo.get_recent(
            since=datetime(1970, 1, 1),
            limit=500,
            model_version=payload.model_version,
            model_kind=None,
        )
    )
    try:
        payload_blob = compute_metric_payload(
            records,
            protocol=protocol,
            prior_metric_protocol_hashes=tuple(h for h in prior_hashes if h),
            session=session,
        )
    except ProtocolViolation as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    row = ModelPerformanceMetric(
        model_version=payload.model_version,
        model_kind=payload.model_kind,
        evaluated_at=now,
        window_from=window_from,
        window_to=window_to,
        sample_count=len(records),
        metric_payload=payload_blob,
    )
    persisted = repo.add(row)
    return ModelPerformanceMetricSchema.model_validate(persisted)
