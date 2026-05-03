# DustOps AI — Session Handoff

**As of:** 2026-05-03
**Active phase:** **Phase W.2 complete — END of T→W batch.** 21 sub-phase commits this session across 8 phases (P → Q → R → S → T → U → V → W). System now has real models at every learnable layer (forecast / intervention / cost) + bias mitigations + UI surfaces + continuous-learning hooks.
**Last completed:** W.2 — drift-triggered retrain endpoint + audit-trail behaviour.
**Validation gate:** `npm run agent-check` GREEN, **22 PASS / 0 SKIP / 0 FAIL**. 6XX backend tests + 46 web tests.

---

## State at handoff

- Working tree clean. All 21 sub-phases committed.
- Recent commits (newest first):
  - `16c7ace` Phase W.2 — drift-triggered retrain endpoint
  - `6cbeb64` Phase W.1 — scheduled weekly retrain
  - `b0d7f67` Phase V.3 — confidence-propagation regression suite
  - `2fd22cd` Phase V.2 — audit-trail model_version consistency
  - `25d37c2` Phase V.1 — registry-state integration tests
  - `84cf2af` Phase U.2 — cycle-time cost auto-promotion
  - `8216d78` Phase U.1 — cycle-time-aware cost model
  - `2f3bbce` Phase T.3 — EvidenceClass distribution chart
  - `c723b69` Phase T.2 — multi-station caveat banners
  - `93a6835` Phase T.1 — per-receptor fairness panel
  - `922ca79` Phase S.2 — logreg attribution auto-promotion
  - `a21e474` Phase S.1 — logreg source-attribution model
  - `49da735` Phase R.2 — intervention calibration + AP-42 promotion
  - `5c95fa8` Phase R.1 — AP-42 physics intervention model
  - `dbd71eb` Phase Q.3 — multi-station discipline (B-5/B-6/B-14 closure)
  - `3f7ede3` Phase Q.2 — shared multi-station GBM
  - `f2597e3` Phase Q.1 — multi-station GBM expansion
  - `6304954` Phase P.3 — GBM auto-promotion via lifespan hook
  - `a996275` Phase P.2 — real GBM fit on Cuncumén
  - `1b33207` Phase P.1 — first trained-forecast scaffold
  - `d1fbec1` Phase O.2 — multi-mine SINCA survey + connector fix
- Rollback log spans `phase-p1-pre-scaffold` through `phase-w2-pre-drift-retrain` — one snapshot per sub-phase.
- DB state: 4 new nullable columns on `equipment` (O.1, AP-42 inputs). 6 `model_performance_metrics` rows persisted (5 per-station GBM + 1 shared). Heuristic baselines remain registered as fallbacks per Guardrail 11 at every layer.

---

## Real-data corpus driving the models

- **PM10 sensor readings**: 148,752 (PIT-versioned)
- **Weather readings**: 70,272 (Open-Meteo / ERA5)
- **Mines registered**: 5 (Los Pelambres, Los Bronces, Chuquicamata, Centinela, +baseline)
- **Sensor stations**: 22 (5 SINCA-public with real PM10 data)

12-month corpus by station (the training corpus):

| Station | Mine | Records | Density |
|---|---|---|---|
| `chq-club-23-marzo` | Chuquicamata | 8,670 | ~99% |
| `lp-em05-cuncumen` | Los Pelambres | 8,604 | ~98% |
| `cnt-sierra-gorda` | Centinela | 7,017 | ~80% |
| `lb-las-condes` | Los Bronces | 6,959 | ~79% |
| `chq-calama-centro` | Chuquicamata | 5,764 | ~66% (skipped per-station, included in shared) |

---

## Models currently `current` on the dev DB

After the FastAPI lifespan hook runs:

| Layer | `current` model | Promotion path |
|---|---|---|
| Forecast | `dust_forecast_gbm_v0.1.0` | P.3 — `decide_promotion()` over latest M.4 metric row passed |
| Intervention impact | `intervention_impact_ap42_v0.1.0` | R.2 — sanity-band probe passed (deferred mode, 0 outcomes) |
| Production cost | `production_cost_cycle_time_v0.1.0` | U.2 — sanity-band probe passed |
| Source attribution | `source_attribution_rules_v0.1.0` (baseline) | S.2 — held; no logreg artifact persisted on dev DB |

To promote logreg attribution: train it via `train_logreg_attributor` against a candidate corpus, then re-bootstrap.

---

## Headline forecast performance (sealed test 2026-04-01 → 2026-05-03)

### Per-station GBM (`dust_forecast_gbm_v0.1.0`)

| Station | test_n | ECE | MAE PM10 | breach_recall |
|---|---|---|---|---|
| `lp-em05-cuncumen` | 758 | ~2e-15 | **9.25 µg/m³** | n/a* |
| `lb-las-condes` | 427 | 0.0023 | **11.29 µg/m³** | 0.00 |
| `chq-club-23-marzo` | 757 | 0.0 | **1.68 µg/m³** | n/a* |
| `cnt-sierra-gorda` | 767 | 0.0143 | **26.09 µg/m³** | 0.10 |

\* No breach events in the sealed window (B-8 class imbalance — expected).

### Shared multi-station GBM (`dust_forecast_gbm_shared_v0.1.0`)

| Aggregate | Value |
|---|---|
| Train rows | 30,017 |
| Test rows | 2,709 |
| Aggregate ECE | **0.003** |
| Aggregate MAE PM10 | **11.05 µg/m³** |
| Aggregate breach_recall | **0.091** |

Per-receptor MAE in the shared model **wins on every station and gains most on the noisiest** (Sierra Gorda 26.09 → 22.40). Cross-station signal is doing real work.

---

## Bias register status

| ID | Status | Phase |
|---|---|---|
| B-5 (survivorship) | **Mitigated** | Q.3 |
| B-6 (selection) | **Mitigated** | Q.3 |
| B-12 (concept drift) | **Mitigated** | M.4.3 |
| B-14 (distribution shift) | **Mitigated** | Q.3 |
| B-18 (confounding) | **Mitigated** | M.4.1 |
| B-30 (calibration) | **Mitigated** | M.4.1 |
| B-32 (receptor asymmetry) | **Mitigated** | M.4.2 |
| B-44 (Goodhart) | **Mitigated** | M.4.2 |

8 numbered biases now have code-level mitigations enforced by the agent-check gate.

Still open (gated on partnership data or net-new engineering):
- B-7 (sampling bias when sensor offline correlates with weather)
- B-13 (long-term calibration drift)
- B-25 (recency bias in retraining — partial via covariate discipline)
- B-29 (stationarity claim)
- B-31 (Simpson's paradox / aggregation)
- B-35 (Chile DST)
- B-40 / B-42 (RCA schema drift / label noise)

---

## Honest deferral list (partnership-gated, not engineering-gated)

| Gap | Blocker |
|---|---|
| AP-42 + cycle-time empirical calibration | 0 `ActionOutcome` rows; needs telematics |
| Logreg attribution as `current` | No fitted artifact on dev DB; needs labelled corpus |
| Real labelled `DustEvent` corpus | Partnership-gated |
| Calama Centro per-station fit | 66% density; thin-station handling |
| Per-receptor ECE breakdown | `_per_receptor_breakdown` only computes MAE/recall/precision/FPR |
| AERMOD/CALPUFF dispersion | ≥ 2 receptors per mine; receptor-density gated |
| Phase M.3.3 true intervention-window cutoff | Operator-real telematics |
| Per-mine back-fill of O.1 truck geometry | OEM datasheet entry (one-time data exercise) |

---

## Concrete next-session priorities

1. **Run the weekly retrain manually once** to confirm the lifespan hook + scheduler integration produce a fresh metric_payload row on the dev DB.
2. **Train + persist a logreg attribution artifact** so S.2 can promote — operator runs `train_logreg_attributor` against a representative candidate pool (synthetic until a labelled corpus exists).
3. **Per-mine back-fill of O.1 truck-geometry** for the Los Pelambres fleet — populate `empty_weight_tonnes`, `tire_count`, etc. from Komatsu / Cat datasheets per `docs/training-features.md`.
4. **Phase X (proposed)** — promote the shared multi-station GBM to current. Currently `dust_forecast_gbm_v0.1.0` (per-station) is current; the shared variant beats it on per-receptor MAE for every station including the noisiest. Wire decide_promotion to compare versions.
5. **Phase Y (proposed)** — class-imbalance mitigation for the breach classifier (Las Condes recall=0.0 is the tell). Options: class-weighted loss, lower decision threshold, focal loss. Also revisit the breach-decision threshold (currently 0.5) per receptor.
6. **Antofagasta partnership conversation** — same blocker as last session. Real `ActionOutcome` rows would unlock R.2 / U.2 calibration mode, S.2 outcome-supervised training, and Phase O proper bias work.

---

## Key references (T → W block)

- **[app/domain/training_scheduler.py](app/domain/training_scheduler.py)** — W.1 weekly retrain wiring
- **[app/domain/drift_response.py](app/domain/drift_response.py)** — W.2 drift-triggered retrain
- **[app/api/routes/drift_retrain.py](app/api/routes/drift_retrain.py)** — `POST /api/v1/drift/retrain` admin-only
- **[app/domain/cost_promotion.py](app/domain/cost_promotion.py)** — U.2 cost auto-promotion via sanity band
- **[app/models/cost/cycle_time_v0_1_0.py](app/models/cost/cycle_time_v0_1_0.py)** — U.1 physics-informed cost
- **[app/domain/production_cost_physics.py](app/domain/production_cost_physics.py)** — U.1 pure-function physics
- **[web/src/components/PerReceptorTable.tsx](web/src/components/PerReceptorTable.tsx)** — T.1
- **[web/src/components/MultiStationCaveats.tsx](web/src/components/MultiStationCaveats.tsx)** — T.2
- **[web/src/components/EvidenceDistribution.tsx](web/src/components/EvidenceDistribution.tsx)** — T.3
- **[tests/integration/test_recommendation_with_real_models.py](tests/integration/test_recommendation_with_real_models.py)** — V.1
- **[tests/domain/test_audit_model_version_consistency.py](tests/domain/test_audit_model_version_consistency.py)** — V.2
- **[tests/domain/test_confidence_propagation.py](tests/domain/test_confidence_propagation.py)** — V.3

## Earlier-phase references (still current)

- **[app/training/dust_forecast_training.py](app/training/dust_forecast_training.py)** — P.1/P.2/Q.1/Q.2 trainer
- **[app/models/forecasting/gbm_v0_1_0.py](app/models/forecasting/gbm_v0_1_0.py)** — per-station GBM
- **[app/models/forecasting/gbm_shared_v0_1_0.py](app/models/forecasting/gbm_shared_v0_1_0.py)** — shared multi-station GBM
- **[app/domain/dust_forecast_promotion.py](app/domain/dust_forecast_promotion.py)** — P.3 forecast promotion
- **[app/domain/intervention_promotion.py](app/domain/intervention_promotion.py)** — R.2 intervention promotion
- **[app/domain/attribution_promotion.py](app/domain/attribution_promotion.py)** — S.2 attribution promotion
- **[app/models/intervention/ap42_v0_1_0.py](app/models/intervention/ap42_v0_1_0.py)** — AP-42 model
- **[app/domain/ap42_emission.py](app/domain/ap42_emission.py)** — AP-42 physics
- **[app/models/attribution/logreg_v0_1_0.py](app/models/attribution/logreg_v0_1_0.py)** — logreg attribution
- **[app/domain/model_performance.py](app/domain/model_performance.py)** — M.4 metric_payload + Q.3 caveats
- **[docs/forecast-model-protocol.md](docs/forecast-model-protocol.md)** — P.1+ binding contract
- **[docs/intervention-physics.md](docs/intervention-physics.md)** — R.1+/U.1+ binding contract
- **[docs/bias-register.md](docs/bias-register.md)** — 8 numbered biases now Mitigated
