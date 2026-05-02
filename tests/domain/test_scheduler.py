"""Scheduler tests (Phase K.3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.scheduler import Scheduler


def test_tick_runs_due_jobs() -> None:
    sched = Scheduler()
    calls: list[datetime] = []

    base = datetime(2026, 5, 2, 10, 0, tzinfo=UTC)
    sched.register(
        name="t",
        interval=timedelta(seconds=10),
        func=lambda now: calls.append(now),
        first_run_in=timedelta(seconds=0),
        now=base,
    )
    ran = sched.tick(now=base + timedelta(seconds=1))
    assert ran == ["t"]
    assert len(calls) == 1


def test_tick_skips_jobs_not_yet_due() -> None:
    sched = Scheduler()
    base = datetime(2026, 5, 2, 10, 0, tzinfo=UTC)
    sched.register(
        name="t",
        interval=timedelta(minutes=10),
        func=lambda now: None,
        now=base,
    )
    ran = sched.tick(now=base + timedelta(seconds=30))  # not due yet
    assert ran == []


def test_tick_swallows_exceptions() -> None:
    sched = Scheduler()

    def boom(_: datetime) -> None:
        raise RuntimeError("nope")

    base = datetime(2026, 5, 2, 10, 0, tzinfo=UTC)
    sched.register(
        name="b",
        interval=timedelta(seconds=10),
        func=boom,
        first_run_in=timedelta(seconds=0),
        now=base,
    )
    ran = sched.tick(now=base + timedelta(seconds=1))
    assert ran == ["b"]
    job = sched.jobs[0]
    assert job.last_error is not None
    # Run again later - the job's next_run_at advances even on failure.
    sched.tick(now=base + timedelta(seconds=20))
    assert job.run_count == 2


def test_register_first_run_in_overrides_interval_for_initial() -> None:
    sched = Scheduler()
    calls: list[datetime] = []
    base = datetime(2026, 5, 2, 10, 0, tzinfo=UTC)
    sched.register(
        name="t",
        interval=timedelta(minutes=15),
        func=lambda now: calls.append(now),
        first_run_in=timedelta(seconds=1),
        now=base,
    )
    sched.tick(now=base + timedelta(seconds=2))
    assert len(calls) == 1
