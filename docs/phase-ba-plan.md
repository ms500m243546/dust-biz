# Phase BA — Terrain-aware dispersion via offline CFD (Los Pelambres pilot)

Replaces the deferred AERMOD/CALPUFF placeholder with offline SimScale
CFD + particle tracking, reduced to source-receptor matrices and
served via realtime lookup. First implementation: Los Pelambres only.

## 10-sub-phase outline

| # | Goal | Output |
|---|---|---|
| **BA.1** | Public sensor census + connectors (SINCA + DGA + DMC) | DMC connector skeleton (this commit). Operator-manual census of Choapa-basin DGA/DMC stations follows. |
| **BA.2** | DEM acquisition (SRTM 30m / ALOS World 3D) cropped to pit + receptors + 10 km buffer | `data_seed/los_pelambres_dem.tif` + extent metadata |
| **BA.3** | SimScale campaign config — 10-sim regime grid + particle-tracking setup | YAML manifest, 10 sims |
| **BA.4** | Run the campaign + export particle-tracking results via SimScale API | Per-regime dispersion fields |
| **BA.5** | Reduce to source-receptor matrices `M[wind_dir][wind_speed_bin][stability][source_zone][receptor]` | New `DispersionMatrix` schema + per-mine artifact |
| **BA.6** | New `app/models/dispersion/cfd_lookup_v0.1.0` model layer | Realtime path: snap wind → matrix lookup → per-receptor concentration share |
| **BA.7** | 6-month bootstrap calibration vs observed PM10 + sanity-band promotion probe | Same shape as AP-42 / cycle-time deferred-mode promotion |
| **BA.8** | Sharpen Phase Z attribution with per-source contribution shares (replaces zone-type heuristic) | `cause_class` resolves to the specific source zone whose contribution dominates the affected receptor under current wind |
| **BA.9** | Wire dispersion into the intervention-impact path (replaces AP-42 distance-decay placeholder for terrain-affected paths) | Bigger deltas where pit recirculation / valley channeling matters |
| **BA.10** | Lifespan-hook auto-promotion for the dispersion model | Deferred mode falls back to AP-42 when calibration fails |

## 10-sim regime grid (BA.3)

Free-tier quota: 10 unrestricted simulations, 3000 core-hours.

* **8 wind directions** at the prevailing speed for each direction at
  Los Pelambres (drawn from ERA5 climatology over the existing 12-month
  weather corpus). Octants: N / NE / E / SE / S / SW / W / NW.
* **+ 1 high-wind extreme**: 95th-percentile speed, prevailing direction.
* **+ 1 low-wind / stable**: 5th-percentile speed, prevailing direction,
  stable boundary layer.

Total: **10 sims** ✓.

### Pasquill–Gifford rescaling (the load-bearing approximation)

Conditions that aren't simulated get analytic rescaling applied
on top of the CFD field at inference time:

* **Stability classes** (A–F) not simulated: scale plume-spread
  parameters σy / σz analytically per Pasquill–Gifford curves on
  top of the CFD-derived mean field.
* **Wind speeds** between simulated grid points: linear interpolation
  by speed magnitude.
* **Wind directions** off-grid: snap to nearest octant; document the
  snap-error per receptor in the calibration step (BA.7) so reviewers
  see the residual the lookup *can't* resolve.

If BA.7 calibration shows direction snapping is the dominant error,
the next free quota goes to filling the cardinal-direction gaps
(promote to 16-direction grid).

### Particle-tracking setup

* Lagrangian particle tracker (not passive scalar) — needed for
  size-resolved settling so PM10 and PM2.5 differ in their fates.
  Two particle classes: PM10 (D ≈ 5 µm, denser settling) and PM2.5
  (D ≈ 1 µm, near-tracer behaviour).
* Source seeding: one tracer release per `Zone` of dust-generating
  type within the bounding domain.
* Receptor sampling: bounded boxes co-located with each populated-
  place + each compliance station listed in
  `data_seed/los_pelambres.yaml`.

## Sensor census (BA.1) — operator-manual steps

The DMC connector ships in this commit (skeleton matching the ERA5 /
DGA pattern, payload-mode parser only, live mode deferred). The
actual census is network-gated and runs out-of-band:

1. **SINCA**: confirm nothing beyond the 11 stations already in
   `data_seed/los_pelambres.yaml`. Status: 1 with data
   (`lp-em05-cuncumen`), 8 registered but empty SINCA archives
   (likely SMA-filed only), 2 operator-private.
2. **DGA hydromet**: enumerate Choapa-basin stations (Cuncumén,
   Salamanca, Illapel, Limáhuida, El Tambo, etc.) and add as
   `weather_targets:` entries.
3. **DMC**: enumerate IV Region (Coquimbo) surface stations and add
   as `weather_targets:`.
4. **CR2 Explorador Climático**: optional. Gridded reanalysis-grade
   products useful for filling wind regime climatology (input to
   BA.3 prevailing-direction picks); redundant with ERA5 for
   realtime weather ingest.
5. **Beyond the 100 km radius**: skip. Adjacent provinces (Aconcagua,
   Petorca, Limarí) don't help for Los Pelambres terrain-aware
   dispersion.

Once the census is run, the operator updates
`data_seed/los_pelambres.yaml` with the new `weather_targets:` and
re-runs `python scripts/seed_public_data.py --source dmc --from-yaml`.

## Calibration (BA.7) — 6-month bootstrap

* **Train window**: months 1-6 of the existing 14-year SINCA
  Cuncumén corpus (sealed; M.4 protocol shape).
* **Validation window**: months 7-12 sealed.
* **Metric**: per-receptor MAE on observed PM10 vs predicted PM10
  (CFD lookup × AP-42 source emission). Sanity-band probe identical
  to AP-42 / cycle-time pattern: predicted concentration must fall
  within ±2σ of an analytic baseline across the test windows.
* **Promotion**: auto-promote `cfd_lookup_v0.1.0` to `current`
  dispersion model when the probe passes; fallback to AP-42
  distance-decay otherwise.
* **Honest deferral**: if Cuncumén alone provides too little spatial
  diversity for calibration (likely), surface as a partnership-
  gated blocker on the SINCA-empty receptors — the multi-receptor
  fit is what makes the dispersion matrix's per-receptor
  predictions verifiable.

## SimScale paid alternatives (reference)

If the free 10-sim quota proves binding, paid tiers (training-time
estimates; verify on simscale.com):

* **Professional**: ~$2.4-4k/yr, more core-hours, parallel runs
* **Enterprise**: $10-50k+/yr, unlimited core-hours, on-prem option

OpenFOAM is the open-source alternative — same physics free, but
self-hosted compute. Tradeoff is engineering time vs subscription.

## Deliverable order

Strict dependency: BA.1 (manual census) → BA.2 → BA.3 → BA.4 → BA.5+.
BA.5–BA.10 can interleave once the matrices exist; BA.8 / BA.9 only
need a working `cfd_lookup` model, not full multi-receptor calibration.
