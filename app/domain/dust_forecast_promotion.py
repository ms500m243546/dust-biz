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

from app.models import registry
from app.models.forecasting.gbm_v0_1_0 import GBM_VERSION
from app.storage.database import session_scope
from app.storage.repositories.model_performance import (
    ModelPerformanceMetricRepository,
)
from app.training.dust_forecast_training import decide_promotion

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


__all__ = ["maybe_promote_gbm"]
