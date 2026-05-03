"""Drift-watch endpoint (Phase M.4.3, B-12 mitigation).

GET /api/v1/drift?model_version=&since_days=14&min_samples=4

Reads recent `model_performance_metrics` rows for a model version,
splits them into baseline + recent windows, and emits one alert per
headline metric whose median has drifted past the per-metric
threshold in `app.domain.drift_watch.DRIFT_THRESHOLDS`. Pure derived
view — no persistence; callers re-run on demand.

Auth-gated at the router level via `current_user`. Read-only —
operators and dispatchers can call without a role check.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies.auth import current_user
from app.api.deps import get_session
from app.domain.drift_watch import compute_drift
from app.schemas.drift import DriftAlertSchema
from app.storage.models import User
from app.storage.repositories.model_performance import (
    ModelPerformanceMetricRepository,
)

router = APIRouter(prefix="/drift", tags=["drift"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[DriftAlertSchema])
def list_drift_alerts(
    session: SessionDep,
    _user: Annotated[User, Depends(current_user)],
    model_version: Annotated[str, Query(min_length=1)],
    since_days: Annotated[int, Query(ge=1, le=365)] = 14,
    min_samples: Annotated[int, Query(ge=2, le=100)] = 4,
) -> list[DriftAlertSchema]:
    since = (datetime.now(UTC) - timedelta(days=since_days)).replace(
        tzinfo=None
    )
    metric_rows = ModelPerformanceMetricRepository(session).get_recent(
        since=since,
        limit=500,
        model_version=model_version,
        model_kind=None,
    )
    # Repo returns descending by evaluated_at; drift_watch wants
    # ascending so the oldest rows form the baseline split.
    metric_rows = list(reversed(metric_rows))
    payloads: list[dict[str, Any]] = [
        (r.metric_payload or {}) for r in metric_rows
    ]
    alerts = compute_drift(
        payloads,
        model_version=model_version,
        detected_at=datetime.now(UTC).replace(tzinfo=None),
        min_samples=min_samples,
    )
    return [
        DriftAlertSchema(
            model_version=a.model_version,
            metric_name=a.metric_name,
            baseline_value=a.baseline_value,
            recent_value=a.recent_value,
            delta=a.delta,
            threshold=a.threshold,
            baseline_sample_count=a.baseline_sample_count,
            recent_sample_count=a.recent_sample_count,
            detected_at=a.detected_at,
        )
        for a in alerts
    ]
