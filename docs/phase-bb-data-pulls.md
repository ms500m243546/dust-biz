# Phase BB — pre-Tuesday data pulls

While the Phase BA OpenFOAM machinery is staged and waiting for the
operator's Tuesday workstation slot, BB pulls in adjacent public data
that lifts the BA.7 calibration ceiling and enriches the recommendation
engine's spatial inputs.

## Status

| # | Source | Status | What landed |
|---|---|---|---|
| BB.1 | OSM Overpass — Los Pelambres mine geometry | **Done (auto)** | `data_cache/osm/los-pelambres.{raw,parsed}.json` — 8 mine zones (pit polygons) + 312 haul-road segments |
| BB.2 | NASA SRTM v3 30 m tiles + STL | **Done (auto)** | 4 tiles in `cfd/los_pelambres/dem/`, terrain.stl built (1.04M tris, 50 MB, ±9.5 km buffer around pit) |
| BB.3 | DGA hydromet (Choapa basin) | Scaffolded | `data_cache/dga/choapa_census.json` — 5 stations registered; CSV export gated on operator session at snia.mop.gob.cl |
| BB.4 | DMC IV Region surface stations | Scaffolded | `data_cache/dmc/iv_region_census.json` — 5 stations; API key gated at climatologia.meteochile.gob.cl |
| BB.5 | Global Wind Atlas | Placeholder + manual | ERA5-derived climatology placeholder dropped; GWA 250 m export gated on operator portal walk |
| BB.6 | SMA / SEIA Antofagasta filings | Scaffolded | Receptor registry written; PDF parser stub (waits on operator-collected PDFs) |
| BB.7 | INE populated-places (Los Pelambres receptors) | **Done (best-effort)** | 6-receptor registry with verified or approximate coords; replaces RCA TODOs locally |
| BB.8 | Sentinel-5P TROPOMI AOD | Scaffolded | Receptor sample points; openEO + Copernicus auth gated |

Auto-pulled artifacts under `data_cache/` and `cfd/los_pelambres/dem/`
are gitignored; the *scripts* that produce them are committed and can
re-run anywhere.

## What each unblocks

* **BB.1 (OSM)** — real `Zone.geometry` polygons for haul roads, dump
  areas, pit boundary. Phase BA.3's `cloudProperties` injection
  sites can now be populated from real polygons instead of empty
  placeholders. Lift: turns the campaign from "domain-wide release"
  into "per-zone source-receptor matrix" — the load-bearing input
  for BA.5 reduction.

* **BB.2 (SRTM)** — Tuesday's steps 3-4 done early. Operator can open
  the 50 MB STL in any 3D viewer (MeshLab / ParaView) before
  committing 60-72 h of compute to it.

* **BB.7 (INE)** — three Los Pelambres receptors (lp-el-manzano,
  lp-chillepin, lp-coiron) had `TODO_FROM_RCA` placeholders in
  `data_seed/los_pelambres.yaml`. The registry script now fills them
  with verified-or-approximate coords flagged for INE replacement.
  Without these, the BA.3 receptor sampling boxes would skip those
  three communities.

* **BB.3 / BB.4 (DGA / DMC)** — when ingested, these lift the regime
  climatology that drives BA.3's wind-speed percentile picks. ERA5
  + Open-Meteo cover us today; DGA + DMC are the cross-check.

* **BB.5 (Global Wind Atlas)** — better than ERA5 for terrain-
  resolved wind regime stats (250 m vs 28 km cell). Drives BA.3
  speed-bin picks. Placeholder ships now; real GWA export is a
  ~10-minute manual task post-Tuesday.

* **BB.6 (SMA / SEIA)** — the load-bearing one for BA.7. 8 of 11
  Los Pelambres receptors have empty SINCA archives but real PM10
  flows through SMA enforcement filings. Even recovering 2-3 lifts
  the multi-receptor calibration from 1-station to 4-station
  spatial diversity.

* **BB.8 (Sentinel-5P TROPOMI)** — independent AOD time series at
  receptor coordinates. Cross-validation channel post-BA.7
  promotion: if the dispersion matrix says high PM10 at receptor X
  under regime Y but TROPOMI says no AOD signal, the matrix is
  suspect.

## What ran in this session vs what waits on the operator

**Auto (this session)**:
* `python scripts/data_pull/fetch_osm_mine.py` — 18,618 OSM elements parsed; 8 zones + 312 haul roads.
* `python scripts/cfd/fetch_srtm.py` — 4 tiles, ~104 MB on disk.
* `python scripts/cfd/dem_to_stl.py` with `--bbox=-70.62,-31.83,-70.42,-31.63` — 50 MB STL.
* `python scripts/data_pull/global_wind_atlas_export.py --emit-template` — climatology placeholder.
* `python scripts/data_pull/{dga_choapa_census,dmc_iv_region_census,sma_seia_los_pelambres,ine_los_pelambres_receptors,sentinel5p_aod}.py` — registries.

**Operator follow-ups (post-Tuesday or whenever)**:
1. **DGA**: portal export from snia.mop.gob.cl per the Choapa registry.
2. **DMC**: register for an API key, write a fetch driver around the existing payload-parser.
3. **GWA**: 10-minute manual export at the pit centroid; replace the ERA5 placeholder.
4. **SMA / SEIA**: the high-leverage one. Antofagasta SEIA expediente walk + PDF download. Then implement the `pdfplumber` extractor in `scripts/data_pull/sma_seia_los_pelambres.py --parse`.
5. **Sentinel-5P**: register at dataspace.copernicus.eu, run an openEO extraction in a separate venv.

## Tuesday checklist amendment

`scripts/cfd/setup_wsl_openfoam.md` steps 3 + 4 are already done
(SRTM tiles + terrain.stl). Tuesday becomes:

1. `wsl --install -d Ubuntu-22.04` (reboots).
2. apt-install OpenFOAM v2312 inside WSL.
3. `python scripts/migrate_dispersion_matrices.py` (one-time DB migration).
4. `python scripts/cfd/run_campaign.py --regime-grid 16x3 --dry-run` — sanity check.
5. `python scripts/cfd/run_campaign.py --regime-grid 16x3 --execute` — kicks the 60-72 h campaign.
6. `python scripts/cfd/reduce_to_matrix.py --runs-dir cfd/los_pelambres/runs --mine-id los-pelambres --out cfd/los_pelambres/reduced/dispersion_matrix.json`.
7. Restart API. Lifespan auto-promotes `cfd_lookup_v0.1.0`.

(Original steps 3-4 — SRTM + STL — already executed in BB.)
