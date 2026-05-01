"""Zone admin endpoints.

GET  /api/v1/zones[?mine_id=]      - list zones (optionally filtered by mine)
GET  /api/v1/zones/{zone_id}        - single zone or 404
POST /api/v1/zones                  - upsert a zone

Auth deferred to Phase I (consistent with site-config). Intervention-id
arrays on the payload (`allowed_interventions`, `requires_approval_for`)
are validated against the S8 catalog as of Phase G.1; unknown IDs 400.
This closes D2-R2.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.domain.interventions import UnknownInterventionError, require_known
from app.schemas.mine import ZoneSchema
from app.storage.models import Mine, Zone
from app.storage.repositories.zones import ZoneRepository

router = APIRouter(prefix="/zones", tags=["mine-map"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[ZoneSchema])
def list_zones(
    session: SessionDep,
    mine_id: Annotated[str | None, Query()] = None,
) -> list[ZoneSchema]:
    repo = ZoneRepository(session)
    rows = (
        repo.get_for_mine(mine_id) if mine_id is not None else list(session.execute(select(Zone)).scalars())
    )
    return [ZoneSchema.model_validate(r) for r in rows]


@router.get("/{zone_id}", response_model=ZoneSchema)
def get_zone(zone_id: str, session: SessionDep) -> ZoneSchema:
    zone = ZoneRepository(session).get(zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail=f"zone not found: {zone_id}")
    return ZoneSchema.model_validate(zone)


@router.post("", response_model=ZoneSchema, status_code=201)
def upsert_zone(payload: ZoneSchema, session: SessionDep) -> ZoneSchema:
    if session.get(Mine, payload.mine_id) is None:
        raise HTTPException(
            status_code=400,
            detail=f"unknown mine_id: {payload.mine_id} (create the Mine row first)",
        )
    try:
        require_known(
            session,
            list(payload.allowed_interventions) + list(payload.requires_approval_for),
        )
    except UnknownInterventionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    zone = ZoneRepository(session).upsert(
        zone_id=payload.zone_id,
        mine_id=payload.mine_id,
        zone_type=payload.zone_type,
        operational_importance=payload.operational_importance,
        dust_generation_baseline=payload.dust_generation_baseline,
        allowed_interventions=list(payload.allowed_interventions),
        requires_approval_for=list(payload.requires_approval_for),
    )
    return ZoneSchema.model_validate(zone)
