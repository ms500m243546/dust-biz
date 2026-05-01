"""S4 - Real-Time Mine State Engine (heuristic core).

Pure-function compute layer. Given recent equipment activity, recent
weather, and resolved site config, produce a `MineStateZoneSchema` for
one zone.

Heuristics only (CLAUDE.md rule 13: no deep learning before
heuristics). The schema's `staleness_flags` field is the authoritative
S4 failure-mode hook (subsystem-contracts.md): if a stream is missing
or stale, the affected output is marked rather than fabricated.

Why pure functions: the API layer (D.4) calls this with a session and
some lookups; future S5/S7/S11 callers will pass the same inputs.
Keeping the function free of session state makes it directly testable
without TestClient or DB fixtures beyond what the inputs require.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timedelta
from typing import cast

from app.schemas.mine_state import (
    DustGenerationPotential,
    MineStateZoneSchema,
    WindExposure,
    ZoneActivity,
)
from app.storage.models import EquipmentActivity, WeatherReading, Zone

DUST_GENERATING_ACTIVITIES: frozenset[str] = frozenset(
    {"loading", "hauling", "dumping", "drilling", "crushing", "grading"}
)

# Map zone dust_generation_baseline + observed activity intensity onto
# a coarse potential level. Not calibrated against site data; revisit
# in Phase E when forecast features expose ground truth (D3-R1).
_BASELINE_BUMP: dict[str, dict[str, DustGenerationPotential]] = {
    "low":    {"none": "low",     "light": "low",    "heavy": "medium"},
    "medium": {"none": "low",     "light": "medium", "heavy": "high"},
    "high":   {"none": "medium",  "light": "high",   "heavy": "high"},
}


def compute_zone_state(
    *,
    zone: Zone,
    now: datetime,
    window_minutes: int,
    recent_activity: list[EquipmentActivity],
    recent_weather: list[WeatherReading],
    downwind_candidates: list[Zone],
) -> MineStateZoneSchema:
    """Compute one zone's current MineState.

    `recent_activity` and `recent_weather` should already be filtered
    to the window; this function trusts the caller's filter rather
    than re-querying. `downwind_candidates` is the set of zones the
    caller wants checked for downwind exposure (typically all
    `boundary` + `loading_area` + community-tagged zones in the mine).
    """

    window_start = now - timedelta(minutes=window_minutes)
    staleness: list[str] = []

    activity, equipment_active, intensity = _summarize_activity(recent_activity)
    if not recent_activity:
        staleness.append("equipment_activity_missing")
    elif _max_timestamp(recent_activity) < window_start:
        staleness.append("equipment_activity_stale")

    wind = _latest_wind(recent_weather)
    if wind is None:
        staleness.append("weather_missing")
        wind_exposure: WindExposure = "unknown"
        downwind_assets: list[str] = []
    elif wind.timestamp < window_start:
        staleness.append("weather_stale")
        wind_exposure = "unknown"
        downwind_assets = []
    else:
        wind_exposure = _wind_exposure_level(wind.wind_speed_ms, wind.gust_speed_ms)
        downwind_assets = _downwind_asset_ids(
            zone=zone,
            wind_direction_deg=wind.wind_direction_deg,
            candidates=downwind_candidates,
        )

    dust_potential: DustGenerationPotential = _dust_generation_potential(
        baseline=zone.dust_generation_baseline,
        intensity=intensity,
        weather_missing=("weather_missing" in staleness or "weather_stale" in staleness),
    )

    return MineStateZoneSchema(
        timestamp=now,
        zone_id=zone.zone_id,
        activity=activity,
        equipment_active=equipment_active,
        production_rate_tph=_production_rate_tph(recent_activity, window_minutes),
        dust_generation_potential=dust_potential,
        wind_exposure=wind_exposure,
        downwind_assets=downwind_assets,
        operational_importance=zone.operational_importance,
        staleness_flags=staleness,
    )


def _summarize_activity(
    activities: list[EquipmentActivity],
) -> tuple[ZoneActivity, list[str], str]:
    """Return (activity_label, equipment_active_ids, intensity)."""
    if not activities:
        return "unknown", [], "none"

    counts = Counter(a.activity_type for a in activities)
    if not counts:
        return "idle", [], "none"

    top_kind, top_count = counts.most_common(1)[0]
    others = sum(1 for k, v in counts.items() if k != top_kind and v > 0)
    label_raw = top_kind if others == 0 else "mixed"
    label: ZoneActivity = cast(ZoneActivity, label_raw if label_raw in _ZONE_ACTIVITY else "unknown")

    equipment_active = sorted({a.equipment_id for a in activities})

    dust_count = sum(v for k, v in counts.items() if k in DUST_GENERATING_ACTIVITIES)
    intensity = "heavy" if dust_count >= 5 else "light" if dust_count > 0 else "none"
    # top_count participates in the intensity calc indirectly via dust_count;
    # keeping the local for readers tracing the heuristic.
    _ = top_count
    return label, equipment_active, intensity


_ZONE_ACTIVITY: frozenset[str] = frozenset(
    {
        "idle",
        "loading",
        "hauling",
        "dumping",
        "drilling",
        "crushing",
        "watering",
        "grading",
        "maintenance",
        "mixed",
        "unknown",
    }
)


def _production_rate_tph(
    activities: list[EquipmentActivity], window_minutes: int
) -> float | None:
    if not activities or window_minutes <= 0:
        return None
    total_t = sum(a.tonnage for a in activities if a.tonnage is not None)
    if total_t <= 0:
        return None
    return round(total_t * (60.0 / window_minutes), 1)


def _max_timestamp(activities: list[EquipmentActivity]) -> datetime:
    return max(a.timestamp for a in activities)


def _latest_wind(readings: list[WeatherReading]) -> WeatherReading | None:
    candidates = [r for r in readings if r.wind_direction_deg is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda r: r.timestamp)


def _wind_exposure_level(
    wind_speed_ms: float | None, gust_speed_ms: float | None
) -> WindExposure:
    speed = wind_speed_ms or 0.0
    gust = gust_speed_ms or speed
    high_marker = max(speed, gust)
    # Thresholds from docs/mining-domain.md general guidance: <3 m/s
    # low transport potential, 3-7 medium, >7 high. Calibrate per site
    # in Phase E when forecast features land.
    if high_marker >= 7.0:
        return "high"
    if high_marker >= 3.0:
        return "medium"
    return "low"


def _dust_generation_potential(
    *, baseline: str, intensity: str, weather_missing: bool
) -> DustGenerationPotential:
    if weather_missing:
        return "unknown"
    bumped = _BASELINE_BUMP.get(baseline, {}).get(intensity)
    if bumped is None:
        return "unknown"
    return bumped


def _downwind_asset_ids(
    *,
    zone: Zone,
    wind_direction_deg: float | None,
    candidates: list[Zone],
) -> list[str]:
    """Straight-line downwind detection.

    Wind direction is reported as the direction the wind is coming
    FROM (meteorological convention). Downwind from `zone` lies in the
    opposite direction. Without zone geometry (data-contracts.md marks
    geometry optional in MVP), we can only return candidates whose
    zone_type is plausibly downwind-exposed (`boundary`,
    `loading_area`, or any zone tagged `critical`); refining this is
    D3-R3 - revisit when GeoJSON lands.
    """
    if wind_direction_deg is None or math.isnan(wind_direction_deg):
        return []
    return sorted(
        c.zone_id
        for c in candidates
        if c.zone_id != zone.zone_id
        and (c.zone_type in {"boundary", "loading_area"} or c.operational_importance == "critical")
    )
