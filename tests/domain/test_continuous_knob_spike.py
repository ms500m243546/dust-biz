"""Phase AE.0 — spike framework tests."""

from __future__ import annotations

from app.domain.continuous_knob_spike import (
    ParametricPoint,
    SpikeWeights,
    measure_lift,
)


def test_grid_dominates_discrete_yields_go() -> None:
    discrete = ParametricPoint(
        parameter_value=20.0, breach_reduction=0.10, production_loss_tonnes=200.0
    )
    grid = [
        ParametricPoint(parameter_value=10.0, breach_reduction=0.20, production_loss_tonnes=200.0),
        discrete,
        ParametricPoint(parameter_value=30.0, breach_reduction=0.05, production_loss_tonnes=100.0),
    ]
    out = measure_lift(grid=grid, discrete_point=discrete, weights=SpikeWeights())
    assert out.verdict == "GO"
    assert out.lift_fraction > 0.05
    assert out.grid_point.parameter_value == 10.0


def test_discrete_already_optimal_yields_hold() -> None:
    discrete = ParametricPoint(
        parameter_value=20.0, breach_reduction=0.10, production_loss_tonnes=50.0
    )
    grid = [
        discrete,
        ParametricPoint(parameter_value=10.0, breach_reduction=0.05, production_loss_tonnes=200.0),
        ParametricPoint(parameter_value=30.0, breach_reduction=0.05, production_loss_tonnes=10.0),
    ]
    out = measure_lift(grid=grid, discrete_point=discrete, weights=SpikeWeights())
    assert out.verdict == "HOLD"
    assert out.lift_fraction == 0.0


def test_empty_grid_yields_hold() -> None:
    discrete = ParametricPoint(
        parameter_value=1.0, breach_reduction=0.1, production_loss_tonnes=10.0
    )
    out = measure_lift(grid=[], discrete_point=discrete, weights=SpikeWeights())
    assert out.verdict == "HOLD"
    assert out.lift_absolute == 0.0
    assert any("empty grid" in n for n in out.notes)


def test_weights_change_chosen_grid_point() -> None:
    grid = [
        ParametricPoint(parameter_value=1.0, breach_reduction=0.20, production_loss_tonnes=200.0),
        ParametricPoint(parameter_value=2.0, breach_reduction=0.05, production_loss_tonnes=10.0),
    ]
    discrete = grid[0]
    cost_heavy = SpikeWeights(w_breach=1.0, w_production=10.0)
    breach_heavy = SpikeWeights(w_breach=10.0, w_production=1.0)
    out_cost = measure_lift(
        grid=grid, discrete_point=discrete, weights=cost_heavy
    )
    out_breach = measure_lift(
        grid=grid, discrete_point=discrete, weights=breach_heavy
    )
    # Cost-heavy weights pick the cheap point with smaller breach drop.
    assert out_cost.grid_point.parameter_value == 2.0
    # Breach-heavy weights pick the expensive point with larger drop.
    assert out_breach.grid_point.parameter_value == 1.0


def test_zero_discrete_score_marks_lift_undefined() -> None:
    discrete = ParametricPoint(
        parameter_value=1.0, breach_reduction=0.0, production_loss_tonnes=0.0
    )
    grid = [discrete]
    out = measure_lift(grid=grid, discrete_point=discrete, weights=SpikeWeights())
    assert out.verdict == "HOLD"
    assert any("near zero" in n for n in out.notes)
