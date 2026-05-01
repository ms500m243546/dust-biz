"""Equipment activity ingestion + query endpoints.

Mirrors sensor_readings.py - see that module for design notes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.schemas.equipment import RawEquipmentActivitySchema
from app.storage.models import EquipmentActivity
from app.storage.repositories.equipment_activity import EquipmentActivityRepository
from app.storage.repositories.ingest_errors import IngestErrorRepository

router = APIRouter(prefix="/equipment-activity", tags=["ingestion"])

ENDPOINT_SINGLE = "POST /api/v1/equipment-activity"
ENDPOINT_BATCH = "POST /api/v1/equipment-activity/batch"

SessionDep = Annotated[Session, Depends(get_session)]


def _format_validation_errors(exc: ValidationError) -> list[dict[str, Any]]:
    return [
        {"field": ".".join(str(p) for p in err["loc"]), "message": err["msg"]}
        for err in exc.errors()
    ]


def _to_orm(s: RawEquipmentActivitySchema) -> EquipmentActivity:
    return EquipmentActivity(
        equipment_id=s.equipment_id,
        timestamp=s.timestamp,
        activity_type=s.activity_type,
        zone_id=s.zone_id,
        speed_kmh=s.speed_kmh,
        tonnage=s.tonnage,
        raw_payload=s.raw_payload,
    )


@router.post("", status_code=201, response_model=RawEquipmentActivitySchema)
def post_activity(
    payload: dict[str, Any],
    session: SessionDep,
) -> RawEquipmentActivitySchema:
    try:
        activity_in = RawEquipmentActivitySchema.model_validate(payload)
    except ValidationError as e:
        IngestErrorRepository(session).add(
            source_endpoint=ENDPOINT_SINGLE,
            raw_payload=payload,
            validation_errors=_format_validation_errors(e),
        )
        session.commit()
        raise HTTPException(status_code=422, detail=e.errors()) from e

    repo = EquipmentActivityRepository(session)
    inserted = repo.add(_to_orm(activity_in))
    return RawEquipmentActivitySchema.model_validate(inserted)


@router.post("/batch", status_code=201, response_model=list[RawEquipmentActivitySchema])
def post_batch(
    payload: list[dict[str, Any]],
    session: SessionDep,
) -> list[RawEquipmentActivitySchema]:
    validated: list[RawEquipmentActivitySchema] = []
    rejected: list[tuple[int, dict[str, Any], list[dict[str, Any]]]] = []
    for idx, item in enumerate(payload):
        try:
            validated.append(RawEquipmentActivitySchema.model_validate(item))
        except ValidationError as e:
            rejected.append((idx, item, _format_validation_errors(e)))

    err_repo = IngestErrorRepository(session)
    for idx, item, errs in rejected:
        err_repo.add(
            source_endpoint=ENDPOINT_BATCH,
            raw_payload={"index": idx, "item": item},
            validation_errors=errs,
        )
    if rejected:
        session.commit()
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"{len(rejected)} of {len(payload)} items failed validation",
                "rejected_indices": [r[0] for r in rejected],
            },
        )

    repo = EquipmentActivityRepository(session)
    inserted = repo.add_many([_to_orm(s) for s in validated])
    return [RawEquipmentActivitySchema.model_validate(r) for r in inserted]


@router.get("", response_model=list[RawEquipmentActivitySchema])
def list_activity(
    session: SessionDep,
    equipment_id: Annotated[str | None, Query()] = None,
    zone_id: Annotated[str | None, Query()] = None,
    since: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
) -> list[RawEquipmentActivitySchema]:
    repo = EquipmentActivityRepository(session)
    if equipment_id is not None and since is not None:
        rows = repo.get_recent_for_equipment(equipment_id, since=since, limit=limit)
    elif zone_id is not None and since is not None:
        rows = repo.get_recent_for_zone(zone_id, since=since, limit=limit)
    else:
        stmt = select(EquipmentActivity).order_by(EquipmentActivity.timestamp.desc()).limit(limit)
        rows = list(session.execute(stmt).scalars())
    return [RawEquipmentActivitySchema.model_validate(r) for r in rows]
