# DustOps AI — Session Handoff

**As of:** 2026-05-03
**Active phase:** Phase N complete — drift-watch UI surfacing. M.4 block (M.4.1 + M.3.2 + M.4.2 + M.4.3) and N now done. 5 biases closed (B-12, B-18, B-30, B-32, B-44).
**Last completed:** Phase N — `web/src/views/Drift.tsx` mounted at `/drift`, role-gated to `environmental_manager` + `admin`, consumes `GET /api/v1/drift`. New `api.driftAlerts()` client method + `DriftAlertSchema` wire type. ui-principles annex documents the role-restricted view.
**Validation gate:** `npm run agent-check` GREEN, **21 PASS / 0 SKIP / 0 FAIL**. 584 backend tests + 25 web tests (was 17 at M.3.2; +8 from `drift.test.tsx`).

---

## State at handoff

- Phase N changes uncommitted (8 files: `web/src/views/Drift.tsx`, `web/src/__tests__/drift.test.tsx`, `web/src/api/types.ts`, `web/src/api/client.ts`, `web/src/views/Layout.tsx`, `web/src/App.tsx`, `docs/ui-principles.md`, `docs/normalization_report.md`, plus this handoff). M.4 changes were already committed.
- Recent commits (newest first):
  - `892fda3` Phase M.4.3 — drift watch (B-12)
  - `58097e6` Phase M.4.2 — fairness + Goodhart canaries (B-32, B-44)
  - `acac35b` Phase M.3.2 — UI surfacing of causal + calibration fields
  - `ad5c7f0` Phase M.4.1 — calibration acceptance gate + covariate discipline (B-30, B-18)
  - `6b8a7ab` Phase M.1 + M.2 + M.3.1 — anti-overfit + anti-hindsight + causal disclosure
- Rollback log: `phase-m4-1-pre-calibration`, `phase-m4-2-pre-fairness`, `phase-m4-3-pre-drift`, `phase-n-pre-drift-ui`. (M.3.2 has no snapshot — git revert `acac35b` is the revert path.)
- DB state: no schema migration required for Phase N (read-only consumer of an existing endpoint).
- Memory: `project_phase_m4_complete.md` superseded by new `project_phase_n_complete.md` entry.

---

## What shipped in Phase N

- `web/src/views/Drift.tsx` — single-card drift dashboard. Polls `GET /api/v1/drift` every 60s; defaults `model_version` to the most recent `modelPerformance()` row; window picker 14 / 30 / 90 days. Per-row severity tier yellow ≥ 1× threshold ("NOTICE") / red ≥ 2× threshold ("ACT"); card border tracks the worst tier. Two distinct empty states ("No model_performance rows yet" vs "No drift detected in window"). Detection-only — no approve/reject controls.
- `web/src/api/types.ts` — `DriftAlertSchema` added (mirror of backend `app/schemas/drift.py`).
- `web/src/api/client.ts` — `api.driftAlerts({ model_version, since_days, min_samples })` method.
- `web/src/views/Layout.tsx` — nav link "Drift" rendered only when `user.role ∈ { environmental_manager, admin }`.
- `web/src/App.tsx` — `/drift` route wrapped in `RoleGate`; non-allowed roles redirect to `/control-room`.
- `web/src/__tests__/drift.test.tsx` — 8 vitest cases: severity helper, version dedup, alerts table, no-drift empty state, window-switch refetch, error row, model-performance-empty empty state.
- `docs/ui-principles.md` — annex section "Drift view (Phase N — env_manager + admin only)".
- `docs/normalization_report.md` — Phase N entry promoted to Active.

**Why a useEffect-driven reload inside `Drift.tsx`:** `useApi`'s `reload` is bound on mount with `useCallback([])`, so it does not naturally re-trigger when the `fetchDrift` closure changes (model_version / since_days picker). The component calls `drift.reload()` from a small effect tied to those state values; `fnRef` inside `useApi` is already kept current. Documented inline; consider lifting into `useApi` later if a second view needs the same pattern.

## What shipped in the M.4 block

### M.4.1 — Calibration acceptance gate + covariate discipline

- `EvaluationProtocol` extended: `feature_set`, `required_covariates`, `forbidden_covariates`, `max_ece` (default **0.05**), `ece_override_reason`. The four hashed fields enter `protocol_hash`; override reason is a non-hashed audit annotation.
- `compute_metric_payload` now emits `calibration_bins[]` (10-bin reliability per Niculescu-Mizil & Caruana 2005), `brier_score`, `ece`. `ece > max_ece` raises `ProtocolViolation` unless an override reason is supplied (logged on the metric row).
- `validate_protocol_obeyed` adds anti-overfit rule 9: required covariates ⊆ `feature_set`; forbidden ones not in `feature_set`.
- `PROTOCOL_VERSION` bumped from "M.1" to "M.4".
- `validate-overfit-discipline.js` enforces calibration + covariate fields on M.4-tagged rows; M.1/M.2/M.3 rows tolerated.
- Bias register: B-30, B-18 → **Mitigated (M.4.1)**.

### M.3.2 — UI surfacing

- Backend schemas threaded: `SourceAttributionSchema.evidence_class`, `RecommendationSchema.causal_confidence`, `InterventionSimulationSchema.{simulation_method, counterfactual_assumption, selection_bias_caveat}` — all defaulting to storage defaults so existing API consumers keep working.
- Web wire types extended; new `api.modelPerformance()` client method.
- New components: `web/src/components/EvidenceChip.tsx` (strong/weak tier per evidence class with hover tooltip) and `web/src/components/CalibrationBadge.tsx` (good/marginal/over driven by ECE vs `max_ece`, surfaces override reason).
- Wired into `ControlRoom` (Likely-cause card → evidence chip; Recommended-action card → predictive + causal confidence pair + calibration badge) and `Compliance` (new Source-attributions card; new Model-calibration card).
- `docs/ui-principles.md` adds rules for the evidence-chip and calibration-badge surfaces.

### M.4.2 — Fairness audit + Goodhart canaries

- `metric_payload` gains `per_receptor` (same headline metrics split by `target_id`) and `canary_metrics` (every deployable KPI paired with a counter-metric whose drift reveals gaming).
- `GOODHART_CANARY_PAIRS` constant: `breach_precision↔breach_recall`, `false_positive_rate↔breach_recall`, `avoided_shutdowns_estimate↔false_negative_rate`, `production_loss_tonnes_total↔breach_recall`.
- `docs/safety-guardrails.md` adds two new sections — Goodhart-canary discipline (**binding on automation-promotion decisions**) and per-receptor fairness audit.
- Bias register: B-32, B-44 → **Mitigated (M.4.2)**.

### M.4.3 — Drift watch

- New `app/domain/drift_watch.py:compute_drift` — splits `model_performance_metrics` rows for one `model_version` into baseline (oldest half) + recent (newest half) and emits one `DriftAlert` per metric whose median crosses the per-metric threshold in `DRIFT_THRESHOLDS`.
- Threshold table: `mae_pm10` 5.0 µg/m³, probability metrics (recall/precision/FPR/FNR) 10pp, `ece` 0.025, `calibration_error` 0.05.
- New `GET /api/v1/drift?model_version=&since_days=14&min_samples=4`, auth-gated. Detection-only; operational alerting and "most-recent-N-years" retraining are post-M.
- New validator `scripts/checks/validate-drift-discipline.js` (#21 in the gate).
- Bias register: B-12 → **Mitigated (M.4.3)**.

---

## Bias-register status (post-M.4)

| ID | Bias | Status | Phase |
|---|---|---|---|
| B-12 | Concept drift | **Mitigated** | M.4.3 |
| B-18 | Confounding | **Mitigated** | M.4.1 |
| B-30 | Confidence miscalibration | **Mitigated** | M.4.1 |
| B-32 | Receptor-priority asymmetry | **Mitigated** | M.4.2 |
| B-44 | Goodhart on the deployed metric | **Mitigated** | M.4.2 |

**Still open** (mostly post-M / multi-station-required):
- B-5 / B-6 (survivorship + selection — needs ≥ 2 SINCA stations).
- B-7 (sampling bias — sensor-offline correlates with weather extremes).
- B-13 (calibration drift over years — partial via PIT versioning).
- B-14 (Los Pelambres → Los Bronces distribution shift).
- B-25 (recency bias in retraining — partial via covariate discipline).
- B-29 (stationarity claim).
- B-31 (Simpson's paradox / aggregation).
- B-35 (Chile DST transitions).
- B-40 (schema drift in old RCAs).
- B-42 (RCA label noise).

---

## Open work / next steps

| ID | Severity | Summary | Resolution |
|---|---|---|---|
| **M.3.3** | medium-latent | True intervention-window cutoff (`ActionOutcome.intervention_window`) once operator-real telematics lands | Phase M.3.3 — depends on Antofagasta partnership data flow |
| L.M1-R1 | medium | 12-month Open-Meteo live pull not yet executed (network was unreachable) | Operator-runnable; idempotent under M.2 orchestrator |
| L7a-R1 | medium | Only 1 of 9 nearby SINCA stations has real data | Antofagasta partnership or SMA SEIA scrape |
| L5-carryover | medium-latent | Equipment-side ingest is the bottleneck | `operator_real` adapter ready; needs partnership data flow |

**Concrete next session priorities:**

1. **Commit Phase N** (8 modified/created files; rollback snapshot `phase-n-pre-drift-ui` already taken).
2. **Run the deferred 12-month Open-Meteo live pull** when network is stable. Idempotent.
3. **Phase M.3.3** — true intervention-window cutoff. Blocked on operator-real telematics; gated by Antofagasta partnership.
4. **Phase O (proposed):** post-M biases that bite at second-mine deployment — B-5 / B-6 / B-14 (Los Bronces). Multi-station survivorship + distribution-shift mitigation needs ≥ 2 stations of real data first.
5. **Phase N follow-ups (deferred):** alert acknowledgement / persistence, per-metric filtering, feature-distribution drift (PSI/KL — needs feature-distribution snapshots stored per row).

---

## How a model declares the M.4 protocol surface

```python
from app.domain.evaluation_protocol import EvaluationProtocol

protocol = EvaluationProtocol(
    split_strategy="walk_forward",
    train_window_from=...,
    train_window_to=...,
    validation_window_from=...,
    validation_window_to=...,
    test_window_from=...,
    test_window_to=...,
    # M.4.1 — covariate discipline
    feature_set=("pm10_lag1", "humidity", "wind_speed"),
    required_covariates=("humidity",),  # B-18 mitigation
    forbidden_covariates=("validated_pm10_col3",),  # B-2 hindsight block
    # M.4.1 — calibration acceptance gate
    max_ece=0.05,  # default; override below requires reason
    # ece_override_reason="diagnostic only - not promoted",
    # M.3 — causal-protocol opt-in (default False)
    causal_intent=False,
)
```

`metric_payload` rows under M.4 carry: `calibration_bins[]`, `ece`, `brier_score`, `per_receptor`, `canary_metrics`, plus the M.1/M.2/M.3 fields. `validate-overfit-discipline.js` enforces presence on every M.4-tagged row.

---

## How to query drift

```bash
GET /api/v1/drift?model_version=dust_forecast_v0.1.0&since_days=30&min_samples=4
```

Returns a list of `DriftAlertSchema` (one per metric whose median crossed its threshold in the most recent half of the window). Empty list = no detected drift in the window.

---

## Key references (M.4 block)

- **[app/domain/evaluation_protocol.py](app/domain/evaluation_protocol.py)** — M.4.1 fields, hash, validation
- **[app/domain/model_performance.py](app/domain/model_performance.py)** — calibration bins, Brier, ECE, per_receptor, canary_metrics
- **[app/domain/drift_watch.py](app/domain/drift_watch.py)** — `compute_drift`, `DRIFT_THRESHOLDS`, `DriftAlert`
- **[app/schemas/drift.py](app/schemas/drift.py)** — `DriftAlertSchema`
- **[app/api/routes/drift.py](app/api/routes/drift.py)** — `GET /api/v1/drift`
- **[web/src/components/EvidenceChip.tsx](web/src/components/EvidenceChip.tsx)** — evidence-class chip
- **[web/src/components/CalibrationBadge.tsx](web/src/components/CalibrationBadge.tsx)** — calibration badge
- **[scripts/checks/validate-drift-discipline.js](scripts/checks/validate-drift-discipline.js)** — gate #21
- **[docs/anti-overfit-protocol.md](docs/anti-overfit-protocol.md)** — rules 8 + 9 (calibration + covariates)
- **[docs/safety-guardrails.md](docs/safety-guardrails.md)** — Goodhart-canary discipline + per-receptor fairness audit
- **[docs/bias-register.md](docs/bias-register.md)** — B-12, B-18, B-30, B-32, B-44 all flipped to Mitigated

## Earlier-phase references (still current)

- **[docs/causal-protocol.md](docs/causal-protocol.md)** — M.3.1 binding spec
- **[docs/anti-hindsight-protocol.md](docs/anti-hindsight-protocol.md)** — M.1 + M.2 contracts
- **[app/domain/causal_protocol.py](app/domain/causal_protocol.py)** — `EvidenceClass`, `SimulationMethod`, validators
- **[app/domain/pit_query.py](app/domain/pit_query.py)** — `sensor_readings_as_of`, `weather_readings_as_of`, `features_pre_intervention`
- **[scripts/migrate_pit_columns.py](scripts/migrate_pit_columns.py)** — M.2 PIT migration
- **[scripts/migrate_causal_columns.py](scripts/migrate_causal_columns.py)** — M.3 schema migration
