"""Haul road segment admin endpoints.

GET  /api/v1/haul-road-segments[?mine_id=]   - list segments
GET  /api/v1/haul-road-segments/{segment_id} - single segment or 404
POST /api/v1/haul-road-segments              - upsert a segment

Watering / grading timestamps are mutated via the repository helpers
when interventions execute (Phase G, S9). They are not exposed as
admin fields here; admin upsert preserves the existing timestamps when
omitted from the payload.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.schemas.mine import HaulRoadSegmentSchema
from app.storage.models import HaulRoadSegment, Mine
from app.storage.repositories.haul_road_segments import HaulRoadSegmentRepository

router = APIRouter(prefix="/haul-road-segments", tags=["mine-map"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[HaulRoadSegmentSchema])
def list_segments(
    session: SessionDep,
    mine_id: Annotated[str | None, Query()] = None,
) -> list[HaulRoadSegmentSchema]:
    repo = HaulRoadSegmentRepository(session)
    rows = (
        repo.get_for_mine(mine_id)
        if mine_id is not None
        else list(session.execute(select(HaulRoadSegment)).scalars())
    )
    return [HaulRoadSegmentSchema.model_validate(r) for r in rows]


@router.get("/{segment_id}", response_model=HaulRoadSegmentSchema)
def get_segment(segment_id: str, session: SessionDep) -> HaulRoadSegmentSchema:
    seg = HaulRoadSegmentRepository(session).get(segment_id)
    if seg is None:
        raise HTTPException(status_code=404, detail=f"segment not found: {segment_id}")
    return HaulRoadSegmentSchema.model_validate(seg)


@router.post("", response_model=HaulRoadSegmentSchema, status_code=201)
def upsert_segment(
    payload: HaulRoadSegmentSchema, session: SessionDep
) -> HaulRoadSegmentSchema:
    if session.get(Mine, payload.mine_id) is None:
        raise HTTPException(
            status_code=400,
            detail=f"unknown mine_id: {payload.mine_id} (create the Mine row first)",
        )
    seg = HaulRoadSegmentRepository(session).upsert(
        segment_id=payload.segment_id,
        mine_id=payload.mine_id,
        from_node=payload.from_node,
        to_node=payload.to_node,
        length_m=payload.length_m,
        surface_type=payload.surface_type,
    )
    return HaulRoadSegmentSchema.model_validate(seg)
