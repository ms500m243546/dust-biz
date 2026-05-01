"""Dust event endpoints (Phase F).

POST /api/v1/dust-events                 - operator manual entry (G12)
GET  /api/v1/dust-events                 - history (filterable)
POST /api/v1/dust-events/from-forecast   - threshold-trigger sweep
GET  /api/v1/dust-events/{event_id}      - single event lookup

Both POSTs land an immutable row; updates are not supported.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.domain.dust_events import (
    DEFAULT_TRIGGER_BREACH_PROBABILITY,
    UnknownStationError,
    record_manual_event,
    trigger_events_from_forecasts,
)
from app.schemas.dust_events import DustEventCreate, DustEventSchema
from app.storage.repositories.dust_events import DustEventRepository

router = APIRouter(prefix="/dust-events", tags=["dust-events"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.post("", response_model=DustEventSchema, status_code=201)
def create_event(payload: DustEventCreate, session: SessionDep) -> DustEventSchema:
    try:
        return record_manual_event(session=session, payload=payload)
    except UnknownStationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("", response_model=list[DustEventSchema])
def list_events(
    session: SessionDep,
    since_minutes: Annotated[int, Query(ge=1, le=24 * 60 * 7)] = 24 * 60,
    station: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[DustEventSchema]:
    since = (datetime.now(UTC) - timedelta(minutes=since_minutes)).replace(tzinfo=None)
    rows = DustEventRepository(session).get_recent(since, limit=limit, station=station)
    return [DustEventSchema.model_validate(r) for r in rows]


@router.get("/{event_id}", response_model=DustEventSchema)
def get_event(event_id: str, session: SessionDep) -> DustEventSchema:
    row = DustEventRepository(session).get(event_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"event not found: {event_id}")
    return DustEventSchema.model_validate(row)


@router.post("/from-forecast", response_model=list[DustEventSchema])
def trigger_from_forecast(
    session: SessionDep,
    sensor_id: Annotated[str, Query()],
    breach_threshold: Annotated[float, Query(ge=0.0, le=1.0)] = DEFAULT_TRIGGER_BREACH_PROBABILITY,
    since_minutes: Annotated[int, Query(ge=1, le=24 * 60)] = 60,
) -> list[DustEventSchema]:
    try:
        return trigger_events_from_forecasts(
            session=session,
            sensor_id=sensor_id,
            breach_threshold=breach_threshold,
            since_minutes=since_minutes,
        )
    except UnknownStationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
