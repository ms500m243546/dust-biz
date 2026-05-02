"""Recommendation endpoints (Phase H, S12).

GET  /api/v1/recommendations/current - compute-on-read for one zone
                                       (or empty list when no zones
                                       are registered yet)
POST /api/v1/recommendations         - issue a recommendation for a
                                       specific zone (compute + persist)
GET  /api/v1/recommendations/{id}    - look up a persisted record
GET  /api/v1/recommendations         - recent persisted history

Auth deferred to Phase I (H1-R1: same posture as forecast /
attribution / simulation endpoints). Per `safety-guardrails.md`
"Safety-reviewer subagent triggers", changes to this file should
trigger the safety reviewer before merge.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.domain.recommendations import (
    NoForecastError,
    ZoneNotFoundError,
    generate_recommendation,
)
from app.domain.site_config_resolver import MissingSiteConfigError
from app.schemas.recommendations import RecommendationSchema
from app.storage.models import Zone
from app.storage.repositories.recommendations import RecommendationRepository

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

SessionDep = Annotated[Session, Depends(get_session)]


class IssueRecommendationRequest(BaseModel):
    target_zone_id: str = Field(min_length=1)


@router.get("/current", response_model=RecommendationSchema | None)
def get_current_recommendation(
    session: SessionDep,
    target_zone_id: Annotated[str | None, Query()] = None,
) -> RecommendationSchema | None:
    """Compute-on-read for one zone.

    Smoke / discovery path: with no zones, returns null. With exactly
    one zone, defaults to it. With multiple, requires the caller to
    pass `target_zone_id`.
    """
    if target_zone_id is None:
        zones = list(session.query(Zone).limit(2).all())
        if not zones:
            return None
        if len(zones) > 1:
            raise HTTPException(
                status_code=400,
                detail="multiple zones registered; pass ?target_zone_id=",
            )
        target_zone_id = zones[0].zone_id

    try:
        return generate_recommendation(
            session=session, target_zone_id=target_zone_id
        )
    except ZoneNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NoForecastError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MissingSiteConfigError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("", response_model=RecommendationSchema)
def issue_recommendation(
    payload: IssueRecommendationRequest, session: SessionDep
) -> RecommendationSchema:
    try:
        return generate_recommendation(
            session=session, target_zone_id=payload.target_zone_id
        )
    except ZoneNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NoForecastError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MissingSiteConfigError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{recommendation_id}", response_model=RecommendationSchema)
def get_recommendation(
    recommendation_id: str, session: SessionDep
) -> RecommendationSchema:
    row = RecommendationRepository(session).get(recommendation_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"recommendation not found: {recommendation_id}",
        )
    return RecommendationSchema.model_validate(row)


@router.get("", response_model=list[RecommendationSchema])
def list_recent_recommendations(
    session: SessionDep,
    since_minutes: Annotated[int, Query(ge=1, le=24 * 60 * 7)] = 24 * 60,
    target_zone_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[RecommendationSchema]:
    since = (datetime.now(UTC) - timedelta(minutes=since_minutes)).replace(tzinfo=None)
    rows = RecommendationRepository(session).get_recent(
        since, limit=limit, target_zone_id=target_zone_id
    )
    return [RecommendationSchema.model_validate(r) for r in rows]
