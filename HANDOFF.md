# DustOps AI — Session Handoff

**As of:** 2026-05-02
**Active phase:** L-complete (training-data ingest pipeline ready)
**Last completed:** L — Public-data ingest pilot (Chile)
**Validation gate:** `npm run agent-check` GREEN, **16 PASS / 0 SKIP / 0 FAIL**, 486 backend tests + 14 web tests

---

## State at handoff

- `.progress_state.json`: `current_phase=L-complete`,
  `completed_phases=[A..L]`.
- Working tree clean. Phase L commits since MVP-complete:
  - `<L.1>` Phase L.1 — Data-source registry + receptor schema + connector scaffold
  - `<L.2>` Phase L.2 — SINCA connector
  - `<L.3>` Phase L.3 — Weather connectors (ERA5 / DGA / Open-Meteo)
  - `<L.4>` Phase L.4 — OSM mine geometry + INE populated places + RCA seed doc
  - `<L.5>` Phase L.5 — `operator_real` source hook + fleet calibration
  - `<L.6>` Phase L.6 — Per-station thresholds + first model_performance_metrics row
- Rollback log: `phase-l1-pre`, `phase-l1-registry`, `phase-l2-sinca`,
  `phase-l3-weather`, `phase-l4-osm-ine-rca`, `phase-l5-operator-real`,
  `phase-l6-station-thresholds`.

## Strategic priority pinned

DustOps targets **Chilean copper mines with adjacent towns**. Pilot is
**Los Pelambres** (insider access path via the new `operator_real`
source discriminator); #2 is **Los Bronces** (Andes, 3,500 m, ERA5
load-bearing because surface met under-represents the operating regime).

## What shipped in Phase L

### L.1 — Registry + receptor scaffold
- `docs/data-source-registry.md` — canonical inventory of every public
  source (SINCA / community stations / ERA5 / DGA / Open-Meteo / OSM /
  INE / SEA / SMA / CMF), license table, refresh cadence policy
- `app/schemas/receptor.py` + `PopulatedPlace` ORM + repository — population
  exposure as a first-class layer
- `app/ingestion/public/__init__.py` — `Connector` protocol (pure fetcher,
  no DB writes)
- `app/ingestion/public/cache.py` — disk cache keyed by
  (source, window, filter-hash)
- `scripts/checks/validate-data-sources.js` — registry/connector drift
  protection; agent-check now 16/16

### L.2 — SINCA
- `app/ingestion/public/sinca.py` — parses MMA's CSV format (semicolon
  delimiter, European decimal commas, `S/I` / `NA` sentinel rows,
  `validated` flag)
- Maps to K.2-compatible `pm10_ugm3` / `pm25_ugm3` keys
- Quality hint: regulator-grade EMRPM stations → 0.9, indicative → 0.7
- Fixture: Cuncumén (Los Pelambres receptor) — closest community
  monitor to the El Mauro tailings dam

### L.3 — Weather (ERA5 + DGA + Open-Meteo)
- `app/ingestion/public/era5.py` — primary for high-altitude mines.
  Combines u10/v10 wind components into speed + meteorological "from"
  direction. Parses pre-extracted JSON (orchestrator handles
  cdsapi/xarray)
- `app/ingestion/public/dga.py` — Chilean hydromet for valley receptors
- `app/ingestion/public/open_meteo.py` — global free fallback. Tagged
  CC-BY-NC; **production must swap to ERA5**

### L.4 — OSM + INE + RCA seed
- `app/ingestion/public/osm_mine.py` — Overpass parser. Classifies ways
  (`landuse=quarry` → pit Polygon; `highway=service service=mine` →
  haul-road LineString). Closes unclosed pit rings per K.3 GeoJSON contract
- `app/ingestion/public/ine_populated_places.py` — parses INE place
  exports + computes haversine distance + initial bearing from each
  mine centroid; output validates against `PopulatedPlaceSchema`
- `docs/rca-seed.md` — provenance for **Los Pelambres** (RCA 38/1997
  + El Mauro consent + Caimanes case + supreme court rulings) and
  **Los Bronces** (RCA 391/2007 + 2020 Integrado rejection at Comité
  de Ministros + Santiago PPDA stricter regime). Cites SEA / SMA URLs

### L.5 — Operator-real hook
- `app/ingestion/fleet_specs.py` — `FleetSpec` calibrated to public
  OEM data (CAT 793F: 218t / 20–40 km/h; Komatsu 930E: 290t; CAT 6030
  shovel: 37t/pass). Sources cited
- `app/ingestion/operator_real.py` — format-agnostic adapter with
  `FieldMap` (dotted-path lookups for nested operator JSON).
  Discriminator `"operator_real"`; sensor records get
  `source_quality_hint=1.0`
- This is the slot Los Pelambres insider data lands in — **domain
  layer doesn't know whether the data is SINCA / mock / operator_real**

### L.6 — Per-station thresholds + first metrics row
- `StationThresholdOverride` ORM + repo + schema — per-sensor PM
  threshold overrides for RCA-mandated stricter community-receptor
  limits (Cuncumén / Caimanes / Salamanca / Las Condes / Lo Barnechea)
- `build_compliance_report` in `app/domain/reports.py` extended with a
  `station_overrides` parameter; missing entries fall back to site
  defaults; `None` values inside an override fall back per-field
- `tests/integration/test_training_pipeline_e2e.py` — proves the full
  pipeline (predictions → recommendations → approvals → outcomes →
  K.1 join → K.1 aggregator → persisted `model_performance_metrics`
  row) works end-to-end. **First real metrics row deliverable.**

## Architecture as it stands

```
   UI (J)    →  web/                          React 18 + TS strict
   API (K.3) →  31 router groups, all auth-gated except health/meta/auth
   Domain    →  ... + reports + shadow_mode + scheduler + training_data + model_performance
   Ingestion →  app/ingestion/
                ├ public/                     L.1+ Connector protocol
                │   ├ sinca.py                L.2 — Chile MMA PM
                │   ├ era5.py / dga.py / open_meteo.py    L.3 — weather
                │   ├ osm_mine.py             L.4 — pit + haul-road geometry
                │   ├ ine_populated_places.py L.4 — receptor metadata
                │   └ cache.py                L.1 — disk cache
                ├ operator_real.py            L.5 — partner data slot
                ├ fleet_specs.py              L.5 — OEM calibration
                └ mock_streams.py             B.5 — dev/test fallback
   Storage   →  21 repositories + alembic-ready settings (K.3)
```

`validate-contracts` checks 32 entities + 22 repositories. The
`validate-data-sources` check enforces the registry doc and the
connector modules stay in sync.

## Open work

| ID | Severity | Summary | Notes |
|---|---|---|---|
| L1 | low | SINCA connector's live HTTP path is intentionally not in this module | Wire from orchestrator script when partner data arrives |
| L2 | low | Open-Meteo CC-BY-NC license blocks production deployment | Swap to ERA5 (commercial-safe) before any paying customer |
| L3 | medium | RCA digitization in `docs/rca-seed.md` is provenance only — actual `SiteConfiguration` + `StationThresholdOverride` rows must be hand-loaded by the orchestrator | Two-person review per mine; cite source URL on every row |
| L4 | low | Pit centroids in `rca-seed.md` are approximate placeholders | Replace with surveyed values when partnership lands |
| L5 | medium-latent | The K.6 integration test seeds synthetic data; no real-data round-trip yet | First real round-trip happens when the orchestrator writes a SINCA fetch into the DB and the K.1 evaluator runs against it |
| K1-R1 | low | Recommendation.linked_prediction_ids JSON-list scan | Resolves with Postgres GIN index |

## How to resume next session

1. `python progress.py` → `current phase: L-complete`.
2. `npm run agent-check` → `16 PASS / 0 SKIP / 0 FAIL`.
3. **Next concrete step (operator decides):**
   - **(a) First real SINCA pull** — write the orchestrator HTTP shim
     in `scripts/seed_public_data.py`, hit Cuncumén EMRPM for the
     last 24h, persist via `RawSensorReadingSchema`, observe the
     records appear in the existing K.2 compliance report.
   - **(b) First real ERA5 pull** — register a Copernicus CDS account,
     download a NetCDF for the Los Pelambres bounding box, run the
     pre-extract step, feed JSON to `app/ingestion/public/era5.py`.
   - **(c) Partner data onboarding for Los Pelambres** — once contracts
     allow, define a `FieldMap` for the operator's dispatch system
     and start replaying historical telematics through
     `app/ingestion/operator_real.py`.
   - **(d) Hand-digitize the first batch of RCA receptor rows** for
     Los Pelambres + Los Bronces (orchestrator script + provenance
     review).
4. The K.1 metric scoreboard becomes load-bearing the moment **any** of
   (a)–(d) flow through the existing pipeline.

## Lessons encoded

- **License obligations live in the registry doc, not the connector
  code.** The dashboard footer must surface OSM / Copernicus / INE
  attributions when L.4 data appears in the UI.
- **Connectors are pure parsers.** Live HTTP is the orchestrator's
  job — keeps tests deterministic and connectors swappable per
  source format.
- **`source_quality_hint` is the L-era reliability signal.** SINCA
  EMRPM = 0.9, indicative = 0.7, operator_real = 1.0, mock = 0.9.
  S2 data-quality propagates this into downstream confidence.

## Key references

- Master plan: `PLAN.md` (Phase L documented in `docs/normalization_report.md` change log)
- Operating contract: `docs/architect_protocol.md`
- Data-source registry: `docs/data-source-registry.md` (THE Phase L contract)
- RCA seed provenance: `docs/rca-seed.md`
- Subsystem contracts: `docs/subsystem-contracts.md` (S1-S16 unchanged)
- Data contracts: `docs/data-contracts.md`
- Model contracts: `docs/model-contracts.md`
