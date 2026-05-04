"""Phase AA — shift_progress resolver tests."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from app.domain.shift_progress import (
    DEFAULT_SHIFT_HOURS,
    DEFAULT_SHIFT_TARGET_TONNES_PER_HOUR,
    compute_shift_progress,
)
from app.storage.database import session_scope
from app.storage.models import Equipment, EquipmentActivity, Mine, Zone


@pytest.fixture
def _mine_with_zone() -> Iterator[str]:
    """Seed a mine + a zone so the resolver can find the activity rows."""
    with session_scope() as s:
        mine = Mine(
            mine_id="aa-test-mine",
            name="AA test",
            default_automation_level="L1",
        )
        zone = Zone(
            zone_id="aa-test-zone",
            mine_id=mine.mine_id,
            zone_type="haul_road",
            operational_importance="primary",
            dust_generation_baseline="medium",
        )
        equipment = Equipment(
            equipment_id="aa-truck-1",
            mine_id=mine.mine_id,
            equipment_type="haul_truck",
            nominal_capacity_t=200.0,
        )
        s.add(mine)
        s.add(zone)
        s.add(equipment)
        s.flush()
    yield "aa-test-mine"
    with session_scope() as s:
        s.query(EquipmentActivity).filter(
            EquipmentActivity.equipment_id == "aa-truck-1"
        ).delete()
        s.query(Equipment).filter(Equipment.equipment_id == "aa-truck-1").delete()
        s.query(Zone).filter(Zone.zone_id == "aa-test-zone").delete()
        s.query(Mine).filter(Mine.mine_id == "aa-test-mine").delete()


def test_synthetic_mode_uses_override_when_no_activity(_mine_with_zone: str) -> None:
    now = datetime(2026, 5, 3, 6, 0, tzinfo=UTC)
    with session_scope() as s:
        progress = compute_shift_progress(
            session=s,
            mine_id=_mine_with_zone,
            now=now,
            cost_curves={"shift_slack_ratio_override": 0.6},
        )
    assert progress.source == "synthetic"
    assert progress.slack_ratio == 0.6
    assert progress.target_tonnes_per_hour == DEFAULT_SHIFT_TARGET_TONNES_PER_HOUR
    assert progress.shift_target_tonnes == (
        DEFAULT_SHIFT_TARGET_TONNES_PER_HOUR * DEFAULT_SHIFT_HOURS
    )


def test_synthetic_mode_defaults_to_on_plan(_mine_with_zone: str) -> None:
    now = datetime(2026, 5, 3, 6, 0, tzinfo=UTC)
    with session_scope() as s:
        progress = compute_shift_progress(
            session=s,
            mine_id=_mine_with_zone,
            now=now,
            cost_curves=None,
        )
    assert progress.source == "synthetic"
    assert progress.slack_ratio == 1.0


def test_live_mode_when_dumping_activity_present(_mine_with_zone: str) -> None:
    # Shift starts at 00:00 UTC by default; at 06:00 UTC, expected
    # done = 200 t/h * 6 h = 1,200 t. We seed 600 t of dumping events
    # (half-pace) and expect slack ≈ 0.5.
    now = datetime(2026, 5, 3, 6, 0, tzinfo=UTC)
    with session_scope() as s:
        for hour, tonnes in [(2, 200.0), (3, 200.0), (5, 200.0)]:
            s.add(
                EquipmentActivity(
                    equipment_id="aa-truck-1",
                    timestamp=datetime(2026, 5, 3, hour, 0),
                    zone_id="aa-test-zone",
                    activity_type="dumping",
                    tonnage=tonnes,
                )
            )
        s.flush()
        progress = compute_shift_progress(
            session=s,
            mine_id=_mine_with_zone,
            now=now,
            cost_curves=None,
        )
    assert progress.source == "live"
    assert progress.tonnes_done == 600.0
    assert progress.expected_done == 1200.0
    assert abs(progress.slack_ratio - 0.5) < 1e-9


def test_hauling_in_flight_does_not_count_as_done(_mine_with_zone: str) -> None:
    # Only `dumping` events are completions; `hauling` is in-flight.
    # Including hauling would double-count or count never-delivered loads.
    now = datetime(2026, 5, 3, 6, 0, tzinfo=UTC)
    with session_scope() as s:
        s.add(
            EquipmentActivity(
                equipment_id="aa-truck-1",
                timestamp=datetime(2026, 5, 3, 2, 0),
                zone_id="aa-test-zone",
                activity_type="hauling",
                tonnage=400.0,
            )
        )
        s.flush()
        progress = compute_shift_progress(
            session=s,
            mine_id=_mine_with_zone,
            now=now,
            cost_curves=None,
        )
    assert progress.source == "live"
    # An activity row exists in the window so live mode kicks in,
    # but tonnes_done should be 0.0 because it was hauling, not dumping.
    assert progress.tonnes_done == 0.0


def test_start_of_shift_treats_as_on_plan(_mine_with_zone: str) -> None:
    # 0 hours elapsed → expected_done == 0; ratio is undefined.
    # The resolver must return slack_ratio=1.0 (on plan) rather than
    # divide-by-zero or claim infinite slack.
    now = datetime(2026, 5, 3, 0, 0, tzinfo=UTC)
    with session_scope() as s:
        s.add(
            EquipmentActivity(
                equipment_id="aa-truck-1",
                timestamp=datetime(2026, 5, 3, 0, 0),
                zone_id="aa-test-zone",
                activity_type="dumping",
                tonnage=10.0,
            )
        )
        s.flush()
        progress = compute_shift_progress(
            session=s,
            mine_id=_mine_with_zone,
            now=now,
            cost_curves=None,
        )
    assert progress.slack_ratio == 1.0
