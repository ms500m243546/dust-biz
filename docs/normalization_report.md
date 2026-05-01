# Normalization Report

Current architectural state, classifications, risks, and active phase
plan for DustOps AI. This document is updated at the end of every
phase.

---

## Active phase

**Phase D - Mine State Engine.**
Status: pending plan/approval. See `PLAN.md`.

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
| D     | Mine State Engine              | pending (next) |
| E     | Forecasting MVP                | pending     |
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
