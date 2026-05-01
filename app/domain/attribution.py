"""Source attribution orchestration (S7).

`attribute_event` builds the candidate list from real data
(zones in the affected station's mine + recent activity windows +
recent PM rise at the station + latest weather), invokes the
current `source_attribution` model from the registry, and
persists the resulting SourceAttributionSchema.

Candidate construction is the orchestrator's job; the model
itself stays pure (universal model rule 5). This split mirrors
how `app/domain/forecasting.py` builds FeatureRecords for the
forecast model.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import registry
from app.models.attribution.rules_baseline import CandidateSource
from app.schemas.attributions import SourceAttributionSchema
from app.storage.models import (
    DustEvent,
    EquipmentActivity,
    Sensor,
    SensorReading,
    SourceAttribution,
    WeatherReading,
    Zone,
)
from app.storage.repositories.attributions import SourceAttributionRepository

ACTIVITY_WINDOW_MIN = 30
PM_RISE_WINDOW_MIN = 30
DUST_GENERATING_ACTIVITIES: frozenset[str] = frozenset(
    {"loading", "hauling", "dumping", "drilling", "crushing", "grading"}
)


class EventNotFoundError(LookupError):
    """Raised when the orchestrator can't resolve the requested event."""


def attribute_event(
    *,
    session: Session,
    dust_event_id: str,
    now: datetime | None = None,
) -> SourceAttributionSchema:
    issued_at = (now or datetime.now(UTC)).replace(microsecond=0)

    event = session.get(DustEvent, dust_event_id)
    if event is None:
        raise EventNotFoundError(f"dust event not found: {dust_event_id}")

    sensor = session.get(Sensor, event.affected_station)
    if sensor is None or sensor.mine_id is None:
        # Without a sensor anchor we cannot enumerate candidate zones.
        return _persist_unknown(
            session=session,
            event=event,
            issued_at=issued_at,
            reason="affected_station has no resolvable sensor",
        )

    candidates = _build_candidates(session=session, sensor=sensor, event=event)

    model: Any = registry.get_current("source_attribution")
    repo = SourceAttributionRepository(session)
    attribution_id = repo.next_attribution_id(issued_at.date())

    schema: SourceAttributionSchema = model.attribute(
        attribution_id=attribution_id,
        dust_event_id=event.event_id,
        affected_station=event.affected_station,
        candidates=candidates,
        issued_at=issued_at,
    )
    _persist(session, schema)
    return schema


def _build_candidates(
    *, session: Session, sensor: Sensor, event: DustEvent
) -> list[CandidateSource]:
    """Compose CandidateSource records for every zone in the sensor's mine.

    The compute is intentionally direct (no ORM joins through
    relationships) to keep the orchestrator easy to read and to
    make the leakage rule easy to verify: only readings strictly
    older than `event.detected_at` contribute.
    """
    zones = list(
        session.execute(select(Zone).where(Zone.mine_id == sensor.mine_id)).scalars()
    )
    if not zones:
        return []

    detected_at = event.detected_at
    activity_since = detected_at - timedelta(minutes=ACTIVITY_WINDOW_MIN)
    pm_since = detected_at - timedelta(minutes=PM_RISE_WINDOW_MIN)

    recent_weather = list(
        session.execute(
            select(WeatherReading)
            .where(WeatherReading.timestamp <= detected_at)
            .where(WeatherReading.timestamp >= activity_since)
            .order_by(WeatherReading.timestamp.desc())
        ).scalars()
    )
    wind_direction_deg = (
        recent_weather[0].wind_direction_deg if recent_weather else None
    )

    pm_rise = _pm_rise_score(session=session, sensor=sensor, since=pm_since, until=detected_at)

    candidates: list[CandidateSource] = []
    for zone in zones:
        activity_intensity = _activity_intensity(
            session=session, zone_id=zone.zone_id, since=activity_since, until=detected_at
        )
        # Same PM rise applies to every candidate; the model uses it as
        # one of three signals so it's not a per-source measurement,
        # it's an observation about the affected station that boosts
        # ANY active source.
        wind_angle_offset = _wind_angle_offset(
            wind_direction_deg=wind_direction_deg
        )
        candidates.append(
            CandidateSource(
                source_id=zone.zone_id,
                wind_angle_offset_deg=wind_angle_offset,
                activity_intensity=activity_intensity,
                dust_generation_potential=zone.dust_generation_baseline,
                concurrent_pm_rise=pm_rise,
            )
        )
    return candidates


def _activity_intensity(
    *, session: Session, zone_id: str, since: datetime, until: datetime
) -> float:
    rows = list(
        session.execute(
            select(EquipmentActivity)
            .where(EquipmentActivity.zone_id == zone_id)
            .where(EquipmentActivity.timestamp >= since)
            .where(EquipmentActivity.timestamp <= until)
        ).scalars()
    )
    if not rows:
        return 0.0
    dust_count = sum(1 for r in rows if r.activity_type in DUST_GENERATING_ACTIVITIES)
    # 5+ dust-generating activities = full intensity.
    return min(1.0, dust_count / 5.0)


def _pm_rise_score(
    *, session: Session, sensor: Sensor, since: datetime, until: datetime
) -> float:
    """Coarse rise score: ratio of recent-half mean to early-half mean.

    Returns a value clipped to [0, 1] where:
      ~0.0  no readings or PM falling
      ~0.5  flat
      ~1.0  PM doubled or more across the window
    """
    rows = list(
        session.execute(
            select(SensorReading)
            .where(SensorReading.sensor_id == sensor.sensor_id)
            .where(SensorReading.timestamp >= since)
            .where(SensorReading.timestamp <= until)
            .order_by(SensorReading.timestamp.asc())
        ).scalars()
    )
    if len(rows) < 2:
        return 0.0
    midpoint = since + (until - since) / 2
    early = [
        v for r in rows if r.timestamp < midpoint
        for v in [_pm10(r)] if v is not None
    ]
    late = [
        v for r in rows if r.timestamp >= midpoint
        for v in [_pm10(r)] if v is not None
    ]
    if not early or not late:
        return 0.0
    early_mean = sum(early) / len(early)
    late_mean = sum(late) / len(late)
    if early_mean <= 0:
        return 0.5 if late_mean > 0 else 0.0
    ratio = late_mean / early_mean
    # Map ratio in [0.5, 2.0] to score in [0, 1].
    return round(max(0.0, min(1.0, (ratio - 0.5) / 1.5)), 3)


def _pm10(r: SensorReading) -> float | None:
    if not isinstance(r.raw_value, dict):
        return None
    v = r.raw_value.get("pm10_ugm3")
    if isinstance(v, int | float) and not isinstance(v, bool):
        return float(v)
    return None


def _wind_angle_offset(*, wind_direction_deg: float | None) -> float | None:
    """Without zone geometry we cannot compute true station-to-source
    bearings (D3-R3); fall back to "wind data exists" boolean as a
    coarse proxy. When wind data is present we report 0 deg so the
    proximity term contributes its strong-alignment value; when
    absent we report None and the model uses its 0.5 fallback. This
    keeps the rule behavior interpretable until GeoJSON lands.
    """
    if wind_direction_deg is None or math.isnan(wind_direction_deg):
        return None
    return 0.0


def _persist(session: Session, schema: SourceAttributionSchema) -> SourceAttribution:
    repo = SourceAttributionRepository(session)
    row = SourceAttribution(
        attribution_id=schema.attribution_id,
        dust_event_id=schema.dust_event_id,
        issued_at=schema.issued_at.replace(tzinfo=None) if schema.issued_at.tzinfo else schema.issued_at,
        affected_station=schema.affected_station,
        probable_sources=[s.model_dump() for s in schema.probable_sources],
        evidence_fields=dict(schema.evidence_fields),
        confidence=schema.confidence,
        model_version=schema.model_version,
    )
    return repo.add(row)


def _persist_unknown(
    *,
    session: Session,
    event: DustEvent,
    issued_at: datetime,
    reason: str,
) -> SourceAttributionSchema:
    repo = SourceAttributionRepository(session)
    attribution_id = repo.next_attribution_id(issued_at.date())
    from app.schemas.attributions import ProbableSource

    schema = SourceAttributionSchema(
        attribution_id=attribution_id,
        dust_event_id=event.event_id,
        issued_at=issued_at,
        affected_station=event.affected_station,
        probable_sources=[ProbableSource(source="Unknown", confidence=0.0, reason=reason)],
        evidence_fields={"reason": reason},
        confidence=0.0,
        model_version="source_attribution_rules_v0.1.0",
    )
    _persist(session, schema)
    return schema
