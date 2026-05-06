"""Phase BA.8 / BD.1 — dispersion-resolved cause-class attribution.

When the CFD lookup model is `current`, the recommendation orchestrator
can sharpen Phase Z's `cause_class` from "zone_type of the
attribution engine's top probable_source" to "zone_type of the source
zone whose CFD-resolved dispersion footprint dominates the affected
receptor under the current wind regime".

The lift: attribution scores sources by activity_intensity x
wind_angle x concurrent_pm_rise (a coarse proxy). With CFD, we
multiply each source's emission by the per-(source, receptor)
dispersion coefficient under the actual wind direction + speed.
Pit recirculation, valley channeling, and short-range vs long-range
sources separate cleanly.

Falls through gracefully:
* No `dispersion` model registered -> returns None.
* Distance-decay baseline registered (CFD not promoted) -> still works
  but degrades to the heuristic's geometric attribution.
* No source zones in the mine -> returns None.
* No current wind state -> returns None.

Returns the zone_type label (e.g. "haul_road", "pit", "crusher") so
it slots straight into the existing `cause_class` plumbing in
recommendations._resolve_cause_class.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import registry
from app.storage.models import WeatherReading, Zone

logger = logging.getLogger(__name__)

# Wind state lookback. The forecast's issue_at is the reference; we
# want the most recent observation strictly older than that for an
# anti-hindsight-clean attribution.
WIND_LOOKBACK_MIN = 60


def latest_wind_state(
    session: Session,
    *,
    as_of: datetime,
    lookback_min: int = WIND_LOOKBACK_MIN,
) -> tuple[float, float] | None:
    """Most recent (wind_direction_deg, wind_speed_ms) pair before `as_of`.

    Returns None if no usable reading lives in the lookback window.
    `as_of` is the forecast's issued_at — using a later weather row
    would be a hindsight leak (M.2 anti-hindsight rule 1).
    """
    since = as_of - timedelta(minutes=lookback_min)
    rows = session.execute(
        select(WeatherReading)
        .where(WeatherReading.timestamp <= as_of)
        .where(WeatherReading.timestamp >= since)
        .order_by(WeatherReading.timestamp.desc())
        .limit(1)
    ).scalars().all()
    if not rows:
        return None
    w = rows[0]
    if w.wind_direction_deg is None or w.wind_speed_ms is None:
        return None
    return float(w.wind_direction_deg), float(w.wind_speed_ms)


def resolve_cause_class_via_dispersion(
    session: Session,
    *,
    mine_id: str,
    receptor_id: str,
    as_of: datetime,
    stability: str = "neutral",
) -> str | None:
    """Return zone_type of the top-contributing source zone, or None.

    None means: orchestrator should fall through to the legacy
    attribution-based cause class (Phase Z behaviour pre-BA.8).
    """
    try:
        model = registry.get_current("dispersion")
    except registry.ModelNotFoundError:
        return None
    predict = getattr(model, "predict", None)
    if not callable(predict):
        return None

    wind = latest_wind_state(session, as_of=as_of)
    if wind is None:
        return None
    wind_dir, wind_speed = wind

    zones = list(
        session.execute(
            select(Zone).where(Zone.mine_id == mine_id)
        ).scalars()
    )
    if not zones:
        return None

    best_zone: Zone | None = None
    best_share = 0.0
    for zone in zones:
        share = _safe_predict(
            predict,
            source_zone_id=zone.zone_id,
            receptor_id=receptor_id,
            wind_direction_from_deg=wind_dir,
            wind_speed_ms=wind_speed,
            stability=stability,
        )
        if share > best_share:
            best_share = share
            best_zone = zone

    if best_zone is None or best_share <= 0.0:
        return None
    return str(best_zone.zone_type)


def _safe_predict(predict: Any, **kwargs: Any) -> float:
    """Tolerant wrapper: any model-side error -> contribution 0."""
    try:
        out = predict(**kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.debug("dispersion predict raised: %s", exc)
        return 0.0
    if isinstance(out, (int, float)):
        return float(out)
    return 0.0


__all__ = [
    "WIND_LOOKBACK_MIN",
    "latest_wind_state",
    "resolve_cause_class_via_dispersion",
]
