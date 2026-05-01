"""Source attribution endpoints (Phase F).

POST /api/v1/attributions/for-event/{event_id} - compute + persist
GET  /api/v1/attributions/for-event/{event_id} - latest persisted
GET  /api/v1/attributions/for-event/{event_id}/history - all persisted
GET  /api/v1/attributions                       - recent (smoke happy path)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.domain.attribution import EventNotFoundError, attribute_event
from app.models import registry
from app.models.attribution.rules_baseline import RulesBaselineAttributor
from app.schemas.attributions import SourceAttributionSchema
from app.storage.repositories.attributions import SourceAttributionRepository

router = APIRouter(prefix="/attributions", tags=["attributions"])

SessionDep = Annotated[Session, Depends(get_session)]


def _ensure_rules_registered() -> None:
    try:
        registry.get_current("source_attribution")
    except registry.ModelNotFoundError:
        registry.register(RulesBaselineAttributor())


@router.post("/for-event/{event_id}", response_model=SourceAttributionSchema)
def attribute_for_event(event_id: str, session: SessionDep) -> SourceAttributionSchema:
    _ensure_rules_registered()
    try:
        return attribute_event(session=session, dust_event_id=event_id)
    except EventNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/for-event/{event_id}", response_model=SourceAttributionSchema | None)
def get_latest_attribution(event_id: str, session: SessionDep) -> SourceAttributionSchema | None:
    row = SourceAttributionRepository(session).latest_for_event(event_id)
    if row is None:
        return None
    return SourceAttributionSchema.model_validate(row)


@router.get(
    "/for-event/{event_id}/history",
    response_model=list[SourceAttributionSchema],
)
def get_attribution_history(
    event_id: str, session: SessionDep
) -> list[SourceAttributionSchema]:
    rows = SourceAttributionRepository(session).history_for_event(event_id)
    return [SourceAttributionSchema.model_validate(r) for r in rows]


@router.get("", response_model=list[SourceAttributionSchema])
def list_recent_attributions(
    session: SessionDep,
    since_minutes: Annotated[int, Query(ge=1, le=24 * 60 * 7)] = 24 * 60,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[SourceAttributionSchema]:
    since = (datetime.now(UTC) - timedelta(minutes=since_minutes)).replace(tzinfo=None)
    rows = SourceAttributionRepository(session).get_recent(since, limit=limit)
    return [SourceAttributionSchema.model_validate(r) for r in rows]
