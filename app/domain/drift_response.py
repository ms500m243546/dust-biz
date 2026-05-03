"""Drift-triggered re-training (Phase W.2).

Bridges `app.domain.drift_watch` (M.4.3 detection) to
`app.domain.training_scheduler` (W.1 retraining). When the operator
triggers `POST /api/v1/drift/retrain` for a model_version with at
least one ACT-tier alert (delta ≥ 2 × threshold), this module runs
the canonical Phase P.1 retrain immediately + writes an audit row
naming the alert that triggered it.

ACT tier = delta ≥ 2 × threshold (per `app/domain/drift_watch.
DRIFT_THRESHOLDS`). Below that, drift is information-only and does
not warrant an unscheduled retrain.

Tolerant by design: per-station retrain failures are captured (same
as W.1), the audit row records the outcome, and the response always
returns 2xx if the request was well-formed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.audit import record as audit_record
from app.domain.drift_watch import DriftAlert, compute_drift
from app.domain.training_scheduler import weekly_dust_forecast_retrain
from app.storage.database import session_scope
from app.storage.repositories.model_performance import (
    ModelPerformanceMetricRepository,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrainOutcome:
    """Audit-trail-bearing return shape for `trigger_drift_retrain()`."""

    model_version: str
    triggering_alerts: tuple[DriftAlert, ...]
    retrained: bool
    reason: str


def _act_tier_alerts(alerts: list[DriftAlert]) -> list[DriftAlert]:
    """Filter to alerts whose delta is at least 2x the threshold."""
    return [a for a in alerts if a.delta >= 2.0 * a.threshold]


def trigger_drift_retrain(
    *,
    model_version: str,
    actor: str,
    since_days: int = 30,
    min_samples: int = 4,
    now: datetime | None = None,
) -> RetrainOutcome:
    """Run W.1 retrain only if at least one ACT-tier alert exists.

    Audits both branches: if no ACT-tier alerts, audit "no-op";
    otherwise audit the alerts that triggered the retrain plus
    whether the retrain succeeded.
    """
    moment = now or datetime.now(UTC).replace(tzinfo=None)
    since = moment - timedelta(days=since_days)
    with session_scope() as session:
        metric_rows = ModelPerformanceMetricRepository(session).get_recent(
            since=since,
            limit=500,
            model_version=model_version,
            model_kind=None,
        )
        # `get_recent` returns descending by evaluated_at; compute_drift
        # wants ascending so the oldest rows form the baseline split.
        metric_rows = list(reversed(metric_rows))
        payloads = [r.metric_payload or {} for r in metric_rows]
        alerts = compute_drift(
            payloads,
            model_version=model_version,
            detected_at=moment,
            min_samples=min_samples,
        )
        act_tier = _act_tier_alerts(alerts)
        if not act_tier:
            audit_record(
                session,
                actor=actor,
                action="drift_retrain_skipped",
                entity_type="model_version",
                entity_id=model_version,
                payload={
                    "reason": "no ACT-tier alerts",
                    "alerts_seen": len(alerts),
                },
            )
            return RetrainOutcome(
                model_version=model_version,
                triggering_alerts=(),
                retrained=False,
                reason="no ACT-tier alerts",
            )
        audit_record(
            session,
            actor=actor,
            action="drift_retrain_triggered",
            entity_type="model_version",
            entity_id=model_version,
            payload={
                "alerts": [
                    {
                        "metric_name": a.metric_name,
                        "delta": a.delta,
                        "threshold": a.threshold,
                    }
                    for a in act_tier
                ],
            },
        )
    # Retrain runs *outside* the session_scope so its own internal
    # session_scope doesn't deadlock.
    try:
        weekly_dust_forecast_retrain(moment)
        retrained = True
        reason = f"retrained on {len(act_tier)} ACT-tier alert(s)"
    except Exception as exc:  # broad: never raise into the API path
        logger.exception("drift retrain failed")
        retrained = False
        reason = f"retrain raised: {exc!r}"
    with session_scope() as session:
        audit_record(
            session,
            actor=actor,
            action=("drift_retrain_completed" if retrained else "drift_retrain_failed"),
            entity_type="model_version",
            entity_id=model_version,
            payload={"reason": reason},
        )
    return RetrainOutcome(
        model_version=model_version,
        triggering_alerts=tuple(act_tier),
        retrained=retrained,
        reason=reason,
    )


__all__ = [
    "RetrainOutcome",
    "trigger_drift_retrain",
]


# Silence unused-import warnings on the constants imported for
# audit-trail completeness.
_ = UTC
