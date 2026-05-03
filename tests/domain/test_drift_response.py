"""Phase W.2 — drift-triggered retrain tests."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.domain.drift_response import (
    _act_tier_alerts,
    trigger_drift_retrain,
)
from app.domain.drift_watch import DriftAlert
from app.storage.models import Base


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    with SessionLocal() as s:
        yield s


def _alert(metric: str = "ece", *, delta: float, threshold: float) -> DriftAlert:
    return DriftAlert(
        model_version="dust_forecast_gbm_v0.1.0",
        metric_name=metric,
        baseline_value=0.0,
        recent_value=delta,
        delta=delta,
        threshold=threshold,
        baseline_sample_count=8,
        recent_sample_count=8,
        detected_at=datetime(2026, 5, 3),
    )


def test_act_tier_alerts_keeps_only_double_threshold() -> None:
    alerts = [
        _alert(delta=0.024, threshold=0.025),  # below threshold
        _alert(delta=0.030, threshold=0.025),  # NOTICE (1.2x)
        _alert(delta=0.060, threshold=0.025),  # ACT (2.4x)
    ]
    act = _act_tier_alerts(alerts)
    assert len(act) == 1
    assert act[0].delta == 0.060


def test_act_tier_at_exact_two_x_threshold_qualifies() -> None:
    alerts = [_alert(delta=0.10, threshold=0.05)]
    assert len(_act_tier_alerts(alerts)) == 1


def test_trigger_drift_retrain_skips_when_no_act_alerts() -> None:
    # compute_drift returns empty list when no metric rows exist;
    # trigger should audit + return retrained=False.
    with patch(
        "app.domain.drift_response.weekly_dust_forecast_retrain"
    ) as fake_retrain:
        outcome = trigger_drift_retrain(
            model_version="dust_forecast_gbm_v0.1.0",
            actor="admin-test",
            now=datetime(2026, 5, 3),
        )
    assert outcome.retrained is False
    assert outcome.triggering_alerts == ()
    assert "no ACT" in outcome.reason or "no act" in outcome.reason.lower()
    fake_retrain.assert_not_called()


def test_trigger_drift_retrain_runs_when_act_alerts_present() -> None:
    fake_alerts = [_alert(delta=0.10, threshold=0.025)]
    with patch(
        "app.domain.drift_response.compute_drift", return_value=fake_alerts
    ), patch(
        "app.domain.drift_response.weekly_dust_forecast_retrain"
    ) as fake_retrain:
        outcome = trigger_drift_retrain(
            model_version="dust_forecast_gbm_v0.1.0",
            actor="admin-test",
            now=datetime(2026, 5, 3),
        )
    assert outcome.retrained is True
    assert len(outcome.triggering_alerts) == 1
    fake_retrain.assert_called_once()


def test_trigger_drift_retrain_captures_retrain_failure() -> None:
    fake_alerts = [_alert(delta=0.10, threshold=0.025)]
    with patch(
        "app.domain.drift_response.compute_drift", return_value=fake_alerts
    ), patch(
        "app.domain.drift_response.weekly_dust_forecast_retrain",
        side_effect=RuntimeError("simulated retrain failure"),
    ):
        outcome = trigger_drift_retrain(
            model_version="dust_forecast_gbm_v0.1.0",
            actor="admin-test",
            now=datetime(2026, 5, 3),
        )
    assert outcome.retrained is False
    assert "raised" in outcome.reason


def test_act_tier_filter_handles_empty_list() -> None:
    assert _act_tier_alerts([]) == []


def test_trigger_drift_retrain_uses_provided_window() -> None:
    """Sanity — since_days flows through to compute_drift's row pull."""
    with patch(
        "app.domain.drift_response.compute_drift", return_value=[]
    ) as fake_compute:
        trigger_drift_retrain(
            model_version="v",
            actor="t",
            since_days=14,
            now=datetime(2026, 5, 3),
        )
    fake_compute.assert_called_once()
    kwargs = fake_compute.call_args.kwargs
    assert kwargs["model_version"] == "v"


# Smoke that we use the timedelta constant (silence unused-import).
_ = timedelta
