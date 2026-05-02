# Normalization Report

Current architectural state, classifications, risks, and active phase
plan for DustOps AI. This document is updated at the end of every
phase.

---

## Active phase

**Phase I - Human Approval Workflow.**
Status: pending plan/approval. See `PLAN.md`.

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
| J     | Dashboard                      | pending     |
| K     | Feedback, Reporting, ROI       | pending     |

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
