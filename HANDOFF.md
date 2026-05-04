# DustOps AI — Session Handoff

**As of:** 2026-05-03
**Active phase:** **Phase AE.0 complete — END of decision-quality batch (X → AE.0).** 9 phase commits + 1 bias-register commit on top of Phase W. The system now closes 6 of the 6 architectural tensions in the recommendation engine; Phase AE remains deferred (kill-switch fired correctly: synthetic spike not load-bearing).
**Last completed:** AE.0 — continuous-knob spike (synthetic verdict GO, real verdict gated on partnership data → AE deferred).
**Validation gate:** `npm run agent-check` GREEN, **22 PASS / 0 SKIP / 0 FAIL**. 767 backend tests + 46 web tests.

---

## Decision-quality batch summary (X → AE.0)

The user asked: *"how does the system actually decide where to reduce or cut output?"* Six tensions fell out of the design review; this batch closes all of them.

| Tension | Phase | Mechanism |
|---|---|---|
| 1 — discrete catalog vs continuous | AE.0 | Spike framework + synthetic GO verdict; AE deferred until non-synthetic corpus exists |
| 2 — attribution↔intervention coupling | Z | `target_cause_classes` + ranker `w_cause_match` boost |
| 3 — single-zone scope | AD | `resource_classes` + `solve_joint_recommendations` greedy bundler |
| 4 — temporal optimization (when) | AC | `decide_trigger_time` + `recommended_trigger_minutes_from_now` |
| 5 — plan-blind cost | AA | `compute_shift_progress` + `slack_ratio` rescale of `w_production` |
| 6 — static catalog risk class | AB | `derive_risk_class(base, context)` — escalate-only, audit trail |

Plus two adjacent quality-of-life phases:

| Goal | Phase | Mechanism |
|---|---|---|
| Promote shared multi-station GBM when it beats per-station | X | `decide_shared_promotion` + lifespan hook |
| Class-imbalance recall lift on noisy receptors | Y | `class_weight="balanced"` on the breach classifier |

---

## Commits this batch (newest first)

- `a218e63` Phase AE.0 — continuous-knob spike (kill-switch + framework)
- `3b84637` Phase AD — multi-zone joint optimization
- `0d49c35` Phase Y — class-imbalance mitigation via `class_weight="balanced"`
- `20d836b` Phase AC — temporal trigger optimization (when, not just what)
- `1f610b6` Bias register — B-46 (cause-action mismatch) + B-47 (plan-blind cost)
- `985cade` Phase AB — context-derived risk class with escalation audit
- `1da6619` Phase AA — plan-relative cost via `shift_progress` + slack rescale
- `173c7a0` Phase Z — attribution-coupled ranking via `target_cause_classes`
- `f267157` Phase X — promote shared multi-station GBM when it beats per-station

Rollback log spans `phase-x-pre-shared-promotion` through `phase-ae0-pre-spike` — one snapshot per phase.

---

## Bias register changes

| ID | Status before | Status after | Phase |
|---|---|---|---|
| B-8 (class imbalance) | Open | **Mitigated** | Y |
| B-46 (cause-action mismatch) | *new* | **Mitigated** | Z |
| B-47 (plan-blind cost) | *new* | **Mitigated** | AA |

10 numbered biases now have code-level mitigations enforced by the agent-check gate (was 8 at end of Phase W).

---

## Models currently `current` on the dev DB

After the FastAPI lifespan hook runs (Phase X promotion logic):

| Layer | `current` model | Promotion path |
|---|---|---|
| Forecast | `dust_forecast_gbm_v0.1.0` (per-station) → flips to `dust_forecast_gbm_shared_v0.1.0` if per-receptor MAE non-worse on every station and strictly better on one | X — `decide_shared_promotion` |
| Intervention impact | `intervention_impact_ap42_v0.1.0` | R.2 (unchanged) |
| Production cost | `production_cost_cycle_time_v0.1.0` | U.2 (unchanged) |
| Source attribution | `source_attribution_rules_v0.1.0` | S.2 (unchanged; logreg artifact still not persisted) |

Class imbalance handling (Phase Y) applies on the next training run; existing artifacts use the pre-Y vanilla classifier until retrain fires.

---

## What the recommendation engine now considers

Per call to `generate_recommendation(target_zone_id=...)`:

1. **Forecast** for target zone (per-station GBM or shared, depending on Phase X promotion).
2. **Attribution** for target station; top probable_source's zone_type → `cause_class`.
3. **Catalog filter** by `allowed_zone_types`.
4. **Per-candidate simulation**: AP-42 + cycle-time + simulator confidence joins.
5. **Shift progress**: live `dumping`-tonnage sum across mine zones, or synthetic from `cost_curves` overrides → `slack_ratio`.
6. **Forecast track**: synthesised flat track (deferred-mode placeholder for multi-horizon).
7. **Per-candidate scoring** with all rescales and boosts:
   - Three compliance regimes (balanced / elevated / extreme) per breach probability.
   - `w_production` rescaled by `1/clamp(slack_ratio, 0.3, 3.0)`.
   - `w_cause_match` boost when `cause_class ∈ candidate.target_cause_classes` (gated on actual breach reduction).
8. **Per-candidate context decoration**:
   - `derive_risk_class(base, shift_progress)` — escalate when deep behind plan or end-of-shift exposure.
   - `decide_trigger_time(forecast_track, time_to_effect)` — emits `recommended_trigger_minutes_from_now` + `act_now`.
   - `_plan_relative_loss(...)` — `absorbable / partial / blocking`.
9. **G6 review filter**: drop medium/high-risk actions when `requires_human_review`.
10. **(New endpoint TBD) Joint solver**: when multiple zones are at risk simultaneously, `solve_joint_recommendations` resolves resource conflicts by greedy assignment with audit trail. The existing single-zone endpoint stays.

---

## Honest deferrals carried into next session

| Item | Blocker |
|---|---|
| AE (continuous-knob optimisation) | `ActionOutcome` rows + calibrated AP-42 / cycle-time required to run a non-synthetic AE.0 spike. |
| Multi-horizon forecast track | Per-horizon GBM artifacts are only trained for `60min`. Real multi-horizon training is a follow-up. |
| AD joint endpoint | Solver shipped; `POST /api/v1/recommendations/joint` route is mechanical wiring — partnership-gated on multi-zone real-time data. |
| Logreg attribution promotion | No fitted artifact on dev DB (carry-over from Phase W). |
| Real labelled `DustEvent` corpus | Partnership-gated. |
| Calama Centro per-station fit | 66% density. |
| AERMOD/CALPUFF dispersion | ≥ 2 receptors per mine. |
| Per-mine back-fill of O.1 truck geometry | OEM datasheet entry. |

---

## Concrete next-session priorities

1. **Run the dev DB forward through the new lifespan**: `python -m uvicorn app.api.main:app` and confirm `maybe_promote_gbm_shared()` fires (or holds with the right reasons). New columns require `python scripts/migrate_intervention_target_classes.py` and `python scripts/migrate_intervention_resource_classes.py` first.
2. **Retrain forecaster with `class_weight="balanced"` (Phase Y)**: trigger via the Phase W retrain endpoint, then check the new `model_performance_metrics` row's per-receptor `breach_recall` against the pre-Y baseline.
3. **Wire the AD joint endpoint** (`POST /api/v1/recommendations/joint`) — solver is shipped, route is the load-bearing follow-up if multi-zone correlated breaches start showing up in the dev data.
4. **Wire multi-horizon forecast track** — replace `synthesize_flat_track` with calls to per-horizon GBM artifacts once those are trained. Phase AC's mechanism is already in place; the input stream is the gap.
5. **Antofagasta partnership** — same blocker. Real `ActionOutcome` rows would unlock R.2/U.2/S.2 calibration AND the AE.0 non-synthetic verdict that gates Phase AE.

---

## Key references (X → AE.0 block)

- **[app/domain/dust_forecast_promotion.py](app/domain/dust_forecast_promotion.py)** — X `maybe_promote_gbm_shared`
- **[app/training/dust_forecast_training.py](app/training/dust_forecast_training.py)** — X `decide_shared_promotion`, Y `class_weight="balanced"`
- **[app/storage/models/interventions.py](app/storage/models/interventions.py)** — Z `target_cause_classes`, AD `resource_classes`
- **[app/domain/interventions.py](app/domain/interventions.py)** — Z + AD seed defaults
- **[app/domain/shift_progress.py](app/domain/shift_progress.py)** — AA live + synthetic shift progress
- **[app/domain/risk_classification.py](app/domain/risk_classification.py)** — AB `derive_risk_class`
- **[app/domain/temporal_trigger.py](app/domain/temporal_trigger.py)** — AC `decide_trigger_time`
- **[app/domain/joint_optimization.py](app/domain/joint_optimization.py)** — AD `solve_joint_recommendations`
- **[app/domain/continuous_knob_spike.py](app/domain/continuous_knob_spike.py)** — AE.0 `measure_lift`
- **[app/models/optimization/heuristic_baseline.py](app/models/optimization/heuristic_baseline.py)** — central wiring; reads all of the above
- **[app/domain/recommendations.py](app/domain/recommendations.py)** — orchestrator threads attribution / shift_progress / forecast track into the ranker
- **[scripts/spike_continuous_knobs.py](scripts/spike_continuous_knobs.py)** — AE.0 runner
- **[docs/phase-ae0-spike.md](docs/phase-ae0-spike.md)** — AE.0 methodology + verdict thresholds
- **[docs/bias-register.md](docs/bias-register.md)** — B-8 / B-46 / B-47 entries

## Earlier-phase references (still current)

- **[app/domain/training_scheduler.py](app/domain/training_scheduler.py)** — W.1 weekly retrain
- **[app/domain/drift_response.py](app/domain/drift_response.py)** — W.2 drift-triggered retrain
- **[app/domain/cost_promotion.py](app/domain/cost_promotion.py)** — U.2 cost auto-promotion
- **[app/models/cost/cycle_time_v0_1_0.py](app/models/cost/cycle_time_v0_1_0.py)** — U.1 physics-informed cost
- **[app/models/forecasting/gbm_v0_1_0.py](app/models/forecasting/gbm_v0_1_0.py)** — per-station GBM
- **[app/models/forecasting/gbm_shared_v0_1_0.py](app/models/forecasting/gbm_shared_v0_1_0.py)** — shared multi-station GBM
- **[app/domain/dust_forecast_promotion.py](app/domain/dust_forecast_promotion.py)** — P.3 + X promotion
- **[docs/forecast-model-protocol.md](docs/forecast-model-protocol.md)** — P.1+ binding contract
- **[docs/intervention-physics.md](docs/intervention-physics.md)** — R.1+/U.1+ binding contract
