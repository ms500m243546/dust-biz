"""Point-in-time (PIT) query helpers (Phase M.2).

Anti-hindsight protocol enforcement at the read side. Every domain
caller that consumes PIT-tracked tables (`SensorReading`,
`WeatherReading`, label tables) goes through this module so the
"as-of" filter is applied uniformly.

Decision rule (`docs/anti-hindsight-protocol.md`):

    A record is legal as a training feature for a prediction at time
    `p_t` iff:
      record.valid_from <= p_t  AND  (record.valid_to IS NULL OR record.valid_to > p_t)

Equivalently for label-PIT tables:
      record.labeled_at <= p_t

This module exposes pure helpers — they take a SQLAlchemy session +
the model class + the prediction-time and return a filtered
`Select` statement. Domain modules execute the statement; this
module never touches I/O directly.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, func, not_, or_, select

from app.storage.models import (
    ActionOutcome,
    DustEvent,
    Recommendation,
    RecommendationApproval,
    SensorReading,
    SourceAttribution,
    WeatherReading,
)


def sensor_readings_as_of(prediction_time: datetime) -> Select[tuple[Any, ...]]:
    """Return a `Select` over `sensor_readings` filtered to records
    that were knowable at `prediction_time`.

    PIT semantics:
      valid_from <= prediction_time
      AND (valid_to IS NULL OR valid_to > prediction_time)

    Caller adds further filters (sensor_id, timestamp window, etc.)
    and executes via the session.
    """
    return (
        select(SensorReading)
        .where(SensorReading.valid_from <= prediction_time)
        .where(
            (SensorReading.valid_to.is_(None))
            | (SensorReading.valid_to > prediction_time)
        )
    )


def weather_readings_as_of(
    prediction_time: datetime,
    *,
    realtime_only: bool = True,
) -> Select[tuple[Any, ...]]:
    """Return a `Select` over `weather_readings` filtered for realtime use.

    `realtime_only=True` (the default for any model with
    `intended_for_realtime=True`) filters out reanalysis sources
    (ERA5, MERRA-2). Set `realtime_only=False` to include reanalysis
    rows for retrospective / climatological analysis.

    Note: `WeatherReading` does not yet carry `valid_from`/`valid_to`
    columns at M.2 — its PIT semantics are encoded in the
    `realtime_proxy` flag plus the `timestamp` column. Future
    extension (M.2.1, if needed) can add a `valid_from`/`valid_to`
    pair when forecast-model weather features land.
    """
    stmt = select(WeatherReading).where(
        WeatherReading.timestamp <= prediction_time
    )
    if realtime_only:
        stmt = stmt.where(WeatherReading.realtime_proxy.is_(True))
    return stmt


def labels_as_of(
    label_model: type, prediction_time: datetime
) -> Select[tuple[Any, ...]]:
    """Return a `Select` over a label-PIT table filtered to labels
    knowable at `prediction_time`.

    `label_model` must be one of: `DustEvent`, `Recommendation`,
    `RecommendationApproval`, `ActionOutcome`, `SourceAttribution`
    — i.e., a table that gained a `labeled_at` column in M.2.
    """
    if label_model not in (
        DustEvent,
        Recommendation,
        RecommendationApproval,
        ActionOutcome,
        SourceAttribution,
    ):
        raise ValueError(
            f"labels_as_of only supports PIT label tables; got {label_model}"
        )
    return select(label_model).where(label_model.labeled_at <= prediction_time)


def features_pre_intervention(
    prediction_time: datetime,
    *,
    intervention_lag: timedelta = timedelta(hours=3),
    sensor_id: str | None = None,
) -> Select[tuple[Any, ...]]:
    """Sensor-reading features with operator-intervention windows excluded.

    M.3 causal-protocol: pre-intervention feature filter. When training a
    forecaster (S6) or attribution model (S7), the goal is to learn the
    *natural* PM10 trajectory rather than the post-intervention reality.
    This helper drops feature rows that fall within `intervention_lag`
    of any logged operator approval.

    M.3.1 implementation note: best-effort heuristic. We use
    `RecommendationApproval.decided_at` as the proxy for "operator
    acted." Catches DustOps-mediated interventions but misses
    operator-initiated actions outside the system. M.3.3 will tighten
    to a hard cutoff once `ActionOutcome.intervention_window` lands
    via the operator-real adapter.

    Returns a `Select[SensorReading]` filtered for both PIT validity
    AND non-overlap with intervention windows. Caller adds further
    filters (timestamp range, sensor_id) and executes.
    """
    base = sensor_readings_as_of(prediction_time)
    if sensor_id is not None:
        base = base.where(SensorReading.sensor_id == sensor_id)

    # Correlated EXISTS subquery: filter out any SensorReading whose
    # `timestamp` falls inside an approval window
    # [decided_at, decided_at + intervention_lag).
    #
    # SQLite lacks native datetime + interval arithmetic, so we compute
    # the window upper-bound via `datetime(decided_at, '+N seconds')`.
    # This SQL form is also valid in PostgreSQL once the dialect
    # rewrite happens (Phase B/E roadmap).
    lag_seconds = int(intervention_lag.total_seconds())
    window_end = func.datetime(
        RecommendationApproval.decided_at, f"+{lag_seconds} seconds"
    )
    intervention_overlap = (
        select(RecommendationApproval.approval_id)
        .where(
            and_(
                SensorReading.timestamp >= RecommendationApproval.decided_at,
                SensorReading.timestamp < window_end,
            )
        )
        .correlate(SensorReading)
        .exists()
    )
    base = base.where(not_(intervention_overlap))
    # `or_` reserved for future extension when intervention_window has
    # explicit end timestamps via the operator-real adapter (M.3.3).
    _ = or_
    return base


__all__ = [
    "features_pre_intervention",
    "labels_as_of",
    "sensor_readings_as_of",
    "weather_readings_as_of",
]
