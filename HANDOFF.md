# DustOps AI — Session Handoff

**As of:** 2026-05-04
**Active phase:** **Phase BA infrastructure complete (BA.1, BA.2, BA.3, BA.4, BA.5, BA.6, BA.10).** OpenFOAM machinery end-to-end staged; awaits operator running the campaign on Tuesday.
**Last completed:** BA.10 — dispersion-model auto-promotion lifespan hook.
**Validation gate:** `npm run agent-check` GREEN, **22 PASS / 0 SKIP / 0 FAIL**. 822 backend tests + 46 web tests.

---

## What this session shipped

Solver decision: **OpenFOAM v2312** (not SimScale; free quota too tight for a 48-run regime grid). Compute target: this workstation — AMD Ryzen 9 5900X (12 cores / 24 threads), 32 GB RAM, 477 GB free on D:. WSL2 + Ubuntu 22.04 is the Linux runtime.

Per-run estimate: ~1-1.5 h at ~5M cells, 12-core parallel. **48-run campaign ≈ 60-72 h serial.**

| Sub-phase | Status | What's in tree |
|---|---|---|
| **BA.1** | done | `app/ingestion/public/dmc.py` connector skeleton + `docs/phase-ba-plan.md` |
| **BA.2** | done | `scripts/cfd/dem_to_stl.py` — pure-Python SRTM .hgt → binary STL with mosaic, bbox crop, void filling, equirectangular projection. 12 tests. |
| **BA.3** | done | `cfd/los_pelambres/template/` — full OpenFOAM case (0/, constant/, system/, Allmesh, Allrun) for `simpleFoam` RANS k-ε + `kinematicCloud` PM10/PM2.5 parcels. Placeholder markers (`__INLET_UX__`, `__PARTICLE_INJECTION_SITES__`, `__RECEPTOR_SAMPLERS__`, etc.) the orchestrator patches. |
| **BA.4** | done | `scripts/cfd/run_campaign.py` — 48-regime orchestrator. ABL inlet derivation (Richards-Hoxey k+ε), per-regime staging, optional WSL invocation. `--dry-run` (default) staged in CI; `--execute` is operator-driven. 11 tests. |
| **BA.5** | done | `app/schemas/dispersion.py`, `app/storage/models/dispersion.py` (new `dispersion_matrices` table), `app/storage/repositories/dispersion.py`, `app/domain/dispersion_matrix.py` (reduce_runs_to_matrix + persist + load), `scripts/migrate_dispersion_matrices.py`, `scripts/cfd/reduce_to_matrix.py` CLI. 7 tests. |
| **BA.6** | done | `app/models/dispersion/distance_decay_baseline.py` (heuristic always-fallback), `app/models/dispersion/cfd_lookup_v0_1_0.py` (snap-to-grid lookup with Pasquill-Gifford rescaling). 13 tests. |
| **BA.7** | deferred | Calibration probe — needs real CFD output. Methodology in `docs/phase-ba-plan.md`. |
| **BA.8** | deferred | Phase Z attribution sharpening with per-source contribution shares — needs cfd_lookup as `current`. |
| **BA.9** | deferred | Wire dispersion into intervention-impact path — same gating. |
| **BA.10** | done | `app/domain/dispersion_promotion.py` + lifespan hook. Always registers the baseline; promotes `cfd_lookup_v0.1.0` over it when a matrix exists for the pilot mine. 6 tests. |

---

## Tuesday operator runbook (verbatim from `scripts/cfd/setup_wsl_openfoam.md`)

1. **Install WSL2 + Ubuntu**: elevated PowerShell → `wsl --install -d Ubuntu-22.04`. Reboots; on first launch pick a username + password.

2. **Install OpenFOAM v2312** inside WSL:
   ```
   sudo sh -c "wget -O - https://dl.openfoam.com/add-debian-repo.sh | bash"
   sudo apt-get update
   sudo apt-get install -y openfoam2312-default
   echo "source /usr/lib/openfoam/openfoam2312/etc/bashrc" >> ~/.bashrc
   source ~/.bashrc
   ```

3. **Download SRTM tiles** for Los Pelambres bounding box from <https://dwtkns.com/srtm30m/> — `S32W071.hgt`, `S32W072.hgt`, `S33W071.hgt`, `S33W072.hgt` → drop in `cfd/los_pelambres/dem/` (gitignored).

4. **Build the STL** (Windows-side, no WSL needed):
   ```
   .venv\Scripts\python.exe scripts\cfd\dem_to_stl.py \
       --tiles cfd\los_pelambres\dem\*.hgt \
       --bbox -71.0,-32.0,-70.5,-31.5 \
       --out cfd\los_pelambres\template\constant\triSurface\terrain.stl
   ```

5. **Migrate the dev DB** (idempotent):
   ```
   .venv\Scripts\python.exe scripts\migrate_dispersion_matrices.py
   ```

6. **Dry-run the campaign**:
   ```
   .venv\Scripts\python.exe scripts\cfd\run_campaign.py --regime-grid 16x3 --dry-run
   ```
   Stages 48 run dirs under `cfd/los_pelambres/runs/` with patched BCs.

7. **Execute** (60-72 h on the 5900X):
   ```
   .venv\Scripts\python.exe scripts\cfd\run_campaign.py --regime-grid 16x3 --execute
   ```
   Each regime writes `results.json` + OpenFOAM `log.simpleFoam` to its run dir. Use `--mesh-once` to reuse the polyMesh across regimes (BCs change, mesh doesn't).

8. **Reduce to matrix**:
   ```
   .venv\Scripts\python.exe scripts\cfd\reduce_to_matrix.py \
       --runs-dir cfd\los_pelambres\runs \
       --mine-id los-pelambres \
       --out cfd\los_pelambres\reduced\dispersion_matrix.json
   ```
   This persists the matrix to the dev DB and emits the JSON artifact.

9. **Restart the API**. The lifespan hook (BA.10) detects the new matrix, registers `cfd_lookup_v0.1.0`, and promotes it over the baseline.

10. **BA.7 calibration follow-up** (next session) — sealed-test sanity-band probe vs observed PM10 at Cuncumén. If the probe passes, lock in; if it fails, surface the partnership-data blocker (Cuncumén-only spatial diversity) and iterate.

---

## Honest deferrals

* **BA.7 / BA.8 / BA.9** — gated on real CFD output. Methodology + auto-promotion path already in tree; integration into the ranker (Phase Z attribution sharpening + intervention-impact coupling) waits for a calibrated matrix.
* **Multi-mine dispersion** — single registry slot per `model_kind`; promotion is currently single-mine (Los Pelambres). Generalising to per-mine `current` is a registry-shape change deferred until a second mine's campaign lands.
* **Particle injection blocks + receptor samplers** — orchestrator currently writes empty placeholder blocks. Operator (or a follow-up phase) populates from `data_seed/los_pelambres.yaml` zones + receptors. The case mesh + solve still works without them; you just get no per-(source, receptor) statistics until they're filled.
* **Live DMC API** — connector ships payload-mode parser; live mode is `NotImplementedError` until the auth path is wired (Phase L.M.2 ERA5 convention).

---

## Standing post-Tuesday priorities (carried from earlier batches)

1. Run migrations + retrain the forecaster with `class_weight="balanced"` (Phase Y) — confirms the recall lift on real Los Pelambres data.
2. Wire the AD joint endpoint (`POST /api/v1/recommendations/joint`) — solver shipped, route is mechanical.
3. Replace `synthesize_flat_track` (AC) with multi-horizon GBM artifacts once trained.
4. Antofagasta partnership for `ActionOutcome` rows — unlocks AE.0 non-synthetic verdict, R.2/U.2/S.2 calibration, and BA.7 multi-receptor calibration.

---

## Key references (BA block)

- **[docs/phase-ba-plan.md](docs/phase-ba-plan.md)** — full plan + 10-sim regime grid (now 48-run with OpenFOAM) + Pasquill-Gifford rescaling + Tuesday checklist
- **[scripts/cfd/setup_wsl_openfoam.md](scripts/cfd/setup_wsl_openfoam.md)** — operator runbook
- **[scripts/cfd/dem_to_stl.py](scripts/cfd/dem_to_stl.py)** — BA.2 SRTM → STL pipeline
- **[scripts/cfd/run_campaign.py](scripts/cfd/run_campaign.py)** — BA.4 orchestrator
- **[scripts/cfd/reduce_to_matrix.py](scripts/cfd/reduce_to_matrix.py)** — BA.5 CLI entry
- **[cfd/los_pelambres/template/](cfd/los_pelambres/template/)** — BA.3 OpenFOAM case template
- **[app/schemas/dispersion.py](app/schemas/dispersion.py)** — DispersionMatrix + RegimeGrid
- **[app/domain/dispersion_matrix.py](app/domain/dispersion_matrix.py)** — BA.5 reduction + persistence
- **[app/models/dispersion/cfd_lookup_v0_1_0.py](app/models/dispersion/cfd_lookup_v0_1_0.py)** — BA.6 lookup model
- **[app/models/dispersion/distance_decay_baseline.py](app/models/dispersion/distance_decay_baseline.py)** — BA.6 heuristic baseline
- **[app/domain/dispersion_promotion.py](app/domain/dispersion_promotion.py)** — BA.10 auto-promotion
- **[app/storage/models/dispersion.py](app/storage/models/dispersion.py)** — `dispersion_matrices` table
- **[app/ingestion/public/dmc.py](app/ingestion/public/dmc.py)** — BA.1 DMC met connector

## Earlier-phase references (still current)

- **[app/domain/recommendations.py](app/domain/recommendations.py)** — central decision orchestrator (Z + AA + AB + AC integrated)
- **[app/models/optimization/heuristic_baseline.py](app/models/optimization/heuristic_baseline.py)** — ranker with cause-coupling (Z), shift-slack rescale (AA), context-derived risk (AB), temporal trigger (AC)
- **[app/domain/joint_optimization.py](app/domain/joint_optimization.py)** — AD multi-zone solver
- **[app/domain/continuous_knob_spike.py](app/domain/continuous_knob_spike.py)** — AE.0 framework
- **[docs/bias-register.md](docs/bias-register.md)** — 10 numbered biases mitigated through B-47
