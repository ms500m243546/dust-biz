# DustOps AI — Session Handoff

**As of:** 2026-05-02
**Active phase:** K — Feedback, Reporting, ROI (pending plan/approval)
**Last completed:** J — Dashboard (initial landing + post-landing deslop pass)
**Validation gate:** `npm run agent-check` GREEN, **15 PASS / 0 SKIP / 0 FAIL**, 371 backend tests + 14 web tests, 17 happy-path smoke endpoints + 3 auth-gated rejections

---

## State at handoff

- `.progress_state.json`: `current_phase=K`, `completed_phases=[A..J]`.
- Working tree clean. Two new commits since end of I:
  - `7556dfd` Phase J — Dashboard (4 operator views, web/ scaffold, web validators)
  - `e3af96d` Phase J deslop — real backend types, real /audit endpoint, KPI module
- Rollback log: `phase-j-pre-scaffold` / `phase-j-dashboard` /
  `phase-j-pre-deslop` / `phase-j-deslop`.
- `web/node_modules/` installed locally; `.gitignore` excludes it.
- Memory updated: `project_phase_j_complete.md` is the authoritative
  entry; supersedes Phase I.

## What shipped in Phase J (initial + deslop)

| Slice | Files |
|---|---|
| Web scaffold | `web/{package.json,tsconfig.json,vite.config.ts,index.html,.eslintrc.cjs,.gitignore}` |
| Wire types (deslopped against schemas) | `web/src/api/types.ts` — every Pydantic Literal exposed as a TS union |
| API client | `web/src/api/client.ts` — typed fetch wrapper, bearer token, ApiError |
| KPI aggregations | `web/src/api/kpi.ts` — pure `operationsKpis` / `executiveKpis` / `complianceKpis` |
| Auth | `web/src/auth/{AuthContext,LoginPage,ProtectedRoute}.tsx` (login → /me flow) |
| Shared components | `web/src/components/{Card,ConfidenceBadge,StaleBadge,DataQualityWarning,StatusPill,ErrorBoundary}.tsx` |
| Hooks | `web/src/hooks/useApi.ts` (initialLoading/refreshing split, payload diff short-circuit) |
| Layout + entry | `web/src/{App,main}.tsx`, `web/src/views/Layout.tsx`, `web/src/index.css` |
| Control room | `web/src/views/{ControlRoom,MapCard,SensorHealthStrip,ApproveRejectOverrideModal}.tsx` |
| Compliance | `web/src/views/{Compliance,AuditTrail}.tsx` (reads real `/audit`) |
| Operations | `web/src/views/Operations.tsx` (uses kpi module + Set-based join) |
| Executive | `web/src/views/Executive.tsx` (uses kpi module) |
| Backend addition | `app/schemas/audit.py`, `app/api/routes/audit.py` (`GET /api/v1/audit`) |
| Tests | `web/src/__tests__/{setup,client.test,components.test,kpi.test}` (14 tests, 3 files) |
| Web validators | `scripts/checks/web-{typecheck,lint,test,build}.js` + `scripts/lib/web.js` helper |
| User seeder | `scripts/seed_user.py` (one-shot CLI for creating dashboard users) |
| Compose | `docker-compose.yml` adds `web` service (`dev` profile) |

## Architecture as it stands

```
   UI (Phase J)  →  web/                         React 18 + TS strict + Vite
                     ├ App + BrowserRouter + 4 NavLink routes
                     ├ AuthProvider (token in localStorage, /me on mount)
                     ├ Card / ConfidenceBadge / StaleBadge / DataQualityWarning / ErrorBoundary
                     ├ api/{client,types,kpi}.ts  ← typed against app/schemas/
                     └ views: ControlRoom · Compliance · Operations · Executive
            │
   API   →  app/api/routes/  health · meta · auth · sensor_readings ·
            weather_readings · equipment_activity · data_quality ·
            site_config · zones · haul_road_segments · mine_state ·
            forecasts · dust_events · attributions · interventions ·
            simulations · recommendations · approvals · outcomes · audit
            (19 router groups)
            │
            app/api/dependencies/auth.py  current_user · require_role(*roles)
            │
   Domain →  app/domain/  data_quality · site_config_resolver · mine_state ·
            features · forecasting · dust_events · attribution ·
            interventions · simulation · recommendations · approvals ·
            outcomes · auth
            │
   Models →  app/models/  registry · forecasting · attribution · intervention ·
            cost · optimization
            │
   Audit  →  app/audit/writer.py  (writes audit_logs)
            │
   Storage →  app/storage/{models,repositories}/  19 repos
```

`validate-boundaries` clean across 89 Python files in 5 layered directories.
`validate-safety` tracks 11 schemas. `validate-contracts` checks 23 entities + 19 repositories.
Web validators (typecheck, lint, 14 vitest tests, vite build) all real, all green.

## Open risks carried into Phase K

| ID | Severity | Summary | K resolution |
|---|---|---|---|
| J1-R2 | low | Mine map uses synthetic grid, no GeoJSON | D3-R3 terrain-aware geometry |
| J1-R3 | low | ROI card is placeholder | Needs `site_config.cost_curves` (G3-R1) + S14 join |
| J1-R4 | low | PM thresholds hardcoded to WHO defaults in compliance view | Read from `site_config` per R2 |
| J1-R5 | low | `web/node_modules` install adds setup time | Validators self-skip cleanly when absent |
| I1-R1 | medium | Read-side endpoints still unauthenticated | K hardening pass |
| I2-R1 | low | JWT signing key rotates on process restart in dev | K — JWKS / rotation |
| I3-R1, F1-R1 | low | Approval expiry is lazy + manual sweep; no scheduler | K background scheduler |
| I3-R2 | low | `override_action` not validated against S8 catalog | tighten if a consumer depends |
| I4-R1 | medium-latent | Outcome capture is manual entry only | K — S14 join with telemetry |
| I5-R1 | low | `audit_logs` grows unbounded on SQLite | D3-R2 Postgres swap |
| H2-R1, H3-R1..R3, G4-R2, F2-R1, F3-R1..R2, E4-R1, E3-R1, E2-R1..R2, E1-R1, D3-R1..R3 | various | Carried over | K as scheduled |

**Closed during Phase J deslop:**
- **J1-R1** — real `GET /api/v1/audit` endpoint replaces client-side synthesizer.

## What Phase K will do (per `PLAN.md`)

> Close the loop: predictions vs actuals, intervention effectiveness,
> avoided shutdowns, tonnes protected, compliance reports.

Deliverables (per PLAN.md and docs/subsystem-contracts.md S14/S15):
- **S14 outcome capture & training data assembly** — full predicted-vs-actual join. Reads `dust_predictions`, `recommendations`, `recommendation_approvals`, `action_outcomes`; emits assembled training records keyed to `prediction_id` / `recommendation_id`. Failure mode: mark `outcome="unobserved"` past the window.
- **`model_performance_metrics`** table + writer per `data-contracts.md:241`.
- **S15 reports** — `GET /api/v1/reports/model-performance`, `/reports/roi`, `/reports/compliance`. Read-only over repositories.
- **ROI reports** consume `site_config.cost_curves` (closes G3-R1, J1-R3).
- **Compliance reports** read site-specific PM thresholds (closes J1-R4 in the compliance view).
- **Shadow-mode evaluation harness** usable end-to-end per `docs/model-contracts.md` model-lifecycle policy.
- **Hardening pass:**
  - Postgres swap (closes I5-R1, D3-R2).
  - Read-side auth gate (closes I1-R1).
  - JWT/JWKS rotation (closes I2-R1).
  - Background scheduler for approval expiry sweep + threshold-trigger forecast sweep (closes I3-R1, F1-R1).
  - GeoJSON contract for zone geometry (closes D3-R3, J1-R2).

Open question for the Phase K plan: split into K.1 (S14 join) → K.2 (reports) → K.3 (hardening) → K.4 (shadow-mode harness + phase advance to "MVP complete"), or land hardening alongside the feature each unblocks.

## How to resume next session

1. Read `docs/normalization_report.md` "Active phase" — Phase K.
2. `git status` — should be clean (J commits already on main).
3. `python progress.py` — `current_phase=K`.
4. `npm run agent-check` — gate green at 15/15.
5. Produce the architect-protocol plan for Phase K and stop for approval. Reference `docs/subsystem-contracts.md` S14 + S15, `docs/data-contracts.md` `action_outcomes` / `model_performance_metrics`, `docs/model-contracts.md` shadow-mode policy.

## How to run the dashboard locally (Windows)

```powershell
# Terminal 1 — backend
cd C:\Users\ignac\OneDrive\Desktop\WFLW
.\.venv\Scripts\Activate.ps1
uvicorn app.api.main:app --reload --port 8000

# Terminal 2 — frontend
cd C:\Users\ignac\OneDrive\Desktop\WFLW\web
npm run dev   # http://localhost:5173, proxies /api → :8000
```

Seed data + create a dashboard user:

```powershell
python scripts\seed_mock_data.py --mine demo --hours 6
python scripts\seed_user.py admin admin123 admin
```

Optional: POST a SiteConfig so the recommendation pipeline doesn't 404
under `require_resolved`:

```powershell
curl.exe -X POST http://localhost:8000/api/v1/site-config -H "Content-Type: application/json" -d "{\"mine_id\":\"demo\",\"site_id\":\"demo-site\",\"pm10_threshold_ugm3\":50,\"pm25_threshold_ugm3\":15}"
```

## Lessons encoded into the normalization report

- **TS wire types must be read from `app/schemas/`, not authored speculatively.** Phase J deslop was a one-shot lesson — the initial commit had wrong field names everywhere because types were invented from API names. Phase K backend additions must add the matching TS type immediately when the schema lands.

## Key references

- Master plan: `PLAN.md`
- Operating contract: `docs/architect_protocol.md`
- Subsystem contracts: `docs/subsystem-contracts.md` (S14 + S15 active in K)
- Data contracts: `docs/data-contracts.md` (`action_outcomes` rows live; `model_performance_metrics` table is K)
- Model contracts: `docs/model-contracts.md`
- UI principles: `docs/ui-principles.md` (consulted for J)
- Safety guardrails: `docs/safety-guardrails.md`
- Phase change log: `docs/normalization_report.md`
