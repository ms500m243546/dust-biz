"""Weather readings ingestion + query endpoints.

Mirrors sensor_readings.py - see that module for design notes.
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
from app.schemas.weather import RawWeatherReadingSchema
from app.storage.models import WeatherReading
from app.storage.repositories.ingest_errors import IngestErrorRepository
from app.storage.repositories.weather_readings import WeatherReadingRepository

router = APIRouter(prefix="/weather-readings", tags=["ingestion"])

ENDPOINT_SINGLE = "POST /api/v1/weather-readings"
ENDPOINT_BATCH = "POST /api/v1/weather-readings/batch"

SessionDep = Annotated[Session, Depends(get_session)]


def _format_validation_errors(exc: ValidationError) -> list[dict[str, Any]]:
    return [
        {"field": ".".join(str(p) for p in err["loc"]), "message": err["msg"]}
        for err in exc.errors()
    ]


def _to_orm(s: RawWeatherReadingSchema) -> WeatherReading:
    return WeatherReading(
        source=s.source,
        zone_id=s.zone_id,
        timestamp=s.timestamp,
        wind_speed_ms=s.wind_speed_ms,
        wind_direction_deg=s.wind_direction_deg,
        gust_speed_ms=s.gust_speed_ms,
        humidity_pct=s.humidity_pct,
        temperature_c=s.temperature_c,
        pressure_hpa=s.pressure_hpa,
        rainfall_mm_15min=s.rainfall_mm_15min,
        solar_wm2=s.solar_wm2,
        visibility_m=s.visibility_m,
    )


@router.post(
    "", status_code=201, response_model=RawWeatherReadingSchema,
    dependencies=[Depends(current_user)],
)
def post_reading(
    payload: dict[str, Any],
    session: SessionDep,
) -> RawWeatherReadingSchema:
    try:
        reading_in = RawWeatherReadingSchema.model_validate(payload)
    except ValidationError as e:
        IngestErrorRepository(session).add(
            source_endpoint=ENDPOINT_SINGLE,
            raw_payload=payload,
            validation_errors=_format_validation_errors(e),
        )
        session.commit()
        raise HTTPException(status_code=422, detail=e.errors()) from e

    repo = WeatherReadingRepository(session)
    inserted = repo.add(_to_orm(reading_in))
    return RawWeatherReadingSchema.model_validate(inserted)


@router.post(
    "/batch", status_code=201, response_model=list[RawWeatherReadingSchema],
    dependencies=[Depends(current_user)],
)
def post_batch(
    payload: list[dict[str, Any]],
    session: SessionDep,
) -> list[RawWeatherReadingSchema]:
    validated: list[RawWeatherReadingSchema] = []
    rejected: list[tuple[int, dict[str, Any], list[dict[str, Any]]]] = []
    for idx, item in enumerate(payload):
        try:
            validated.append(RawWeatherReadingSchema.model_validate(item))
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

    repo = WeatherReadingRepository(session)
    inserted = repo.add_many([_to_orm(s) for s in validated])
    return [RawWeatherReadingSchema.model_validate(r) for r in inserted]


@router.get("", response_model=list[RawWeatherReadingSchema])
def list_readings(
    session: SessionDep,
    source: Annotated[str | None, Query()] = None,
    zone_id: Annotated[str | None, Query()] = None,
    since: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
) -> list[RawWeatherReadingSchema]:
    repo = WeatherReadingRepository(session)
    if zone_id is not None and since is not None:
        rows = repo.get_recent_for_zone(zone_id, since=since, limit=limit)
    elif source is not None and since is not None:
        rows = repo.get_recent(source, since=since, limit=limit)
    else:
        stmt = select(WeatherReading).order_by(WeatherReading.timestamp.desc()).limit(limit)
        rows = list(session.execute(stmt).scalars())
    return [RawWeatherReadingSchema.model_validate(r) for r in rows]
