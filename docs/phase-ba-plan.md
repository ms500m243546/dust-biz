# Phase BA — Terrain-aware dispersion via offline OpenFOAM (Los Pelambres pilot)

Replaces the deferred AERMOD/CALPUFF placeholder with offline OpenFOAM
RANS + Lagrangian particle tracking, reduced to source-receptor
matrices and served via realtime lookup. First implementation:
Los Pelambres only.

## Solver choice — OpenFOAM (decided 2026-05-04)

After SimScale free quota of 10 sims proved binding for a 16×3
regime grid, the campaign moved to OpenFOAM v2312 on a workstation.
SimScale Pro ($2.4-4k/yr) ruled out as not justified at pilot stage.

**Compute target**: AMD Ryzen 9 5900X, 12 cores / 24 threads, 32 GB
RAM, 165 GB free on C: + 477 GB on D:. WSL2 + Ubuntu 22.04 is the
target Linux runtime; OpenFOAM v2312 from `apt`. Per-run estimate
1-1.5 h at ~5M cells, 12-core parallel; 48-run campaign = 60-72 h
serial. Run dirs live on D: drive, mounted into WSL at `/mnt/d/`.

## 10-sub-phase outline

| # | Goal | Output |
|---|---|---|
| **BA.1** | DMC connector + plan doc | done — `app/ingestion/public/dmc.py`, this doc |
| **BA.2** | SRTM `.hgt` → STL terrain pipeline (pure-Python; no GDAL dep) | `scripts/cfd/dem_to_stl.py` + tests |
| **BA.3** | OpenFOAM case template — `simpleFoam` (RANS, k-ε) + `kinematicCloud` (PM10 + PM2.5 parcel classes) | `cfd/los_pelambres/template/{0,constant,system}/` + Allmesh / Allrun |
| **BA.4** | Campaign orchestrator | `scripts/cfd/run_campaign.py` — loops 48 regimes, copies template, patches BCs, drives WSL via subprocess, extracts per-receptor concentrations, `--dry-run` for CI |
| **BA.5** | Reduce runs to source-receptor matrices | `app/domain/dispersion_matrix.py`, `app/schemas/dispersion.py`, `dispersion_matrices` table + migration |
| **BA.6** | `cfd_lookup_v0.1.0` model layer | `app/models/dispersion/{__init__,distance_decay_baseline,cfd_lookup_v0_1_0}.py` |
| **BA.7** | 6-month bootstrap calibration vs observed PM10 | deferred (post-campaign) |
| **BA.8** | Sharpen Phase Z attribution with per-source contribution shares | deferred (post-campaign) |
| **BA.9** | Wire dispersion into the intervention-impact path | deferred (post-campaign) |
| **BA.10** | Lifespan auto-promotion for the dispersion model | `app/domain/dispersion_promotion.py` + `app/api/main.py` hook |

## 48-run regime grid (BA.3 / BA.4)

* **16 wind directions** at compass-octant + half-octant resolution
  (N, NNE, NE, ENE, E, …) — full 22.5° coverage. Direction sweep is
  the dominant terrain-effect driver at Los Pelambres (Choapa valley
  channels NW-SE).
* **3 wind speed bins** at 25th / 50th / 75th percentiles drawn from
  the existing 12-month ERA5 climatology over the Los Pelambres pit
  centroid.
* **1 stability class** (neutral, Pasquill class D) for the campaign;
  stable / unstable handled via analytic Pasquill–Gifford rescaling
  on top of the neutral CFD field at inference time.

Total: **48 regime runs** ≈ 60-72 h serial on the Ryzen 5900X.

If BA.7 calibration shows stability-class rescaling is the dominant
error, a follow-on campaign adds Pasquill A/B + E/F at the prevailing
direction × speed cells (~16 extra runs).

## Solver setup (BA.3)

* **simpleFoam** (RANS, steady-state, k-ε turbulence model) for the
  background flow field. Captures pit recirculation and valley
  channeling via `snappyHexMesh`-refined terrain. Mean field is what
  the lookup needs — LES eddy resolution is overkill.
* **kinematicCloud** Lagrangian particle tracker overlaid on the
  converged RANS field. Two parcel classes:
    * **PM10** — D=5 µm, density=2650 kg/m³ (mineral dust), settling
      velocity dominant; sticks to terrain on impact.
    * **PM2.5** — D=1 µm, density=2650 kg/m³, near-tracer behaviour;
      tracks the air mass.
* **Source seeding**: one particle release per dust-generating
  `Zone` in `data_seed/los_pelambres.yaml` (haul road segments,
  pit benches, dump areas, crusher feed, stockpiles). Release rate
  is irrelevant for the matrix — we normalise per unit emission
  before storing — but should be high enough that statistical
  noise is negligible (~1e6 parcels per regime).
* **Receptors**: bounded sampling boxes co-located with each
  populated place (Cuncumén, Caimanes, Salamanca, …) and each
  compliance station. `kinematicCloud` records concentration at
  these via `cloudFunctionObject`s.

## Mesh setup

* **Background mesh** (`blockMesh`): 10 km × 10 km × 3 km bounding
  box, ~50 m hex cells (~120 × 120 × 60 ≈ 0.9M base cells).
* **Terrain refinement** (`snappyHexMesh`): SRTM 30m STL surface,
  refine levels 2-4 within 200 m of terrain → ~5M total cells.
* **Domain orientation**: keep the mesh axis-aligned; rotate the
  inlet velocity vector per regime instead of rotating the mesh.
  Avoids re-meshing 48 times (mesh once, change BCs only).

## DEM pipeline (BA.2)

* **Source**: NASA SRTM 30 m (1 arc-second) `.hgt` files, public
  domain, downloadable from USGS Earth Explorer or
  `dwtkns.com/srtm30m` (no auth for the latter as a fallback).
* **Required tiles** for Los Pelambres bounding box (-71.50 to
  -70.00 lon, -32.50 to -31.00 lat): `S32W071.hgt`, `S32W072.hgt`,
  `S33W071.hgt`, `S33W072.hgt`. Operator downloads manually.
* **Pipeline**: pure-Python `.hgt` parser (NASA SRTM3 = 1201×1201
  big-endian int16 voids = -32768) → numpy elevation grid → STL
  triangulation cropped to the mine bounding box → `cfd/los_pelambres/template/constant/triSurface/terrain.stl`.
* **No GDAL / rasterio dep** — keeps the CI footprint clean. The
  pure-Python path is ~50 lines and matches the deferred-mode
  pattern used elsewhere in the codebase.

## Campaign orchestrator (BA.4)

* **Regime grid generator** — produces 48 `Regime(direction_deg,
  speed_ms, stability)` rows from the climatology JSON.
* **Per-regime steps**:
  1. `mkdir cfd/los_pelambres/runs/<regime_id>/`
  2. Copy template files into the run dir.
  3. Patch `0/U` inlet BC with `(speed * cos(dir), speed * sin(dir), 0)`.
  4. Patch `0/k`, `0/epsilon` from speed-derived ABL turbulence
     (Richards-Hoxey log law inputs).
  5. Run `wsl.exe bash -c "cd /mnt/d/.../runs/<regime_id> && ./Allmesh && ./Allrun"`.
  6. Capture exit code + log.
  7. Run `postProcessing` extraction: read per-receptor concentration
     time series, write `results.json` with `{receptor_id:
     {source_zone_id: concentration_normalised}}`.
* **Modes**:
  * `--dry-run` — stage directories + patched files, do NOT invoke
    OpenFOAM. Exercised by CI smoke test.
  * `--execute` — full run. Operator-driven, not in CI.
  * `--regime-grid {16x3,8x3,8x2}` — explicit grid override.
* **Result location**: `cfd/los_pelambres/runs/` is `.gitignore`d
  (mesh + field files balloon to GBs). Only `results.json` per
  regime is artifact-grade and gets retained out-of-tree.

## Matrix reduction (BA.5)

* **Input**: 48 `results.json` files, one per regime.
* **Output**: `DispersionMatrix` schema —
    `coefficients: dict[(dir_bin, speed_bin, stability), dict[(source_zone, receptor), float]]`
  — fraction of source emission reaching the receptor under that
  regime, normalised by source rate.
* **Persistence**: new `dispersion_matrices` table. One row per mine,
  versioned (`mine_id`, `model_version`, `created_at`,
  `coefficients` JSON, `regime_grid` JSON, `source_run_dir`).
* **Migration**: `scripts/migrate_dispersion_matrices.py` (idempotent
  ALTER TABLE pattern matching prior migrations).

## Lookup model (BA.6)

* `app/models/dispersion/cfd_lookup_v0_1_0.py` — `CFDLookupDispersionModel`.
  * `predict(source_emissions, current_wind, stability, receptor) -> concentration`
  * Snap-to-grid: nearest direction bin, linear interpolation between
    speed bins, Pasquill–Gifford analytic rescaling for stability
    classes off the trained grid.
* **Heuristic baseline** `app/models/dispersion/distance_decay_baseline.py`:
  current AP-42-shape distance × wind-alignment placeholder. Always
  registered; falls back when `cfd_lookup` isn't promoted (matches
  AP-42 / cycle-time pattern).
* **Registry**: new `model_kind = "dispersion"`. Lifespan promotes
  `cfd_lookup` over baseline iff a calibrated `DispersionMatrix`
  exists for the current mine.

## Calibration (BA.7) — deferred to post-campaign

Same shape as AP-42 / cycle-time:
* **Train window**: months 1-6 of the existing 14-year SINCA
  Cuncumén corpus.
* **Validation window**: months 7-12 sealed.
* **Sanity-band probe**: predicted PM10 (CFD lookup × AP-42 source
  emission) within ±2σ of observed across the test windows.
* **Auto-promotion**: lifespan hook flips `current` from baseline
  to `cfd_lookup` when probe passes.

If Cuncumén alone provides too little spatial diversity (likely),
surface as partnership-gated blocker on the SINCA-empty receptors
— multi-receptor fit is what makes the matrix verifiable.

## Tuesday checklist (operator-side)

1. `wsl --install` (reboots) → installs Ubuntu 22.04.
2. Inside WSL: install OpenFOAM v2312:
   ```
   sudo sh -c "wget -O - https://dl.openfoam.com/add-debian-repo.sh | bash"
   sudo apt-get install openfoam2312-default
   echo "source /usr/lib/openfoam/openfoam2312/etc/bashrc" >> ~/.bashrc
   ```
3. Manually download SRTM tiles (`S32W071.hgt`, `S32W072.hgt`,
   `S33W071.hgt`, `S33W072.hgt`) from `dwtkns.com/srtm30m` to
   `cfd/los_pelambres/dem/`.
4. `python scripts/cfd/dem_to_stl.py --tiles cfd/los_pelambres/dem/*.hgt --bbox -71.0,-32.0,-70.5,-31.5 --out cfd/los_pelambres/template/constant/triSurface/terrain.stl`.
5. `python scripts/cfd/run_campaign.py --regime-grid 16x3 --dry-run` to confirm staging.
6. `python scripts/cfd/run_campaign.py --regime-grid 16x3 --execute` to launch the 48-run campaign (~60-72 h serial). Monitor via `cfd/los_pelambres/runs/<regime>/log.simpleFoam`.
7. Once complete: `python scripts/cfd/reduce_to_matrix.py --runs-dir cfd/los_pelambres/runs/ --out dispersion_matrix.json` (BA.5 entry point) → persist via API → lifespan promotion fires on next API restart (BA.10).
8. BA.7 calibration follow-up.
