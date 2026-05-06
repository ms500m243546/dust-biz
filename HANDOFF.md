# DustOps AI — Session Handoff

**As of:** 2026-05-06
**Active phase:** **Phase BD complete (BD.1-BD.4) — dispersion integration scaffolding pre-campaign + joint endpoint live.** OpenFOAM machinery (Phase BA infra + BB data + BC cleanup + BD integration) all staged and waiting on the operator's 60-72 h compute.
**Last completed:** BD.4 — `POST /api/v1/recommendations/joint` endpoint.
**Validation gate:** `npm run agent-check` GREEN, **22 PASS / 0 SKIP / 0 FAIL**. 869 backend tests + 46 web tests.

---

## Where we are

The decision-quality batch (X→AE.0) is complete. The Phase BA OpenFOAM dispersion track is fully built end-to-end except the campaign itself (operator-driven; box is running it):

| Phase | Status | What's wired |
|---|---|---|
| BA.1 | done | DMC connector + plan doc |
| BA.2 | done | SRTM `.hgt` → STL pipeline (pure-Python) |
| BA.3 | done | OpenFOAM case template (`simpleFoam` + `kinematicCloud`) with placeholder markers |
| BA.4 | done | Campaign orchestrator with Richards-Hoxey ABL |
| BA.5 | done | `DispersionMatrix` schema + storage + reduction |
| BA.6 | done | `cfd_lookup_v0.1.0` model + heuristic baseline |
| BA.10 | done | Lifespan auto-promotion |
| BB.1-BB.9 | done | Public-data scaffolds + auto-pulled OSM (8 zones + 312 haul roads) and SRTM tiles |
| BC.1-BC.4 | done | OpenFOAM cloud-block renderer, OSM persistence, YAML cleanup, STL validator |
| **BA.7 / BA.8 / BA.9 / AD.endpoint** = **BD.1-BD.4** | **done** | dispersion-driven attribution, intervention uplift, calibration sanity-band probe, joint endpoint |

## Phase BD — what landed today

| # | What | Activates when |
|---|---|---|
| **BD.1 (= BA.8)** | `app/domain/dispersion_attribution.py` — `resolve_cause_class_via_dispersion(...)` overrides Phase Z's `cause_class` with the source whose CFD-resolved footprint dominates the affected receptor under current wind. Anti-hindsight-safe `latest_wind_state` lookup. 8 tests. | `cfd_lookup_v0.1.0` promoted |
| **BD.2 (= BA.9)** | `app/domain/dispersion_intervention.py` — `compute_dispersion_uplift(...)` returns a clamped multiplier (0.5..2.0) on AP-42 impact, scaled vs `REFERENCE_COUPLING=0.10`. Simulator wires it via `_apply_dispersion_uplift_to_impact`. 9 tests. | same |
| **BD.3 (= BA.7)** | `app/domain/dispersion_calibration.py` — `decide_dispersion_promotion(matrix, receptor_observations?)` with 3 modes (deferred / calibrated / blocked). Wired into `maybe_promote_cfd_lookup`. 6 tests. | matrix exists; calibrated mode awaits ≥ 2 receptors × ≥ 100 obs |
| **BD.4** | `POST /api/v1/recommendations/joint` route + schemas (`JointSolveRequest` / `JointSolveResponse`). Calls `solve_joint_recommendations` (Phase AD solver, already shipped). 5 tests. | already (solver exists) |

## How the fully-promoted decision path looks (post-Wednesday)

When the campaign finishes and the matrix is reduced + persisted, on next API restart:

1. Lifespan sees a `DispersionMatrix` for `los-pelambres` with non-empty coefficients.
2. `decide_dispersion_promotion` returns `passed=True, mode="deferred"` (1-receptor calibration is the current ceiling).
3. `cfd_lookup_v0.1.0` is registered + flipped to `current` for the `dispersion` kind.
4. Next `generate_recommendation(...)` call:
   - `_resolve_cause_class` first asks the attribution engine, then is overridden by `resolve_cause_class_via_dispersion` if the CFD model returns a non-zero top contributor.
   - Per intervention candidate, `simulate_intervention` post-multiplies the AP-42 impact by `compute_dispersion_uplift(...)` (clamped 0.5..2.0).
   - Ranker uses Phase Z `w_cause_match`, Phase AA shift slack rescale, Phase AB context-derived risk, Phase AC temporal trigger as before — all already wired.
5. Multi-zone breach events: `POST /api/v1/recommendations/joint` resolves resource conflicts via Phase AD solver.

Nothing else needs to change. The integration is fully passive until the matrix exists, then activates.

## Tuesday operator runbook (live state)

Steps already done by BB/BC: SRTM tiles, terrain.stl, cloud blocks, OSM persistence, YAML cleanup. Tuesday is now ~6 ops-side commands:

```powershell
cd C:\Users\ignac\OneDrive\Desktop\WFLW

# (manual) wsl --install -d Ubuntu-22.04 then reboot
# (inside WSL) sudo apt-get install -y openfoam2312-default ; source ~/.bashrc

# Migration
.\.venv\Scripts\python.exe scripts\migrate_dispersion_matrices.py

# Validate STL
.\.venv\Scripts\python.exe scripts\cfd\validate_stl.py --stl cfd\los_pelambres\template\constant\triSurface\terrain.stl --strict

# Dry-run (5 min) — ALWAYS use --runs-dir off OneDrive to dodge sync races
.\.venv\Scripts\python.exe scripts\cfd\run_campaign.py `
  --regime-grid 16x3 --dry-run `
  --runs-dir=D:\openfoam-runs\los_pelambres `
  --injection-sites=data_cache\cfd\los-pelambres_injection_sites.txt `
  --receptor-samplers=data_cache\cfd\los-pelambres_receptor_samplers.txt `
  --receptor-cellzones=data_cache\cfd\los-pelambres_topo_set_cellzones.txt

# After dry-run validates, wipe + execute (60-72 h)
Remove-Item D:\openfoam-runs\los_pelambres -Recurse -Force
# Then Start-Process detached run with --execute --mesh-once and same --runs-dir + cloud blocks

# After campaign completes
.\.venv\Scripts\python.exe scripts\cfd\reduce_to_matrix.py `
  --runs-dir D:\openfoam-runs\los_pelambres `
  --mine-id los-pelambres `
  --out cfd\los_pelambres\reduced\dispersion_matrix.json

# Restart API → lifespan promotes cfd_lookup → BD.1-BD.4 activate
```

## Honest deferrals (post-campaign)

* **BA.7 calibrated-mode probe (Pearson)** — implementation gated on ≥ 2 receptors × ≥ 100 observations. Cuncumén alone is the current ceiling; SMA/SEIA scrape (BB.6) would unlock this.
* **Multi-mine dispersion** — single registry slot per `model_kind`. Per-mine `current` deferred until 2nd mine's campaign.
* **Particle-injection block tuning** — Default `parcelsPerSecond=50`, `duration=2000s`, `5 µm PM10`. May want size-distributed parcels post-calibration.
* **Receptor cylinder dimensions** — 200 m radius × 30 m tall × 2 m AGL base. Sensitivity check post-campaign.
* **DMC live-API mode** — payload-mode parser only; live mode awaits operator-registered API key.
* **SMA / SEIA scrape** — operator-portal + PDF parsing; high leverage for BA.7 multi-receptor calibration.

## Standing post-campaign priorities

1. Reduce + restart → confirm `cfd_lookup_v0.1.0` promotion in lifespan log.
2. Run the existing recommendation engine against a Los Pelambres sensor and observe `cause_class` change vs heuristic-only baseline.
3. Implement BA.7 calibrated-mode Pearson once SMA-SEIA receptors land.
4. Multi-horizon GBM training (replaces `synthesize_flat_track` placeholder used by Phase AC).

## Key references (BD block)

- **[app/domain/dispersion_attribution.py](app/domain/dispersion_attribution.py)** — BD.1 cause-class override
- **[app/domain/dispersion_intervention.py](app/domain/dispersion_intervention.py)** — BD.2 uplift computation
- **[app/domain/dispersion_calibration.py](app/domain/dispersion_calibration.py)** — BD.3 sanity-band probe
- **[app/domain/dispersion_promotion.py](app/domain/dispersion_promotion.py)** — BA.10 + BD.3 wiring
- **[app/api/routes/joint_recommendations.py](app/api/routes/joint_recommendations.py)** — BD.4 endpoint
- **[app/schemas/joint_recommendations.py](app/schemas/joint_recommendations.py)** — BD.4 schemas

## Earlier-phase references (still current)

- **[app/domain/recommendations.py](app/domain/recommendations.py)** — central decision orchestrator (Z + AA + AB + AC + BD.1 + BD.2 integrated)
- **[app/domain/joint_optimization.py](app/domain/joint_optimization.py)** — Phase AD multi-zone solver (BD.4 surfaces it)
- **[scripts/cfd/run_campaign.py](scripts/cfd/run_campaign.py)** — orchestrator
- **[docs/phase-ba-plan.md](docs/phase-ba-plan.md)** — BA-block plan
- **[docs/phase-bb-data-pulls.md](docs/phase-bb-data-pulls.md)** — BB-block runbook
