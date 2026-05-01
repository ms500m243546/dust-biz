"""Dust event creation paths (Phase F).

Two ways an event lands in `dust_events`:

1. `record_manual_event` - operator-entered (G12). Trusts the
   caller's payload and timestamps; events are immutable once
   written.
2. `trigger_events_from_forecasts` - scans recent DustPredictions
   for breach probability above the configurable threshold and
   materializes one `threshold_trigger`-source event per
   (target, day) pair, with `linked_prediction_ids` carrying the
   prediction IDs that crossed.

Background scheduling for (2) is deferred to Phase K; today this
is a manual-call orchestrator the API layer (and tests) drive.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.schemas.dust_events import DustEventCreate, DustEventSchema
from app.storage.models import DustEvent, Sensor
from app.storage.repositories.dust_events import DustEventRepository
from app.storage.repositories.forecasts import DustPredictionRepository

DEFAULT_TRIGGER_BREACH_PROBABILITY = 0.7


class UnknownStationError(LookupError):
    """Raised when a manual entry references a sensor that doesn't exist."""


def record_manual_event(
    *, session: Session, payload: DustEventCreate
) -> DustEventSchema:
    """G12: operator-recorded dust event."""
    if session.get(Sensor, payload.affected_station) is None:
        raise UnknownStationError(
            f"affected_station not found: {payload.affected_station}"
        )

    repo = DustEventRepository(session)
    detected_at = payload.detected_at
    if detected_at.tzinfo is not None:
        detected_at = detected_at.astimezone(UTC).replace(tzinfo=None)

    event_id = repo.next_event_id(detected_at.date())
    row = DustEvent(
        event_id=event_id,
        detected_at=detected_at,
        affected_station=payload.affected_station,
        peak_pm10=payload.peak_pm10,
        peak_pm25=payload.peak_pm25,
        breach_occurred=payload.breach_occurred,
        event_source=payload.event_source,
        linked_prediction_ids=list(payload.linked_prediction_ids),
        notes=payload.notes,
    )
    repo.add(row)
    return DustEventSchema.model_validate(row)


def trigger_events_from_forecasts(
    *,
    session: Session,
    sensor_id: str,
    breach_threshold: float = DEFAULT_TRIGGER_BREACH_PROBABILITY,
    since_minutes: int = 60,
    now: datetime | None = None,
) -> list[DustEventSchema]:
    """Materialize threshold-trigger events from recent forecasts.

    Restricted to sensor-targeted forecasts: `affected_station` is
    a sensor FK in `dust_events`, so the trigger only meaningfully
    applies to forecasts already keyed on a sensor. Zone-target
    forecasts can become events via operator manual entry instead.

    Idempotency: at most one trigger event per (sensor, UTC day);
    if one already exists for today, additional crossing forecasts
    are linked to that event by appending their IDs.
    """
    if session.get(Sensor, sensor_id) is None:
        raise UnknownStationError(f"sensor not found: {sensor_id}")

    issued_now = (now or datetime.now(UTC)).replace(microsecond=0, tzinfo=None)
    since = issued_now - timedelta(minutes=since_minutes)

    predictions = DustPredictionRepository(session).get_recent(
        "sensor", sensor_id, since=since
    )
    crossing = [p for p in predictions if p.breach_probability >= breach_threshold]
    if not crossing:
        return []

    repo = DustEventRepository(session)
    today = issued_now.date()
    today_start = datetime.combine(today, datetime.min.time())
    existing = [
        e
        for e in repo.get_recent(today_start, limit=500, station=sensor_id)
        if e.event_source == "threshold_trigger"
    ]

    if existing:
        event = existing[0]
        already = set(event.linked_prediction_ids or [])
        added = [p.prediction_id for p in crossing if p.prediction_id not in already]
        if added:
            event.linked_prediction_ids = list(already) + added
            event.peak_pm10 = max(event.peak_pm10, max(p.predicted_pm10 for p in crossing))
            event.peak_pm25 = max(event.peak_pm25, max(p.predicted_pm25 for p in crossing))
            event.breach_occurred = event.breach_occurred or any(
                p.breach_probability >= 0.85 for p in crossing
            )
            session.flush()
        return [DustEventSchema.model_validate(event)]

    peak_pm10 = max(p.predicted_pm10 for p in crossing)
    peak_pm25 = max(p.predicted_pm25 for p in crossing)
    event_id = repo.next_event_id(today)
    row = DustEvent(
        event_id=event_id,
        detected_at=issued_now,
        affected_station=sensor_id,
        peak_pm10=peak_pm10,
        peak_pm25=peak_pm25,
        breach_occurred=any(p.breach_probability >= 0.85 for p in crossing),
        event_source="threshold_trigger",
        linked_prediction_ids=[p.prediction_id for p in crossing],
        notes=f"breach_probability >= {breach_threshold} on {len(crossing)} forecast(s)",
    )
    repo.add(row)
    return [DustEventSchema.model_validate(row)]


__all__ = [
    "DEFAULT_TRIGGER_BREACH_PROBABILITY",
    "UnknownStationError",
    "record_manual_event",
    "trigger_events_from_forecasts",
]
