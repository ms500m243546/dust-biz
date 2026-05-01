# DustOps AI — Session Handoff

**As of:** 2026-05-01
**Active phase:** G — Intervention Simulation (pending plan/approval)
**Last completed:** F — Source Attribution (F.1 → F.4)
**Validation gate:** `npm run agent-check` GREEN, 11/11, 217 tests, 13 smoke endpoints

---

## State at handoff

- `.progress_state.json`: `current_phase=G`, `completed_phases=[A,B,C,D,E,F]`.
- Working tree: clean after Phase F commits (F.1–F.4 each on `main`).
- Rollback log (`python ops/rollback.py list`): all D.*, E.*, F.* pre/post snapshots present.
- Memory at `C:\Users\ignac\.claude\projects\C--Users-ignac-OneDrive-Desktop-WFLW\memory\` updated:
  Phase F entry now reflects what shipped; Phase D/E entries are historical.

## What shipped in Phase F

| Step | Subsystem | Snapshots (pre / post) | Key files |
|---|---|---|---|
| F.1 | DustEvent storage + creation | `phase-f1-pre-events` / `phase-f1-events` | `app/schemas/dust_events.py`, `app/storage/{models,repositories}/dust_events.py`, `app/domain/dust_events.py`, `app/api/routes/dust_events.py` |
| F.2 | SourceAttribution storage | `phase-f2-pre-attribution` / `phase-f2-attribution` | `app/schemas/attributions.py`, `app/storage/{models,repositories}/attributions.py` |
| F.3 | Rule-based attribution model + orchestrator | `phase-f3-pre-attribution-model` / `phase-f3-attribution-model` | `app/models/attribution/rules_baseline.py` (`source_attribution_rules_v0.1.0`), `app/domain/attribution.py:attribute_event` |
| F.4 | API + smoke + contract index | `phase-f4-pre-api` / (post snapshot pending) | `app/api/routes/attributions.py`, `scripts/_smoke.py` (13 endpoints), `scripts/lib/contract_index.js` (PHASE_F block) |

## Architecture as it stands

```
   UI (Phase J, not started)
            │
   API   →  app/api/routes/  health · meta · sensor_readings · weather_readings ·
            equipment_activity · data_quality · site_config · zones ·
            haul_road_segments · mine_state · forecasts · dust_events · attributions
            │
   Domain →  app/domain/  data_quality · site_config_resolver · mine_state ·
            features · forecasting · dust_events · attribution
            │
   Models →  app/models/  (Domain peer; cannot import app.api.* or app.storage.*)
            registry · forecasting/heuristic_baseline · attribution/rules_baseline
            │
   Storage →  app/storage/models/  Mine · Zone · HaulRoadSegment · Sensor · Equipment ·
            SensorReading · WeatherReading · EquipmentActivity · IngestError ·
            SiteConfiguration · MineStateSnapshot · FeatureRecord · DustPrediction ·
            DustEvent · SourceAttribution
            app/storage/repositories/  12 repos
```

`validate-boundaries` confirms zero upward imports across 54 Python files in 5 layered directories.
`validate-safety` is **active**: 3 safety-relevant schemas tracked (`DustForecastSchema`,
`ForecastTargetSchema`, `SourceAttributionSchema`), all required guardrail fields present.

## Open risks carried into Phase G

| ID | Severity | Summary | Resolution phase |
|---|---|---|---|
| D2-R1 / E4-R2 / F4-R1 | low | Admin & forecast & attribution endpoints unauthenticated | I |
| D2-R2 | low | Zone `allowed_interventions` IDs unvalidated | **G** (S8 lands the catalog) |
| D-R3 | low | `intervention_constraints` JSON shape unenforced | **G** |
| D3-R1 / E2-R1 / F3-R2 | medium-latent | Heuristic / rule coefficients uncalibrated | K |
| D3-R2 | low | Snapshot writes per request stress SQLite | R8 — Postgres swap |
| D3-R3 / F3-R1 | low | Downwind / per-source bearing straight-line, not terrain-aware | when GeoJSON / elevation lands |
| E1-R1 | low | Leakage guard single-point at builder | K (offline sweep harness) |
| E2-R2 | low | Registry process-global | re-visit on multi-tenant |
| E3-R1 | low | `input_data_quality_score` rounded on persist | K |
| E4-R1 | low | Forecast compute-on-read cost grows with zones | J (perf pass) |
| F1-R1 | low | Threshold-trigger sweep is manual-call only | K (background scheduler) |
| F2-R1 | low | `evidence_fields` JSON shape unenforced | tighten if a consumer depends on it |

**Closed during Phase F:** none of the prior risks fully closed; Phase F added the
`app/models/attribution/` namespace under the existing Domain-peer rule.

## What Phase G will do (per `PLAN.md`)

> For each candidate intervention, estimate dust reduction, time-to-effect, production
> cost, and confidence.

Deliverables:
- Intervention library (S8) — `intervention_options` table per `data-contracts.md`
  lines 167–175. Closes D2-R2 and D-R3.
- Intervention simulator (S9) — `app/models/intervention/...` implementing
  `InterventionImpactModel` per `model-contracts.md`.
- Production cost model baseline (S10) — `ProductionCostModel`.
- Counterfactual "do nothing" comparison.
- Endpoints likely: `GET /api/v1/interventions`, `POST /api/v1/simulations/...`.

`validate-safety` will pick up `Simulation`-named schemas in `app/schemas/`
automatically (the scanner already matches that kind).

## How to resume next session

1. Read `docs/normalization_report.md` "Active phase" — should now say Phase G.
2. `git status` — clean (F.1–F.4 committed).
3. `python progress.py` — `current_phase=G`.
4. `npm run agent-check` — gate green.
5. Produce the architect-protocol plan for Phase G and stop for approval.

## Key references

- Master plan: `PLAN.md`
- Operating contract: `docs/architect_protocol.md`
- Subsystem contracts: `docs/subsystem-contracts.md` (S8, S9, S10 next)
- Data contracts: `docs/data-contracts.md` (`intervention_options`,
  `intervention_simulations` are next-up tables)
- Model contracts: `docs/model-contracts.md` (`InterventionImpactModel`,
  `ProductionCostModel` interfaces)
- Safety guardrails: `docs/safety-guardrails.md`
- Phase change log: `docs/normalization_report.md`
