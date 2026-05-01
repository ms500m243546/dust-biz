# PLAN.md - DustOps AI master build plan

This is the single source of truth for **what** to build and **in what
order**. Phase definitions are binding; per-phase deliverables are the
acceptance scope. No phase begins until the previous one is validated and
approved.

The current active phase is recorded in `docs/normalization_report.md`.

---

## Product wedge

> Help mines avoid dust-related stoppages by forecasting dust-risk and
> recommending the minimum operational adjustment needed to remain under
> thresholds without sacrificing unnecessary production.

DustOps AI must answer, at any moment:

1. Where is dust risk building?
2. What is causing it?
3. Where will the dust likely move?
4. What happens if nothing changes?
5. What is the smallest operational adjustment to reduce risk below threshold?
6. What is the estimated production cost of each candidate intervention?
7. Did the recommendation work after it was executed?
8. Did we avoid unnecessary shutdown or over-throttling?
9. How confident is the system?
10. What should the human operator do now?

---

## Phase sequence

Phases are sequential. No skipping. Every phase ends with: validation
gate green, rollback verified, `progress.py` updated, sign-off recorded
in `docs/normalization_report.md`.

### Phase A - Architecture Constitution

**Goal:** Establish the constitution, contracts, safety guardrails, domain
context, and phase plan that govern every later phase.

Deliverables:
- `CLAUDE.md`
- `PLAN.md`
- `README.md`
- `progress.py`
- `ops/rollback.py`
- `docs/architect_protocol.md`
- `docs/architecture.md`
- `docs/system-map.md`
- `docs/subsystem-contracts.md`
- `docs/data-contracts.md`
- `docs/model-contracts.md`
- `docs/safety-guardrails.md`
- `docs/definition-of-done.md`
- `docs/ui-principles.md`
- `docs/mining-domain.md`
- `docs/compliance-context.md`
- `docs/normalization_report.md`

Validation: documentary checklist (see `docs/definition-of-done.md`,
"Phase A gate"). Automated `agent-check` arrives in Phase B.

### Phase B - Repo Scaffold

**Goal:** Create the application skeleton and the automated validation
gate. After Phase B, every change can be checked by `npm run agent-check`.

Deliverables:
- Backend skeleton: `app/api/`, `app/domain/`, `app/storage/`,
  `app/schemas/`, `app/config/`, `app/audit/`
- Frontend skeleton: `web/` with React + TypeScript scaffold
- Config system: `app/config/settings.py`, `app/config/site_config.py`
- Initial DB models for entities listed in
  `docs/data-contracts.md` (mines, zones, sensors, sensor_readings,
  weather_readings, equipment, equipment_activity)
- Mock data generator stubs (real generators in Phase C)
- Health endpoints (`/api/v1/health`, `/api/v1/meta`)
- `scripts/agent-check.js` chaining lint + typecheck + test + smoke +
  validate-boundaries + validate-contracts + validate-safety +
  review-diff
- Git initialized; `.gitignore` configured
- Docker / docker-compose for backend + frontend

### Phase C - Data Harness

**Goal:** Ingest sensor, weather, and equipment-activity streams with
schema validation, quality scoring, and storage. Mock streams stand in for
real instruments.

Deliverables:
- Sensor ingestion pipeline (S1)
- Weather ingestion
- Equipment activity ingestion
- Validators and outlier detection
- Data quality scoring (S2)
- Mock stream generators
- Repository layer for raw readings

### Phase D - Mine State Engine

**Goal:** Convert raw streams + site config into a live operational map
of "what the mine is doing now."

Deliverables:
- Site config & mine map storage (S3)
- Real-time mine state computation (S4)
- Per-zone activity, truck density, wind exposure, downwind risk
- `GET /api/v1/mine-state/current` and per-zone endpoints

### Phase E - Forecasting MVP

**Goal:** Predict PM10/PM2.5 risk for at least 15/30/60 minute horizons,
with confidence and model version metadata.

Deliverables:
- Feature pipeline (S5)
- Baseline forecasting model (S6) behind `DustForecastModel` interface
- Forecast endpoints
- Prediction logging with model version + confidence

### Phase F - Source Attribution

**Goal:** For each elevated-risk forecast, rank likely operational causes
with confidence and a human-readable reason.

Deliverables:
- Source candidate generator (S7)
- Wind-aligned attribution
- Activity correlation
- Ranked source output with explanations

### Phase G - Intervention Simulation

**Goal:** For each candidate intervention, estimate dust reduction,
time-to-effect, production cost, and confidence.

Deliverables:
- Intervention library (S8)
- Intervention simulator (S9)
- Production cost model baseline (S10)
- Counterfactual "do nothing" comparison

### Phase H - Recommendation Engine

**Goal:** Choose the lowest-cost effective intervention. Rank
alternatives. Prioritize compliance when risk is extreme.

Deliverables:
- Production-aware optimization engine (S11)
- Recommendation engine (S12) producing the recommendation template from
  `docs/subsystem-contracts.md`
- Compliance-priority logic
- Risk-tolerance configuration per site

### Phase I - Human Approval Workflow

**Goal:** Every recommendation passes through a human approval step;
every decision is auditable.

Deliverables:
- Approval / rejection / override endpoints (S13)
- Audit log of every decision
- Outcome capture endpoint
- Default automation level: **L1 - Advisory**

### Phase J - Dashboard

**Goal:** Operational UI that helps a shift supervisor decide under
pressure. Four views: control room, environmental compliance, operations
manager, executive.

Deliverables:
- Control-room view (current risk, forecast, cause, action, heatmap)
- Environmental compliance view (PM trends, rolling averages, sensor
  health, audit trail)
- Operations manager view (production impact, ROI, tonnes protected)
- Executive view (downtime avoided, compliance incidents avoided)

### Phase K - Feedback, Reporting, ROI

**Goal:** Close the loop. Predictions vs actuals. Intervention
effectiveness. Avoided shutdowns. Tonnes protected. Compliance reports.

Deliverables:
- Outcome capture & training data assembly (S14)
- Model performance reports
- ROI reports
- Compliance reports
- Shadow-mode evaluation harness usable end-to-end

---

## What Phase A explicitly does NOT deliver

- Application code (no `app/`, no `web/`)
- Git initialization (Phase B)
- `npm run agent-check` and validation scripts (Phase B)
- Docker / docker-compose (Phase B)
- Database (Phase B/C)
- Models (Phase E onward)

This is intentional. Phase A produces only the rules and contracts that
constrain Phases B-K.

---

## MVP acceptance (target after Phase J)

The full MVP acceptance criteria are in the operating prompt section 20
and reproduced in `docs/definition-of-done.md`.

The minimum bar:
1. Mock data drives the loop end to end.
2. Forecasts include confidence, model version, reason.
3. Attribution ranks likely sources with reasons.
4. At least three intervention options can be simulated.
5. Recommendations are ranked by dust reduction and production impact.
6. A human can approve / reject / override.
7. Outcomes are recorded; predicted vs actual is tracked.
8. Shadow mode is supported.
9. No high-impact action executes without approval.
10. Validation gate (`agent-check`) is green.
