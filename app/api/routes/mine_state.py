"""Mine state endpoints (S4).

GET /api/v1/mine-state/current?mine_id=...&window_minutes=15
GET /api/v1/mine-state/zones/{zone_id}?window_minutes=15

Compute-on-read: each request runs the heuristic engine over the
configured window. The endpoint persists the result via
`MineStateSnapshotRepository` so audit / replay / future S14 training
data assembly can reconstruct what the system saw. Persisting on read
is acceptable at MVP scale (R8 covers the Postgres swap when
throughput becomes a constraint).

The handler enforces S3's "fail loud" rule via `require_resolved`: if
no site_configuration and no Mine row exist for the requested
`mine_id`, the request 404s rather than fabricating defaults.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.domain.mine_state import compute_zone_state
from app.domain.site_config_resolver import MissingSiteConfigError, require_resolved
from app.schemas.mine_state import MineStateSchema, MineStateZoneSchema
from app.storage.models import (
    EquipmentActivity,
    Mine,
    MineStateSnapshot,
    WeatherReading,
    Zone,
)
from app.storage.repositories.mine_state import MineStateSnapshotRepository
from app.storage.repositories.site_config import SiteConfigRepository
from app.storage.repositories.zones import ZoneRepository

router = APIRouter(prefix="/mine-state", tags=["mine-state"])

SessionDep = Annotated[Session, Depends(get_session)]

WindowParam = Annotated[int, Query(ge=1, le=240)]


def _ensure_authoritative_config(session: Session, mine_id: str) -> None:
    """Apply S3 fail-loud rule (D-R2 closure)."""
    site_cfg = next(iter(SiteConfigRepository(session).get_for_mine(mine_id)), None)
    mine = session.get(Mine, mine_id)
    try:
        require_resolved(mine_id=mine_id, site_config=site_cfg, mine=mine)
    except MissingSiteConfigError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _recent_activity_for_zone(
    session: Session, zone_id: str, since: datetime
) -> list[EquipmentActivity]:
    stmt = (
        select(EquipmentActivity)
        .where(EquipmentActivity.zone_id == zone_id)
        .where(EquipmentActivity.timestamp >= since)
        .order_by(EquipmentActivity.timestamp.desc())
    )
    return list(session.execute(stmt).scalars())


def _recent_weather_for_mine(
    session: Session, mine_id: str, since: datetime
) -> list[WeatherReading]:
    # Weather is sourced per-mine via on-site stations; we accept any
    # weather row whose `zone_id` belongs to the mine, plus rows with
    # no zone (mine-level station). Filtering by mine without a join
    # column on weather_readings keeps the query simple.
    mine_zone_ids = list(
        session.execute(select(Zone.zone_id).where(Zone.mine_id == mine_id)).scalars()
    )
    stmt = (
        select(WeatherReading)
        .where(WeatherReading.timestamp >= since)
        .where(
            (WeatherReading.zone_id.is_(None))
            | (WeatherReading.zone_id.in_(mine_zone_ids))
        )
        .order_by(WeatherReading.timestamp.desc())
    )
    return list(session.execute(stmt).scalars())


def _persist(
    session: Session, mine_id: str, computed: list[MineStateZoneSchema]
) -> None:
    repo = MineStateSnapshotRepository(session)
    rows = [
        MineStateSnapshot(
            timestamp=z.timestamp,
            zone_id=z.zone_id,
            activity=z.activity,
            equipment_active=list(z.equipment_active),
            production_rate_tph=z.production_rate_tph,
            dust_generation_potential=z.dust_generation_potential,
            wind_exposure=z.wind_exposure,
            downwind_assets=list(z.downwind_assets),
            operational_importance=z.operational_importance,
            staleness_flags=list(z.staleness_flags),
        )
        for z in computed
    ]
    if rows:
        repo.add_many(rows)
    _ = mine_id  # surfacing arg keeps call sites consistent if mine-level metadata is added


@router.get("/current", response_model=MineStateSchema)
def get_current_state(
    session: SessionDep,
    mine_id: Annotated[str | None, Query()] = None,
    window_minutes: WindowParam = 15,
) -> MineStateSchema:
    now = datetime.now(UTC).replace(tzinfo=None)

    # No mine_id: smoke / discovery path. If no mines are registered,
    # return an empty payload (200) rather than 404. If one mine
    # exists, default to it. With multiple mines, force the caller to
    # disambiguate.
    if mine_id is None:
        mines = list(session.execute(select(Mine)).scalars())
        if not mines:
            return MineStateSchema(
                mine_id="",
                computed_at=now,
                window_minutes=window_minutes,
                zones=[],
            )
        if len(mines) > 1:
            raise HTTPException(
                status_code=400,
                detail="multiple mines registered; pass ?mine_id=...",
            )
        mine_id = mines[0].mine_id

    _ensure_authoritative_config(session, mine_id)

    since = now - timedelta(minutes=window_minutes)

    zones = ZoneRepository(session).get_for_mine(mine_id)
    weather = _recent_weather_for_mine(session, mine_id, since)
    downwind_candidates = zones

    computed: list[MineStateZoneSchema] = []
    for zone in zones:
        activity = _recent_activity_for_zone(session, zone.zone_id, since)
        state = compute_zone_state(
            zone=zone,
            now=now,
            window_minutes=window_minutes,
            recent_activity=activity,
            recent_weather=weather,
            downwind_candidates=downwind_candidates,
        )
        computed.append(state)

    _persist(session, mine_id, computed)

    return MineStateSchema(
        mine_id=mine_id,
        computed_at=now,
        window_minutes=window_minutes,
        zones=computed,
    )


@router.get("/zones/{zone_id}", response_model=MineStateZoneSchema)
def get_zone_state(
    zone_id: str,
    session: SessionDep,
    window_minutes: WindowParam = 15,
) -> MineStateZoneSchema:
    zone = ZoneRepository(session).get(zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail=f"zone not found: {zone_id}")

    _ensure_authoritative_config(session, zone.mine_id)

    now = datetime.now(UTC).replace(tzinfo=None)
    since = now - timedelta(minutes=window_minutes)
    activity = _recent_activity_for_zone(session, zone.zone_id, since)
    weather = _recent_weather_for_mine(session, zone.mine_id, since)
    downwind_candidates = ZoneRepository(session).get_for_mine(zone.mine_id)

    state = compute_zone_state(
        zone=zone,
        now=now,
        window_minutes=window_minutes,
        recent_activity=activity,
        recent_weather=weather,
        downwind_candidates=downwind_candidates,
    )
    _persist(session, zone.mine_id, [state])
    return state
