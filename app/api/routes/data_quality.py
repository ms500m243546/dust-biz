"""Data quality endpoint - S2 read surface.

GET /api/v1/data-quality              - score every known sensor
GET /api/v1/data-quality/{sensor_id}  - score one sensor
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.domain.data_quality import SensorHealthScorer
from app.schemas.sensor import SensorHealthStatusSchema
from app.storage.models import Sensor
from app.storage.repositories.sensor_readings import SensorReadingRepository

router = APIRouter(prefix="/data-quality", tags=["data-quality"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[SensorHealthStatusSchema])
def list_quality(session: SessionDep) -> list[SensorHealthStatusSchema]:
    sensors = list(session.execute(select(Sensor)).scalars())
    scorer = SensorHealthScorer(SensorReadingRepository(session))
    return [scorer.score(s.sensor_id) for s in sensors]


@router.get("/{sensor_id}", response_model=SensorHealthStatusSchema)
def get_quality(sensor_id: str, session: SessionDep) -> SensorHealthStatusSchema:
    sensor = session.get(Sensor, sensor_id)
    if sensor is None:
        raise HTTPException(status_code=404, detail=f"sensor not found: {sensor_id}")
    scorer = SensorHealthScorer(SensorReadingRepository(session))
    return scorer.score(sensor_id)
