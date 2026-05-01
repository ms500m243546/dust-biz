"""Intervention simulation endpoints (Phase G, S9 + S10 joined).

POST /api/v1/simulations/intervention - simulate one candidate
POST /api/v1/simulations/do-nothing   - counterfactual baseline
GET  /api/v1/simulations              - recent persisted simulations

Auth deferred to Phase I (G4-R1: same posture as forecast / attribution
endpoints).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.domain.interventions import UnknownInterventionError
from app.domain.simulation import (
    NoForecastError,
    ZoneNotFoundError,
    simulate_do_nothing,
    simulate_intervention,
)
from app.schemas.simulations import InterventionSimulationSchema
from app.storage.repositories.simulations import InterventionSimulationRepository

router = APIRouter(prefix="/simulations", tags=["simulations"])

SessionDep = Annotated[Session, Depends(get_session)]


class SimulateInterventionRequest(BaseModel):
    intervention_id: str = Field(min_length=1)
    target_zone_id: str = Field(min_length=1)
    duration_minutes: int | None = Field(default=None, ge=0, le=24 * 60)


class SimulateDoNothingRequest(BaseModel):
    target_zone_id: str = Field(min_length=1)


@router.post("/intervention", response_model=InterventionSimulationSchema)
def post_simulate_intervention(
    payload: SimulateInterventionRequest, session: SessionDep
) -> InterventionSimulationSchema:
    try:
        return simulate_intervention(
            session=session,
            intervention_id=payload.intervention_id,
            target_zone_id=payload.target_zone_id,
            duration_minutes=payload.duration_minutes,
        )
    except UnknownInterventionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ZoneNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NoForecastError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/do-nothing", response_model=InterventionSimulationSchema)
def post_simulate_do_nothing(
    payload: SimulateDoNothingRequest, session: SessionDep
) -> InterventionSimulationSchema:
    try:
        return simulate_do_nothing(
            session=session, target_zone_id=payload.target_zone_id
        )
    except ZoneNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NoForecastError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("", response_model=list[InterventionSimulationSchema])
def list_recent_simulations(
    session: SessionDep,
    since_minutes: Annotated[int, Query(ge=1, le=24 * 60 * 7)] = 24 * 60,
    target_zone_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[InterventionSimulationSchema]:
    since = (datetime.now(UTC) - timedelta(minutes=since_minutes)).replace(tzinfo=None)
    rows = InterventionSimulationRepository(session).get_recent(
        since, limit=limit, target_zone_id=target_zone_id
    )
    return [InterventionSimulationSchema.model_validate(r) for r in rows]
