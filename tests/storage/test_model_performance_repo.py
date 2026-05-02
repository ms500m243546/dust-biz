"""ModelPerformanceMetric repository tests (Phase K)."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.storage.models import ModelPerformanceMetric
from app.storage.repositories.model_performance import (
    ModelPerformanceMetricRepository,
)


def _row(
    *,
    model_version: str = "df-0.1.0",
    model_kind: str = "dust_forecast",
    evaluated_at: datetime,
) -> ModelPerformanceMetric:
    return ModelPerformanceMetric(
        model_version=model_version,
        model_kind=model_kind,
        evaluated_at=evaluated_at,
        window_from=evaluated_at - timedelta(hours=6),
        window_to=evaluated_at,
        sample_count=42,
        metric_payload={"mae_pm10": 11.3, "breach_precision": 0.81},
    )


def test_add_and_latest(session: Session) -> None:
    repo = ModelPerformanceMetricRepository(session)
    repo.add(_row(evaluated_at=datetime(2026, 5, 1, 12, 0, 0)))
    repo.add(_row(evaluated_at=datetime(2026, 5, 1, 18, 0, 0)))
    session.commit()

    latest = repo.latest_for_version("df-0.1.0")
    assert latest is not None
    assert latest.evaluated_at == datetime(2026, 5, 1, 18, 0, 0)


def test_filter_by_kind_and_version(session: Session) -> None:
    repo = ModelPerformanceMetricRepository(session)
    repo.add(_row(evaluated_at=datetime(2026, 5, 1, 12, 0, 0)))
    repo.add(
        _row(
            model_version="oa-0.1.0",
            model_kind="optimization",
            evaluated_at=datetime(2026, 5, 1, 13, 0, 0),
        )
    )
    session.commit()

    rows = repo.get_recent(
        since=datetime(2026, 5, 1, 0, 0), model_kind="optimization"
    )
    assert len(rows) == 1
    assert rows[0].model_version == "oa-0.1.0"

    rows = repo.get_recent(
        since=datetime(2026, 5, 1, 0, 0), model_version="df-0.1.0"
    )
    assert len(rows) == 1
    assert rows[0].model_kind == "dust_forecast"
