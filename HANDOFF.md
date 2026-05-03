# DustOps AI — Session Handoff

**As of:** 2026-05-02
**Active phase:** L.7a complete — SINCA pipeline verified live against real portal; 12 months of Cuncumén PM10 hourly data persisted; single-station reality documented for Los Pelambres
**Last completed:** L.7a — SINCA URL/parser rewritten on real portal evidence + batch-from-yaml orchestrator + first real-data ingest
**Validation gate:** `npm run agent-check` GREEN, **17 PASS / 0 SKIP / 0 FAIL**, 499 backend tests + 14 web tests

---

## State at handoff

- `.progress_state.json`: `current_phase=L-complete`, `completed_phases=[A..L]` (L.7a is a sub-phase of L.7, not a new top-level phase).
- L.7a commit log on `main`:
  - `<L.7a>` Phase L.7a — verify SINCA URL pattern live, rewrite parser for real 6-col format, add `--from-yaml` batch orchestrator, persist 12 months of Cuncumén PM10 to dustops.db.
- Rollback log adds: `phase-l7-pre-sinca-pull`, `phase-l7-sinca-rewrite`, `phase-l7-yaml-expand`, `phase-l7-yaml-data-status`, `phase-l7-from-yaml`.
- Memory updated: `project_phase_l7_complete.md` superseded by `project_phase_l7a_complete.md`.

---

## What shipped in L.7a

### SINCA URL pattern verified empirically

The `build_url` from the original L.7 phase was wrong on **four axes** — it had been written from a WebFetch summary, not from the real portal. Fixes after live probing:

| Axis | Was | Now |
|---|---|---|
| Endpoint | `apub.tsindico2.cgi?macro=...&from=YYYYMMDD` | unchanged endpoint, but: |
| Macro structure | `./RM/<station>/Cal/<PARAM>` | `./<region_path>/<station>/Cal/<PARAM>/<PARAM>.<resolution>.<resolution>.ic` |
| Date format | `YYYYMMDD` | `YYMMDDHH` (`from` anchored 00, `to` anchored 23) |
| Region path | hardcoded `RM` | parametric `region_path` arg (RM / RIV / RV / ...) |
| Resolution | n/a | new `resolution` arg: `horario` (hourly) or `diario` (daily) |

The fully-verified URL for Cuncumén PM10 hourly:
```
https://sinca.mma.gob.cl/cgi-bin/APUB-MMA/apub.tsindico2.cgi
  ?outtype=xcl
  &macro=./RIV/424/Cal/PM10/PM10.horario.horario.ic
  &from=25050100&to=26050123
```

### Parser rewritten for real 6-column SINCA format

The L.7 parser assumed `FECHA YYYY-MM-DD HH:MM;VALOR;VALIDADO`. The real format from `tsindico2.cgi?outtype=xcl` is six semicolon-separated columns with only the first two labeled in the header:

```
FECHA (YYMMDD);HORA (HHMM);
260425;0100;;24;;            <- recent: validated value at col 3
260425;0400;;;0;             <- raw fallback at col 4
250521;2000;23;;;            <- older: pre-validated value at col 2
260429;1700;;;;              <- sensor outage (all empty)
```

Column semantics (inferred empirically across a 12-month Cuncumén dump):

| Col | Meaning |
|---|---|
| 0 | FECHA (YYMMDD) |
| 1 | HORA (HHMM) — `0000` for daily-resolution exports |
| 2 | pre-validated value; populated for the most-recent ~year |
| 3 | validated value; promoted from col 2 ~1 week after collection |
| 4 | raw / non-validated fallback |
| 5 | trailing empty padding |

Parser priority: col 3 → col 2 → col 4. `validated=True` only when source is col 3.

### `--from-yaml` batch orchestrator

`scripts/seed_public_data.py --from-yaml data_seed/los_pelambres.yaml` reads every sensor with a non-null `sinca_station_code`, fans out one HTTP request per sensor, and continues past per-station failures. New flags:

- `--from-yaml PATH` — drive a batch from an RCA-seed YAML
- `--include-empty` — also pull sensors flagged `sinca_data_status: no_published_data` (default: skip)
- `--resolution {horario,diario}` — for single-station mode; ignored under `--from-yaml`

YAML now carries per-sensor `sinca_region_path`, `sinca_resolution`, and `sinca_data_status` fields (purely metadata to the loader; consumed by the orchestrator).

### Single-station reality at Los Pelambres

Empirical probe of every Choapa-province SINCA station discovered that **only Cuncumén (424) publishes actual data**. All 8 other stations near Los Pelambres are registered in the SINCA portal with valid macropath schemas but return all-empty CSVs over 5+ year windows:

| Station | SINCA code | sinca_data_status |
|---|---|---|
| Cuncumén (Salamanca) | 424 | `has_data` (hourly + daily) |
| Caimanes (Los Vilos) | 407 | `no_published_data` |
| El Mauro (Los Vilos) | 406 | `no_published_data` |
| Coirón (Salamanca) | 404 | `no_published_data` |
| Camisas (Salamanca) | 405 | `no_published_data` |
| Hotel Mina (Salamanca) | 401 | `no_published_data` |
| Quelen Alto (Salamanca) | 409 | `no_published_data` |
| Chacay (Los Vilos) | 402 | `no_published_data` |
| Punta Chungo (Los Vilos) | 408 | `no_published_data` |

These are likely paper-compliance stations whose actual readings flow through SMA SEIA filings or operator audits rather than the public portal. Real coverage of Los Pelambres receptors will require either (a) the operator partnership for Antofagasta-direct telemetry (already known per L7-R5), (b) SMA SEIA report scraping, or (c) alternate networks (CAMS / MODIS / aggregators).

### First real-data ingest

`dustops.db` now holds **8617 PM10 hourly readings** for `lp-em05-cuncumen` covering 2025-05-01 01:00 → 2026-05-02 00:00 (~98.4% of nominal 8760 hours; ~143 hours of sensor outage spread across the year). Average `source_quality_hint` 0.900 (regulator-grade EMRPM).

---

## Open work / next steps

| ID | Severity | Summary | Resolution |
|---|---|---|---|
| L7a-R1 | medium | Only 1 of 9 nearby SINCA stations has real data; receptor coverage of Los Pelambres is sparse via SINCA alone | Pursue Antofagasta partnership (operator_real adapter) or SMA SEIA report scraping |
| L7a-R2 | low | Full historical Cuncumén pull (2012-04-01 → present, ~14 years × 8760 hrs ≈ 122K records) not yet performed | Run as overnight batch — orchestrator already supports it; just widen `--from`/`--to` |
| L7a-R3 | low | `sinca_resolution`, `sinca_region_path`, `sinca_data_status` in YAML are metadata-only — not stored in the Sensor schema | Schema migration deferred; orchestrator reads YAML directly, which is fine for now |
| L7a-R4 | low | Cuncumén PM2.5 not yet pulled (separate macro: `PM2.5.horario.horario.ic`) | Add a second sensor row + run the orchestrator |
| L5-carryover | medium-latent | Equipment-side ingest (Los Pelambres telematics) is the bottleneck for honest training | `operator_real` adapter wired since L.5; needs partnership data flow |

**Concrete next session priorities:**

1. **Overnight full-history Cuncumén pull** — 2012-04-01 → 2026-05-02 hourly (~122K records). Single command, just widen the window.
2. **Cuncumén PM2.5 pull** — add a `lp-em05-cuncumen-pm25` sensor row (or pivot to multi-parameter per sensor) and re-run `--from-yaml`.
3. **AQICN failover adapter (Phase L.8)** — small (~50 LOC) parallel source; useful when SINCA portal is down. Tag `source_quality_hint=0.7` (re-aggregated).
4. **CAMS adapter (Phase L.9)** — Copernicus model-grid PM10/PM2.5 every 3h on a 0.4° grid. Fills the spatial gaps where Los Pelambres receptors lack SINCA data.
5. **MODIS AOD adapter (Phase L.10)** — NASA Earthdata; ~1km daily aerosol optical depth as an independent cross-check.
6. **SMA SEIA report parser (Phase L.11)** — likely the only path to historical receptor data for Caimanes / El Mauro / etc. PDF parsing required.

---

## How to run the overnight full-history pull

```bash
# Cuncumén only (the only station with data); ~14 years of hourly
.venv/Scripts/python.exe scripts/seed_public_data.py --source sinca \
    --from-yaml data_seed/los_pelambres.yaml \
    --from 2012-04-01 --to 2026-05-02

# Or one station explicitly
.venv/Scripts/python.exe scripts/seed_public_data.py --source sinca \
    --station 424 --region-path RIV --resolution horario \
    --station-name "Cuncumen" --region "Coquimbo" --commune "Salamanca" \
    --longitude -70.701 --latitude -31.971 --tier EMRPM \
    --parameter pm10 --from 2012-04-01 --to 2026-05-02 \
    --sensor-id lp-em05-cuncumen
```

Disk cache lives at `data_cache/sinca/`; re-runs are free after the first fetch. Persists into `dustops.db`.

---

## Key references

- **`app/ingestion/public/sinca.py`** — `build_url` + `parse_sinca_csv` (verified empirically on 2026-05-02)
- **`scripts/seed_public_data.py`** — orchestrator with single-station + `--from-yaml` modes
- **`data_seed/los_pelambres.yaml`** — RCA seed with `sinca_data_status` annotations per station
- **`tests/ingestion/fixtures/sinca_cuncumen_pm10.csv`** — captured real SINCA response (3KB, 1 week)
- **`docs/data-source-registry.md`** — contract for every public source
- **`docs/rca-seed.md`** — RCA provenance for Los Pelambres + Los Bronces
- **Model contracts:** `docs/model-contracts.md` (lifecycle step 5 shadow-evaluation now usable against real Cuncumén history)
