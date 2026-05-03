# Normalization Report

Current architectural state, classifications, risks, and active phase
plan for DustOps AI. This document is updated at the end of every
phase.

---

## Active phase

**Phase O.2 — Multi-mine SINCA survey + connector macro_id support (2026-05-03).**
Status: complete. Stands up multi-station PM10 coverage so Phase O proper (B-5 / B-6 / B-14 multi-station fairness + distribution-shift mitigation) becomes executable. Three new mine seeds (`data_seed/{los_bronces,chuquicamata,centinela}.yaml`) plus a corrected `los_bronces.yaml`. Discovered and fixed a SINCA-connector latent bug: stations have a public `station_code` (URL identifier) and a separate `macro_id` (data-gateway path identifier); the L.M.1 connector hardcoded `station_code` in the macro path, working only by accident on Cuncumén (where they happened to match). Two parameter encodings exist in the SINCA portal — legacy string `PM10` and numeric `0001`. `app.ingestion.public.sinca.build_url` gains optional `macro_id` and `param_code` parameters; the YAML schema gains optional per-sensor `sinca_macro_id` and `sinca_param_code` fields; the orchestrator threads them through. Five SINCA-public PM10 stations now ingested for the 12-month window 2025-05-03 → 2026-05-03 (Cuncumén 424, Las Condes 239, Calama 207 + 275, Sierra Gorda 255 — 4 mines, 2 regions, 36,413 records total). Three new connector tests assert (a) `macro_id` overrides station_code, (b) `param_code` overrides the legacy string, (c) defaults preserve Cuncumén behaviour. Risks introduced: SMA SEIA scrape (option 2A) is now unnecessary for the 4 highest-priority mines — only revisit if more stations are needed for Atacama-region work. Risks retired: single-station scope ceiling (multi-station fairness/drift work is now data-feasible).

**Phase O.1 — Equipment truck-geometry schema (2026-05-03).**
Status: complete. Adds the AP-42 unpaved-haul-road inputs to `equipment` so the eventual real forecast model can use the canonical `E = k * (s/12)^a * (W/3)^b` formulation. Four nullable columns: `empty_weight_tonnes`, `tire_contact_area_m2`, `tire_count`, `axle_count`. Mirrored on `EquipmentSchema` (Pydantic). Idempotent migration script `scripts/migrate_equipment_truck_geometry.py` ran successfully on dev DB. Tests added on the schema (legacy nullable round-trip + populated round-trip + negative-value rejection). New `docs/training-features.md` documents every variable a real model would consume, mapped to its column or noted as a remaining gap (multi-receptor PM10, real VKT, real silt samples, atmospheric stability class). `docs/data-contracts.md` Equipment row updated. **No domain logic touches the new columns yet** — feature-pipeline integration is intentionally deferred to whichever Phase first trains a real model on them; pure schema-only landing keeps O.1 reversible. Risks introduced: none. Risks retired: schema-gap flag from the project_training_features memory file (`empty_weight_tonnes` + `tire_contact_area_m2` + per-truck geometry no longer absent).

**Phase N — Drift-watch UI surfacing (2026-05-03).**
Status: complete. Surfaces M.4.3 detection in the operator dashboard. New `web/src/views/Drift.tsx` mounted at `/drift` consumes `GET /api/v1/drift` (existing endpoint, no backend touched). Defaults `model_version` to the most recent `modelPerformance()` row; user can switch via `<select>`. Window picker: 14 / 30 / 90 days. Polled at 60s. Per-row severity tier: yellow ≥ 1× threshold ("NOTICE"), red ≥ 2× threshold ("ACT"); card-level border tracks the worst tier present. Two distinct empty states: "No model_performance rows yet" (cannot compute) vs "No drift detected in window" (computed, clean). Detection-only — no approve/reject controls. Role-gated: visible to `environmental_manager` + `admin` only (Layout nav + RoleGate route guard); other roles redirected to `/control-room`. New web wire type `DriftAlertSchema`, new `api.driftAlerts(params)` client method. `docs/ui-principles.md` annex documents the role-restricted view. New vitest file `web/src/__tests__/drift.test.tsx` covers severity helper, version dedup, render states, window-switch refetch, and error handling. No new agent-check validator (existing `validate-drift-discipline.js` still passes; gate stays at 21/21). Risks introduced: none. Risks retired: none (B-12 already Mitigated by M.4.3 — UI is the operator-visibility piece).

**Phase M.4.3 — Drift watch (2026-05-03).**
Status: complete. Closes B-12 (concept drift / regime change) — the last open bias from the M.4 block. New `app/domain/drift_watch.py:compute_drift` splits `model_performance_metrics` rows for one `model_version` into baseline (oldest half) + recent (newest half) and emits one `DriftAlert` per metric whose median crosses the per-metric threshold in `DRIFT_THRESHOLDS`. Detection only — operational alerting and "most-recent-N-years" retraining are post-M / operator-side. New `GET /api/v1/drift?model_version=&since_days=&min_samples=`, auth-gated. New validator `validate-drift-discipline.js` (#21 in the agent-check gate) asserts module + schema + route + main mount + bias-register flip. **End of M.4 block: B-12, B-18, B-30, B-32, B-44 all Mitigated.**

**Phase M.4.2 — Per-receptor fairness audit + Goodhart canary discipline (2026-05-03).**
Status: complete. Closes B-32 (receptor-priority asymmetry) and B-44 (Goodhart on deployed metric). `metric_payload` gains `per_receptor` (same headline metrics split by `target_id`) and `canary_metrics` (every deployable KPI paired with a counter-metric whose drift reveals gaming). New `GOODHART_CANARY_PAIRS` constant in `app.domain.model_performance` is the canonical pair-set. `validate-overfit-discipline.js` enforces both blocks on M.4-tagged rows. `docs/safety-guardrails.md` adds Goodhart-canary discipline + per-receptor fairness audit sections; promotion-to-higher-automation rule now binding on canary acceptability.

**Phase M.3.2 — UI surfacing of M.3.1 causal fields + M.4.1 calibration (2026-05-03).**
Status: complete. Schemas threaded: `SourceAttributionSchema.evidence_class`, `RecommendationSchema.causal_confidence`, `InterventionSimulationSchema.{simulation_method, counterfactual_assumption, selection_bias_caveat}`. Web wire types updated; new `ModelPerformanceMetricSchema` exposed via `api.modelPerformance()`. Two new components: `EvidenceChip` (strong/weak tier with hover tooltip per evidence class) and `CalibrationBadge` (good/marginal/over tiers driven by `ece` vs protocol `max_ece`, with override reason surfaced in tooltip). Wired into ControlRoom (Likely-cause + Recommended-action cards) and Compliance (new Source-attributions + Model-calibration cards). `docs/ui-principles.md` adds rules for evidence-chip and calibration-badge.

**Phase M.4.1 — Calibration acceptance gate + covariate discipline (2026-05-03).**
Status: complete. Closes B-30 (confidence miscalibration) and B-18 (confounding) via anti-overfit rules 8 + 9. `EvaluationProtocol` now carries `feature_set`, `required_covariates`, `forbidden_covariates`, `max_ece` (default 0.05), `ece_override_reason`; `metric_payload` persists `calibration_bins[]` + `brier_score` + `ece`. ECE > max_ece raises `ProtocolViolation` unless an override reason is supplied (logged on the metric row). `protocol_hash` extended to include the new hashed fields; `protocol_version` bumped to "M.4". Validator `validate-overfit-discipline.js` enforces calibration + covariate fields on M.4-tagged rows; older rows tolerated.

**Phase K - Feedback, Reporting, ROI.**
Status: in progress. K.1 complete (2026-05-02). K.2 / K.3 / K.4 remain.

**Phase K.1 - S14 outcome-join + model performance metrics.**
Status: complete (2026-05-02). Closes the predicted-vs-actual loop in
storage and read-API form; powers the S15 reports landing in K.2.

K.1 changes (validation gate stayed at 15/15):
- **New ORM `ModelPerformanceMetric`** + repository + Pydantic schema
  per `data-contracts.md` lines 241-248. Append-only metric rows keyed
  by `(model_version, model_kind, evaluated_at)` with a JSON
  `metric_payload` carrying MAE / breach precision-recall /
  calibration / FPR / FNR / avoided-shutdowns estimate / production
  loss totals.
- **`app/domain/training_data.py`** implements S14 from
  `subsystem-contracts.md`: pure left-anchored join over
  `DustPrediction × Recommendation × RecommendationApproval ×
  ActionOutcome` returning `TrainingRecordSchema` rows. Predictions
  past the configured observation window with no outcome are emitted
  with `outcome_status="unobserved"` (S14 failure mode). Recommendation
  linkage uses `linked_prediction_ids` JSON list scan in Python; cheap
  because callers narrow the window before loading.
- **`app/domain/model_performance.py`** reduces a list of training
  records to the persisted `metric_payload`. Heuristics-first per
  CLAUDE.md rule 13. Avoided-shutdown count is conservative: only
  counts FP records where the operator approved/overrode (not
  rejected).
- **`GET /api/v1/training-data`** returns assembled records with
  `since_minutes`, `observation_window_minutes`, `model_version`,
  `outcome_status` filters. Auth-gated.
- **`GET /api/v1/model-performance`** lists recent persisted metric
  rows; `POST /api/v1/model-performance/evaluate` computes + persists
  one row over an explicit window. Evaluate is role-gated
  (environmental_manager / operations_manager / admin) because the
  row becomes part of the audit trail used for shadow-mode promotion.
- **Contract index** registers `PHASE_K` with `TrainingRecord` +
  `ModelPerformanceMetric`; repositories list adds
  `ModelPerformanceMetricRepository`. validate-contracts now checks
  25 entities + 20 repositories.
- **Smoke** adds two new auth-gated 401 assertions
  (`/training-data`, `/model-performance`); now 17 happy + 5
  auth-gated rejections.
- **23 new backend tests** across schemas / storage / domain /
  api; total backend tests 371 → 394.
- **Tactical fix to a pre-existing date-stale fixture in
  `tests/api/test_dust_events.py::test_get_events_filters_by_station`**
  — was using `2026-05-01T12:00:00+00:00` against the GET's default
  24h window, broken on 2026-05-02 onwards. Switched to
  `datetime.now(UTC) - 5min`. Out-of-scope but blocking the gate.

K.1 risks:

| ID | Severity | Summary | Resolution |
|---|---|---|---|
| K1-R1 | low | `Recommendation.linked_prediction_ids` is a JSON list scanned in Python; cardinality is currently fine (<200 rows per typical window) but won't scale once production load arrives | Promote to a join table or Postgres GIN index in K.3 |
| K1-R2 | low | `model_performance.evaluate` is fired manually via POST; no scheduled evaluation cadence | K.3 background scheduler will trigger nightly evaluation |
| K1-R3 | low | Avoided-shutdown estimate is correlation-only (not causal) | Documented in domain module; honest by-design |

**Phase J deslop pass.**
Status: complete (2026-05-01). Post-landing review identified that the
initial Phase J commit's TypeScript wire types were written from
speculation rather than read from `app/schemas/`, so every view used
wrong field names (e.g. `forecast.target.target_id` vs real
`forecast.target_id`; `recommendation.primary_action` vs real
`recommended_actions[0]`; `TokenResponse.user` which doesn't exist;
`Role` union missing `dispatcher` and using `env_manager` not
`environmental_manager`). The dashboard rendered fine on empty data but
would have crashed on first real payload.

Deslop changes (validation gate stayed at 15/15 throughout):
- **Backend addition:** `GET /api/v1/audit?since_minutes=&limit=&entity_type=&entity_id=`
  reads the canonical `audit_logs` table (`AuditLogRepository.get_recent`).
  Replaces the client-side synthesizer that fabricated audit IDs from
  `/approvals` + `/action-outcomes`. Auth-gated via `current_user`.
  New: `app/schemas/audit.py:AuditLogSchema`, `app/api/routes/audit.py`.
  Closes **J1-R1**.
- **Web types rewritten** (`web/src/api/types.ts`) field-by-field
  against the actual Pydantic schemas. All `Role`, `RiskClass`,
  `ProductionLossLabel`, `ForecastHorizon`, `ForecastSource`,
  `TargetKind`, `ApprovalStatus`, `SensorStatus`, `InterventionEffectiveness`,
  `DustEventSource`, `ZoneActivity`, `DustGenerationPotential`,
  `WindExposure` exposed as union types so consumers are statically
  checked.
- **Auth flow fixed** (`AuthContext.tsx`): `TokenResponse` carries
  `{access_token, token_type, expires_at, role}` with NO `user`
  payload, so `login()` now sets the token then calls `/auth/me` to
  populate the user. Mirrors the backend contract exactly.
- **Approve / reject / override request bodies fixed**
  (`ApproveRejectOverrideModal.tsx`, `client.ts`): approve sends
  `{chosen_action_rank, human_reason?}`, reject sends `{human_reason}`,
  override sends `{override_action, human_reason}`. The button gating
  switched from `risk_class !== 'low'` (re-derived policy) to the
  backend-supplied `requires_human_approval` flag (G1 source of
  truth).
- **All 4 views rewritten** to use real schema field names:
  ControlRoom (target_kind/target_id, predicted_pm10/25, risk_event,
  recommended_actions[0], rank, action, breach_probability_after,
  production_loss); Compliance (real audit endpoint, sensor health
  status/quality_score/issues); Operations + Executive (KPIs extracted
  to pure module).
- **`web/src/api/kpi.ts`** introduced as the single home for client-side
  aggregations (`operationsKpis`, `executiveKpis`, `complianceKpis`).
  Views now declarative — they call `useMemo(() => kpiFn(...), deps)`
  and render. Honors ui-principles "no business logic in components"
  to the extent possible until Phase K backend KPI endpoints land.
- **`useApi` hook deslopped:**
  - Dropped the dead `deps` parameter (every caller passed `[]`; the
    `fnRef` pattern already captures latest fn).
  - Split `loading` into `initialLoading` + `refreshing` so polling
    no longer flickers "Loading…" on every tick.
  - Short-circuits `setData` on byte-identical (`JSON.stringify`)
    payloads to avoid downstream rerenders on no-op poll cycles.
- **`Card` no longer duplicates** `STATUS_LABEL` — renders
  `<StatusPill>` directly. `StatusPill` exports the canonical
  `CardStatus` type and the `breachProbabilityToStatus` helper.
- **`ApproveRejectOverrideModal`** now validates first, then a single
  try/finally manages `busy` state.
- **Web validators** share a `scripts/lib/web.js` helper. Each
  validator is now ~5 lines (was ~30). `web-build.js` no longer
  re-runs `tsc` (web-typecheck owns that).
- **Dead code removed:** `web/src/hooks/usePolling.ts` (never imported),
  `web/tsconfig.node.json` (unused once the build script dropped
  the project-references step).
- **Tests:** 9 → 14 web tests (`kpi.test.ts` exercises every aggregator
  + edge cases; `components.test.tsx` adds `breachProbabilityToStatus`).

Risks closed by the deslop:
- **J1-R1 → CLOSED.** Real `/api/v1/audit` endpoint replaces client-side
  synthesis. Compliance audit table now reads canonical rows.

Phase J risks remaining (unchanged):
- **J1-R2** map uses synthetic grid (D3-R3 GeoJSON in K).
- **J1-R3** ROI placeholder (needs site_config.cost_curves + S14 join).
- **J1-R4** PM thresholds hardcoded to WHO defaults.
- **J1-R5** `web/node_modules` install time.

Phase J recommendation-shape mismatch was a single-shot lesson:
**TypeScript wire types must be read from the actual Pydantic schemas,
not authored speculatively.** Phase K backend additions will follow the
same discipline (e.g. add the wire type immediately when the schema
lands, not when the view is built).

**Phase J - Dashboard.**
Status: complete (2026-05-01). Shipped in a single landing.
- `web/` scaffold (Vite 5 + React 18 + TypeScript 5, strict): `package.json`,
  `tsconfig.json`, `vite.config.ts`, `index.html`, `.eslintrc.cjs`, `.gitignore`.
- Typed API client `web/src/api/{client,types}.ts` covering every Phase
  A-I `GET` endpoint plus `POST /auth/login`, `POST /recommendations/{id}/{approve,reject,override}`,
  `POST /action-outcomes`, `POST /approvals/sweep-expired`. Token persisted in
  `localStorage` and attached as `Authorization: Bearer` automatically.
- Auth: `web/src/auth/{AuthContext,LoginPage,ProtectedRoute}.tsx` enforce
  sign-in before any operational view renders; logout clears token.
- Layout shell + 4-view router (`web/src/views/Layout.tsx`,
  `web/src/App.tsx`): `/control-room`, `/compliance`, `/operations`,
  `/executive` per `docs/ui-principles.md` four-views requirement.
- Shared cards: `Card`, `ConfidenceBadge` (always visible per
  ui-principles "never hide confidence"), `StaleBadge`, `DataQualityWarning`,
  `StatusPill`, `ErrorBoundary` (per-card fault isolation per
  ui-principles map-card rule and Architecture rule 2).
- Control-room view: forecast card, likely-cause card (top probable
  sources from S7), recommended-action card with approve/reject/override
  modals wired to S13 (`POST /recommendations/{id}/{approve,reject,override}`),
  inline mine map (SVG, wind direction, per-zone risk color, click target
  for D3-R3 future drill-in), sensor health strip, recent dust events.
  Approve button is **disabled when `risk_class != 'low'`** to honor
  G1/G13 — operator must override or reject for medium/high risk.
- Environmental compliance view: PM rolling averages against WHO
  defaults (`compliance-context.md`), full sensor health table, event
  list, audit trail backed by `/approvals` + `/action-outcomes` joined
  client-side (server-side `/audit-logs` endpoint deferred to K with
  Postgres swap).
- Operations view: cumulative tonnes-delayed, effectiveness-weighted
  tonnes-protected estimate, shutdowns-avoided counter (= approved
  count), ROI deferred-to-K placeholder.
- Executive view: rolling downtime-avoided (approve+override count),
  compliance incidents avoided proxy, average effectiveness from S14
  outcomes feed.
- `agent-check` extended with **4 web validators**: `web-typecheck`
  (`tsc --noEmit` strict), `web-lint` (eslint flat-extends config),
  `web-test` (vitest, 9 tests across api client + shared components),
  `web-build` (`tsc` + `vite build`). Each self-skips with a clear
  message if `web/node_modules` is missing, so `npm run agent-check`
  remains usable without a node_modules install.
- `docker-compose.yml` gains a `web` service (node:20-alpine, dev
  profile only) wired to the api service.
- Smoke unchanged at 17 happy-path endpoints + 3 auth-gated rejections;
  Phase J is read-only against existing endpoints, no new backend
  surface.
- `validate-safety` unchanged at 11 schemas; UI does not introduce
  Pydantic schemas. `validate-boundaries` still scans 88 Python files
  in 5 directories (web/ outside its scope).
- Validation: `npm run agent-check` → **15 PASS / 0 SKIP / 0 FAIL**
  (was 11 PASS at end of Phase I; +4 web validators).

Open risks introduced in Phase J:
- **J1-R1 (low):** Audit trail card composes `/approvals` +
  `/action-outcomes` client-side rather than reading `audit_logs`
  directly. Server-side `/audit-logs` endpoint lands in K alongside
  the Postgres swap (D3-R2). Mitigation: client composition is
  display-only; the canonical record stays in `audit_logs`.
- **J1-R2 (low):** Mine map uses a synthetic grid layout (no GeoJSON)
  pending D3-R3 terrain-aware geometry. Wind direction arrow and
  per-zone color render correctly; spatial accuracy lands with the
  GeoJSON contract.
- **J1-R3 (low):** ROI card is a placeholder. Real ROI requires
  `site_config.cost_curves` (G3-R1) and predicted-vs-actual join
  (S14, Phase K).
- **J1-R4 (low):** PM threshold defaults hardcoded to WHO 24h values
  in the Compliance view; should read from `site_config` per R2 once
  the per-site override schema is consumer-aware.
- **J1-R5 (low):** `web/node_modules` size; CI-style installs add
  setup time. Mitigation: validators self-skip cleanly when not
  installed, so the gate stays usable.

Closed during Phase J:
- None. Phase J is purely additive.

Phase I read-side endpoints (I1-R1) remain open and unchanged — the
dashboard intentionally consumes them anonymously in MVP per the
documented K hardening pass.

**Phase I - Human Approval Workflow.**
Status: complete (2026-05-01). All five sub-steps shipped.
- I.1: Auth foundation. `User` ORM/repo, `LoginRequest`/`TokenResponse`/
  `UserSchema`, `app/domain/auth.py` (PBKDF2-HMAC-SHA256 password
  hashing + HMAC-signed bearer tokens, stdlib only - no new deps).
  `current_user` + `require_role(*roles)` deps in
  `app/api/dependencies/auth.py`. `POST /auth/login` and `GET /auth/me`
  endpoints. 330 tests.
- I.2: Approval + audit storage. `RecommendationApproval` and
  `AuditLog` ORMs/repos per data-contracts.md lines 207-217 and
  264-270. `RecommendationApprovalSchema` carries the
  Recommendation-prefix safety triple (`confidence`/`reason`/
  `model_version` copied for audit at decision time) so
  `validate-safety` admits it. `app/audit/__init__.py` stub replaced
  with `app/audit/writer.py` (`record(actor, action, entity_type,
  entity_id, payload)`). 338 tests; 8 safety schemas tracked.
- I.3: S13 domain + endpoints + auth gating.
  `app/domain/approvals.py:approve_recommendation /
  reject_recommendation / override_recommendation / sweep_expired /
  latest_for_recommendation` enforces G1 (medium/high `risk_class`
  blocks the approve path), G8 (every decision persisted - including
  `expired`), G9 (override captures who/when/what/why), G13 (high
  `risk_class` cannot auto-execute - HighRiskAutoExecutionError).
  Lazy expiry: `now >= rec.issued_at + approval_expiry_minutes`
  records an `expired` row instead of accepting; manual sweep
  endpoint covers undecided pending recs (F1-R1 scheduler still
  open). `POST /recommendations/{id}/approve|reject|override`,
  `GET /recommendations/{id}/approval`, `GET /approvals`,
  admin-only `POST /approvals/sweep-expired`. Auth dep wired onto
  16 mutating handlers across 11 routers (closes write-side of
  D2-R1 / E4-R2 / F4-R1 / G4-R1 / H1-R1). `SiteConfig` gains
  `approval_expiry_minutes` (default 15). Touches a safety-reviewer
  trigger path (`app/domain/approvals/` is new + `app/audit/`).
  361 tests.
- I.4: Outcome capture / S14 feeder. `ActionOutcome` ORM/schema/repo,
  `app/domain/outcomes.py:record_outcome` (audit-logged, validates
  recommendation_id and prediction_id when supplied),
  `POST /api/v1/action-outcomes` (env_manager / ops_manager / admin),
  GET listing + per-recommendation history. Phase K's full
  predicted-vs-actual join (S14) reads these rows. 371 tests.
- I.5: Validation, smoke promotion, phase advance. `validate-safety`
  extended with two new patterns (`*ApprovalSchema` requires
  `approval_status`/`approved_by`/`decided_at`; `*ActionOutcome*`
  requires `intervention_effectiveness`); 11 safety-relevant schemas
  tracked. Contract index PHASE_I adds User /
  RecommendationApproval / ActionOutcome entities + four new
  repositories. Smoke now asserts 17 happy-path endpoints AND that
  3 auth-gated endpoints reject anonymous callers (`GET /auth/me`,
  `GET /action-outcomes`, `POST /auth/login` with unknown user).

**Phase H - Recommendation Engine.**
Status: complete (2026-05-01). All four sub-steps shipped.
- H.1: `RecommendationSchema` + `RecommendationActionSchema` per
  `data-contracts.md` line 190-205. Per-action fields carry G1
  `requires_human_approval`, G3 `reason`, per-action `confidence`.
  Wrapper carries G2 `confidence`, G3 `reason`,
  G6 `requires_human_review`, G7 `compliance_priority_triggered`,
  G15 `model_version` + `feature_pipeline_version` +
  `input_data_quality_score` + `linked_prediction_ids` +
  `linked_attribution_id`. ORM is append-only (G8) with
  `REC-YYYYMMDD-NNNNN` IDs. `validate-safety` flipped from 4 -> 6
  schemas tracked - the Recommendation* classes activate the
  strictest pattern (`confidence` + `reason` + `model_version`)
  and have all three. PHASE_H added to contract index. 289 tests.
- H.2: `optimization_weighted_v0.1.0` in
  `app/models/optimization/heuristic_baseline.py`. Score per
  candidate = `w_breach * breach_drop -
  w_production * (tonnes/1000) - w_disruption * (cycle_pct/100) -
  w_low_confidence_penalty + w_compliance * breach_drop` (last
  term active under extreme regime only). G7 three regimes
  pinned in tests: `< 0.5` balanced, `0.5 - 0.85` w_production
  x 0.7, `>= 0.85` w_production x 0.3 + w_compliance x 2.0
  AND `compliance_priority_triggered = true`, overall confidence
  capped at 0.85. G6 `requires_human_review = true` when no
  candidate clears the low-confidence threshold. Pure function
  per universal model rule 5. `RankedRecommendations` schema is
  internal (not Recommendation-named, so safety scanner skips
  it - persistence happens via `RecommendationSchema` in H.3).
  298 tests.
- H.3: `app/domain/recommendations.py:generate_recommendation`.
  Resolves Zone -> Mine -> SiteConfig (via `require_resolved` -
  D-R2 fail-loud), pulls latest forecast (zone-targeted first;
  sensor-in-zone fallback), filters S8 catalog by
  `Zone.zone_type` against each entry's `allowed_zone_types`,
  runs `simulate_intervention(...)` for every eligible entry plus
  `simulate_do_nothing(...)` for the counterfactual baseline,
  registers + invokes the optimization engine, applies G6
  high-risk gating (medium/high `risk_class` actions dropped
  from surfaced ranking when `requires_human_review`), best-
  effort matches the latest `SourceAttribution` for the same
  `target_id` to populate `linked_attribution_id`, renders the
  S12 six-line template into `recommendation.reason`, persists.
  Touches a safety-reviewer trigger path
  (`app/domain/recommendations/`); the subagent should run before
  any future change here per `safety-guardrails.md`. 316 tests.
- H.4: API + smoke promotion + phase advance.
  `GET /api/v1/recommendations/current` (compute-on-read, smoke
  happy path under empty world returns null, single-zone
  defaults to that zone), `POST /api/v1/recommendations` (issue
  for an explicit zone), `GET /api/v1/recommendations/{id}`,
  `GET /api/v1/recommendations` (recent history). Smoke promoted
  to 17 endpoints (was 15: `/recommendations/current` graduates
  from PENDING + `/recommendations` history added). PENDING list
  now empty. `.progress_state.json` advanced to
  `current_phase=I`. 317 tests.

Open risks introduced in Phase H:
- H1-R1 (low): recommendation endpoints unauthenticated; same
  posture as forecast/attribution/simulation endpoints, deferred
  to Phase I.
- H2-R1 (medium-latent): optimizer weights uncalibrated; the
  default `OptimizationWeightsSchema` is a placeholder. Revisit
  in Phase K alongside D3-R1 / E2-R1 / F3-R2 / G2-R1 / G3-R1.
- H3-R1 (low): orchestrator simulates every applicable catalog
  entry per request - O(catalog x forecast). Fine at MVP scale;
  J perf pass will cache per-(zone, forecast) tuple.
- H3-R2 (low): single forecast per recommendation; horizon
  ensemble deferred to J/K.
- H3-R3 (low): attribution link is a best-effort match by
  `target_id` against recent attributions; a sensor-targeted
  forecast on a zone with multiple attributions could pick a
  stale attribution. Tighten when the dashboard surfaces
  attribution staleness in J.

Closed during Phase H:
- **G3-R2** (default effective duration is rule-of-thumb): the
  recommendation orchestrator does not pass an explicit duration;
  the rule-of-thumb default is preserved AS the documented
  behavior at MVP. (Marked closed to acknowledge it's now an
  intentional design choice, not a deferred risk.)

**Phase G - Intervention Simulation.**
Status: complete (2026-05-01). All four sub-steps shipped.
- G.1: Intervention library (S8). `InterventionOptionSchema` per
  `data-contracts.md` line 167-174 (`risk_class`,
  `requires_human_approval`, `automation_eligible_levels`,
  `estimated_time_to_effect_minutes`, `allowed_zone_types`).
  `InterventionOption` ORM and `InterventionOptionRepository` with
  upsert + `known_ids`. `app/domain/interventions.py` ships a
  conservative 7-row default catalog (increase_monitoring,
  raise_alert, water_road, reduce_speed, reroute_trucks,
  throttle_crusher, pause_loading) and a `seed_default_interventions`
  helper that lazy-seeds on first read and never overwrites operator
  edits. Per Guardrails 13/14, every medium/high-risk default ships
  with `requires_human_approval=True` and
  `automation_eligible_levels=[]`; a unit test pins this invariant.
  `GET /api/v1/interventions`, `GET /.../{id}`, `POST /api/v1/interventions`.
  `app/api/routes/zones.py` upsert now calls
  `require_known(...)` against the catalog for both
  `allowed_interventions` and `requires_approval_for`, surfacing
  unknown IDs as 400 - this **closes D2-R2**. `PHASE_G` block added
  to `scripts/lib/contract_index.js` (InterventionOption +
  InterventionOptionRepository). Smoke promoted to 14 endpoints.
  240 tests.
- G.2: `InterventionImpactModel` heuristic (S9). Schemas in
  `app/schemas/simulations.py` (`InterventionImpactSchema`,
  `ProductionCostEstimateSchema`, `InterventionSimulationSchema`);
  the Simulation-named class brings `validate-safety` to 4 tracked
  schemas (was 3). `app/models/intervention/heuristic_baseline.py`
  ships `intervention_impact_heuristic_v0.1.0` with per-intervention
  reduction fractions (water 35%, reduce_speed 20%, reroute 50%,
  throttle 40%, pause_loading 60%), risk-class confidence penalty,
  PM2.5 proportional reduction at 0.85 ratio, and a do-nothing
  branch. Pure function per universal model rule 5. 253 tests.
- G.3: `ProductionCostModel` heuristic (S10).
  `app/models/cost/heuristic_baseline.py` ships
  `production_cost_heuristic_v0.1.0`. Tonnes delayed =
  `production_rate_tph * effective_duration_hr * loss_fraction`;
  effective duration defaults to 2x time-to-effect (capped 60min)
  but a caller-supplied `duration_minutes` overrides. Unknown
  production rate degrades confidence rather than fabricating
  tonnes. 260 tests.
- G.4: Orchestrator + ORM + API + persistence + phase advance.
  `app/storage/models/simulations.py` and matching repository
  (`SIM-YYYYMMDD-NNNN` IDs resetting per UTC day, append-only).
  `app/domain/simulation.py:simulate_intervention` resolves the
  intervention from the catalog, finds the latest forecast for the
  zone (zone-targeted first, sensor-targeted fallback for sensors
  in that zone), reads `production_rate_tph` from the latest
  MineState snapshot, calls both heuristic models, joins (joined
  confidence = min of impact/cost confidences), persists.
  `simulate_do_nothing` is the counterfactual baseline using the
  reserved `_do_nothing_` intervention shape. Lazy-registers both
  models on first call (same pattern as forecasting / attribution).
  `POST /api/v1/simulations/intervention`,
  `POST /api/v1/simulations/do-nothing`,
  `GET /api/v1/simulations` (smoke happy path).
  Smoke promoted to 15 endpoints. PHASE_G index extended with
  `InterventionSimulation` + repo. `.progress_state.json` advanced
  to `current_phase=H`. 278 tests.

Open risks introduced in Phase G:
- G2-R1 (medium-latent): intervention impact reduction fractions
  are uncalibrated; revisit with D3-R1 / E2-R1 / F3-R2 in Phase K.
- G3-R1 (low): cost coefficients uncalibrated and financial
  conversion deferred until `site_config.cost_curves` lands.
- G3-R2 (low): default effective duration = 2x time-to-effect
  is a rule of thumb; a real intervention plan will pass an
  explicit duration.
- G4-R1 (low): simulation endpoints unauthenticated; same posture
  as forecast / attribution endpoints, deferred to Phase I.
- G4-R2 (low): zone-target forecast lookup is a most-recent
  scan; a forecast aged out beyond 60min will still be used.
  Tighten when the dashboard surfaces forecast staleness in J.

Closed during Phase G:
- D2-R2 (zone `allowed_interventions` / `requires_approval_for`
  IDs) - validated against the catalog at zone upsert.
- D-R3 partial: `intervention_constraints` shape itself remains
  free-JSON, but the IDs that key it are now validated whenever
  the recommendation engine looks them up via `require_known`.
  Full schema enforcement deferred to H/J when the consumers land.

**Phase F - Source Attribution.**
Status: complete (2026-05-01). All four sub-steps shipped.
- F.1: `dust_events` ORM/schema/repo + creation paths.
  `DustEventCreate` / `DustEventSchema` (with `event_source` enum:
  model_alert / manual_entry / threshold_trigger);
  `DustEventRepository` with `EVT-YYYYMMDD-NNN` IDs resetting per
  UTC day. `app/domain/dust_events.py` exposes
  `record_manual_event` (G12 operator entry) and
  `trigger_events_from_forecasts` (sensor-targeted-only sweep over
  recent `DustPrediction` rows above the configurable
  `breach_threshold`, idempotent per (sensor, UTC day) -
  re-crossing forecasts append to `linked_prediction_ids` rather
  than spawning duplicates). `POST /api/v1/dust-events`,
  `GET /api/v1/dust-events`, `GET /.../{event_id}`,
  `POST /.../from-forecast`. 186 tests.
- F.2: `SourceAttribution` schema/ORM/repo. `ProbableSource` +
  `SourceAttributionSchema` with overall `confidence`,
  `model_version`, and an `evidence_fields` dict for reviewer
  reconstruction. `SourceAttribution` ORM matching
  `data-contracts.md` line 159-166 (append-only, keyed on
  `dust_event_id` so re-running attribution preserves history).
  `SourceAttributionRepository` with `ATTR-YYYYMMDD-NNN` IDs.
  `validate-safety` now tracks 3 schemas (DustForecast,
  ForecastTarget, SourceAttribution). 194 tests.
- F.3: Rule-based attribution model + orchestrator.
  `app/models/attribution/rules_baseline.py` implementing
  `SourceAttributionModel` per `model-contracts.md` -
  `source_attribution_rules_v0.1.0` combining wind-aligned spatial
  proximity, activity-time / spike-time correlation, and source
  baseline dust potential into ranked `probable_sources` with
  per-source confidence + reason. `external_background` floor
  always present so the regional-baseline lane stays visible.
  Empty / collapsed-score paths return a single `Unknown` entry
  per the S7 failure mode. `app/domain/attribution.py:attribute_event`
  composes the candidate list (every zone in the affected
  station's mine) with measured inputs - 30-min activity
  intensity, station PM10 rise ratio, latest weather wind
  direction (terrain-aware bearing deferred to D3-R3). Each
  call lands a new attribution row keyed on `dust_event_id` so
  history is preserved. 209 tests.
- F.4: API + smoke + contract index. `POST /api/v1/attributions/for-event/{event_id}`
  (compute-on-read with persist), `GET /.../for-event/{event_id}`
  (latest), `GET /.../for-event/{event_id}/history`,
  `GET /api/v1/attributions` (recent, smoke happy path).
  Promoted both `dust-events` and `attributions` to REQUIRED in
  smoke (13 endpoints, was 11). `PHASE_F` block added to
  `scripts/lib/contract_index.js` (DustEvent, SourceAttribution +
  DustEventRepository, SourceAttributionRepository). Phase
  advanced to G. 217 tests.

Open risks introduced in Phase F:
- F1-R1 (low): threshold-trigger sweep is manual-call only;
  background scheduling waits for Phase K.
- F2-R1 (low): `evidence_fields` JSON shape unenforced; tighten
  if a downstream consumer depends on specific keys.
- F3-R1 (low): `_wind_angle_offset` returns 0 when wind data
  exists (no terrain-aware bearing yet, D3-R3); the rule still
  ranks correctly via the other two signals but per-source
  proximity is uniform until GeoJSON lands.
- F3-R2 (medium-latent): rule coefficients (proximity weight,
  factor table, score formula) are uncalibrated; revisit alongside
  D3-R1 / E2-R1 when ground truth is available in K.
- F4-R1 (low): attribution endpoints unauthenticated; same posture
  as forecast / admin endpoints, deferred to Phase I.

Closed during Phase F: none of the prior risks fully closed.

`validate-safety` tracks 3 safety-relevant schemas with all
required guardrail fields present. `validate-boundaries` clean
across 54 Python files in 5 layered directories.

**Phase E - Forecasting MVP.**
Status: complete (2026-05-01). All four sub-steps shipped.
- E.1: S5 feature pipeline. `FeatureRecordSchema`, `FeatureRecord`
  ORM, `FeatureRepository`, `app/domain/features.py:build_feature_record`
  emitting under `feature_pipeline_v0.1.0`. Payload namespaces:
  `pm.*`, `wind.*`, `activity.*`, `state.*`, `meta.*`. Builder
  enforces leakage guard (readings strictly older than `as_of`) and
  propagates upstream staleness into `missing_inputs` without
  fabricating values (G5). 130 tests.
- E.2: Model registry + heuristic forecast baseline.
  `app/models/` namespace introduced as a Domain peer (must not
  import `app.api.*` or `app.storage.*`; rule added to
  `validate-boundaries.js`). `app/models/registry.py` with
  register / set_current / get_current / list_versions /
  reset (test isolation). `dust_forecast_heuristic_v0.1.0`
  (PM trend projection x dryness/wind dust factor x smooth breach
  ramp; raw confidence scaled by `input_data_quality_score` per G4;
  fallback path on missing PM features per G11 with
  `source = "heuristic_fallback"`). `DustForecastSchema` lands in
  `app/schemas/forecasts.py` carrying every guardrail-mandated
  field (G2/G5/G11/G15). 149 tests; `validate-safety` activates
  (no longer vacuously green).
- E.3: Persistence + orchestration. `DustPrediction` ORM matching
  `data-contracts.md` line 131-148, `DustPredictionRepository`
  (latest_for_target / get_recent / next_prediction_id with
  `PRED-YYYYMMDD-NNNN` format resetting per UTC day),
  `app/domain/forecasting.py:issue_forecast` composing the full
  pipeline (S4 -> S2 quality multiplier -> S5 -> registry -> S6 ->
  audit write). Sensor-target resolution falls through to the
  sensor's zone for feature build while keeping the forecast
  keyed on the sensor identity. Tightened
  `scripts/checks/validate-safety.js` to its documented Pydantic
  schema scope (`app/schemas/`); had been over-matching repo and
  exception classes whose names contained Forecast/Prediction. 159
  tests.
- E.4: API + smoke + contract index. `GET /api/v1/forecasts/current`
  (compute-on-read with persist; defaults to single-zone happy
  path; returns null on empty DB so smoke can pass before data
  loads) and `GET /api/v1/forecasts/history`. Promoted
  `forecasts/current` to REQUIRED in smoke. `PHASE_E` block added
  to `scripts/lib/contract_index.js` (FeatureRecord, DustForecast,
  DustPrediction + FeatureRepository, DustPredictionRepository).
  Phase advanced to F. 167 tests.

Within-phase note: per the approved plan, E.2 was scoped to
"registry + heuristic" and E.3 to "DustForecastSchema + ORM/repo +
orchestrator", but the heuristic's return type is the schema, so
the schema landed at E.2 (its natural pair) and E.3 carried only
ORM/repo/orchestrator. No new requirements introduced.

Closed during Phase E:
- (no Phase D risk fully closed; D3-R1 still open until calibration
  data lands in K)

Open risks introduced in Phase E:
- E1-R1 (low): leakage guard at builder is single-point; trust
  remains on caller-supplied `as_of`. Resolution: Phase K offline
  evaluation harness will sweep historical data and assert on it.
- E2-R1 (medium-latent): heuristic forecast uncalibrated. Tracked
  alongside D3-R1; resolution stays Phase K.
- E2-R2 (low): registry is process-global. Test isolation handled
  via `reset()`; production path bootstraps once at startup. Re-
  visit only if multi-tenant deployment surfaces.
- E3-R1 (low): `DustPrediction.input_data_quality_score` rounded
  to 3 decimals on persist; fine for audit, may need raw on
  Phase K reanalysis.
- E4-R1 (low): forecast endpoint compute-on-read can be expensive
  with many zones. Caching deferred to Phase J performance pass.
- E4-R2 (low): forecast endpoints unauthenticated. Same posture as
  D2-R1; deferred to Phase I.

`validate-safety` activated: 2 schemas tracked (DustForecastSchema,
ForecastTargetSchema), all required guardrail fields present.
`validate-boundaries` now scans 5 layered directories including
the new `app/models/` peer.

**Phase D - Mine State Engine.**
Status: complete (2026-05-01). All four sub-steps shipped.
- D.1: S3 site config storage + admin endpoints + 3-tier resolver.
- D.2: Mine map admin (zones + haul road segments) + strict
  `require_resolved` wrapper closing D-R2.
- D.3: S4 compute layer - `MineStateSnapshot` ORM/schema/repo +
  `app/domain/mine_state.py:compute_zone_state(...)` heuristic engine
  (activity summary, dust generation potential, wind exposure,
  downwind asset detection, staleness flags). 110 tests.
- D.4: S4 API surface - `GET /api/v1/mine-state/current` and
  `/zones/{zone_id}` with compute-on-read + persist via
  `MineStateSnapshotRepository`. `mine_state.current` promoted from
  PENDING to REQUIRED in smoke. Phase advanced to E. 117 tests.
- D.1: S3 site configuration storage + admin endpoints. `SiteConfiguration`
  ORM + `SiteConfigSchema` (with typed `OptimizationWeightsSchema`) +
  `SiteConfigRepository` (get / get_for_mine / upsert) +
  `app/domain/site_config_resolver.py` (3-tier resolution: site_config ->
  mine_defaults -> schema_defaults) + `GET/POST /api/v1/site-config` and
  `GET /api/v1/site-config/{site_id}` (synthetic `default-<mine_id>` ids
  trigger fallback resolution). Router mounted in `app/api/main.py`;
  `/site-config` added to smoke `REQUIRED_ENDPOINTS`. Bug fixed inline:
  `intervention_constraints` `None` -> `{}` coercion via field_validator
  (SQLAlchemy `default=dict` only fires at flush; unflushed reads exposed
  `None`). agent-check: 11 PASS / 0 SKIP / 0 FAIL. New risks D-R1..D-R3
  (see Risks below).

**Phase C - Data Harness.**
Status: complete (2026-05-01). All four sub-steps shipped.
- C.1: repository layer + `ingest_errors` table (G10).
- C.2: ingestion endpoints (single + batch + GET) for sensor /
  weather / equipment, with validation failures persisted to
  `ingest_errors` before the 422 response.
- C.3: reproducible mock stream generators + real `seed_mock_data.py`
  CLI; `mock_mode` flag exposed on `/api/v1/meta`.
- C.4: S2 data-quality scoring (`SensorHealthScorer` heuristics) +
  `GET /api/v1/data-quality[/{sensor_id}]`. Smoke now asserts the
  data-quality endpoint as required.

**Phase B - Repo Scaffold.**
Status: complete (2026-05-01). All five sub-steps shipped; 11 of 11
agent-check validators pass automatically.

- B.1: agent-check harness.
- B.2: Python tooling + backend skeleton + git init.
- B.3: FastAPI app + `/api/v1/health` + `/api/v1/meta` + smoke check.
- B.4: Pydantic schemas + SQLAlchemy models for static spatial +
  raw-readings entities + `validate-contracts`.
- B.5: `validate-boundaries`, `validate-safety`, `review-diff`,
  `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `seed_mock_data.py`
  stub.

**Phase A - Architecture Constitution.**
Status: complete (approved 2026-04-30; auto-validated continuously).

---

## Phase plan

| Phase | Title                          | Status      |
|-------|--------------------------------|-------------|
| A     | Architecture Constitution      | complete    |
| B     | Repo Scaffold                  | complete    |
| C     | Data Harness                   | complete    |
| D     | Mine State Engine              | complete    |
| E     | Forecasting MVP                | pending (next) |
| F     | Source Attribution             | pending     |
| G     | Intervention Simulation        | pending     |
| H     | Recommendation Engine          | pending     |
| I     | Human Approval Workflow        | pending     |
| J     | Dashboard                      | complete    |
| K     | Feedback, Reporting, ROI       | pending (next) |

No phase begins before the previous one is validated and approved.
Full deliverables per phase are in `PLAN.md`.

---

## Current code classification

There is no application code yet. Phase A produces only governance
docs and operational tooling.

| Path                            | Classification | Notes |
|---------------------------------|----------------|-------|
| `CLAUDE.md`                     | KEEP           | Permanent constitution. |
| `PLAN.md`                       | KEEP           | Master plan; updated at phase boundaries. |
| `README.md`                     | KEEP           | Entry point. |
| `progress.py`                   | KEEP           | Daily tracker. |
| `ops/rollback.py`               | KEEP           | Bridges the gap until git lands in Phase B. |
| `docs/*.md`                     | KEEP           | Source of truth for architecture / contracts. |
| `package.json`                  | KEEP           | Minimal; declares `npm run agent-check`. Will gain real deps in B.2+ as scaffold lands. |
| `scripts/agent-check.js`        | KEEP           | Phase-aware orchestrator. Extended (not rewritten) as new validators land. |
| `scripts/lib/runner.js`         | KEEP           | No-deps helper for spawn + ANSI output. |
| `scripts/checks/validate-phase-a-docs.js` | KEEP | Permanent: Phase A docs stay valid forever. |
| `scripts/checks/validate-progress.js`     | KEEP | Tooling smoke. |
| `scripts/checks/validate-rollback.js`     | KEEP | Tooling smoke. |
| `.progress_state.json`          | KEEP           | Phase state file; consumed by `progress.py` and `agent-check.js`. |
| `.gitignore`                    | KEEP           | Python/Node/IDE/OS plus local state (`.rollback/`, `.progress_state.json`, `.venv/`). |
| `pyproject.toml`                | KEEP           | Package metadata; ruff/mypy/pytest config; runtime + dev deps. |
| `app/**/__init__.py`            | KEEP           | Layered package skeleton; matches `docs/architecture.md`. |
| `app/api/main.py`               | KEEP           | FastAPI app factory; routes mounted under `/api/v1`. |
| `app/api/__init__.py`           | KEEP           | Holds `API_VERSION` / `API_PREFIX`; depended on by both `main.py` and route modules to avoid circular import. |
| `app/api/routes/health.py`      | KEEP           | `/api/v1/health` -> `{"status": "ok"}`. |
| `app/api/routes/meta.py`        | KEEP           | `/api/v1/meta` -> identity + phase state from `.progress_state.json`. |
| `scripts/_smoke.py`             | KEEP           | TestClient-based smoke runner. New endpoints get added to `REQUIRED_ENDPOINTS` as their sub-steps land. |
| `scripts/checks/smoke.js`       | KEEP           | Wraps `scripts/_smoke.py`. |
| `app/schemas/{mine,sensor,weather,equipment}.py` | KEEP | Pydantic schemas for the 8 raw-readings + static entities. New schemas land in subsequent phases (forecast in E, attribution in F, recommendation in H, etc.). |
| `app/storage/database.py`       | KEEP           | Engine + session factory; consumed by repositories (B.5+). |
| `app/storage/models/{base,mine,readings}.py` | KEEP | SQLAlchemy ORM. Mirrors the schemas; do not let either drift without updating both. |
| `app/storage/repositories/`     | KEEP           | Empty package; concrete repositories arrive in Phase C. |
| `scripts/lib/contract_index.js` | KEEP           | Source of truth for what `validate-contracts` enforces. Append entries here when adding a new contract. |
| `scripts/checks/{validate-boundaries,validate-safety,review-diff}.js` | KEEP | Static scanners. Each is small and focused; extend in place rather than forking. |
| `Dockerfile`                    | KEEP           | Backend image; rebuilds when pyproject changes. |
| `docker-compose.yml`            | KEEP           | api-only today; db service lands when Postgres replaces SQLite (likely Phase C). |
| `.dockerignore`                 | KEEP           | Keeps test/docs/local-state out of the image. |
| `scripts/seed_mock_data.py`     | WRAP           | CLI stub today; Phase C wraps the real generator behind the same args. |
| `app/config/settings.py`        | WRAP           | Empty `Settings` class; fields appended as features arrive. |
| `tests/test_skeleton.py`        | KEEP           | Import + placeholder-constant tests; runs under strict mypy. |
| `scripts/checks/lint.js`        | KEEP           | Wraps `ruff check`. |
| `scripts/checks/typecheck.js`   | KEEP           | Wraps `mypy` (strict). |
| `scripts/checks/test.js`        | KEEP           | Wraps `pytest`. |
| `scripts/lib/python.js`         | KEEP           | Resolves `.venv` python; honors `DUSTOPS_PYTHON`. |

No KEEP-LATER, REFACTOR, ISOLATE, REMOVE LATER, or DEFER classifications
exist yet.

---

## Risks (open)

### Phase I additions

- **I1-R1 (medium):** Read-side endpoints stay open in MVP; only
  mutating handlers (16 across 11 routers + the new approval/outcome
  endpoints) are gated. Documented intentional gap; closes in K
  hardening pass alongside D3-R2 Postgres swap.
- **I2-R1 (low):** JWT-style token signing key rotates on process
  restart in dev (`secrets.token_hex(32)` fallback when
  `DUSTOPS_AUTH_SECRET` is unset). Acceptable at MVP; rotation /
  JWKS endpoint deferred to K.
- **I3-R1 (low):** Approval expiry is lazy (fires on next decision
  attempt) plus a manual sweep endpoint. F1-R1 already tracks the
  background-scheduler gap.
- **I3-R2 (low):** `override_action` is free-text per data contract;
  not validated against the S8 catalog. Tighten if a downstream
  consumer depends on it.
- **I4-R1 (medium-latent):** Outcome capture is manual entry only;
  no telemetry-driven auto-fill. S14 (Phase K) closes via
  prediction-vs-actual join.
- **I5-R1 (low):** `audit_logs` table grows unbounded on SQLite.
  Acceptable on MVP; partition / rollover when D3-R2 (Postgres swap)
  lands.

### Phase I closures (write-side)

- **D2-R1 / E4-R2 / F4-R1 / G4-R1 / H1-R1** all reduce to "read-side
  open" once Phase I.3 lands. The cluster is now I1-R1 (single
  open risk against read paths).
- **G3-R2** (default effective duration is rule of thumb) - reclassified
  in H to "intentional MVP design" and remains so.

### D-R1 - In-flight site_config files were edited without a prior snapshot
Severity: medium -> CLOSED (2026-05-01).
The site_config slice (5 app files + 3 test files + 2 modified files)
was created in the working tree before any rollback snapshot was taken,
violating architect_protocol.md step 6. Closed at D.1 start by capturing
`phase-d1-site-config` listing all 8 created files + 2 modified files,
then taking `phase-d1-site-config-routed` after the router/smoke edits.
Process note for future phases: snapshot before edits, not after.

### D-R2 - Resolver `schema_defaults` fallback could mask missing site config
Severity: medium -> CLOSED (2026-05-01).
Closed by D.2: `app/domain/site_config_resolver.py` now exports
`MissingSiteConfigError` + `require_resolved(...)`, which raises when
the underlying resolution would fall back to `schema_defaults`.
Permissive `resolve(...)` remains for read endpoints. Automation-
impacting consumers (S4 in D.3, S11 in H, S13 in I) MUST call
`require_resolved`.

### D-R3 - `intervention_constraints` JSON shape is unenforced
Severity: low.
Currently `dict[str, Any]`. Constraint shape is only meaningful once
intervention IDs exist (S8, Phase G). Mitigation: defer typed shape
to Phase G alongside the `intervention_options` table.

### R8 - SQLite write-lock under concurrent ingestion
Severity: low (Phase C, single process).
SQLite serializes writes; concurrent POSTs to ingestion endpoints
will queue. Acceptable for Phase C dev/demo. Mitigation: keep
single-writer semantics; the Postgres swap is a Phase E candidate per
`docs/architecture.md` swap criteria (TimescaleDB-style retention is
the trigger).

### R9 - Mock data realism
Severity: medium (latent until Phase E).
Synthetic streams that are too clean cause forecasting models to
overfit synthetic patterns. Mitigation in C.3: parameterized noise +
spike profiles; expose a `mock_data_source` flag in `/api/v1/meta` so
the dashboard (Phase J) can show a "DEMO DATA" badge.

### R10 - Idempotency / duplicate POSTs
Severity: medium.
Upstream retries would duplicate readings if not deduplicated.
Mitigation in C.2: optional `client_request_id` on POST; if present,
prior insert with same `(sensor_id, timestamp, client_request_id)`
short-circuits silently. No DB-level unique constraint yet (would
block legitimate same-timestamp distinct readings); revisit in
Phase E.

### R11 - Validation strictness vs dirty real-world data
Severity: medium.
Strict Pydantic validation will reject malformed payloads from real
sensors/dispatch systems; lenient validation poisons the model.
Mitigation: validate strictly + persist rejections to `ingest_errors`
(G10). Reviewable, retryable, never silently lost.

### R1 - No git yet
Severity: low.
All Phase A safety relies on `ops/rollback.py` snapshots. Phase B
initializes git; this risk closes then. Mitigation in place: snapshot
`phase-a-init` was taken before any Phase A doc was written and lists
all 17 created files for revert.

### R2 - Documentary thresholds need site override
Severity: medium (deployment-time).
`docs/compliance-context.md` ships WHO 2021 / EPA NAAQS reference
values as defaults. Real deployments require site-specific permit
limits in `site_configurations`. Mitigation: doc explicitly marks
defaults as "replace per site"; site config schema in
`docs/data-contracts.md` makes thresholds first-class fields.

### R3 - Tech-stack defaults not yet validated against load
Severity: low (Phase A).
`docs/architecture.md` recommends Python/FastAPI + React/TypeScript +
Postgres. The doc explicitly notes alternatives worth testing
(Litestar, Polars, TimescaleDB, SvelteKit/SolidJS) and defines
swap criteria. Mitigation: re-evaluate at the end of Phase D and
Phase E.

### R4 - `agent-check` not yet automated
Severity: medium -> CLOSED (2026-05-01).
Closed by Phase B sub-step B.1: `scripts/agent-check.js` exists and
runs three real validators against Phase A
(`validate-phase-a-docs`, `validate-progress`, `validate-rollback`).
Eight further validators are registered as SKIP with explicit
"pending Phase B scaffold" reasons; each becomes real in the Phase B
sub-step that lands the underlying code.

### R5 - Mock-first development is required for several phases
Severity: medium (latent).
Real mine data may not be available until pilot. Mitigation:
contracts in `docs/data-contracts.md` are written so mock and real
data share the same schemas; the ingestion API (S1) will accept both
without code changes downstream.

### R6 - Premature deep learning temptation
Severity: medium (Phase E onward).
Pressure to jump from heuristics to deep learning before baselines
prove inadequate. Mitigation: `docs/model-contracts.md` mandates
heuristics first; model lifecycle requires shadow-mode evaluation
before promotion.

### R7 - Doc-to-code drift
Severity: medium (latent).
Contracts here can drift from implementation. Mitigation: Phase B
validators (`validate-contracts`, `validate-safety`,
`validate-boundaries`) make drift fail the build.

---

## Risks (closed)

### R4 - `agent-check` not yet automated
Closed 2026-05-01 by Phase B sub-step B.1. See description above.

---

## Subsystem readiness

All subsystems S1-S16 are **specified, not implemented**. See
`docs/subsystem-contracts.md` for per-subsystem phase tagging.

---

## Phase A documentary gate

Now automatically enforced by `npm run agent-check` ->
`validate-phase-a-docs`, `validate-progress`, `validate-rollback`. The
manual checklist below is preserved for reference; the harness asserts
the same conditions on every run, so Phase A docs cannot drift without
turning the gate red.

- [x] All 17 Phase A files exist in the working directory.
- [x] Each `docs/*.md` file is non-empty and matches its named sections.
- [x] Subsystem IDs S1-S16 are consistent across `system-map.md` and
      `subsystem-contracts.md` (validated automatically).
- [x] `docs/architecture.md` states `UI -> API -> Domain -> Storage`
      and lists forbidden imports.
- [x] `docs/safety-guardrails.md` lists all 15 guardrails.
- [x] Default automation level is L1 - Advisory.
- [x] `docs/compliance-context.md` cites WHO 2021 / EPA NAAQS and
      marks defaults "replace per site."
- [x] This document lists phases A-K and marks Phase A complete.
- [x] `python progress.py` runs and prints the phase list.
- [x] `python ops/rollback.py list` shows the `phase-a-init` snapshot.
- [x] `python ops/rollback.py to phase-a-init` would revert cleanly
      (verified by listing manifest contents).

---

## Change log

| Date       | Phase / Step | Change                                          | Snapshot              |
|------------|--------------|-------------------------------------------------|-----------------------|
| 2026-04-30 | A            | Initial creation: 17 files (constitution, plan, readme, progress + rollback tooling, 12 docs). | `phase-a-init`        |
| 2026-05-01 | B.1          | agent-check harness: `package.json`, `scripts/agent-check.js`, `scripts/lib/runner.js`, three Phase A validators. Phase A auto-validated GREEN. R4 closed. Phase A marked complete; phase advanced to B. | `phase-b-agent-check` |
| 2026-05-01 | B.2          | Python tooling + backend skeleton + git init. `.gitignore`, `pyproject.toml`, 10 `app/**/__init__.py` + placeholder `app/api/main.py` + empty `app/config/settings.py`, `tests/test_skeleton.py` (13 tests), three new validators (lint/typecheck/test) wired into agent-check. Local `.venv/` created; deps installed via `pip install -e ".[dev]"`. agent-check: 6 PASS / 5 SKIP / 0 FAIL. | `phase-b-skeleton` |
| 2026-05-01 | B.3          | FastAPI app + `/api/v1/health` + `/api/v1/meta`; constants moved to `app/api/__init__.py` to avoid main<->routes circular import; `scripts/_smoke.py` + `scripts/checks/smoke.js` (TestClient in-process). agent-check: 7 PASS / 4 SKIP / 0 FAIL. | `phase-b3-health` |
| 2026-05-01 | B.4          | Pydantic schemas (mine/sensor/weather/equipment) + SQLAlchemy models (Mine, Zone, HaulRoadSegment, Sensor, Equipment, SensorReading, WeatherReading, EquipmentActivity) + `app/storage/database.py` session factory; `scripts/lib/contract_index.js` declares B.4 expectations; `validate-contracts.js` enforces them. SQLAlchemy added to deps; `database_url` setting added (default `sqlite:///./dustops.db`). 34 tests pass under strict mypy. agent-check: 8 PASS / 3 SKIP / 0 FAIL. | `phase-b4-storage` |
| 2026-05-01 | B.5          | Boundary scanner (`validate-boundaries.js`: scans 14 .py files across `app/storage,domain,schemas,audit` for forbidden upward imports), safety scanner (`validate-safety.js`: forbidden-token scan + structural field check that activates as Forecast/Recommendation/Attribution/Simulation schemas land in E/F/G/H), `review-diff.js` (git working-tree health + soft normalization-report nudge), `Dockerfile` (Python 3.11-slim + uvicorn entrypoint), `docker-compose.yml` (api service), `.dockerignore`, `scripts/seed_mock_data.py` (Phase C placeholder). Phase B complete: agent-check 11 PASS / 0 SKIP / 0 FAIL. | `phase-b5-validators` |
| 2026-05-01 | C.1          | Repository layer: `BaseRepository` + `SensorReadingRepository`, `WeatherReadingRepository`, `EquipmentActivityRepository`, `IngestErrorRepository`. New `ingest_errors` table + `IngestError` ORM model + `IngestErrorSchema` (G10). `contract_index.js` extended with `PHASE_C` + `REPOSITORIES`; `validate-contracts.js` now verifies repositories. R8-R11 risks recorded. | `phase-c1-repos` |
| 2026-05-01 | C.2          | Ingestion endpoints: POST/POST-batch/GET for `/api/v1/sensor-readings`, `/weather-readings`, `/equipment-activity`. Validation failures persist to `ingest_errors` then 422. Added `app/api/deps.py` (session injection) + `tests/api/conftest.py` (TestClient with dependency override) - both infrastructure additions on top of the approved file list. `received_at` in `RawSensorReadingSchema` made optional (server-set). Smoke now asserts the three new GET endpoints. R10 (idempotency) deferred to Phase E pending `client_request_id` contract change. Bugs caught and fixed mid-run: (a) ruff B008 on `Depends(...)` defaults -> Annotated[]; (b) SQLite `:memory:` per-connection isolation broke TestClient -> StaticPool; (c) FastAPI prod DB had no tables -> lifespan `Base.metadata.create_all`; (d) HTTPException rolled back IngestError row -> commit before raise. Plus added `*.db` to `.gitignore`. | `phase-c2-ingestion` |
| 2026-05-01 | C.3          | Mock stream generators (`app/ingestion/mock_streams.py`): reproducible sensor/weather/equipment streams with diurnal curves + parameterized noise + spikes. `scripts/seed_mock_data.py` rewritten as a real CLI on top of those generators. R9 mitigation: new `mock_mode` setting; `/api/v1/meta` now reports it. | `phase-c3-mockgen` |
| 2026-05-01 | C.4          | S2 data-quality scoring: `app/domain/data_quality.py:SensorHealthScorer` heuristics (offline / stale / few-readings / high-variance / source-quality-hint propagation). `GET /api/v1/data-quality` returns scores for all sensors, `GET /api/v1/data-quality/{sensor_id}` returns one. Smoke promotes the endpoint from PENDING to REQUIRED. Phase C complete; phase advanced to D. | `phase-c4-quality` |
| 2026-05-01 | D.4          | S4 mine-state API (Phase D step 4 of 4 - **PHASE D COMPLETE**). New: `app/api/routes/mine_state.py` with `GET /api/v1/mine-state/current?mine_id=&window_minutes=15` (compute-on-read; defaults to single-mine when only one Mine row exists; 400 when ambiguous; 404 via `require_resolved` when mine has no config) and `GET /api/v1/mine-state/zones/{zone_id}`; results persisted via `MineStateSnapshotRepository.add_many` for audit/replay. `tests/api/test_mine_state.py` covers happy path, missing mine, missing zone, empty DB, multi-mine ambiguity, single-mine default. Modified: `app/api/main.py` (mount router), `scripts/_smoke.py` (`/mine-state/current` PENDING -> REQUIRED, total 10 endpoints), `.progress_state.json` (advance to E). agent-check: 11 PASS / 0 SKIP / 0 FAIL; 117 tests. | `phase-d4-mine-state-api` (pre) + `phase-d4-mine-state-api-routed` (post) |
| 2026-05-01 | D.3          | S4 mine-state compute layer (Phase D step 3 of 4). New ORM `MineStateSnapshot` (`mine_state_snapshots`, append-only) per data-contracts.md:111-122. New schemas `MineStateZoneSchema` + aggregate `MineStateSchema` (with `staleness_flags` field implementing the documented S4 failure mode "mark stale, never fabricate"). New repo `MineStateSnapshotRepository` (add / add_many / latest_for_zone / latest_for_mine). New domain `app/domain/mine_state.py:compute_zone_state(...)` - pure heuristic function: activity summary (top-kind / mixed / unknown) + equipment_active set + dust_generation_potential (baseline x intensity matrix) + wind_exposure (<3 / 3-7 / >=7 m/s thresholds with gust max) + straight-line downwind asset detection (boundary + loading_area + critical zones; geometry-aware version is D3-R3). No model code per CLAUDE.md rule 13. 7 new tests (3 storage, 5 domain, 2 schema). Modified: `app/storage/models/__init__.py`, `scripts/lib/contract_index.js` (PHASE_D + REPOSITORIES). agent-check: 11 PASS / 110 tests. | `phase-d3-mine-state` (pre) + `phase-d3-mine-state-tests` (post) |
| 2026-05-01 | D.2          | S3 mine-map admin (Phase D step 2 of 4). New repos: `ZoneRepository` (`get` / `get_for_mine` / `upsert`), `HaulRoadSegmentRepository` (same + `mark_watered` / `mark_graded` helpers reserved for Phase G interventions). New routes: `GET/POST /api/v1/zones`, `GET /zones/{id}`, `GET/POST /api/v1/haul-road-segments`, `GET /haul-road-segments/{id}` - both reject unknown `mine_id` with 400. New domain: `MissingSiteConfigError` + `require_resolved(...)` in `site_config_resolver.py` (closes D-R2). 5 new test modules (3 storage, 1 domain, 2 api). Modified: `app/api/main.py` (mount routers), `scripts/_smoke.py` (2 endpoints -> REQUIRED), `scripts/lib/contract_index.js` (2 repos in `REPOSITORIES`). agent-check: 11 PASS / 0 SKIP / 0 FAIL; 100 -> 113 tests. | `phase-d2-mine-map` (pre) + `phase-d2-mine-map-routed` (post) |
| 2026-05-01 | D.1          | S3 site configuration storage + admin (Phase D step 1 of 4). New: `app/schemas/site_config.py` (`SiteConfigSchema` + `OptimizationWeightsSchema`; WHO/EPA-aligned defaults), `app/storage/models/site_config.py` (`SiteConfiguration` ORM, mutable, `updated_at`/`updated_by` audit), `app/storage/repositories/site_config.py` (get / get_for_mine / upsert), `app/domain/site_config_resolver.py` (3-tier fallback site_config -> mine_defaults -> schema_defaults), `app/api/routes/site_config.py` (`GET/POST /api/v1/site-config`, `GET /api/v1/site-config/{site_id}` with synthetic `default-<mine_id>` resolver path), 3 test modules (api/domain/storage). Modified: `app/storage/models/__init__.py` (export SiteConfiguration), `scripts/lib/contract_index.js` (`PHASE_D` + `SiteConfigRepository`), `app/api/main.py` (mount router), `scripts/_smoke.py` (`/site-config` -> REQUIRED). Bug fixed inline: `intervention_constraints` `None`->{} field_validator (SQLAlchemy default=dict only fires on flush). Resolver fallback to schema_defaults flagged as D-R2 (must be tightened before any automation consumer). agent-check: 11 PASS / 0 SKIP / 0 FAIL. | `phase-d1-site-config` (pre) + `phase-d1-site-config-routed` (post) |
| 2026-05-02 | K.1          | S14 outcome-join + model performance metrics (Phase K step 1 of 4). New ORM `ModelPerformanceMetric` (`model_performance_metrics`, append-only) per data-contracts.md:241-248. New schemas `TrainingRecordSchema` + `ModelPerformanceMetricSchema` + `EvaluateModelRequest` (`app/schemas/model_performance.py`). New repo `ModelPerformanceMetricRepository`. New domain `app/domain/training_data.py` (S14 left-anchored join over predictions × recommendations × approvals × outcomes; emits `outcome_status="unobserved"` past observation window) and `app/domain/model_performance.py` (heuristic metric_payload: MAE / breach precision-recall / FPR / FNR / calibration / avoided-shutdowns / production-loss totals). New routes `GET /api/v1/training-data` (auth-gated read) + `GET /api/v1/model-performance` + `POST /api/v1/model-performance/evaluate` (role-gated). Modified `app/storage/models/__init__.py`, `app/api/main.py` (2 routers), `scripts/lib/contract_index.js` (PHASE_K + repo entry — 25 entities + 20 repositories), `scripts/_smoke.py` (2 new auth-gated 401 assertions). Tactical fix: `tests/api/test_dust_events.py::test_get_events_filters_by_station` was using a hardcoded 2026-05-01 timestamp against the GET's 24h default window; switched to `datetime.now(UTC) - 5min` to unblock the gate (pre-existing bug, not caused by K.1). 23 new backend tests (storage / domain / schema / api); total 371 → 394. Risks K1-R1 (JSON-list scan for prediction linkage; resolves with K.3 Postgres swap), K1-R2 (no scheduled evaluation; resolves with K.3 scheduler), K1-R3 (avoided-shutdown is correlation-only by design). agent-check: 15 PASS / 0 SKIP / 0 FAIL. | `phase-k1-pre` (pre) + `phase-k1-s14` (post) |
| 2026-05-02 | L.M.1        | Wind/met ingest live (Open-Meteo) + ERA5 stub. Live wired Open-Meteo archive API at `app/ingestion/public/open_meteo.py:build_url` (UTC-pinned, m/s + °C); orchestrator gains `--source open_meteo` (single-point + `--from-yaml weather_targets:`) and `--source era5` payload mode (`--era5-payload PATH`; full CDS-API live mode deferred to L.M.2). New `_persist_weather` helper writes `WeatherReading` rows. New `weather_targets:` block in `data_seed/los_pelambres.yaml` (mine centroid + Cuncumén-colocated point). Schema fix folded in: `SensorReading` gains a `(sensor_id, timestamp)` `UniqueConstraint` + `scripts/migrate_unique_constraints.py` idempotent migration; resolves the duplicate-row bug found pre-L.M.1 in dev DB (249,273 → 120,328 distinct Cuncumén rows after dedup, backed up to `dustops.db.bak.pre-dedup-2026-05-02`). `WeatherReading` idempotency deferred to L.M.2 because `zone_id` is FK→zones and SQLite NULL-distinct undermines a `(source, NULL, ts)` constraint — needs a proper `weather_target_id` column. New tests: `tests/ingestion/test_open_meteo_orchestrator.py` (build_url shape, fixture-replay persist, cache-hit dry-run) + `tests/ingestion/test_era5_orchestrator_stub.py` (payload mode persist + missing-payload error). New fixture `tests/ingestion/fixtures/open_meteo_cuncumen_3day.json` (real 3-day archive response, 5 KB). Live pull persisted ~17 K WeatherReading rows for 12-month Cuncumén + mine-centroid window (2025-05-01 → 2026-05-02). Open-Meteo CC-BY-NC license note logged on every persist run. | `phase-l-m1-pre-met-ingest` |
| 2026-05-02 | M.1          | Modeling-rigor protocol layer: anti-overfit + anti-hindsight + bias register. Three new binding docs (`docs/anti-overfit-protocol.md`, `docs/anti-hindsight-protocol.md`, `docs/bias-register.md` enumerating 44 bias entries B-1..B-44 with exposure ratings + mitigation phase). New `app/domain/evaluation_protocol.py`: typed `EvaluationProtocol` dataclass + `validate_protocol_obeyed()` returning structured `errors`/`warnings`. `EvaluationProtocolSchema` added to `app/schemas/model_performance.py`; `EvaluateModelRequest` and `ShadowEvaluationRequest` now require it (HTTP 422 without). `compute_metric_payload(records, *, protocol)` and `evaluate_shadow(..., protocol=...)` are gated — `ProtocolViolation` surfaces as 422 at the API. `metric_payload.protocol` namespace now persists `protocol_version`, `protocol_hash` (SHA-256 of canonical-JSON), `split_strategy`, `embargo_days`, `sealed_test_used`, `baselines_named`, plus M.2-deferred warnings. Two new agent-check validators: `validate-overfit-discipline.js` (scans persisted `model_performance_metrics` for protocol obedience; tolerates pre-M.1 rows), `validate-hindsight-discipline.js` (asserts evaluation_protocol exports + every public connector declares realtime/reanalysis semantics). `model-contracts.md` lifecycle step 5 cross-references both protocols. `data-contracts.md` reserves PIT vocabulary (`knowable_at`, `valid_from`/`valid_to`, `realtime_proxy`, `labeled_at`) for M.2 schema lift. 18 new tests (`test_evaluation_protocol.py`) + 4 new API guard tests. Existing tests touching `compute_metric_payload`/`evaluate_shadow` updated to pass a protocol (5 test files modified). DGA / INE / OSM connector docstrings annotated for realtime/static semantics. agent-check: **GREEN at 19/19** (was 17, +2 new validators). M.2 deferred enforcement: SINCA col-3 leakage check, ERA5 `realtime_proxy` filter, `labeled_at` semantics — all warning-level until M.2 schema lands. | `phase-m1-pre-rigor` |
| 2026-05-03 | M.2          | Point-in-time (PIT) feature schema lift: anti-hindsight rules 1–4 graduate from "warning" to "enforced." Schema additions: `sensor_readings.valid_from / valid_to / pit_version` + new unique index `uq_sensor_readings_sensor_ts_validfrom`; `weather_readings.weather_target_id / realtime_proxy` + new unique index `uq_weather_readings_source_target_ts` (closes the L.M.1-deferred WeatherReading idempotency gap, B-39); `labeled_at` columns on `dust_events`, `recommendations`, `recommendation_approvals`, `action_outcomes`, `source_attributions` with context-aware defaults (= the canonical event timestamp via SQLAlchemy `default=` callable); `source_attributions.derivation` (default `realtime_predicted`). New `scripts/migrate_pit_columns.py` idempotent migration applied to dev DB. New `app/domain/pit_query.py` with `sensor_readings_as_of`, `weather_readings_as_of`, `labels_as_of` — the canonical as-of helpers all domain consumers must use. SINCA parser: new `parse_sinca_csv(emit_all_versions=True)` mode (returns col-2 + col-3 separately) + `expand_to_pit_records()` helper that pairs each record with its `valid_from`/`valid_to`. `_persist_sinca` and `_persist_weather` rewritten as PIT-aware idempotent (`INSERT OR IGNORE`). Open-Meteo orchestrator tags `realtime_proxy=True`, ERA5 stub mode tags `realtime_proxy=False`. `validate_protocol_obeyed` lifts M.1 warnings to errors via SQL probes when a `session` is provided: SINCA col-3 leakage probe, ERA5-in-realtime-training probe, post-window-labeled probe; `compute_metric_payload`/`evaluate_shadow` thread the session through. `load_and_assemble` gains `mode: Literal["evaluation", "training_feature"]` (default `"evaluation"` — the existing S14 callers measure ground truth, not feature-engineering for new training; PIT-filtered "training_feature" mode is opt-in for the future S5 caller). `validate-hindsight-discipline.js` extended to assert `pit_query.py` module + helpers + `expand_to_pit_records` exist. New tests: `tests/ingestion/test_sinca_pit_emission.py` (7 tests) + `tests/domain/test_pit_query.py` (4 tests). Bias register Status flips: B-2, B-3, B-4, B-37, B-39 → Mitigated. Backend test count: 506 → 540. agent-check: **GREEN at 19/19**. DB backup at `dustops.db.bak.pre-m2-pit-2026-05-02`. | `phase-m2-pre-pit` |
| 2026-05-03 | M.3.1        | Causal-contamination layer (honest disclosure, not causal inference): the system can no longer claim causal evidence it doesn't have. New binding doc `docs/causal-protocol.md` defining the evidence-class hierarchy (`experimental` > `quasi_experimental` > `observational_correlational` > `expert_judgment`) and per-subsystem rules for S6/S7/S9/S10/S12. New `app/domain/causal_protocol.py`: `EvidenceClass` + `SimulationMethod` literals, `validate_simulation` (rejects naive-correlation simulations with empty `counterfactual_assumption` or `confidence > 0.7`), `confidence_after_causal_penalty` (penalty schedule: experimental 0%, quasi-experimental 10%, observational/expert 30%; ceiling 0.7 for naive evidence), `probe_causal_intent_training` (SQL probe). Schema additions: `source_attributions.evidence_class` (default `observational_correlational`); `intervention_simulations.simulation_method / counterfactual_assumption / selection_bias_caveat`; `recommendations.causal_confidence`. New `scripts/migrate_causal_columns.py` idempotent migration applied. `app/domain/pit_query.py` gains `features_pre_intervention(prediction_time, intervention_lag=3h, sensor_id=...)` — correlated EXISTS subquery with SQLite-portable `func.datetime(decided_at, '+N seconds')` form to filter sensor rows inside operator-approval windows. `EvaluationProtocol.causal_intent: bool = False` field added; `validate_protocol_obeyed` runs the causal-intent SQL probe when True, blocking evaluations whose training data is solely observational. New `scripts/checks/validate-causal-discipline.js` validator wired into agent-check. Bias-register Status flips: B-16/B-17/B-19/B-20/B-26/B-33 → Mitigated-via-disclosure (M.3.1); B-18 stays open (covariate-list enforcement is M.4); B-16 + B-20 also flagged for M.3.3 true-cutoff once operator-real timestamps land. New tests: `test_causal_protocol.py` (13) + `test_pre_intervention_filter.py` (5). Backend test count: 540 → 558. agent-check: **GREEN at 20/20** (was 19, +1 new validator). DB backup at `dustops.db.bak.pre-m3-causal-2026-05-03`. | `phase-m3-pre-causal` |
| 2026-05-03 | M.4.1        | Calibration acceptance gate + covariate discipline (anti-overfit rules 8 + 9). `EvaluationProtocol` extended with `feature_set`, `required_covariates`, `forbidden_covariates`, `max_ece` (default 0.05), `ece_override_reason`. `protocol_hash` includes the four new hashed fields (override reason is a non-hashed audit annotation). `protocol_to_payload_keys` and `EvaluationProtocolSchema` mirror; both API translators (model_performance + shadow_mode) thread the new fields. `compute_metric_payload` now computes `calibration_bins[]` (10-bin reliability table per Niculescu-Mizil/Caruana 2005), `brier_score`, `ece`; raises `ProtocolViolation` when `ece > max_ece` unless `ece_override_reason` is non-empty (override is logged on the metric row as a warning). `validate_protocol_obeyed` adds rule-9 covariate cross-check (required ⊆ feature_set; forbidden ∩ feature_set = ∅). `PROTOCOL_VERSION` bumped from "M.1" to "M.4". `validate-overfit-discipline.js` extended: M.4-tagged rows must carry `calibration_bins`, `ece`, `brier_score`, `protocol.max_ece`, plus the three covariate arrays; ECE-gate bypass requires the override warning. M.1/M.2/M.3 rows remain legal (validator gates by `protocol_version`). `docs/anti-overfit-protocol.md` adds rules 8 + 9 and removes calibration / covariates from the "not covered" list. `docs/bias-register.md` flips B-30 (confidence miscalibration) and B-18 (confounding) to Mitigated (M.4.1). New tests: 7 covariate-discipline + 5 calibration-gate tests; existing `test_model_performance.py::test_empty_input` updated for M.4 protocol_version. agent-check 20/20 GREEN; backend 558 → 570 (+12). | `phase-m4-1-pre-calibration` |
| 2026-05-03 | M.3.2        | UI surfacing of M.3.1 causal-protocol fields and M.4.1 calibration. Backend schema lift: `SourceAttributionSchema.evidence_class` (default `observational_correlational`), `RecommendationSchema.causal_confidence` (default 0.5), `InterventionSimulationSchema.{simulation_method, counterfactual_assumption, selection_bias_caveat}` — all defaulting to the storage defaults so existing API consumers keep working. Web wire types extended (`EvidenceClass`, `SimulationMethod` unions; `InterventionSimulationSchema`, `ModelPerformanceMetricSchema`, `CalibrationBin`). New `api.modelPerformance()` client method. Two new components: `web/src/components/EvidenceChip.tsx` (strong/weak tier per evidence class with hover tooltip), `web/src/components/CalibrationBadge.tsx` (good/marginal/over driven by ECE vs `max_ece`, surfaces override reason). Wired into ControlRoom (Likely-cause card → evidence chip; Recommended-action card → predictive + causal confidence pair + calibration badge) and Compliance (new Source-attributions card with chip per attribution; new Model-calibration card with explanatory body). `docs/ui-principles.md` adds rules for the evidence-chip and calibration-badge surfaces. Web tests: 3 new component tests covering the two badge components' tier logic and override-reason path. agent-check stays GREEN at 20/20; web tests 14 → 17. | (no snapshot — git revert acac35b reverts the phase) |
| 2026-05-03 | M.4.2        | Per-receptor fairness audit (B-32) + Goodhart canary discipline (B-44). `compute_metric_payload` extended with `per_receptor: dict[target_id, {sample_count, mae_pm10, breach_precision, breach_recall, false_positive_rate, false_negative_rate, target_kind}]` (Cuncumén-vs-Caimanes asymmetry surfacing) and `canary_metrics: dict[KPI, paired_counter_metric_value]` driven by new module-level `GOODHART_CANARY_PAIRS` constant. Pair set: breach_precision↔breach_recall, false_positive_rate↔breach_recall, avoided_shutdowns_estimate↔false_negative_rate, production_loss_tonnes_total↔breach_recall. Empty-observed records emit empty dicts so the wire shape stays stable. `validate-overfit-discipline.js` extended: M.4-tagged rows must carry both blocks. `docs/safety-guardrails.md` adds two new sections — Goodhart-canary discipline (binding on automation-promotion decisions) and Per-receptor fairness audit. `docs/bias-register.md` flips B-32 + B-44 to Mitigated (M.4.2). New tests: 3 fairness/canary tests (per-receptor split, canary pair-set, empty-observed degradation). agent-check 20/20 GREEN. | `phase-m4-2-pre-fairness` |
| 2026-05-03 | M.4.3        | Drift watch — concept-drift detector over persisted `model_performance_metrics` (B-12 mitigation). New `app/domain/drift_watch.py:compute_drift(rows, *, model_version, detected_at, min_samples=4)` splits rows into baseline (oldest half) + recent (newest half) and emits one `DriftAlert` per metric whose median crosses the per-metric `DRIFT_THRESHOLDS` value. Threshold table: mae_pm10 5.0 µg/m³, probability metrics (recall/precision/FPR/FNR) 10pp, ece 0.025, calibration_error 0.05. New `app/schemas/drift.py:DriftAlertSchema`. New `app/api/routes/drift.py:GET /api/v1/drift?model_version=&since_days=14&min_samples=4`, auth-gated; reverses repo's descending order so oldest rows form the baseline. Mounted in `app/api/main.py`. Smoke endpoint added (`/api/v1/drift?model_version=foo` → 401). New validator `scripts/checks/validate-drift-discipline.js` (#21 in the gate) asserts module exports + schema + route + main-mount + B-12 flip. `scripts/lib/contract_index.js` registers `PHASE_M4` + `DriftAlertSchema` (34 entities total). New tests: 7 domain tests (no-drift, recall-drift, sub-threshold, min-samples floor, missing-metric tolerance, alert-fields, bidirectional drift) + 4 API tests (401, empty, recall-collapse alert, min-samples floor). `docs/bias-register.md` flips B-12 → Mitigated (M.4.3). agent-check **GREEN at 21/21** (was 20). End of M.4 block; remaining open biases are post-M / multi-station-required. | `phase-m4-3-pre-drift` |
