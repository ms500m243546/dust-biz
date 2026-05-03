"""Scheduled re-training hooks (Phase W.1).

Wires re-training callbacks into `app.domain.scheduler.Scheduler`.
Default cadence: weekly. Each invocation runs `train_many` over the
multi-station roster and writes fresh metric_payload rows; the
existing auto-promotion logic (P.3 / R.2 / U.2) decides whether to
flip `current` based on the new rows.

Tolerant by design: any failure logs INFO and lets the scheduler
keep ticking. Never raises into `Scheduler.tick()`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from app.domain.scheduler import Scheduler
from app.storage.database import session_scope
from app.training.dust_forecast_training import (
    MULTI_STATION_ROSTER,
    build_p1_protocol,
    train_many,
)

logger = logging.getLogger(__name__)

WEEKLY_RETRAIN_INTERVAL = timedelta(days=7)
DEFAULT_TRAINING_WINDOW_DAYS = 365


def weekly_dust_forecast_retrain(now: datetime) -> None:
    """Re-train all stations under the canonical Phase P.1 protocol.

    Pulls the most-recent year of data ending at `now`. Honestly per-
    station-failure-tolerant: train_many captures insufficient-data
    cases as placeholder TrainingResults so a thin station never
    aborts the batch.
    """
    end = now.replace(tzinfo=None) if now.tzinfo is not None else now
    train_to = end
    train_from = end - timedelta(days=DEFAULT_TRAINING_WINDOW_DAYS - 60)
    val_from = end - timedelta(days=53)
    val_to = end - timedelta(days=23)
    test_from = end - timedelta(days=15)
    test_to = end
    protocol = build_p1_protocol(
        train_window_from=train_from,
        train_window_to=train_to - timedelta(days=60),
        validation_window_from=val_from,
        validation_window_to=val_to,
        test_window_from=test_from,
        test_window_to=test_to,
    )
    try:
        with session_scope() as session:
            results = train_many(
                station_ids=MULTI_STATION_ROSTER,
                session=session,
                protocol=protocol,
                persist=True,
            )
        ok = sum(1 for r in results if r.metric_row_id is not None)
        logger.info(
            "weekly_dust_forecast_retrain: %d/%d stations persisted",
            ok,
            len(results),
        )
    except Exception as exc:  # broad: scheduler must not die on a retrain failure
        logger.info("weekly_dust_forecast_retrain skipped: %s", exc)


def register_weekly_retraining(
    scheduler: Scheduler,
    *,
    interval: timedelta = WEEKLY_RETRAIN_INTERVAL,
    first_run_in: timedelta | None = None,
    now: datetime | None = None,
) -> None:
    """Register the weekly retrain callback against the given scheduler.

    Idempotent: re-registering by name appends another job (matches
    Scheduler.register's contract), so callers should call this once
    per process.
    """
    scheduler.register(
        name="weekly_dust_forecast_retrain",
        interval=interval,
        func=weekly_dust_forecast_retrain,
        first_run_in=first_run_in,
        now=now or datetime.now(UTC),
    )


__all__ = [
    "DEFAULT_TRAINING_WINDOW_DAYS",
    "WEEKLY_RETRAIN_INTERVAL",
    "register_weekly_retraining",
    "weekly_dust_forecast_retrain",
]
