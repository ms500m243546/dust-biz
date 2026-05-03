"""Production-cost physics module (Phase U.1).

Pure-function calculations behind the cycle-time-aware
`CycleTimeProductionCost` model. Replaces the heuristic baseline's
hand-tuned `cycle_time_pct` constants with explicit physics over
fleet specs (Equipment.nominal_capacity_t, Equipment.empty_weight_tonnes
from O.1) and the operator's intervention parameters.

The two physics regimes covered:

  speed_reduction_cycle_impact(speed_before, speed_after, cycle_baseline)
    A truck cycling at speed v has cycle time t. Cutting speed to v'
    increases cycle time roughly proportional to v/v' (the loaded
    leg dominates; queueing & dump time are unchanged). Returns
    fractional cycle time increase.

  watering_one_time_cycle_hit(watering_window_min, cycle_baseline)
    A watering action blocks one truck per pass over the wetted
    segment for ~watering_window_min. Returns the equivalent
    fractional cycle increase averaged across the active fleet.

  tonnes_delayed_from_cycle(production_rate_tph, duration_minutes, cycle_increase_frac)
    Convert a fractional cycle-time increase + intervention duration
    into a tonnes-delayed estimate. Conservative: assumes any cycle-
    time increase translates linearly to throughput loss.
"""

from __future__ import annotations

# AP-42 §13.2.2 says haul-truck speed effect on emission scales with
# v^0.5; for cycle time the approximate inverse holds (slower trucks
# spend more time per cycle). We use the linear-in-1/v approximation
# for cycle-time-impact since dump+load are fixed.
SPEED_CYCLE_EXPONENT = 1.0

# Watering-window default: how long a single watering pass takes per
# truck transit. Empirical default; site-specific.
DEFAULT_WATERING_WINDOW_MIN = 8.0

# Default cycle-time baseline (sec) when site config doesn't supply
# one. 180 s ≈ 3-min loop on a typical short pit→dump cycle.
DEFAULT_CYCLE_BASELINE_SEC = 180.0


def speed_reduction_cycle_impact(
    *,
    speed_before_kmh: float,
    speed_after_kmh: float,
) -> float:
    """Fractional cycle-time increase from a speed reduction.

    Returns a non-negative float in approximately [0, 2]. A reduction
    from 50 → 25 km/h returns 1.0 (cycle time doubles). Returns 0
    for non-reductions and degenerate inputs.
    """
    if speed_before_kmh <= 0 or speed_after_kmh <= 0:
        return 0.0
    if speed_after_kmh >= speed_before_kmh:
        return 0.0
    ratio = speed_before_kmh / speed_after_kmh
    return float(max(0.0, ratio**SPEED_CYCLE_EXPONENT - 1.0))


def watering_one_time_cycle_hit(
    *,
    watering_window_min: float = DEFAULT_WATERING_WINDOW_MIN,
    cycle_baseline_sec: float = DEFAULT_CYCLE_BASELINE_SEC,
    fleet_size: int = 1,
) -> float:
    """Fractional cycle increase averaged over `fleet_size` trucks.

    A single watering pass blocks one truck for `watering_window_min`
    minutes; averaged across the fleet that's a fraction of the
    cycle baseline.
    """
    if cycle_baseline_sec <= 0 or fleet_size <= 0:
        return 0.0
    blocked_sec = watering_window_min * 60.0
    return float(blocked_sec / (cycle_baseline_sec * float(fleet_size)))


def tonnes_delayed_from_cycle(
    *,
    production_rate_tph: float,
    duration_minutes: float,
    cycle_increase_frac: float,
) -> float:
    """Tonnes deferred over `duration_minutes` given a cycle-time hit.

    Linear-in-fractional-loss conversion: a 20% cycle-time increase
    over 60 min at 1000 t/h ≈ 1000 × 1 × (0.20 / 1.20) = 166.67 t.
    Uses the closed-form `loss / (1 + loss)` so the fraction never
    exceeds the underlying tonnage.
    """
    if production_rate_tph <= 0 or duration_minutes <= 0 or cycle_increase_frac <= 0:
        return 0.0
    hours = duration_minutes / 60.0
    loss_share = cycle_increase_frac / (1.0 + cycle_increase_frac)
    return float(production_rate_tph * hours * loss_share)


__all__ = [
    "DEFAULT_CYCLE_BASELINE_SEC",
    "DEFAULT_WATERING_WINDOW_MIN",
    "SPEED_CYCLE_EXPONENT",
    "speed_reduction_cycle_impact",
    "tonnes_delayed_from_cycle",
    "watering_one_time_cycle_hit",
]
