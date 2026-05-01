"""Dust forecast endpoints (S6).

GET /api/v1/forecasts/current?target_kind=zone&target_id=...&horizon=60min
GET /api/v1/forecasts/history?target_kind=zone&target_id=...&since_minutes=120

Compute-on-read for `current`: each request runs the orchestrator
(features + model + audit write). `history` reads previously
persisted DustPredictions.

The empty-DB happy path mirrors `mine-state/current`: with no zones
registered the endpoint returns 200 + empty result so smoke can pass
before the operator wires real data. With a target argument that
doesn't resolve we 404.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.domain.forecasting import TargetNotFoundError, issue_forecast
from app.models import registry
from app.models.forecasting.heuristic_baseline import HeuristicBaselineForecaster
from app.schemas.forecasts import (
    DustForecastSchema,
    ForecastHorizon,
    ForecastTargetSchema,
)
from app.storage.models import Zone
from app.storage.repositories.forecasts import DustPredictionRepository

router = APIRouter(prefix="/forecasts", tags=["forecasts"])

SessionDep = Annotated[Session, Depends(get_session)]
TargetKind = Literal["zone", "sensor"]


def _ensure_baseline_registered() -> None:
    """Lazy registration so the registry has a default model.

    The registry is process-global. In production the bootstrap path
    runs once at startup; in tests it's reset between cases. Calling
    this on each request keeps both paths simple at MVP scale.
    """
    try:
        registry.get_current("dust_forecast")
    except registry.ModelNotFoundError:
        registry.register(HeuristicBaselineForecaster())


@router.get("/current", response_model=DustForecastSchema | None)
def get_current_forecast(
    session: SessionDep,
    target_kind: Annotated[TargetKind | None, Query()] = None,
    target_id: Annotated[str | None, Query()] = None,
    horizon: Annotated[ForecastHorizon, Query()] = "60min",
    window_minutes: Annotated[int, Query(ge=1, le=240)] = 60,
) -> DustForecastSchema | None:
    _ensure_baseline_registered()

    # Smoke / discovery path: no target supplied. If no zones exist,
    # return null so smoke can hit this endpoint before any data is
    # loaded. If exactly one zone exists, default to it.
    if target_kind is None or target_id is None:
        zones = list(session.query(Zone).limit(2).all())
        if not zones:
            return None
        if len(zones) > 1:
            raise HTTPException(
                status_code=400,
                detail="multiple zones registered; pass ?target_kind=&target_id=",
            )
        target_kind = "zone"
        target_id = zones[0].zone_id

    target = ForecastTargetSchema(target_kind=target_kind, target_id=target_id)
    try:
        return issue_forecast(
            session=session,
            target=target,
            horizon=horizon,
            window_minutes=window_minutes,
        )
    except TargetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/history", response_model=list[DustForecastSchema])
def get_forecast_history(
    session: SessionDep,
    target_kind: Annotated[TargetKind, Query()],
    target_id: Annotated[str, Query()],
    since_minutes: Annotated[int, Query(ge=1, le=24 * 60)] = 60,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[DustForecastSchema]:
    repo = DustPredictionRepository(session)
    since = (datetime.now(UTC) - timedelta(minutes=since_minutes)).replace(tzinfo=None)
    rows = repo.get_recent(target_kind, target_id, since=since, limit=limit)
    return [DustForecastSchema.model_validate(r) for r in rows]
