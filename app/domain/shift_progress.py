"""Shift-progress resolver (Phase AA, Tension 5).

Closes the "cost is marginal, not plan-relative" gap. The optimizer
needs to know whether a 200-tonne delay matters — if the shift is
hours ahead of plan, that's absorbable; if it's behind, that delay
breaks the schedule. Without this, the ranker treats every shift as
if it were on plan.

Two modes:

* **Live** — sums tonnage from EquipmentActivity `dumping` rows in the
  current shift window for any zone in the mine. Falls back to
  synthetic when no rows are present (a fresh dev DB / partnership-
  pre-data state).
* **Synthetic** — reads operator-set overrides from
  `SiteConfiguration.cost_curves` (`shift_target_tonnes_per_hour`,
  `shift_hours`, `shift_start_hour_utc`, `shift_slack_ratio_override`).
  Default slack=1.0 means "assume on plan, no rescale" — the safest
  default when nothing is known.

Layered: this module is in `app/domain` so it can pull from the ORM
(via repos / direct selects) and feed the optimizer without crossing
the storage->domain boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.schemas.shift_progress import ShiftProgressSchema
from app.storage.models import EquipmentActivity, Zone

# Conservative deferred-mode defaults. Operators override per-site via
# SiteConfiguration.cost_curves. Numbers picked to be plausible for a
# mid-size open-pit operation; the mechanism is the value, not the
# specific defaults.
DEFAULT_SHIFT_TARGET_TONNES_PER_HOUR = 200.0
DEFAULT_SHIFT_HOURS = 12.0
DEFAULT_SHIFT_START_HOUR_UTC = 0  # 00:00 UTC kicks the day shift
DEFAULT_SLACK_RATIO = 1.0

# Activity types that materialize completed haul cycles. `dumping` is
# the canonical "delivered tonnage" event; `hauling` is in-flight and
# would double-count if included.
COMPLETED_HAUL_ACTIVITY = "dumping"


def _resolve_shift_window(
    *,
    now: datetime,
    cost_curves: dict[str, Any] | None,
) -> tuple[datetime, float, float]:
    """(shift_start, shift_hours, target_tonnes_per_hour) for `now`."""
    cc = cost_curves or {}
    shift_hours = float(cc.get("shift_hours", DEFAULT_SHIFT_HOURS))
    if shift_hours <= 0.0:
        shift_hours = DEFAULT_SHIFT_HOURS
    target_tph = float(
        cc.get("shift_target_tonnes_per_hour", DEFAULT_SHIFT_TARGET_TONNES_PER_HOUR)
    )
    if target_tph <= 0.0:
        target_tph = DEFAULT_SHIFT_TARGET_TONNES_PER_HOUR
    start_hour = int(cc.get("shift_start_hour_utc", DEFAULT_SHIFT_START_HOUR_UTC)) % 24

    now_utc = now if now.tzinfo else now.replace(tzinfo=UTC)
    candidate = now_utc.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    # Walk back in `shift_hours` increments until we land in the
    # window enclosing `now`. This handles night shifts and
    # operators with non-12h cycles without special-casing them.
    while candidate > now_utc:
        candidate -= timedelta(hours=shift_hours)
    while candidate + timedelta(hours=shift_hours) <= now_utc:
        candidate += timedelta(hours=shift_hours)
    # Strip tzinfo for downstream DB comparisons (SQLite stores naive).
    shift_start = candidate.replace(tzinfo=None)
    return shift_start, shift_hours, target_tph


def _live_tonnes_done(
    *,
    session: Session,
    mine_id: str,
    shift_start: datetime,
    now: datetime,
) -> float | None:
    """Sum dumping tonnage in the shift window across the mine's zones.

    Returns None when no rows landed in the window — the caller falls
    back to synthetic mode. Returns 0.0 when the window has rows but
    none are dumping events (an active shift hauling but no completions
    yet, e.g. start-of-shift).
    """
    zone_ids = list(
        session.execute(
            select(Zone.zone_id).where(Zone.mine_id == mine_id)
        ).scalars()
    )
    if not zone_ids:
        return None
    now_naive = now.replace(tzinfo=None) if now.tzinfo else now
    rows = list(
        session.execute(
            select(EquipmentActivity)
            .where(EquipmentActivity.zone_id.in_(zone_ids))
            .where(EquipmentActivity.timestamp >= shift_start)
            .where(EquipmentActivity.timestamp <= now_naive)
        ).scalars()
    )
    if not rows:
        return None
    total = 0.0
    for r in rows:
        if r.activity_type != COMPLETED_HAUL_ACTIVITY:
            continue
        if r.tonnage is None:
            continue
        total += float(r.tonnage)
    return total


def compute_shift_progress(
    *,
    session: Session,
    mine_id: str,
    now: datetime,
    cost_curves: dict[str, Any] | None,
) -> ShiftProgressSchema:
    """Compute current shift progress for `mine_id` as of `now`."""
    shift_start, shift_hours, target_tph = _resolve_shift_window(
        now=now, cost_curves=cost_curves
    )
    now_naive = now.replace(tzinfo=None) if now.tzinfo else now
    elapsed_seconds = max(
        0.0, (now_naive - shift_start).total_seconds()
    )
    hours_elapsed = min(shift_hours, elapsed_seconds / 3600.0)
    hours_remaining = max(0.0, shift_hours - hours_elapsed)

    expected_done = target_tph * hours_elapsed
    shift_target_tonnes = target_tph * shift_hours

    tonnes_done = _live_tonnes_done(
        session=session,
        mine_id=mine_id,
        shift_start=shift_start,
        now=now_naive,
    )
    if tonnes_done is None:
        cc = cost_curves or {}
        override = cc.get("shift_slack_ratio_override")
        slack_ratio = float(override) if override is not None else DEFAULT_SLACK_RATIO
        # Synthesize tonnes_done so downstream consumers see a
        # consistent slack_ratio. expected_done * slack_ratio
        # reproduces the same ratio.
        synthetic_tonnes_done = expected_done * slack_ratio
        return ShiftProgressSchema(
            mine_id=mine_id,
            shift_start=shift_start,
            now=now_naive,
            hours_elapsed=round(hours_elapsed, 4),
            hours_remaining=round(hours_remaining, 4),
            target_tonnes_per_hour=target_tph,
            shift_target_tonnes=shift_target_tonnes,
            tonnes_done=round(synthetic_tonnes_done, 2),
            expected_done=round(expected_done, 2),
            slack_ratio=round(slack_ratio, 4),
            source="synthetic",
        )

    # Start of shift (no hours elapsed yet) → undefined ratio; treat
    # as on-plan rather than divide-by-zero or claim infinite slack.
    slack_ratio = (
        DEFAULT_SLACK_RATIO
        if expected_done <= 0.0
        else tonnes_done / expected_done
    )

    return ShiftProgressSchema(
        mine_id=mine_id,
        shift_start=shift_start,
        now=now_naive,
        hours_elapsed=round(hours_elapsed, 4),
        hours_remaining=round(hours_remaining, 4),
        target_tonnes_per_hour=target_tph,
        shift_target_tonnes=shift_target_tonnes,
        tonnes_done=round(tonnes_done, 2),
        expected_done=round(expected_done, 2),
        slack_ratio=round(slack_ratio, 4),
        source="live",
    )


__all__ = [
    "DEFAULT_SHIFT_HOURS",
    "DEFAULT_SHIFT_START_HOUR_UTC",
    "DEFAULT_SHIFT_TARGET_TONNES_PER_HOUR",
    "DEFAULT_SLACK_RATIO",
    "COMPLETED_HAUL_ACTIVITY",
    "compute_shift_progress",
]
