"""S15 report endpoints (Phase K.2).

GET /api/v1/reports/model-performance  - latest-per-model aggregates
GET /api/v1/reports/roi                - cost / value summary over a window
GET /api/v1/reports/compliance         - per-station PM exceedance counts

All read-only. Auth-gated for any signed-in user; the data is already
audited at write time (predictions, recommendations, approvals,
outcomes, sensor readings, dust events all live in append-only
tables).

S15 failure mode (subsystem-contracts.md line 474): report generation
must never block the operational loop. Each handler returns a populated
payload even if some inputs are empty.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.auth import current_user
from app.api.deps import get_session
from app.domain.reports import (
    _bucket_readings,
    build_compliance_report,
    build_model_performance_report,
    build_roi_report,
)
from app.domain.training_data import load_and_assemble
from app.schemas.reports import (
    ComplianceReport,
    ModelPerformanceReport,
    ROIReport,
)
from app.schemas.site_config import (
    DEFAULT_PM10_THRESHOLDS,
    DEFAULT_PM25_THRESHOLDS,
    SiteConfigSchema,
)
from app.storage.models import (
    DustEvent,
    ModelPerformanceMetric,
    Sensor,
    SensorReading,
    User,
)
from app.storage.repositories.site_config import SiteConfigRepository

router = APIRouter(prefix="/reports", tags=["reports"])

SessionDep = Annotated[Session, Depends(get_session)]


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@router.get("/model-performance", response_model=ModelPerformanceReport)
def model_performance_report(
    session: SessionDep,
    _user: Annotated[User, Depends(current_user)],
    since_minutes: Annotated[int, Query(ge=1, le=24 * 60 * 90)] = 7 * 24 * 60,
) -> ModelPerformanceReport:
    now = _now()
    window_from = now - timedelta(minutes=since_minutes)
    rows = list(
        session.execute(
            select(ModelPerformanceMetric).where(
                ModelPerformanceMetric.evaluated_at >= window_from
            )
        ).scalars()
    )
    return build_model_performance_report(
        metrics=rows,
        generated_at=now,
        window_from=window_from,
        window_to=now,
    )


@router.get("/roi", response_model=ROIReport)
def roi_report(
    session: SessionDep,
    _user: Annotated[User, Depends(current_user)],
    since_minutes: Annotated[int, Query(ge=1, le=24 * 60 * 90)] = 30 * 24 * 60,
    site_id: Annotated[str | None, Query()] = None,
    observation_window_minutes: Annotated[int, Query(ge=1, le=24 * 60 * 7)] = 180,
    model_version: Annotated[str | None, Query()] = None,
) -> ROIReport:
    now = _now()
    window_from = now - timedelta(minutes=since_minutes)
    cost_curves = None
    if site_id is not None:
        cfg = SiteConfigRepository(session).get(site_id)
        if cfg is not None:
            cost_curves = SiteConfigSchema.model_validate(cfg).cost_curves
    records = load_and_assemble(
        session=session,
        window_from=window_from,
        window_to=now,
        now=now,
        observation_window=timedelta(minutes=observation_window_minutes),
        model_version=model_version,
    )
    return build_roi_report(
        training_records=records,
        cost_curves=cost_curves,
        generated_at=now,
        window_from=window_from,
        window_to=now,
        site_id=site_id,
    )


@router.get("/compliance", response_model=ComplianceReport)
def compliance_report(
    session: SessionDep,
    _user: Annotated[User, Depends(current_user)],
    since_minutes: Annotated[int, Query(ge=1, le=24 * 60 * 90)] = 24 * 60,
    site_id: Annotated[str | None, Query()] = None,
    mine_id: Annotated[str | None, Query()] = None,
) -> ComplianceReport:
    now = _now()
    window_from = now - timedelta(minutes=since_minutes)

    pm10_thresholds = dict(DEFAULT_PM10_THRESHOLDS)
    pm25_thresholds = dict(DEFAULT_PM25_THRESHOLDS)
    if site_id is not None:
        cfg = SiteConfigRepository(session).get(site_id)
        if cfg is not None:
            schema = SiteConfigSchema.model_validate(cfg)
            pm10_thresholds = schema.pm10_thresholds
            pm25_thresholds = schema.pm25_thresholds
            mine_id = mine_id or cfg.mine_id

    sensor_stmt = select(Sensor)
    if mine_id is not None:
        sensor_stmt = sensor_stmt.where(Sensor.mine_id == mine_id)
    sensors = list(session.execute(sensor_stmt).scalars())
    sensor_ids = [s.sensor_id for s in sensors]

    readings_stmt = (
        select(SensorReading)
        .where(SensorReading.timestamp >= window_from)
        .where(SensorReading.timestamp <= now)
    )
    if sensor_ids:
        readings_stmt = readings_stmt.where(SensorReading.sensor_id.in_(sensor_ids))
    readings = list(session.execute(readings_stmt).scalars())

    events_stmt = select(DustEvent).where(DustEvent.detected_at >= window_from)
    events = list(session.execute(events_stmt).scalars())

    return build_compliance_report(
        sensor_ids=sensor_ids,
        readings_by_sensor=_bucket_readings(readings),
        pm10_thresholds=pm10_thresholds,
        pm25_thresholds=pm25_thresholds,
        dust_events=events,
        generated_at=now,
        window_from=window_from,
        window_to=now,
        site_id=site_id,
    )
