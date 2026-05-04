"""Phase AE.0 — go/no-go runner for continuous-knob optimisation.

Builds three reference scenarios (reduce_speed, water_road,
throttle_crusher) using *synthetic* parameter expansion plausibly
matching the AP-42 + cycle-time shape, runs the spike comparison, and
prints a verdict.

Honest-deferral note: real verdicts require operator outcome data
(`ActionOutcome` rows). Until partnership telematics arrives, the
numbers below are illustrative; the script is the framework future
runs will use, and it documents the methodology.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.domain.continuous_knob_spike import (  # noqa: E402
    LiftMeasurement,
    ParametricPoint,
    SpikeWeights,
    measure_lift,
)


def _reduce_speed_grid() -> list[ParametricPoint]:
    """5-step grid over haul-truck speed: 30 / 25 / 20 / 15 / 10 km/h.

    Synthetic AP-42 shape: emission factor scales with (W/3)^0.45 in
    the formula but the *speed* dependency comes through resuspension
    intensity, which we approximate as linear in (1 - speed/30). Cost
    grows roughly linearly in 1/speed (more cycle time per haul).
    """
    catalog_speed = 20.0  # current discrete catalog ships 20 km/h
    points: list[ParametricPoint] = []
    for speed in (30.0, 25.0, 20.0, 15.0, 10.0):
        # Higher speed -> more dust -> less reduction.
        breach_reduction = round(0.10 + 0.05 * (catalog_speed - speed) / 5.0, 4)
        # Lower speed -> more cycle time per haul -> larger production
        # loss (in tonnes per shift).
        production_loss = round(50.0 + 12.0 * (catalog_speed - speed), 2)
        points.append(
            ParametricPoint(
                parameter_value=speed,
                breach_reduction=max(0.0, breach_reduction),
                production_loss_tonnes=max(0.0, production_loss),
            )
        )
    return points


def _water_road_grid() -> list[ParametricPoint]:
    """5-step grid over water application volume (L/m^2/pass)."""
    points: list[ParametricPoint] = []
    for vol in (0.5, 0.75, 1.0, 1.25, 1.5):
        breach_reduction = round(0.05 + 0.07 * (vol / 1.5), 4)
        production_loss = round(20.0 * vol, 2)
        points.append(
            ParametricPoint(
                parameter_value=vol,
                breach_reduction=breach_reduction,
                production_loss_tonnes=production_loss,
            )
        )
    return points


def _throttle_crusher_grid() -> list[ParametricPoint]:
    """5-step grid over crusher throughput cut (%)."""
    points: list[ParametricPoint] = []
    for pct in (10.0, 20.0, 30.0, 40.0, 50.0):
        breach_reduction = round(0.04 + 0.005 * pct, 4)
        production_loss = round(8.0 * pct, 2)
        points.append(
            ParametricPoint(
                parameter_value=pct,
                breach_reduction=breach_reduction,
                production_loss_tonnes=production_loss,
            )
        )
    return points


def _print_measurement(name: str, m: LiftMeasurement) -> None:
    print(f"\n[{name}]")
    print(
        f"  discrete: param={m.discrete_point.parameter_value:.2f}  "
        f"reduction={m.discrete_point.breach_reduction:.3f}  "
        f"cost={m.discrete_point.production_loss_tonnes:.1f} t  "
        f"score={m.discrete_score:.4f}"
    )
    print(
        f"  grid    : param={m.grid_point.parameter_value:.2f}  "
        f"reduction={m.grid_point.breach_reduction:.3f}  "
        f"cost={m.grid_point.production_loss_tonnes:.1f} t  "
        f"score={m.grid_score:.4f}"
    )
    print(
        f"  lift    : abs={m.lift_absolute:+.4f}  "
        f"frac={m.lift_fraction:+.2%}  -> {m.verdict}"
    )
    for note in m.notes:
        print(f"    note: {note}")


def main() -> int:
    print("Phase AE.0 spike — synthetic continuous-knob lift measurement")
    print("=" * 70)
    weights = SpikeWeights()
    measurements: list[tuple[str, LiftMeasurement]] = []

    rs_grid = _reduce_speed_grid()
    rs_discrete = next(p for p in rs_grid if p.parameter_value == 20.0)
    measurements.append(
        ("reduce_speed", measure_lift(grid=rs_grid, discrete_point=rs_discrete, weights=weights))
    )

    wr_grid = _water_road_grid()
    wr_discrete = next(p for p in wr_grid if p.parameter_value == 1.0)
    measurements.append(
        ("water_road", measure_lift(grid=wr_grid, discrete_point=wr_discrete, weights=weights))
    )

    tc_grid = _throttle_crusher_grid()
    tc_discrete = next(p for p in tc_grid if p.parameter_value == 30.0)
    measurements.append(
        ("throttle_crusher", measure_lift(grid=tc_grid, discrete_point=tc_discrete, weights=weights))
    )

    for name, m in measurements:
        _print_measurement(name, m)

    n_go = sum(1 for _, m in measurements if m.verdict == "GO")
    overall = "GO" if n_go >= 2 else "HOLD"
    avg_lift = sum(m.lift_fraction for _, m in measurements) / len(measurements)

    print("\n" + "=" * 70)
    print(f"Spike summary: {n_go}/{len(measurements)} families GO; "
          f"avg lift {avg_lift:+.2%}")
    print(f"Overall verdict: {overall}")
    print(
        "\nCaveat: scenarios are SYNTHETIC. A real verdict requires "
        "ActionOutcome\nrows + calibrated AP-42 / cycle-time models. "
        "This run measures the\nmechanism (Pareto frontier dominates "
        "discrete pick when curvature exists),\nnot the deployed magnitude."
    )
    print(
        "\nDecision: AE proceeds only when this script prints GO on a "
        "non-synthetic run\n(real outcome corpus). Until then AE remains "
        "deferred."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
