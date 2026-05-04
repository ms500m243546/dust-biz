"""Dust-forecast model auto-promotion (Phase P.3).

Decides whether to flip the registry's `current` `dust_forecast`
pointer from the heuristic baseline to the trained GBM, based on
the latest persisted M.4 `model_performance_metrics` row.

Layered: this module sits in `app/domain` so it can import both
`app/models` (registry) and `app/storage` (repos). The API lifespan
hook calls `maybe_promote_gbm()` once at startup; tests can call it
directly. Never raises in the bootstrap path — failures log INFO
and leave the heuristic as current.
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.models import registry
from app.models.forecasting.gbm_shared_v0_1_0 import GBM_SHARED_VERSION
from app.models.forecasting.gbm_v0_1_0 import GBM_VERSION
from app.storage.database import session_scope
from app.storage.repositories.model_performance import (
    ModelPerformanceMetricRepository,
)
from app.training.dust_forecast_training import (
    MULTI_STATION_ROSTER,
    decide_promotion,
    decide_shared_promotion,
)

logger = logging.getLogger(__name__)


def maybe_promote_gbm() -> bool:
    """If the latest GBM metric row passes promotion criteria, promote.

    Returns True when the registry's `current` pointer was flipped to
    the GBM, False otherwise. Failure reasons are logged at INFO so
    operators can see why promotion was held.

    Tolerant by design: any storage / decode / registry exception
    leaves the heuristic as current, logs the cause, and returns
    False. Never raises into the bootstrap path.
    """
    try:
        with session_scope() as session:
            repo = ModelPerformanceMetricRepository(session)
            latest = repo.latest_for_version(GBM_VERSION)
            if latest is None:
                logger.info(
                    "gbm promotion held: no model_performance row for %s",
                    GBM_VERSION,
                )
                return False
            decision = decide_promotion(latest.metric_payload or {})
            if not decision.passed:
                logger.info(
                    "gbm promotion held: %s",
                    "; ".join(decision.reasons),
                )
                return False
            registry.set_current("dust_forecast", GBM_VERSION)
            logger.info("gbm promoted to current (metric_id=%s)", latest.metric_id)
            return True
    except Exception as exc:  # broad: bootstrap must never raise
        logger.info("gbm promotion skipped: %s", exc)
        return False


def maybe_promote_gbm_shared() -> bool:
    """Phase X — flip `current` to the shared multi-station GBM if it wins.

    Runs after `maybe_promote_gbm()`. Compares the latest shared
    metric_payload against the latest per-station metric_payloads
    (one per station in MULTI_STATION_ROSTER) using
    `decide_shared_promotion`. Promotes only when shared is non-worse
    on every station and strictly better on at least one.

    Tolerant by design: any failure in the comparison or registry
    leaves whatever was previously `current` in place, logs the cause,
    and returns False. Never raises into the bootstrap path.
    """
    try:
        with session_scope() as session:
            repo = ModelPerformanceMetricRepository(session)
            shared_row = repo.latest_for_version(GBM_SHARED_VERSION)
            if shared_row is None:
                logger.info(
                    "shared gbm promotion held: no metric row for %s",
                    GBM_SHARED_VERSION,
                )
                return False
            per_station_payloads: dict[str, dict[str, object]] = {}
            for station_id in MULTI_STATION_ROSTER:
                ps_row = _latest_per_station_payload(repo, station_id)
                if ps_row is not None:
                    per_station_payloads[station_id] = ps_row
            decision = decide_shared_promotion(
                shared_payload=shared_row.metric_payload or {},
                per_station_payloads=per_station_payloads,
            )
            if not decision.passed:
                logger.info(
                    "shared gbm promotion held: %s",
                    "; ".join(decision.reasons),
                )
                return False
            registry.set_current("dust_forecast", GBM_SHARED_VERSION)
            logger.info(
                "shared gbm promoted to current (metric_id=%s)",
                shared_row.metric_id,
            )
            return True
    except Exception as exc:  # broad: bootstrap must never raise
        logger.info("shared gbm promotion skipped: %s", exc)
        return False


def _latest_per_station_payload(
    repo: ModelPerformanceMetricRepository, station_id: str
) -> dict[str, object] | None:
    """Pull the latest per-station GBM payload whose per_receptor
    block carries this station_id.

    The per-station model writes one metric_payload row per station;
    each row's `per_receptor` block contains exactly one entry keyed
    by `station_id`. We resolve by version + scan, so an out-of-order
    write (e.g. a re-train of one station only) doesn't poison the
    comparison.
    """
    rows = repo.get_recent(
        since=datetime.min.replace(tzinfo=None),
        limit=200,
        model_version=GBM_VERSION,
    )
    for row in rows:
        payload = row.metric_payload or {}
        per_receptor = payload.get("per_receptor") or {}
        if station_id in per_receptor:
            return payload
    return None


__all__ = ["maybe_promote_gbm", "maybe_promote_gbm_shared"]
