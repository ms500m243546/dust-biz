# DustOps AI — Session Handoff

**As of:** 2026-05-01
**Active phase:** K — Feedback, Reporting, ROI (pending plan/approval)
**Last completed:** J — Dashboard (single landing)
**Validation gate:** `npm run agent-check` GREEN, **15 PASS / 0 SKIP / 0 FAIL**, 371 backend tests + 9 web tests, 17 happy-path smoke endpoints + 3 auth-gated rejections, web typecheck/lint/test/build all real (not skipped)

---

## State at handoff

- `.progress_state.json`: `current_phase=K`, `completed_phases=[A..J]`.
- Working tree contains uncommitted Phase J landing (web/, scripts/checks/web-*, agent-check.js, docker-compose.yml, normalization report, .progress_state.json, handoff.md).
- Rollback log: `phase-j-pre-scaffold` snapshot taken before any Phase J edit.
- `web/node_modules/` installed locally; `.gitignore` excludes it.
- Memory at `C:\Users\ignac\.claude\projects\C--Users-ignac-OneDrive-Desktop-WFLW\memory\`
  needs an update — supersede the Phase I entry with Phase J.

## What shipped in Phase J

| Slice | Files |
|---|---|
| Scaffold | `web/package.json`, `web/tsconfig.json`, `web/tsconfig.node.json`, `web/vite.config.ts`, `web/index.html`, `web/.eslintrc.cjs`, `web/.gitignore` |
| API client | `web/src/api/client.ts`, `web/src/api/types.ts` |
| Auth | `web/src/auth/{AuthContext,LoginPage,ProtectedRoute}.tsx` |
| Shared components | `web/src/components/{Card,ConfidenceBadge,StaleBadge,DataQualityWarning,StatusPill,ErrorBoundary}.tsx` |
| Hooks | `web/src/hooks/{useApi,usePolling}.ts` |
| Layout | `web/src/views/Layout.tsx`, `web/src/App.tsx`, `web/src/main.tsx`, `web/src/index.css` |
| Control room | `web/src/views/{ControlRoom,MapCard,SensorHealthStrip,ApproveRejectOverrideModal}.tsx` |
| Compliance | `web/src/views/{Compliance,AuditTrail}.tsx` |
| Operations | `web/src/views/Operations.tsx` |
| Executive | `web/src/views/Executive.tsx` |
| Tests | `web/src/__tests__/{setup,client.test,components.test}.{ts,tsx}` (9 tests, 2 files) |
| agent-check | `scripts/checks/web-{typecheck,lint,test,build}.js` (self-skip if `web/node_modules` absent) + `scripts/agent-check.js` adds `WEB_VALIDATORS` block |
| Compose | `docker-compose.yml` adds `web` service under `dev` profile |

## Architecture as it stands

```
   UI (Phase J)  →  web/                         React 18 + TS strict + Vite
                     ├ App + BrowserRouter + 4 NavLink routes
                     ├ AuthProvider (token in localStorage)
                     ├ Card / ConfidenceBadge / StaleBadge / DataQualityWarning / ErrorBoundary
                     └ views: ControlRoom · Compliance · Operations · Executive
            │
   API   →  app/api/routes/  health · meta · auth · sensor_readings ·
            weather_readings · equipment_activity · data_quality ·
            site_config · zones · haul_road_segments · mine_state ·
            forecasts · dust_events · attributions · interventions ·
            simulations · recommendations · approvals · outcomes
            │
   Domain →  app/domain/  data_quality · site_config_resolver · mine_state ·
            features · forecasting · dust_events · attribution ·
            interventions · simulation · recommendations · approvals ·
            outcomes · auth
            │
   Models →  app/models/  registry · forecasting · attribution · intervention ·
            cost · optimization
            │
   Audit  →  app/audit/writer.py
            │
   Storage →  app/storage/{models,repositories}/  19 repos
```

`validate-boundaries` confirms zero upward imports across 88 Python files in 5 layered directories (web/ outside its scope, which is the intended `UI → API → Domain → Storage` rule).
`validate-safety` unchanged at 11 schemas tracked.
`web-typecheck` (strict tsc), `web-lint` (eslint), `web-test` (9 vitest tests), `web-build` (tsc + vite build) all green.

## Open risks carried into Phase K

| ID | Severity | Summary | Resolution |
|---|---|---|---|
| J1-R1 | low | Audit trail composes `/approvals` + `/action-outcomes` client-side; no `/audit-logs` endpoint yet | Add server-side audit endpoint alongside Postgres swap |
| J1-R2 | low | Mine map uses synthetic grid layout, no GeoJSON | D3-R3 terrain-aware geometry |
| J1-R3 | low | ROI card is placeholder | needs `site_config.cost_curves` (G3-R1) + S14 join |
| J1-R4 | low | PM thresholds hardcoded to WHO defaults in compliance view | read from `site_config` per R2 |
| J1-R5 | low | `web/node_modules` install adds setup time | validators self-skip cleanly when absent |
| I1-R1 | medium | Read-side endpoints still unauthenticated | K hardening pass |
| I2-R1 | low | JWT signing key rotates on process restart in dev | K — JWKS / rotation |
| I3-R1 | low | Approval expiry is lazy + manual sweep | F1-R1 background scheduler |
| I3-R2 | low | `override_action` not validated against S8 catalog | tighten if a consumer depends |
| I4-R1 | medium-latent | Outcome capture is manual entry only | K — S14 join with telemetry |
| I5-R1 | low | `audit_logs` grows unbounded on SQLite | D3-R2 Postgres swap |
| H2-R1, H3-R1, H3-R2, H3-R3, G4-R2, F2-R1, F1-R1, E4-R1, E3-R1, E2-R1, E2-R2, E1-R1, D3-R1, D3-R2, D3-R3 | various | Carried over | K as scheduled |

**Closed during Phase J:** none — Phase J is purely additive.

## What Phase K will do (per `PLAN.md`)

> Close the loop: predictions vs actuals, intervention effectiveness,
> avoided shutdowns, tonnes protected, compliance reports.

Deliverables (per PLAN):
- Outcome capture & training data assembly (S14) — full predicted-vs-actual join
- Model performance reports
- ROI reports (consumes `site_config.cost_curves`, closes G3-R1, J1-R3)
- Compliance reports
- Shadow-mode evaluation harness usable end-to-end
- Hardening: server-side `/audit-logs` endpoint (closes J1-R1, I5-R1), Postgres swap (closes D3-R2), read-side auth (closes I1-R1), JWT rotation (closes I2-R1), background scheduler (closes F1-R1, I3-R1)

## How to resume next session

1. Read `docs/normalization_report.md` "Active phase" — Phase K.
2. `git status` — verify Phase J landing committed.
3. `python progress.py` — `current_phase=K`.
4. `npm run agent-check` — gate green at 15/15.
5. Produce the architect-protocol plan for Phase K and stop for approval.

## How to run the dashboard locally

```bash
cd web
npm install         # one-time
npm run dev         # http://localhost:5173, proxies /api → :8000

# from another shell, run the backend:
uvicorn app.api.main:app --reload --port 8000
```

## Key references

- Master plan: `PLAN.md`
- Operating contract: `docs/architect_protocol.md`
- UI principles (drove Phase J): `docs/ui-principles.md`
- Subsystem contracts: `docs/subsystem-contracts.md` (S16 active)
- Data contracts: `docs/data-contracts.md`
- Safety guardrails: `docs/safety-guardrails.md`
- Phase change log: `docs/normalization_report.md`
