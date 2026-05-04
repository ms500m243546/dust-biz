"""Phase AE.0 — continuous-knob lift measurement (the kill-switch spike).

Phase AE proposes generalising the discrete catalog into parameterised
*families* of actions (reduce_speed → speed ∈ {30, 25, 20, 15, 10} km/h)
and ranking the Pareto-optimal point on the frontier. AE is the most
expensive phase in the decision-quality batch, so AE.0 is its
go/no-go gate.

This module provides a pure-function lift estimator. It models a
parameterised intervention as a set of (breach_reduction, cost) points
and compares:

  * `discrete_choice(...)` — the prior catalog behaviour: pick the
    single point that the catalog ships.
  * `grid_choice(...)`     — Pareto-optimal point given the current
    weights, scanned over the full parameter grid.

The reported lift is the score gap (continuous − discrete) divided by
|discrete|. A grid-choice that ties the discrete catalog yields lift
≈ 0; a Pareto-optimal point that meaningfully dominates yields > 0.

Real measurement requires real intervention-outcome data (calibrated
AP-42 + cycle-time models). On synthetic scenarios the framework
demonstrates the *mechanism* but not the *magnitude* — the verdict
can only be trusted once partnership telematics arrives. The spike
documents this limitation explicitly so downstream callers don't
treat the synthetic verdict as load-bearing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParametricPoint:
    """One (parameter_value, breach_reduction, production_loss) tuple."""

    parameter_value: float
    breach_reduction: float
    production_loss_tonnes: float


@dataclass(frozen=True)
class SpikeWeights:
    w_breach: float = 1.0
    w_production: float = 1.0


@dataclass(frozen=True)
class LiftMeasurement:
    """Result of one spike comparison.

    `lift_fraction` is the relative improvement of grid vs discrete on
    the same scenario. `verdict` is either `"GO"` (>= go_threshold) or
    `"HOLD"`.
    """

    discrete_score: float
    discrete_point: ParametricPoint
    grid_score: float
    grid_point: ParametricPoint
    lift_absolute: float
    lift_fraction: float
    verdict: str
    notes: tuple[str, ...]


def _score(point: ParametricPoint, weights: SpikeWeights) -> float:
    """Same shape as `WeightedOptimizationEngine._score_candidate` —
    breach reduction less production cost in tonne-thousands."""
    return weights.w_breach * point.breach_reduction - weights.w_production * (
        point.production_loss_tonnes / 1000.0
    )


def measure_lift(
    *,
    grid: list[ParametricPoint],
    discrete_point: ParametricPoint,
    weights: SpikeWeights,
    go_threshold: float = 0.05,
) -> LiftMeasurement:
    """Compute lift from grid scan vs discrete catalog.

    `discrete_point` is the catalog's shipped parameter value for this
    family. `grid` is the parameter scan AE.1+ would ship. Both must
    use the same simulation/cost basis; this function does not call
    the simulator.
    """
    notes: list[str] = []
    if not grid:
        return LiftMeasurement(
            discrete_score=_score(discrete_point, weights),
            discrete_point=discrete_point,
            grid_score=_score(discrete_point, weights),
            grid_point=discrete_point,
            lift_absolute=0.0,
            lift_fraction=0.0,
            verdict="HOLD",
            notes=("empty grid; nothing to compare",),
        )
    grid_best = max(grid, key=lambda p: _score(p, weights))
    discrete_score = _score(discrete_point, weights)
    grid_score = _score(grid_best, weights)
    lift_absolute = grid_score - discrete_score
    if abs(discrete_score) < 1e-9:
        # Avoid divide-by-zero when the discrete pick scores ~0.
        lift_fraction = 0.0 if abs(lift_absolute) < 1e-9 else float("inf")
        notes.append("discrete score near zero; lift_fraction undefined")
    else:
        lift_fraction = lift_absolute / abs(discrete_score)
    verdict = "GO" if lift_fraction >= go_threshold else "HOLD"
    return LiftMeasurement(
        discrete_score=discrete_score,
        discrete_point=discrete_point,
        grid_score=grid_score,
        grid_point=grid_best,
        lift_absolute=lift_absolute,
        lift_fraction=lift_fraction,
        verdict=verdict,
        notes=tuple(notes),
    )


__all__ = [
    "LiftMeasurement",
    "ParametricPoint",
    "SpikeWeights",
    "measure_lift",
]
