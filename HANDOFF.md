# DustOps AI — Session Handoff

**As of:** 2026-05-02
**Active phase:** MVP-complete (Phase K landed end-to-end)
**Last completed:** K — Feedback, Reporting, ROI (K.1 → K.2 → K.3 → K.4)
**Validation gate:** `npm run agent-check` GREEN, **15 PASS / 0 SKIP / 0 FAIL**, 437 backend tests + 14 web tests, 3 happy-path smoke endpoints + 23 auth-gated rejections (the read-side auth gate landed in K.3)

---

## State at handoff

- `.progress_state.json`: `current_phase=MVP-complete`, `completed_phases=[A..K]`.
- Working tree clean. Phase K commits since end of J:
  - `0833278` Phase K.1 — S14 outcome-join + model performance metrics
  - `<k2>` Phase K.2 — S15 reports (model-performance / ROI / compliance)
  - `<k3>` Phase K.3 — Hardening (auth gate / JWT rotation / scheduler / GeoJSON)
  - `<k4>` Phase K.4 — Shadow-mode evaluation harness + MVP-complete advance
- Rollback log: `phase-k1-pre`, `phase-k1-s14`, `phase-k2-pre`,
  `phase-k2-reports`, `phase-k3-hardening`.
- Memory: `project_phase_k1_complete.md` is the K.1 entry; the next session
  should land a `project_mvp_complete.md` superseding it.

## What shipped in Phase K (K.1 → K.4)

### K.1 — S14 outcome-join + model performance metrics

| Slice | Files |
|---|---|
| ORM | `app/storage/models/model_performance.py` (`ModelPerformanceMetric`, append-only) |
| Repo | `app/storage/repositories/model_performance.py` |
| Schemas | `app/schemas/model_performance.py` (`TrainingRecordSchema`, `ModelPerformanceMetricSchema`, `EvaluateModelRequest`) |
| Domain | `app/domain/training_data.py` (S14 join), `app/domain/model_performance.py` (heuristic metric_payload) |
| Routes | `GET /training-data`, `GET /model-performance`, role-gated `POST /model-performance/evaluate` |

Closes the predicted-vs-actual loop. Avoided-shutdowns counted only on
operator-approved/overridden FPs (correlation, not causal).

### K.2 — S15 reports

| Slice | Files |
|---|---|
| Schema additions | `app/schemas/site_config.py` adds `cost_curves` (default `tonne_value_usd=80`) |
| ORM | `SiteConfiguration.cost_curves` JSON column |
| Schemas | `app/schemas/reports.py` (`ModelPerformanceReport`, `ROIReport`, `ComplianceReport`) |
| Domain | `app/domain/reports.py` — pure aggregations |
| Routes | `GET /reports/model-performance`, `GET /reports/roi`, `GET /reports/compliance` |

Closes G3-R1, J1-R3 (ROI), J1-R4 (per-site PM thresholds in compliance).

### K.3 — Hardening

| Slice | Files |
|---|---|
| Read-side auth gate | `app/api/main.py` mounts every non-health/meta/auth router with `dependencies=[Depends(current_user)]` (closes I1-R1) |
| JWT/JWKS rotation | `app/domain/auth.py:KeyRing` (`add` / `rotate` / `prune` / `metadata`); tokens carry `kid`; `GET /auth/keys` exposes metadata only (closes I2-R1) |
| Scheduler | `app/domain/scheduler.py` — stdlib in-process tick scheduler with `approval_expiry_sweep` + `keyring_prune` jobs; opt-in via `DUSTOPS_SCHEDULER_ENABLED` (closes I3-R1, F1-R1) |
| GeoJSON | `Zone.geometry` (Polygon) + `HaulRoadSegment.geometry` (LineString) with strict ring/lon-lat validators (closes D3-R3, J1-R2) |
| Postgres readiness | `Settings.database_url` documented as the swap point; ORM uses dialect-agnostic types only; SQLite remains the dev/test default (partial close on D3-R2 / I5-R1) |

### K.4 — Shadow-mode evaluation harness

| Slice | Files |
|---|---|
| Domain | `app/domain/shadow_mode.py:evaluate_shadow` — pure comparison over the K.1 join + K.1 metrics |
| Schemas | `app/schemas/shadow_mode.py` (`ShadowEvaluationRequest`/`Response`) |
| Route | role-gated `POST /shadow-mode/evaluate` returning candidate vs production metrics, deltas, and a `recommendation` in `{promote, hold, regress}` |

Promotion remains an explicit human action (the harness only recommends;
the operator calls `app.models.registry.set_current` to actually flip
the live pointer — conservative posture per G13).

## Architecture as it stands

```
   UI  →  web/                            React 18 + TS strict + Vite (J)
                                          ├ Auth, 4 operator views, ROI/compliance views ready for K.2 wiring
                                          └ Web validators in agent-check

   API →  app/api/routes/   31 router groups now:
            health · meta · auth (open by design)
            sensor_readings · weather_readings · equipment_activity ·
            data_quality · site_config · zones · haul_road_segments ·
            mine_state · forecasts · dust_events · attributions ·
            interventions · simulations · recommendations · approvals ·
            outcomes · audit · training_data · model_performance ·
            reports · shadow_mode               (auth-gated by router-level dep)
            │
   Domain →  features · forecasting · attribution · dust_events ·
            interventions · simulation · recommendations · approvals ·
            outcomes · auth · scheduler · training_data ·
            model_performance · reports · shadow_mode
            │
   Models →  registry · forecasting · attribution · intervention · cost · optimization
            │
   Storage →  20 repositories
```

`validate-boundaries` clean across 96 Python files; `validate-safety` covers 11 schemas; `validate-contracts` checks 30 entities + 20 repositories.

## MVP acceptance — checked against PLAN.md §"MVP acceptance"

1. Mock data drives the loop end-to-end → seeded via `scripts/seed_mock_data.py`. ✓
2. Forecasts include confidence + model_version + reason. ✓ (validate-safety)
3. Attribution ranks likely sources with reasons. ✓
4. ≥ 3 intervention options can be simulated. ✓
5. Recommendations ranked by dust reduction + production impact. ✓
6. Human can approve / reject / override. ✓
7. Outcomes recorded; predicted-vs-actual tracked (S14 join). ✓ K.1
8. Shadow mode supported. ✓ K.4
9. No high-impact action executes without approval (G1, G13). ✓
10. Validation gate green. ✓ 15/15

## Open risks at MVP-complete

| ID | Severity | Summary | Notes |
|---|---|---|---|
| K1-R1 | low | `Recommendation.linked_prediction_ids` JSON-list scan in Python | Resolves with full Postgres swap (GIN index on JSON) |
| K1-R2 | low | Manual evaluate cadence; scheduler jobs configured but evaluate not auto-fired | Add `model_performance_evaluate` job to scheduler when sites want nightly cadence |
| K1-R3 | low | Avoided-shutdown is correlation-only by design | Documented in `app/domain/model_performance.py` |
| D3-R2 / I5-R1 | medium-latent | SQLite still the default in-tree | Production deploys swap via `DUSTOPS_DATABASE_URL`; alembic migrations not yet authored — first migration delta should snapshot current schema |
| G2-R1 / E2-R1 / F3-R2 | medium-latent | Heuristic models uncalibrated | Train real models in a follow-up; the K.1 metric writer is the calibration scoreboard |

## How to resume next session

1. `python progress.py` should print `current phase: MVP-complete`.
2. `npm run agent-check` should print `15 PASS / 0 SKIP / 0 FAIL`.
3. If new work is "calibrate models" — point at `model_performance_metrics`
   rows; the K.1 writer is the calibration source-of-truth.
4. If new work is "production deploy" — author the first alembic migration
   from current schema, swap `DUSTOPS_DATABASE_URL` to Postgres, set
   `DUSTOPS_SCHEDULER_ENABLED=true`, and rotate `DUSTOPS_AUTH_SECRET` via
   the `KeyRing.rotate` API.
5. If new work is "wire reports into the dashboard" — `web/` already has
   the placeholder ROI/compliance views; add typed fetchers against the
   K.2 endpoints (`/reports/model-performance`, `/reports/roi`,
   `/reports/compliance`) and follow the J-deslop lesson: read field
   names from `app/schemas/reports.py`, do not invent.

## Lessons encoded into the normalization report

- **TS wire types must be read from `app/schemas/`, not authored
  speculatively.** Phase J deslop was a one-shot lesson; K.1 + K.2 added
  the matching TS exposure work as a backlog note for the dashboard
  wiring follow-up.
- **Date-relative test fixtures rot.** A pre-existing
  `test_dust_events.py` fixture using a hardcoded `2026-05-01` timestamp
  broke on day+1; fixed in K.1. New tests use `datetime.now(UTC) - delta`.
- **SQLite dev DB does not auto-migrate when a column is added.** When
  `cost_curves` landed in K.2, the on-disk `dustops.db` had to be
  deleted so `Base.metadata.create_all` recreated it with the new
  column. Production deploys use alembic — this hazard is dev-local only.

## Key references

- Master plan: `PLAN.md`
- Operating contract: `docs/architect_protocol.md`
- Subsystem contracts: `docs/subsystem-contracts.md` (S14 + S15 are now live)
- Data contracts: `docs/data-contracts.md`
- Model contracts: `docs/model-contracts.md` (lifecycle step 5 — shadow eval — is now usable end-to-end)
- Safety guardrails: `docs/safety-guardrails.md`
- Phase change log: `docs/normalization_report.md`
