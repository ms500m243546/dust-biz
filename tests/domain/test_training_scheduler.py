"""Phase W.1 — training-scheduler tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from app.domain.scheduler import Scheduler
from app.domain.training_scheduler import (
    WEEKLY_RETRAIN_INTERVAL,
    register_weekly_retraining,
    weekly_dust_forecast_retrain,
)


def test_register_weekly_retraining_appends_job() -> None:
    s = Scheduler()
    register_weekly_retraining(s, now=datetime(2026, 5, 3, tzinfo=UTC))
    names = [j.name for j in s.jobs]
    assert "weekly_dust_forecast_retrain" in names


def test_register_weekly_retraining_uses_default_interval() -> None:
    s = Scheduler()
    register_weekly_retraining(s, now=datetime(2026, 5, 3, tzinfo=UTC))
    job = next(j for j in s.jobs if j.name == "weekly_dust_forecast_retrain")
    assert job.interval == WEEKLY_RETRAIN_INTERVAL


def test_register_weekly_retraining_respects_first_run_in() -> None:
    s = Scheduler()
    moment = datetime(2026, 5, 3, tzinfo=UTC)
    register_weekly_retraining(s, first_run_in=timedelta(minutes=5), now=moment)
    job = next(j for j in s.jobs if j.name == "weekly_dust_forecast_retrain")
    assert job.next_run_at == (moment + timedelta(minutes=5)).replace(microsecond=0)


def test_weekly_retrain_tolerates_failure_silently() -> None:
    """Scheduler must keep ticking even if the retrain raises."""
    with patch(
        "app.domain.training_scheduler.train_many",
        side_effect=RuntimeError("simulated training failure"),
    ):
        # Should NOT raise.
        weekly_dust_forecast_retrain(datetime(2026, 5, 3))


def test_weekly_retrain_runs_train_many_with_protocol() -> None:
    captured: dict[str, object] = {}

    def fake_train_many(**kwargs: object) -> list[object]:
        captured.update(kwargs)
        return []

    with patch(
        "app.domain.training_scheduler.train_many", side_effect=fake_train_many
    ):
        weekly_dust_forecast_retrain(datetime(2026, 5, 3))
    assert "station_ids" in captured
    assert "protocol" in captured
    assert captured.get("persist") is True


def test_scheduler_default_includes_weekly_retrain() -> None:
    # Reset the default so this test is hermetic.
    import app.domain.scheduler as sched_mod

    sched_mod._DEFAULT = None
    s = sched_mod.get_default_scheduler()
    names = [j.name for j in s.jobs]
    assert "weekly_dust_forecast_retrain" in names
    sched_mod._DEFAULT = None
