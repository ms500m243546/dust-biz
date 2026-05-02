"""Sensor readings ingestion + query endpoints.

POST /api/v1/sensor-readings        - single reading
POST /api/v1/sensor-readings/batch  - list of readings
GET  /api/v1/sensor-readings        - recent readings (default last 50)
GET  /api/v1/sensor-readings?sensor_id=X[&since=ISO][&limit=N]

Validation failures are persisted to `ingest_errors` (G10) before the
422 response, so nothing silently disappears.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.auth import current_user
from app.api.deps import get_session
from app.schemas.sensor import RawSensorReadingSchema
from app.storage.models import SensorReading
from app.storage.repositories.ingest_errors import IngestErrorRepository
from app.storage.repositories.sensor_readings import SensorReadingRepository

router = APIRouter(prefix="/sensor-readings", tags=["ingestion"])

ENDPOINT_SINGLE = "POST /api/v1/sensor-readings"
ENDPOINT_BATCH = "POST /api/v1/sensor-readings/batch"

SessionDep = Annotated[Session, Depends(get_session)]


def _format_validation_errors(exc: ValidationError) -> list[dict[str, Any]]:
    return [
        {"field": ".".join(str(p) for p in err["loc"]), "message": err["msg"]}
        for err in exc.errors()
    ]


@router.post(
    "", status_code=201, response_model=RawSensorReadingSchema,
    dependencies=[Depends(current_user)],
)
def post_reading(
    payload: dict[str, Any],
    session: SessionDep,
) -> RawSensorReadingSchema:
    try:
        reading_in = RawSensorReadingSchema.model_validate(payload)
    except ValidationError as e:
        IngestErrorRepository(session).add(
            source_endpoint=ENDPOINT_SINGLE,
            raw_payload=payload,
            validation_errors=_format_validation_errors(e),
        )
        # Commit the audit row before raising; otherwise the dep's
        # except-branch rollback would discard it (G10).
        session.commit()
        raise HTTPException(status_code=422, detail=e.errors()) from e

    repo = SensorReadingRepository(session)
    reading = repo.add(
        sensor_id=reading_in.sensor_id,
        timestamp=reading_in.timestamp,
        raw_value=reading_in.raw_value,
        source_quality_hint=reading_in.source_quality_hint,
    )
    return RawSensorReadingSchema.model_validate(reading)


@router.post(
    "/batch", status_code=201, response_model=list[RawSensorReadingSchema],
    dependencies=[Depends(current_user)],
)
def post_batch(
    payload: list[dict[str, Any]],
    session: SessionDep,
) -> list[RawSensorReadingSchema]:
    validated: list[RawSensorReadingSchema] = []
    rejected: list[tuple[int, dict[str, Any], list[dict[str, Any]]]] = []
    for idx, item in enumerate(payload):
        try:
            validated.append(RawSensorReadingSchema.model_validate(item))
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
        # Commit ingest_errors (G10) before the rollback triggered by
        # raising below.
        session.commit()
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"{len(rejected)} of {len(payload)} items failed validation",
                "rejected_indices": [r[0] for r in rejected],
            },
        )

    repo = SensorReadingRepository(session)
    rows = [
        SensorReading(
            sensor_id=r.sensor_id,
            timestamp=r.timestamp,
            raw_value=r.raw_value,
            source_quality_hint=r.source_quality_hint,
        )
        for r in validated
    ]
    inserted = repo.add_many(rows)
    return [RawSensorReadingSchema.model_validate(r) for r in inserted]


@router.get("", response_model=list[RawSensorReadingSchema])
def list_readings(
    session: SessionDep,
    sensor_id: Annotated[str | None, Query()] = None,
    since: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
) -> list[RawSensorReadingSchema]:
    repo = SensorReadingRepository(session)
    if sensor_id is not None and since is not None:
        rows = repo.get_recent(sensor_id, since=since, limit=limit)
    elif sensor_id is not None:
        rows = repo.get_for_sensor(sensor_id, limit=limit)
    else:
        stmt = select(SensorReading).order_by(SensorReading.timestamp.desc()).limit(limit)
        rows = list(session.execute(stmt).scalars())
    return [RawSensorReadingSchema.model_validate(r) for r in rows]
