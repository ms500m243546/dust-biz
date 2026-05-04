# Phase AE.0 — continuous-knob spike (go / no-go gate for AE)

Phase AE proposes generalising the discrete `InterventionOption`
catalog into parameterised *families* (e.g. `reduce_speed` becomes
`speed ∈ [10, 30] km/h` instead of a fixed 20). The ranker would then
select the Pareto-optimal point on the breach-reduction × cost
frontier under current weights.

AE is the most expensive phase in the decision-quality batch
(catalog migration, vectorised AP-42 + cycle-time, Pareto rendering,
UI changes). AE.0 is its kill-switch: if the lift over the discrete
catalog is too small to justify the engineering, AE doesn't ship.

## Methodology

For each parameterised family:

1. Build a 5-step grid over the parameter (`scripts/spike_continuous_knobs.py`).
2. Compute `(breach_reduction, production_loss_tonnes)` per point
   under the same simulation + cost basis the optimiser uses.
3. Score each point as `score = w_breach * Δp - w_production * (tonnes/1000)`.
4. Compare:
   * **discrete**  — score at the catalog's shipped parameter value.
   * **grid**      — Pareto-best score over the full grid.
5. Compute `lift_fraction = (grid_score - discrete_score) / |discrete_score|`.

## Verdict thresholds

* **per-family**: `GO` iff `lift_fraction ≥ 0.05` (5% relative).
* **overall**:    `GO` iff at least 2 of 3 reference families flip GO.

## Reference families (current run)

* `reduce_speed`     — speed ∈ {30, 25, 20, 15, 10} km/h. Catalog ships 20.
* `water_road`       — volume ∈ {0.5, 0.75, 1.0, 1.25, 1.5} L/m²/pass. Catalog ships 1.0.
* `throttle_crusher` — cut % ∈ {10, 20, 30, 40, 50}. Catalog ships 30.

## Honest deferral

The current scoring uses **synthetic** breach-reduction × cost curves
plausibly matching AP-42 + cycle-time shape. A real verdict requires
`ActionOutcome` rows + the calibrated intervention/cost models. The
synthetic run demonstrates the framework — not the deployed magnitude.

**Decision:** AE proceeds only when `python scripts/spike_continuous_knobs.py`
prints `Overall verdict: GO` on a non-synthetic corpus. Until partnership
telematics arrives, **AE remains deferred** and the discrete catalog
stands.

## Why a synthetic spike is still worth shipping

* Documents the methodology so the verdict path is reproducible.
* Provides the framework code (`app/domain/continuous_knob_spike.py`)
  that future real-data runs use without re-design.
* Exposes the Pareto-frontier mechanism as a reusable building block
  if AE eventually proceeds.
