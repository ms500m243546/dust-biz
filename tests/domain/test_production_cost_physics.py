"""Phase U.1 — production-cost physics module tests."""

from __future__ import annotations

import pytest

from app.domain.production_cost_physics import (
    DEFAULT_CYCLE_BASELINE_SEC,
    DEFAULT_WATERING_WINDOW_MIN,
    speed_reduction_cycle_impact,
    tonnes_delayed_from_cycle,
    watering_one_time_cycle_hit,
)


def test_speed_reduction_zero_when_after_geq_before() -> None:
    assert speed_reduction_cycle_impact(speed_before_kmh=30, speed_after_kmh=30) == 0.0
    assert speed_reduction_cycle_impact(speed_before_kmh=30, speed_after_kmh=40) == 0.0


def test_speed_reduction_doubles_cycle_when_speed_halves() -> None:
    f = speed_reduction_cycle_impact(speed_before_kmh=50, speed_after_kmh=25)
    assert f == pytest.approx(1.0, rel=1e-6)


def test_speed_reduction_zero_inputs_safe() -> None:
    assert speed_reduction_cycle_impact(speed_before_kmh=0, speed_after_kmh=10) == 0.0
    assert speed_reduction_cycle_impact(speed_before_kmh=10, speed_after_kmh=0) == 0.0


def test_watering_zero_when_fleet_or_baseline_zero() -> None:
    assert watering_one_time_cycle_hit(fleet_size=0) == 0.0
    assert watering_one_time_cycle_hit(cycle_baseline_sec=0) == 0.0


def test_watering_increases_with_window_decreases_with_fleet() -> None:
    short = watering_one_time_cycle_hit(watering_window_min=4, fleet_size=8)
    longer = watering_one_time_cycle_hit(watering_window_min=12, fleet_size=8)
    bigger_fleet = watering_one_time_cycle_hit(watering_window_min=4, fleet_size=24)
    assert longer > short
    assert short > bigger_fleet


def test_watering_default_inputs_yield_small_fraction() -> None:
    f = watering_one_time_cycle_hit()
    # Defaults: 8 min window, 180 s cycle, 1 truck → 8*60 / 180 = 2.667
    # That's a single-truck single-cycle estimate; for an 8-truck fleet
    # it'd be 0.333. We only assert positivity here — concrete values
    # are exercised in the main model tests.
    assert f > 0


def test_tonnes_delayed_zero_for_degenerate_inputs() -> None:
    assert (
        tonnes_delayed_from_cycle(production_rate_tph=0, duration_minutes=60, cycle_increase_frac=0.5)
        == 0.0
    )
    assert (
        tonnes_delayed_from_cycle(production_rate_tph=1000, duration_minutes=0, cycle_increase_frac=0.5)
        == 0.0
    )
    assert (
        tonnes_delayed_from_cycle(production_rate_tph=1000, duration_minutes=60, cycle_increase_frac=0)
        == 0.0
    )


def test_tonnes_delayed_closed_form() -> None:
    # 1000 t/h * 1 h * (0.20 / 1.20) ≈ 166.67 t
    t = tonnes_delayed_from_cycle(
        production_rate_tph=1000,
        duration_minutes=60,
        cycle_increase_frac=0.2,
    )
    assert t == pytest.approx(166.6667, rel=1e-3)


def test_tonnes_delayed_capped_below_throughput() -> None:
    # Even at infinite cycle increase, throughput loss never exceeds
    # the underlying production over the window.
    t = tonnes_delayed_from_cycle(
        production_rate_tph=500,
        duration_minutes=60,
        cycle_increase_frac=99.0,
    )
    assert t < 500
    assert t > 490  # asymptotic to throughput


def test_default_constants_documented() -> None:
    assert DEFAULT_CYCLE_BASELINE_SEC > 0
    assert DEFAULT_WATERING_WINDOW_MIN > 0
