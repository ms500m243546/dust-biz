"""Background scheduler (Phase K.3).

Tiny in-process tick scheduler that runs registered jobs on fixed
intervals. Stdlib only; no apscheduler / celery / cron daemons.

Jobs:
- `approval_expiry_sweep` — calls `sweep_expired` every minute so the
  audit trail eventually contains a row for every recommendation. Closes
  the manual-only sweep gap (I3-R1, F1-R1).
- `keyring_prune` — drops retired HMAC keys past the grace window so
  `KeyRing` doesn't grow unbounded.
- `model_performance_eval` (optional) — kicked off via the scheduler
  tick when configured; uses the K.1 evaluator. Disabled by default;
  enable via `register_model_eval_job(...)` from a startup hook when a
  site wants nightly evaluation.

Design constraints:
- Pure-Python stdlib (`threading.Timer` + a `_lock`-guarded job list).
- Each job runs inside its own session_scope; exceptions are caught
  and logged via the audit table so a failing job never crashes the
  ticker.
- The runtime is opt-in: importing this module does NOT start the
  thread. The API entrypoint starts it via `start()` only when
  `settings.scheduler_enabled` is true (default off in tests).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.audit import record as audit_record
from app.domain.approvals import sweep_expired
from app.domain.auth import get_keyring
from app.storage.database import session_scope

logger = logging.getLogger(__name__)

JobFunc = Callable[[datetime], None]


@dataclass
class Job:
    name: str
    interval: timedelta
    func: JobFunc
    next_run_at: datetime
    last_run_at: datetime | None = None
    last_error: str | None = None
    run_count: int = 0


@dataclass
class Scheduler:
    jobs: list[Job] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _stopped: threading.Event = field(default_factory=threading.Event, repr=False)
    _thread: threading.Thread | None = None
    tick_seconds: float = 5.0

    def register(
        self,
        *,
        name: str,
        interval: timedelta,
        func: JobFunc,
        first_run_in: timedelta | None = None,
        now: datetime | None = None,
    ) -> None:
        moment = (now or datetime.now(UTC)).replace(microsecond=0)
        delay = first_run_in if first_run_in is not None else interval
        with self._lock:
            self.jobs.append(
                Job(
                    name=name,
                    interval=interval,
                    func=func,
                    next_run_at=moment + delay,
                )
            )

    def tick(self, *, now: datetime | None = None) -> list[str]:
        """Run any jobs whose next_run_at has elapsed. Returns the names run."""
        moment = (now or datetime.now(UTC)).replace(microsecond=0)
        ran: list[str] = []
        with self._lock:
            jobs = list(self.jobs)
        for job in jobs:
            if moment < job.next_run_at:
                continue
            try:
                job.func(moment)
                job.last_run_at = moment
                job.last_error = None
            except Exception as exc:  # noqa: BLE001 - keep the ticker alive
                job.last_error = repr(exc)
                logger.exception("scheduler job failed: %s", job.name)
            job.run_count += 1
            job.next_run_at = moment + job.interval
            ran.append(job.name)
        return ran

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stopped.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name="dustops-scheduler", daemon=True
        )
        self._thread.start()

    def stop(self, *, timeout: float = 5.0) -> None:
        self._stopped.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _run_loop(self) -> None:
        while not self._stopped.is_set():
            try:
                self.tick()
            except Exception:  # noqa: BLE001
                logger.exception("scheduler tick failed")
            self._stopped.wait(self.tick_seconds)


def approval_expiry_sweep(now: datetime) -> None:
    """Run S13 expiry sweep. Audits one row per sweep with the count."""
    moment = now.replace(tzinfo=None) if now.tzinfo is not None else now
    with session_scope() as session:
        results = sweep_expired(session=session, now=moment)
        if results:
            audit_record(
                session,
                actor="scheduler",
                action="approval_expiry_sweep",
                entity_type="scheduler",
                entity_id="approval_expiry_sweep",
                payload={"expired_count": len(results)},
                occurred_at=moment,
            )


def keyring_prune(now: datetime) -> None:
    get_keyring().prune(now=now)


_DEFAULT: Scheduler | None = None


def get_default_scheduler() -> Scheduler:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = Scheduler()
        _DEFAULT.register(
            name="approval_expiry_sweep",
            interval=timedelta(minutes=1),
            func=approval_expiry_sweep,
        )
        _DEFAULT.register(
            name="keyring_prune",
            interval=timedelta(minutes=15),
            func=keyring_prune,
        )
        # Phase W.1 — weekly dust-forecast retrain. Lazy import so
        # this module doesn't pull the training stack at import time
        # (training stack pulls sklearn).
        from app.domain.training_scheduler import register_weekly_retraining

        register_weekly_retraining(_DEFAULT)
    return _DEFAULT


__all__ = [
    "Job",
    "Scheduler",
    "approval_expiry_sweep",
    "get_default_scheduler",
    "keyring_prune",
]
