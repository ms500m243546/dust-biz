"""Drift-watch API tests (Phase M.4.3)."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.storage.models import ModelPerformanceMetric


def _seed_metric(
    session: Session,
    *,
    model_version: str,
    evaluated_at: datetime,
    breach_recall: float,
) -> None:
    row = ModelPerformanceMetric(
        model_version=model_version,
        model_kind="dust_forecast",
        evaluated_at=evaluated_at,
        window_from=evaluated_at - timedelta(hours=1),
        window_to=evaluated_at,
        sample_count=10,
        metric_payload={
            "breach_recall": breach_recall,
            "sample_count": 10,
            "observed_count": 10,
        },
    )
    session.add(row)


def test_drift_unauthed_returns_401(unauthed_client: TestClient) -> None:
    r = unauthed_client.get("/api/v1/drift?model_version=v1")
    assert r.status_code == 401


def test_drift_no_data_returns_empty_list(
    client: TestClient, api_session: Session
) -> None:
    r = client.get("/api/v1/drift?model_version=does-not-exist")
    assert r.status_code == 200
    assert r.json() == []


def test_drift_emits_alert_on_recall_collapse(
    client: TestClient, api_session: Session
) -> None:
    base = datetime.now() - timedelta(days=10)
    # 4 baseline rows at recall=0.85, 4 recent rows at recall=0.50.
    for i in range(4):
        _seed_metric(
            api_session,
            model_version="v-drifty",
            evaluated_at=base + timedelta(hours=i),
            breach_recall=0.85,
        )
    for i in range(4):
        _seed_metric(
            api_session,
            model_version="v-drifty",
            evaluated_at=base + timedelta(days=5, hours=i),
            breach_recall=0.50,
        )
    api_session.commit()

    r = client.get("/api/v1/drift?model_version=v-drifty&since_days=30")
    assert r.status_code == 200, r.text
    body = r.json()
    recall_alerts = [a for a in body if a["metric_name"] == "breach_recall"]
    assert len(recall_alerts) == 1
    a = recall_alerts[0]
    assert a["model_version"] == "v-drifty"
    assert a["baseline_value"] == 0.85
    assert a["recent_value"] == 0.50
    assert a["delta"] > a["threshold"]


def test_drift_under_min_samples_returns_empty(
    client: TestClient, api_session: Session
) -> None:
    base = datetime.now() - timedelta(days=2)
    _seed_metric(
        api_session,
        model_version="v-tiny",
        evaluated_at=base,
        breach_recall=0.5,
    )
    api_session.commit()
    r = client.get("/api/v1/drift?model_version=v-tiny&min_samples=4")
    assert r.status_code == 200
    assert r.json() == []
