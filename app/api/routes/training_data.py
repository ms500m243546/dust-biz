"""Training-data endpoints (Phase K, S14).

GET /api/v1/training-data  - assembled S14 join over a window. Read-only.

Auth: any signed-in user (read-side; the assembled join is derived
from already-audited rows).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies.auth import current_user
from app.api.deps import get_session
from app.domain.training_data import load_and_assemble
from app.schemas.model_performance import TrainingRecordSchema
from app.storage.models import User

router = APIRouter(prefix="/training-data", tags=["training-data"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[TrainingRecordSchema])
def list_training_records(
    session: SessionDep,
    _user: Annotated[User, Depends(current_user)],
    since_minutes: Annotated[int, Query(ge=1, le=24 * 60 * 30)] = 24 * 60,
    observation_window_minutes: Annotated[int, Query(ge=1, le=24 * 60 * 7)] = 180,
    model_version: Annotated[str | None, Query()] = None,
    outcome_status: Annotated[str | None, Query(pattern="^(observed|unobserved)$")] = None,
) -> list[TrainingRecordSchema]:
    now = datetime.now(UTC).replace(tzinfo=None)
    window_from = now - timedelta(minutes=since_minutes)
    records = load_and_assemble(
        session=session,
        window_from=window_from,
        window_to=now,
        now=now,
        observation_window=timedelta(minutes=observation_window_minutes),
        model_version=model_version,
    )
    if outcome_status is not None:
        records = [r for r in records if r.outcome_status == outcome_status]
    return records
