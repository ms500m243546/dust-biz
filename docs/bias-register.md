# Bias register

The full bias / integrity-hazard surface for DustOps, ranked by current exposure and mapped to the phase that mitigates each one.

This is a living document. New biases are appended; mitigated biases stay listed (with their mitigation phase) so the audit trail is complete. Every architect-protocol planning response (per `docs/architect_protocol.md` §3) must scan this register and call out which entries the proposed change touches.

Last reviewed: **2026-05-03 (Phase M.4.1)**.

---

## How to read this register

| Column | Meaning |
|---|---|
| **#** | Stable ID — never reassigned. Cite as `B-12` in code comments and audit reports. |
| **Family** | Statistical, Operational, Causal, Cognitive, Reporting, Fairness, Engineering, Adversarial. |
| **Bias** | One-line name. |
| **Exposure today** | High = actively biting us at current data scale; Medium = will bite at next-mine deployment; Low = latent until later phases; Latent = no exposure until specific trigger. |
| **Mitigation phase** | M.1 = anti-overfit + anti-hindsight protocol docs; M.2 = PIT feature schema; M.3 = causal layer; M.4 = calibration + fairness + Goodhart; "post-M" = deferred beyond Phase M. |
| **Status** | Open / Mitigated / Deferred. |

---

## Statistical / ML-process biases

| # | Family | Bias | Exposure today | Mitigation phase | Status | Notes |
|---|---|---|---|---|---|---|
| B-1 | Statistical | Overfit (1 station × 14 yrs × repeated peeks at the same eval window) | High | M.1 | Open → Mitigated by anti-overfit protocol once the gate flips | See `docs/anti-overfit-protocol.md`. |
| B-2 | Statistical | Hindsight — SINCA col-3 backfill leaks into "realtime" training | High | M.1 protocol + M.2 schema | **Mitigated (M.2)** | `SensorReading.valid_from/valid_to` + SQL probe in `validate_protocol_obeyed`. |
| B-3 | Statistical | Hindsight — ERA5 reanalysis used as realtime feature | High | M.1 protocol + M.2 schema | **Mitigated (M.2)** | `WeatherReading.realtime_proxy` + SQL probe; `pit_query.weather_readings_as_of(realtime_only=True)`. |
| B-4 | Statistical | Look-ahead in rolling-window features | Medium | M.1 (embargo) + M.2 (PIT) | **Mitigated (M.2)** | Walk-forward + embargo + `pit_query.sensor_readings_as_of`. |
| B-5 | Statistical | Survivorship — only 1 of 9 SINCA stations publishes; the survivor may be the "showcase" station | Medium | M.4 | Deferred | Document in any per-station claim until ≥ 2 receptors exist. |
| B-6 | Statistical | Selection — sensor placement chosen to monitor specific risks; spatial distribution non-random | Medium | M.4 | Deferred | Same family as B-5; weighted/stratified analysis required. |
| B-7 | Statistical | Sampling bias — sensor offline correlates with weather extremes | Medium | M.2 (PIT)| Open | Missing-not-at-random. Carry data-quality multiplier from S2 into all metrics. |
| B-8 | Statistical | Class imbalance — breach events are rare, naive accuracy is meaningless | High | M.1 | Mitigated by required precision/recall + avoided-shutdowns metrics. |
| B-9 | Statistical | Multiple comparisons / p-hacking — testing N models, picking the best | High | M.1 | Mitigated by pre-registered `protocol_hash`. |
| B-10 | Statistical | Cherry-picked test windows | High | M.1 | Mitigated by sealed test window + pre-registration. |
| B-11 | Statistical | Model selection on test set instead of validation set | High | M.1 | Mitigated by anti-peeking discipline. |

## Operational / domain biases

| # | Family | Bias | Exposure today | Mitigation phase | Status | Notes |
|---|---|---|---|---|---|---|
| B-12 | Operational | Concept drift / regime change over 14 yrs (mine expansions, fleet changes, RCA amendments) | High | M.4 | Deferred | Most-recent-N-years training option + drift watch in production. |
| B-13 | Operational | Calibration drift — sensors drift over years; old data has different calibration than new data | Medium | M.2 (PIT can carry calibration version) | Open | SINCA QC handles some but not all. |
| B-14 | Operational | Distribution shift — Los Pelambres → Los Bronces deployment will see different distributions | Medium | M.4 | Deferred | Block geographic-generalization claims until cross-validated. |
| B-15 | Operational | Time-zone drift — Chile DST policy has changed; legacy SINCA timestamps may be ambiguous | Medium | L.M.1 | Mitigated | Pinned `timezone=UTC` everywhere. Document Chile DST transitions as data-quality risk. |

## Causal / counterfactual biases

| # | Family | Bias | Exposure today | Mitigation phase | Status | Notes |
|---|---|---|---|---|---|---|
| B-16 | Causal | Treatment-effect contamination — historical PM10 reflects the post-intervention world (operators already watered roads, slowed trucks). Model learns "given the operator reacted" not "if no one acted." | High | M.3.1 (disclosure) + M.3.3 (true cutoff via operator-real timestamps) | **Mitigated-via-disclosure (M.3.1)** | `pit_query.features_pre_intervention` filter + `InterventionSimulation.counterfactual_assumption` required + naive-simulation confidence cap 0.7. True causal mitigation deferred to RCT data. |
| B-17 | Causal | Reverse causality — operator slows trucks because PM10 spiked → model could learn "slow trucks → high PM10" backwards | Medium | M.3.1 | **Mitigated-via-filter (M.3.1)** | `pit_query.features_pre_intervention` excludes feature rows inside operator-approval windows. |
| B-18 | Causal | Confounding — dry day → both trucks busy AND PM10 high; without conditioning on humidity, attribution goes to trucks | Medium | M.3.1 protocol + M.4.1 covariate-list enforcement | **Mitigated (M.4.1)** | `EvaluationProtocol.required_covariates / forbidden_covariates` enforced in `validate_protocol_obeyed`; `feature_set` is part of `protocol_hash` so covariate swaps trigger re-pre-registration. Models claiming to control for humidity must declare `required_covariates=("humidity", ...)` or fail anti-overfit rule 9. |
| B-19 | Causal | Spurious correlation — patterns that exist in training but don't generalize | Medium | M.3.1 + M.4 (drift watch) | **Mitigated-via-disclosure (M.3.1)** | `evidence_class=observational_correlational` flagged on every attribution; downstream consumers see the class. M.4 adds drift watch for production catch. |
| B-20 | Causal | Lack of counterfactual — we never observe "what if the operator did nothing"; S9 simulator must use causal graph or experimental design, not pure ML on history | High | M.3.1 disclosure + M.3.3 cutoff + post-M for true counterfactual | **Mitigated-via-disclosure (M.3.1)** | `simulation_method=naive_correlation` declared explicitly; `counterfactual_assumption` required; confidence capped. True counterfactual evidence requires RCT — out of scope for current data. |

## Cognitive / human-factors biases

| # | Family | Bias | Exposure today | Mitigation phase | Status | Notes |
|---|---|---|---|---|---|---|
| B-21 | Cognitive | Anchoring — operator anchors on the first prediction shown; same for an LLM in the loop | Latent → high at L1+ automation | M.4 (or human-factors phase) | Deferred | UI shows confidence interval, not point estimate (S16 already does). |
| B-22 | Cognitive | Automation bias — operators trust the model too much, override less than they should | Latent → high at L1+ automation | M.4 | Deferred | Audit override rate vs model confidence. |
| B-23 | Cognitive | Algorithm aversion — operators trust the model too little, override too much | Latent → high at L1+ automation | M.4 | Deferred | Sibling of B-22. |
| B-24 | Cognitive | Hawthorne / observer effect — knowing the system watches changes operator behavior | Latent | post-M | Deferred | Real once telematics integration goes live. |
| B-25 | Cognitive | Recency bias in retraining — over-weight last week's data, forget seasonality | Medium | M.4 (drift watch) | Open | Seasonal-naive baseline (B-9 mitigation) catches this. |
| B-26 | Cognitive | Availability heuristic in incident labeling — RCA blames the most-visible event, not the actual root cause | Medium | M.3.1 (provenance) + M.4 (cross-check) | **Mitigated-via-disclosure (M.3.1)** | `derivation` (M.2) distinguishes realtime vs post-event; `evidence_class=expert_judgment` (M.3.1) flags RCA-derived labels as evaluation-only. M.4 adds SMA-enforcement cross-check. |

## Reporting / communication biases

| # | Family | Bias | Exposure today | Mitigation phase | Status | Notes |
|---|---|---|---|---|---|---|
| B-27 | Reporting | Backtesting illusion — pitch deck shows the best fold; aggregate stats hide volatility | Medium | M.1 | Mitigated | Required to report distribution + worst fold per `docs/anti-overfit-protocol.md`. |
| B-28 | Reporting | Significant-figure inflation — claiming "73.4% accuracy" when CI is ±15% | Low | M.4 | Deferred | Confidence-interval reporting. |
| B-29 | Reporting | Stationarity claim — implicit assumption that future = past | High | M.4 | Deferred | Required disclaimer on every model report. |
| B-30 | Reporting | Confidence miscalibration — when model says 80%, it should be right 80%; most ML models are over-confident | High | M.4.1 | **Mitigated (M.4.1)** | Calibration acceptance gate (anti-overfit rule 8): `ECE ≤ protocol.max_ece` (default 0.05) is a hard `ProtocolViolation`. `metric_payload` persists `calibration_bins[]` + `brier_score` + `ece`; reliability diagram reproducible from the audit row. Override allowed only with explicit `ece_override_reason`, logged on the metric row. |
| B-31 | Reporting | Simpson's paradox / aggregation paradox — model is great on station-average but bad on the station you actually deploy at | Medium | M.4 + M.3 | Deferred | Require per-receptor reporting. |

## Fairness biases (Chile RCA-specific)

| # | Family | Bias | Exposure today | Mitigation phase | Status | Notes |
|---|---|---|---|---|---|---|
| B-32 | Fairness | Receptor-priority asymmetry — model trained to minimize "average" PM10 may disproportionately allow high readings at less-visible receptors (Caimanes) vs more-visible (Cuncumén) | Medium | M.4 | Open | Per-receptor breach-rate audit in S15; `project_target_mines.md` makes this load-bearing. |
| B-33 | Fairness | Operator-priority bias — model weighted toward production preservation because labeled outcomes only cover interventions operators chose to act on | Medium | M.3.1 (disclosure) + M.4 (production-cost recalibration) | **Mitigated-via-disclosure (M.3.1)** | `InterventionSimulation.selection_bias_caveat=True` by default; flag travels with every cost estimate. True recalibration deferred to operator-real telematics + M.4. |

## Engineering / data-quality hazards

| # | Family | Bias | Exposure today | Mitigation phase | Status | Notes |
|---|---|---|---|---|---|---|
| B-34 | Engineering | Time-zone bugs — UTC vs local | Latent | L.M.1 | Mitigated | UTC pinned in Open-Meteo URL builder. |
| B-35 | Engineering | DST bugs — Chile observed DST historically; hours go missing/duplicate twice a year | Latent | M.2 | Open | Document Chile DST transitions; PIT schema handles double-stamped hours. |
| B-36 | Engineering | Unit confusion — m/s vs km/h, °C vs K, hPa vs mb, µg/m³ vs mg/m³ | Latent | M.1 | Mitigated by parser-does-no-conversion discipline; `validate-units` check possible later. |
| B-37 | Engineering | Missing-value semantics — NaN / empty / 0 / -9999 confusion (SINCA col-4=0 means "raw=0" not missing) | Medium | M.2 | **Mitigated (M.2)** | Parser handles correctly; PIT carries `valid_from`/`valid_to` discriminator so absent col-2 vs col-3 vs col-4 are distinguishable in storage. |
| B-38 | Engineering | ID drift — sensor_id changes over 14-year window (rebadging, network restructures) | Low | post-M | Deferred | Cross-walk table when it bites. |
| B-39 | Engineering | Duplicate ingestion — same window pulled twice | Resolved both | L.M.1 (SensorReading) / M.2 (WeatherReading) | **Mitigated** | Both tables enforce unique constraints; orchestrator uses `INSERT OR IGNORE` for idempotent re-runs. |
| B-40 | Engineering | Schema drift — older RCAs use different parameter names | Low | M.2 | Open | Versioned schema registry. |

## Adversarial / trust hazards

| # | Family | Bias | Exposure today | Mitigation phase | Status | Notes |
|---|---|---|---|---|---|---|
| B-41 | Adversarial | Adversarial examples — operator/client feeds bad data to game the system | Low (no adversary at L0/L1 automation) | post-M | Deferred | Real once L4 automation lands. |
| B-42 | Adversarial | Label noise — RCA-derived breach labels may themselves be incorrect | Medium | M.4 | Open | Cross-check vs SMA enforcement. |
| B-43 | Adversarial | Audit-trail integrity — who labeled what, when, why | High | K.1 (S15) | Mitigated | Append-only `model_performance_metrics`, `RecommendationApproval`. |

## Goodhart-class hazards

| # | Family | Bias | Exposure today | Mitigation phase | Status | Notes |
|---|---|---|---|---|---|---|
| B-44 | Operational | Goodhart's law on the deployed metric — once "minimize FPR" is the KPI, operators game it (e.g. turn off sensor before drilling) | Latent → high once deployed | M.4 | Deferred | Each KPI gets a paired counter-metric (canary). |

---

## Review obligations

- Every architect-protocol planning response (§3 three-layer reasoning) lists the bias-register entries the proposed change touches and how it changes their `Status`.
- New biases discovered during a phase are appended with the next sequential `B-N`; never reassign IDs.
- Mitigated biases are kept on the register with the mitigation phase pinned. They are **not** removed.
- This register is consulted before every model promotion to a new automation level (`docs/safety-guardrails.md` cross-reference: `automation-promotion-checklist.md`, deferred).
