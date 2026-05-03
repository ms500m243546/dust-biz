"""POST /api/v1/drift/retrain — admin-only manual retrain trigger (Phase W.2).

Triggers `app.domain.drift_response.trigger_drift_retrain` for a
named model_version. Skips the retrain unless at least one ACT-tier
drift alert (delta ≥ 2 × threshold) is present in the recent window.

Audit-trail behaviour: this endpoint always emits at least one
audit row — `drift_retrain_skipped` if no ACT alerts, otherwise
`drift_retrain_triggered` + `drift_retrain_completed` (or
`drift_retrain_failed`).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.dependencies.auth import current_user, require_role
from app.domain.drift_response import trigger_drift_retrain
from app.storage.models import User

router = APIRouter(prefix="/drift", tags=["drift"])


class DriftRetrainResponse(BaseModel):
    model_version: str
    retrained: bool
    triggering_alert_count: int
    reason: str


@router.post(
    "/retrain",
    response_model=DriftRetrainResponse,
    dependencies=[Depends(require_role("admin"))],
)
def post_drift_retrain(
    user: Annotated[User, Depends(current_user)],
    model_version: Annotated[str, Query(min_length=1)],
    since_days: Annotated[int, Query(ge=1, le=365)] = 30,
    min_samples: Annotated[int, Query(ge=2, le=100)] = 4,
) -> DriftRetrainResponse:
    outcome = trigger_drift_retrain(
        model_version=model_version,
        actor=user.username,
        since_days=since_days,
        min_samples=min_samples,
    )
    return DriftRetrainResponse(
        model_version=outcome.model_version,
        retrained=outcome.retrained,
        triggering_alert_count=len(outcome.triggering_alerts),
        reason=outcome.reason,
    )
