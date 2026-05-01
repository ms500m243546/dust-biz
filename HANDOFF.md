# DustOps AI — Session Handoff

**As of:** 2026-05-01
**Active phase:** H — Recommendation Engine (pending plan/approval)
**Last completed:** G — Intervention Simulation (G.1 → G.4)
**Validation gate:** `npm run agent-check` GREEN, 11/11, 278 tests, 15 smoke endpoints

---

## State at handoff

- `.progress_state.json`: `current_phase=H`, `completed_phases=[A,B,C,D,E,F,G]`.
- Working tree: clean after Phase G commits (G.1–G.4 each on `main`).
- Rollback log: all D.*, E.*, F.*, G.* pre/post snapshots present.
- Memory at `C:\Users\ignac\.claude\projects\C--Users-ignac-OneDrive-Desktop-WFLW\memory\`
  needs an update — supersede the Phase F entry with Phase G.

## What shipped in Phase G

| Step | Subsystem | Snapshots (pre / post) | Key files |
|---|---|---|---|
| G.1 | Intervention library (S8) | `phase-g1-pre-interventions` / `phase-g1-interventions` | `app/schemas/interventions.py`, `app/storage/{models,repositories}/interventions.py`, `app/domain/interventions.py` (default catalog + `seed_default_interventions` + `require_known`), `app/api/routes/interventions.py` |
| G.2 | InterventionImpactModel heuristic (S9) | `phase-g2-pre-impact-model` / `phase-g2-impact-model` | `app/schemas/simulations.py` (Impact + Cost + joined Simulation schemas), `app/models/intervention/heuristic_baseline.py` (`intervention_impact_heuristic_v0.1.0`) |
| G.3 | ProductionCostModel heuristic (S10) | `phase-g3-pre-cost-model` / `phase-g3-cost-model` | `app/models/cost/heuristic_baseline.py` (`production_cost_heuristic_v0.1.0`) |
| G.4 | Orchestrator + ORM + API + smoke + phase advance | `phase-g4-pre-api` / `phase-g4-api-routed` | `app/storage/models/simulations.py`, `app/storage/repositories/simulations.py`, `app/domain/simulation.py`, `app/api/routes/simulations.py` |

## Architecture as it stands

```
   UI (Phase J, not started)
            │
   API   →  app/api/routes/  health · meta · sensor_readings · weather_readings ·
            equipment_activity · data_quality · site_config · zones ·
            haul_road_segments · mine_state · forecasts · dust_events ·
            attributions · interventions · simulations
            │
   Domain →  app/domain/  data_quality · site_config_resolver · mine_state ·
            features · forecasting · dust_events · attribution ·
            interventions · simulation
            │
   Models →  app/models/  registry · forecasting/heuristic_baseline ·
            attribution/rules_baseline · intervention/heuristic_baseline ·
            cost/heuristic_baseline
            │
   Storage →  app/storage/models/  Mine · Zone · HaulRoadSegment · Sensor · Equipment ·
            SensorReading · WeatherReading · EquipmentActivity · IngestError ·
            SiteConfiguration · MineStateSnapshot · FeatureRecord · DustPrediction ·
            DustEvent · SourceAttribution · InterventionOption · InterventionSimulation
            app/storage/repositories/  14 repos
```

`validate-boundaries` confirms zero upward imports across 66 Python files in 5 layered directories.
`validate-safety` is **active**: 4 safety-relevant schemas tracked
(`DustForecastSchema`, `ForecastTargetSchema`, `SourceAttributionSchema`,
`InterventionSimulationSchema`), all required guardrail fields present.

## Open risks carried into Phase H

| ID | Severity | Summary | Resolution phase |
|---|---|---|---|
| D2-R1 / E4-R2 / F4-R1 / G4-R1 | low | Admin / forecast / attribution / simulation endpoints unauthenticated | I |
| D3-R1 / E2-R1 / F3-R2 / G2-R1 / G3-R1 | medium-latent | Heuristic / rule / impact / cost coefficients uncalibrated | K |
| D3-R2 | low | Snapshot writes per request stress SQLite | R8 — Postgres swap |
| D3-R3 / F3-R1 | low | Downwind / per-source bearing straight-line, not terrain-aware | when GeoJSON / elevation lands |
| E1-R1 | low | Leakage guard single-point at builder | K (offline sweep harness) |
| E2-R2 | low | Registry process-global | re-visit on multi-tenant |
| E3-R1 | low | `input_data_quality_score` rounded on persist | K |
| E4-R1 | low | Forecast compute-on-read cost grows with zones | J (perf pass) |
| F1-R1 | low | Threshold-trigger sweep is manual-call only | K (background scheduler) |
| F2-R1 | low | `evidence_fields` JSON shape unenforced | tighten if a consumer depends on it |
| G3-R2 | low | Default effective duration = 2x time-to-effect (rule of thumb) | when intervention plan API lands |
| G4-R2 | low | Zone-target forecast lookup uses most-recent without staleness check | J (forecast staleness surfaced in dashboard) |

**Closed during Phase G:**
- **D2-R2** — zone `allowed_interventions` / `requires_approval_for` IDs
  validated against the catalog at zone upsert.
- **D-R3** partial — `intervention_constraints` JSON shape itself remains
  free-form, but its keys (intervention IDs) are now validated whenever a
  consumer looks them up via `require_known`. Full schema enforcement
  deferred to H/J.

## What Phase H will do (per `PLAN.md`)

> Choose the lowest-cost effective intervention. Rank alternatives.
> Prioritize compliance when risk is extreme.

Deliverables:
- Production-aware optimization engine (S11) implementing
  `OptimizationEngine` per `model-contracts.md`.
- Recommendation engine (S12) producing the recommendation template.
- Compliance-priority logic (Guardrail 7): when breach probability >=
  configurable extreme threshold (default 0.85), shift weights toward
  compliance and surface the shift in the recommendation reason.
- Per-site risk-tolerance configuration via existing `SiteConfig`
  optimization weights.
- Endpoints likely: `GET /api/v1/recommendations/current`
  (already pending in smoke), `GET /api/v1/recommendations/{id}`,
  `GET /api/v1/recommendations` history.

`validate-safety` will activate G2/G3/G15 enforcement on
`RecommendationSchema` (currently no Recommendation-named schema
exists; landing one in H is what flips the scanner from 4 → 5
tracked schemas).

## How to resume next session

1. Read `docs/normalization_report.md` "Active phase" — Phase H.
2. `git status` — clean (G.1–G.4 committed).
3. `python progress.py` — `current_phase=H`.
4. `npm run agent-check` — gate green.
5. Produce the architect-protocol plan for Phase H and stop for approval.

## Key references

- Master plan: `PLAN.md`
- Operating contract: `docs/architect_protocol.md`
- Subsystem contracts: `docs/subsystem-contracts.md` (S11, S12 next)
- Data contracts: `docs/data-contracts.md` (`recommendations` table next)
- Model contracts: `docs/model-contracts.md` (`OptimizationEngine` interface)
- Safety guardrails: `docs/safety-guardrails.md` (Guardrails 1, 3, 6, 7, 15
  all pin Phase H behavior)
- Phase change log: `docs/normalization_report.md`
