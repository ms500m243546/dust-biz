# Intervention-impact physics (Phase R)

The binding contract for the AP-42 physics-informed intervention
model (`intervention_impact_ap42_v0.1.0`) and its Phase R.2
calibration / promotion path.

## What R.1 ships

`AP42InterventionImpact` (`app/models/intervention/ap42_v0_1_0.py`)
implements `InterventionImpactModel` per `docs/model-contracts.md`,
routing the two interventions where AP-42 §13.2.2 applies:

| intervention_id | physics function | source flag |
|---|---|---|
| `water_road` | `watering_decay_curve(...)` | `model` |
| `reduce_speed` | `speed_reduction_factor(...)` | `model` |
| any other | heuristic-baseline fraction (PM10_REDUCTION_FRACTION) | `heuristic` |

The pure-function implementations live in `app/domain/ap42_emission.py`.

## Documented R.1 defaults

The current `simulate()` Protocol does not surface (silt, vehicle
weight, time since watering, meteorology). R.1 uses these defaults:

| input | default | basis |
|---|---|---|
| `silt_content_pct` | 8 | typical Chilean copper-mine haul road; AP-42 §13.2.2 example range 1.6–25.2 |
| `vehicle_weight_metric_tonnes` | 489 | Komatsu 930E (199 t empty + 290 t payload) |
| `minutes_since_watering` | 0 | model assumes the action just executed |
| `wind_speed_ms` | 5 | moderate Andean afternoon |
| `humidity_pct` | 50 | annual mean for Coquimbo / Antofagasta interior |
| `temperature_c` | 15 | annual mean ditto |
| `speed_before_kmh` | 50 | typical loaded haul-truck cruise |
| `speed_after_kmh` | 25 | typical operator-imposed reduced limit |

These are conservative pending Phase R.2 calibration. The
recommendation engine should pass real values when available — the
model class accepts overrides at the constructor level (planned Phase
R.3).

## R.2 calibration & promotion

`app/training/intervention_validation.py:validate_intervention_calibration`
joins `ActionOutcome × Recommendation × RecommendationApproval` and
returns a `CalibrationReport`:

| status | trigger | meaning |
|---|---|---|
| `calibrated` | `joined_row_count ≥ 30` AND error metrics computed | use `mean_abs_error_pct` for promotion |
| `deferred` | fewer than 30 joined rows | promotion falls back to AP-42 sanity-band check |
| `violated` | metrics computed AND error above threshold | do not promote |

`app/domain/intervention_promotion.py:maybe_promote_ap42` is wired
into the FastAPI lifespan hook. Its decision tree:

1. **calibrated** → promote iff `mean_abs_error_pct < 0.30`.
2. **deferred** → run AP-42 against canonical inputs; promote iff
   both `water_road` and `reduce_speed` reductions fall in
   `[SANITY_BAND_LOWER=0.05, SANITY_BAND_UPPER=0.65]`.
3. **violated** → do not promote.

Tolerant by design: any exception leaves the heuristic baseline as
`current` and logs INFO.

## Honest deferral (current state, 2026-05-03)

The dev DB has 0 `ActionOutcome` rows. R.2 ships in `deferred` mode:
calibration is unvalidated; promotion uses the sanity-band fallback.
Real calibration arrives once partnership telematics start flowing
recommendation/outcome pairs. Until then:

- `AP42InterventionImpact` is registered alongside the heuristic.
- The lifespan promotion check runs `maybe_promote_ap42()` once.
- If the sanity band passes, AP-42 becomes `current` for this
  process. The `main_uncertainty` field on every prediction calls
  this out: "AP-42 physics; R.1 uses documented defaults … pending
  Phase R.2 calibration."

## What this protocol does NOT cover

- Production-cost model (S10) — separate `ProductionCostModel`.
- Source attribution (S7) — Phase S.
- Forecast model (S6) — Phase P.
- Optimization (S11) — heuristic for the foreseeable future.
- Dispersion modelling (AERMOD/CALPUFF) — deferred until ≥ 2
  receptors per mine; currently not in any phase.
