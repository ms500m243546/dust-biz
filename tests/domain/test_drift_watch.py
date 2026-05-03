"""Phase M.4.3: drift-watch detector tests (B-12 mitigation).

Pure unit tests for `app.domain.drift_watch.compute_drift` — no DB,
no API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.domain.drift_watch import (
    DRIFT_THRESHOLDS,
    DriftAlert,
    compute_drift,
)


def _row(**metrics: float) -> dict[str, Any]:
    """Build a metric_payload-shaped dict carrying the given metrics."""
    return dict(metrics)


def test_no_drift_when_baseline_and_recent_match() -> None:
    rows = [_row(breach_recall=0.8, ece=0.02) for _ in range(8)]
    alerts = compute_drift(
        rows,
        model_version="v1",
        detected_at=datetime(2026, 5, 3),
    )
    assert alerts == []


def test_recall_drift_above_threshold_emits_alert() -> None:
    # Baseline 4 rows at recall=0.85, recent 4 rows at recall=0.50 → delta 0.35.
    rows = [
        _row(breach_recall=0.85),
        _row(breach_recall=0.85),
        _row(breach_recall=0.86),
        _row(breach_recall=0.84),
        _row(breach_recall=0.50),
        _row(breach_recall=0.50),
        _row(breach_recall=0.51),
        _row(breach_recall=0.49),
    ]
    alerts = compute_drift(
        rows,
        model_version="v1",
        detected_at=datetime(2026, 5, 3),
    )
    recall_alerts = [a for a in alerts if a.metric_name == "breach_recall"]
    assert len(recall_alerts) == 1
    a = recall_alerts[0]
    assert a.baseline_value == 0.85
    assert a.recent_value == 0.50
    assert a.delta > DRIFT_THRESHOLDS["breach_recall"]
    assert a.threshold == DRIFT_THRESHOLDS["breach_recall"]
    assert a.baseline_sample_count == 4
    assert a.recent_sample_count == 4


def test_drift_below_threshold_does_not_alert() -> None:
    # 5pp drift on recall — under the 10pp threshold.
    rows = [_row(breach_recall=0.80) for _ in range(4)] + [
        _row(breach_recall=0.75) for _ in range(4)
    ]
    alerts = compute_drift(
        rows,
        model_version="v1",
        detected_at=datetime(2026, 5, 3),
    )
    assert all(a.metric_name != "breach_recall" for a in alerts)


def test_under_min_samples_returns_empty() -> None:
    """Below 2*min_samples we have no statistical claim; emit nothing."""
    rows = [_row(breach_recall=0.85, ece=0.02)]
    alerts = compute_drift(
        rows,
        model_version="v1",
        detected_at=datetime(2026, 5, 3),
        min_samples=4,
    )
    assert alerts == []


def test_missing_metric_skips_silently() -> None:
    """A row that lacks the metric key is excluded from that metric's split."""
    rows = [_row(breach_recall=0.85) for _ in range(4)] + [
        _row(breach_recall=0.50) for _ in range(4)
    ]
    # No row has `ece` — drift module must skip rather than crash.
    alerts = compute_drift(
        rows,
        model_version="v1",
        detected_at=datetime(2026, 5, 3),
    )
    metric_names = {a.metric_name for a in alerts}
    assert "ece" not in metric_names
    assert "breach_recall" in metric_names


def test_alert_carries_model_version_and_detected_at() -> None:
    rows = [_row(breach_recall=0.9) for _ in range(4)] + [
        _row(breach_recall=0.5) for _ in range(4)
    ]
    detected = datetime(2026, 5, 3, 12, 0)
    alerts = compute_drift(
        rows,
        model_version="dust_forecast_v0.2",
        detected_at=detected,
    )
    assert all(isinstance(a, DriftAlert) for a in alerts)
    assert alerts[0].model_version == "dust_forecast_v0.2"
    assert alerts[0].detected_at == detected


def test_threshold_is_absolute_either_direction() -> None:
    """Drift up or down both alert — abs(recent - baseline) is the metric."""
    # Recall improves (good news, but still drift).
    rows = [_row(breach_recall=0.5) for _ in range(4)] + [
        _row(breach_recall=0.9) for _ in range(4)
    ]
    alerts = compute_drift(
        rows,
        model_version="v1",
        detected_at=datetime(2026, 5, 3),
    )
    assert any(a.metric_name == "breach_recall" for a in alerts)
