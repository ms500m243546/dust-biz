# DustOps AI — Session Handoff

**As of:** 2026-05-01
**Active phase:** F — Source Attribution (pending plan/approval)
**Last completed:** E — Forecasting MVP (E.1 → E.4)
**Validation gate:** `npm run agent-check` GREEN, 11/11, 167 tests, 11 smoke endpoints

---

## State at handoff

- `.progress_state.json`: `current_phase=F`, `completed_phases=[A,B,C,D,E]`.
- Working tree: clean after Phase E commits (E.1–E.4 each on its own commit on `main`).
- Rollback log (`python ops/rollback.py list`): all D.* and E.* pre/post snapshots present.
- Memory at `C:\Users\ignac\.claude\projects\C--Users-ignac-OneDrive-Desktop-WFLW\memory\` populated;
  Phase D entry now stale relative to repo state — verify before quoting.

## What shipped in Phase E

| Step | Subsystem | Snapshots (pre / post) | Key files |
|---|---|---|---|
| E.1 | S5 feature pipeline | `phase-e1-pre-features` / `phase-e1-features` | `app/schemas/features.py`, `app/storage/models/features.py`, `app/storage/repositories/features.py`, `app/domain/features.py` (`feature_pipeline_v0.1.0`) |
| E.2 | Model registry + heuristic baseline | `phase-e2-pre-registry` / `phase-e2-registry` | `app/models/registry.py`, `app/models/forecasting/heuristic_baseline.py` (`dust_forecast_heuristic_v0.1.0`), `app/schemas/forecasts.py` (`DustForecastSchema`), `validate-boundaries.js` extended |
| E.3 | Persistence + orchestration | `phase-e3-pre-forecasts` / `phase-e3-forecasts` | `app/storage/models/forecasts.py`, `app/storage/repositories/forecasts.py`, `app/domain/forecasting.py:issue_forecast`; `validate-safety.js` scoped to `app/schemas/` |
| E.4 | Forecast API + smoke promotion | `phase-e4-pre-api` / (post snapshot pending) | `app/api/routes/forecasts.py`, `scripts/_smoke.py`, `scripts/lib/contract_index.js` (PHASE_E block) |

## Architecture as it stands

```
   UI (Phase J, not started)
            │
   API   →  app/api/routes/  health · meta · sensor_readings · weather_readings ·
            equipment_activity · data_quality · site_config · zones ·
            haul_road_segments · mine_state · forecasts
            │
   Domain →  app/domain/  data_quality · site_config_resolver · mine_state ·
            features · forecasting (issue_forecast orchestrator)
            │
   Models →  app/models/  (Domain peer)
            registry · forecasting/heuristic_baseline (DustForecastModel)
            │
   Storage →  app/storage/models/  Mine · Zone · HaulRoadSegment · Sensor · Equipment ·
            SensorReading · WeatherReading · EquipmentActivity · IngestError ·
            SiteConfiguration · MineStateSnapshot · FeatureRecord · DustPrediction
            app/storage/repositories/  10 repos (8 prior + features + forecasts)
```

`scripts/checks/validate-boundaries.js` confirms zero upward imports across 44 Python
files in 5 layered directories (now including `app/models/`).
`scripts/checks/validate-safety.js` is **active**: 2 safety-relevant schemas tracked
(`DustForecastSchema`, `ForecastTargetSchema`), all guardrail fields present.

## Open risks carried into Phase F

| ID | Severity | Summary | Resolution phase |
|---|---|---|---|
| D2-R1 | low | Admin POSTs unauthenticated | I |
| D2-R2 | low | Zone `allowed_interventions` IDs unvalidated | G (S8 lands the catalog) |
| D-R3 | low | `intervention_constraints` JSON shape unenforced | G |
| D3-R1 / E2-R1 | medium-latent | Forecast heuristic uncalibrated | K (offline harness + ground truth) |
| D3-R2 | low | Snapshot writes per request stress SQLite | R8 — Postgres swap |
| D3-R3 | low | Downwind detection straight-line, not terrain-aware | when GeoJSON / elevation lands |
| E1-R1 | low | Leakage guard single-point at builder | K (offline sweep harness) |
| E2-R2 | low | Registry process-global | re-visit on multi-tenant |
| E3-R1 | low | `input_data_quality_score` rounded on persist | K (raw needed for reanalysis) |
| E4-R1 | low | Forecast compute-on-read cost grows with zones | J (perf pass) |
| E4-R2 | low | Forecast endpoints unauthenticated | I |

**Closed during Phase E:** none of the prior risks fully closed; E activated
`validate-safety` and added the model-registry + Domain-peer layer rule.

## What Phase F will do (per `PLAN.md`)

> For each elevated-risk forecast, rank likely operational causes with confidence
> and a human-readable reason.

Deliverables:
- Source candidate generator (S7) — `app/models/attribution/...`.
- Wind-aligned spatial proximity + activity-time correlation.
- `SourceAttribution` schema with `probable_sources: [{source, confidence,
  reason}]`, `evidence_fields`, overall `confidence`, `model_version`.
- `dust_events` and `source_attributions` tables per `data-contracts.md` lines 149–166.
- New endpoints (likely `GET /api/v1/attributions/...`).

**Important:** Phase F lands the second batch of safety-relevant schemas;
`validate-safety` will start tracking `Attribution`-named schemas in `app/schemas/`.

## How to resume next session

1. Read `docs/normalization_report.md` "Active phase" — should now say Phase F.
2. `git status` — should be clean (E.1–E.4 committed).
3. `python progress.py` — should show `current_phase=F`.
4. `npm run agent-check` — confirm gate is still green.
5. Produce the architect-protocol plan for Phase F and stop for approval.

## Key references

- Master plan: `PLAN.md`
- Operating contract: `docs/architect_protocol.md`
- Subsystem contracts: `docs/subsystem-contracts.md` (S7 next)
- Data contracts: `docs/data-contracts.md` (`dust_events`, `source_attributions` are next)
- Model contracts: `docs/model-contracts.md` (`SourceAttributionModel` interface)
- Safety guardrails: `docs/safety-guardrails.md`
- Phase change log: `docs/normalization_report.md`
