"""Site configuration admin endpoints.

GET  /api/v1/site-config                       - list all site configs (optionally filtered by mine_id)
GET  /api/v1/site-config/{site_id}             - resolved config for a site (with fallback to mine defaults)
POST /api/v1/site-config                       - upsert a site config

The GET-by-id route applies the resolver from
`app/domain/site_config_resolver.py` so callers always receive a usable
config even when no row exists yet.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.domain.site_config_resolver import resolve
from app.schemas.site_config import SiteConfigSchema
from app.storage.models import Mine
from app.storage.repositories.site_config import SiteConfigRepository

router = APIRouter(prefix="/site-config", tags=["site-config"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[SiteConfigSchema])
def list_configs(
    session: SessionDep,
    mine_id: Annotated[str | None, Query()] = None,
) -> list[SiteConfigSchema]:
    repo = SiteConfigRepository(session)
    if mine_id is not None:
        rows = repo.get_for_mine(mine_id)
    else:
        from sqlalchemy import select

        from app.storage.models import SiteConfiguration

        rows = list(session.execute(select(SiteConfiguration)).scalars())
    return [SiteConfigSchema.model_validate(r) for r in rows]


@router.get("/{site_id}", response_model=SiteConfigSchema)
def get_config(site_id: str, session: SessionDep) -> SiteConfigSchema:
    repo = SiteConfigRepository(session)
    cfg = repo.get(site_id)
    if cfg is not None:
        return SiteConfigSchema.model_validate(cfg)

    # No row - apply the resolver. Convention: site_id "default-<mine_id>"
    # is the synthetic id the resolver returns when falling back to mine
    # defaults; callers asking for that variant get the resolved value.
    if site_id.startswith("default-"):
        mine_id = site_id.removeprefix("default-")
        mine = session.get(Mine, mine_id)
        resolved, _source = resolve(mine_id=mine_id, site_config=None, mine=mine)
        return resolved

    raise HTTPException(status_code=404, detail=f"site_config not found: {site_id}")


@router.post("", response_model=SiteConfigSchema, status_code=201)
def upsert_config(payload: SiteConfigSchema, session: SessionDep) -> SiteConfigSchema:
    if session.get(Mine, payload.mine_id) is None:
        raise HTTPException(
            status_code=400,
            detail=f"unknown mine_id: {payload.mine_id} (create the Mine row first)",
        )
    repo = SiteConfigRepository(session)
    cfg = repo.upsert(
        site_id=payload.site_id,
        mine_id=payload.mine_id,
        automation_level=payload.automation_level,
        pm10_thresholds=payload.pm10_thresholds,
        pm25_thresholds=payload.pm25_thresholds,
        extreme_breach_threshold=payload.extreme_breach_threshold,
        low_confidence_threshold=payload.low_confidence_threshold,
        optimization_weights=payload.optimization_weights.model_dump(),
        intervention_constraints=payload.intervention_constraints,
        updated_by=payload.updated_by,
    )
    return SiteConfigSchema.model_validate(cfg)
