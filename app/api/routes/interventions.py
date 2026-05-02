"""Intervention library endpoints (Phase G, S8).

GET  /api/v1/interventions             - full catalog (lazy-seeds defaults)
GET  /api/v1/interventions/{id}        - one entry or 404
POST /api/v1/interventions             - upsert (admin)

Auth deferred to Phase I (consistent with other admin endpoints; tracked
as F4-R1 / D2-R1 / E4-R2).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies.auth import current_user
from app.api.deps import get_session
from app.domain.interventions import list_interventions
from app.schemas.interventions import InterventionOptionSchema
from app.storage.repositories.interventions import InterventionOptionRepository

router = APIRouter(prefix="/interventions", tags=["interventions"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[InterventionOptionSchema])
def list_catalog(session: SessionDep) -> list[InterventionOptionSchema]:
    return list_interventions(session)


@router.get("/{intervention_id}", response_model=InterventionOptionSchema)
def get_intervention(
    intervention_id: str, session: SessionDep
) -> InterventionOptionSchema:
    row = InterventionOptionRepository(session).get(intervention_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"intervention not found: {intervention_id}"
        )
    return InterventionOptionSchema.model_validate(row)


@router.post(
    "", response_model=InterventionOptionSchema, status_code=201,
    dependencies=[Depends(current_user)],
)
def upsert_intervention(
    payload: InterventionOptionSchema, session: SessionDep
) -> InterventionOptionSchema:
    row = InterventionOptionRepository(session).upsert(
        intervention_id=payload.intervention_id,
        name=payload.name,
        description=payload.description,
        risk_class=payload.risk_class,
        requires_human_approval=payload.requires_human_approval,
        automation_eligible_levels=list(payload.automation_eligible_levels),
        estimated_time_to_effect_minutes=payload.estimated_time_to_effect_minutes,
        allowed_zone_types=list(payload.allowed_zone_types),
    )
    return InterventionOptionSchema.model_validate(row)
