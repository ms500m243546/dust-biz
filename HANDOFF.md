# DustOps AI — Session Handoff

**As of:** 2026-05-02
**Active phase:** L.7 complete — SINCA + RCA seed pipeline ready; first live SINCA pull is the next operator action
**Last completed:** L.7 — SINCA orchestrator + RCA seeds + dispersion-modeling schema fields
**Validation gate:** `npm run agent-check` GREEN, **17 PASS / 0 SKIP / 0 FAIL**, 494 backend tests + 14 web tests

---

## State at handoff

- `.progress_state.json`: `current_phase=L-complete`, `completed_phases=[A..L]`.
- L.7 commit log on `main`:
  - `<L.7>` Phase L.7 — SINCA orchestrator + RCA seeds + dispersion-modeling fields
- Rollback log adds: `phase-l7-pre`, `phase-l7-ingest`.
- Memory updated: `project_phase_l_complete.md` superseded by
  `project_phase_l7_complete.md`; training-feature gaps tracked in
  `project_training_features.md`.

---

## What shipped in L.7

### Training-feature schema gaps closed

Per the user-flagged variable list (air density, humidity, temperature,
wind, particle size, wheel area, truck weight) plus the additional
dispersion variables I called out:

| Field | Where | Purpose |
|---|---|---|
| `FleetSpec.empty_weight_tonnes` | `app/ingestion/fleet_specs.py` | EPA AP-42 W (mean vehicle weight); CAT 793F=161t, Komatsu 930E=200t, CAT 6030=583t |
| `FleetSpec.tire_contact_area_m2` | same | Surface scuffing component of fugitive dust |
| `FleetSpec.engine_tier` | same | Decompose diesel exhaust PM from fugitive PM |
| `RawWeatherReading.cloud_cover_pct` | `app/schemas/weather.py` + ORM | Stability class derivation |
| `RawWeatherReading.mixing_height_m` | same | Plume cap height; ERA5 `blh` |
| `Zone.surface_roughness_m` | `app/schemas/mine.py` + ORM | Wind-profile z₀ per zone |
| `HaulRoadSegmentSilt` (new ORM + repo + schema) | `app/storage/models/road_silt.py` | EPA AP-42 `s` term — periodic silt sampling |

**Air density** stays as a derived feature (compute from T/P/RH in
`app/domain/features.py` later — not a raw column).

### SINCA orchestrator

`scripts/seed_public_data.py` — stdlib `urllib.request`, no new dep.

```bash
# Dry-run (no network; uses cache + parses)
python scripts/seed_public_data.py --source sinca --station EM05 \
    --parameter pm10 --from 2026-04-25 --to 2026-05-01 --dry-run --no-persist

# First live pull (verify URL pattern against the actual SINCA portal)
python scripts/seed_public_data.py --source sinca --station EM05 \
    --station-name "Cuncumen" --region "Coquimbo" --commune "Salamanca" \
    --longitude -70.701 --latitude -31.971 --tier EMRPM \
    --parameter pm10 --from 2026-04-25 --to 2026-05-01 \
    --sensor-id lp-em05-cuncumen --mine-id los-pelambres
```

Live path caches the raw CSV body to `data_cache/sinca/<window>_<hash>.json`,
then parses + persists via `SensorReadingRepository`. The first run
will validate the URL pattern empirically — adjust `build_url` in
`app/ingestion/public/sinca.py` if the portal returns a 4xx.

### RCA seeds

`data_seed/los_pelambres.yaml` and `data_seed/los_bronces.yaml`:

- **Los Pelambres** populates Cuncumén / Caimanes / Salamanca with
  known coordinates + populations; El Manzano / Chillepín / Coirón as
  receptor names with `TODO_FROM_RCA` lat/lon for you to verify
  against the RCA PDF. Six sensor entries (3 community + 3 faena) with
  station threshold overrides mirroring D.S. 12/2011 (provenance, not
  numeric stringency, since LP RCAs reference the national norm at
  receptors).
- **Los Bronces** populates Las Condes / Lo Barnechea / Vitacura with
  full coordinates; Aconcagua valley + San Francisco / Farellones as
  named entries with `TODO_FROM_RCA` coords. Six sensor entries with
  PPDA-stricter overrides (PM2.5 warning at 20 µg/m³ instead of 25 —
  verify against current PPDA cycle).

`scripts/seed_rca.py` loads any number of YAML files and upserts every
row through the existing repositories. Idempotent.

`scripts/checks/validate-rca-seed.js` is wired into agent-check (now
17 validators). Production-tagged YAMLs with any `TODO_FROM_RCA`
substring fail the gate; dev + staging tolerate placeholders.

---

## How to run the first live pulls

```bash
# 1. Make sure DB is fresh
rm -f dustops.db

# 2. Load the RCA seeds (creates Mine + SiteConfig + Sensor +
#    PopulatedPlace + StationThresholdOverride rows)
python scripts/seed_rca.py \
    --file data_seed/los_pelambres.yaml \
    --file data_seed/los_bronces.yaml

# 3. Pull SINCA Cuncumen PM10 for the last week
python scripts/seed_public_data.py --source sinca \
    --station <REAL_SINCA_CODE_FROM_PORTAL> \
    --station-name "Cuncumen" --region "Coquimbo" --commune "Salamanca" \
    --longitude -70.701 --latitude -31.971 --tier EMRPM \
    --parameter pm10 --from 2026-04-25 --to 2026-05-02 \
    --sensor-id lp-em05-cuncumen

# 4. Verify the K.2 compliance report shows real readings
curl -H "Authorization: Bearer <token>" \
     http://localhost:8000/api/v1/reports/compliance?mine_id=los-pelambres
```

The **real SINCA station code** for Cuncumén is the one variable I
couldn't confirm without hitting the portal; SINCA uses internal codes
that vary by region (e.g., `D14` for Las Condes). When you do the
first live pull, sub `<REAL_SINCA_CODE_FROM_PORTAL>` for the actual
code from sinca.mma.gob.cl, capture the response body, and we'll
back-fill it into the YAML for permanence.

---

## Open work / next steps

| ID | Severity | Summary | Resolution |
|---|---|---|---|
| L7-R1 | medium | SINCA URL pattern in `build_url()` is empirical and unverified against the live portal | First live pull validates; adjust URL pattern if 4xx |
| L7-R2 | low | TODO_FROM_RCA markers in both YAMLs | User populates from RCA PDFs as part of the digitization effort |
| L7-R3 | low | Real SINCA station codes for non-headline stations are unknown | Capture from portal during first pull |
| L7-R4 | low | PPDA stricter PM2.5 warning value (20 µg/m³) is an estimate of the current Santiago cycle; verify against the active PPDA before deployment | Re-confirm and update Los Bronces YAML |
| L7-R5 | medium-latent | Equipment-side ingest (Los Pelambres telematics) is the bottleneck for honest training | `operator_real` adapter is wired; needs partnership data flow |

**Concrete next session priorities:**

1. **First live SINCA pull** at Cuncumén using the orchestrator above.
2. **Hand-digitize the remaining `TODO_FROM_RCA` values** from the
   real RCA PDFs (especially LP receptor coords + LB Aconcagua valley
   coords). Update both YAMLs and re-run `seed_rca.py`.
3. **Tag the YAMLs** `deployment_tier: production` once values are
   filled in — the `validate-rca-seed` gate catches stragglers.
4. **First ERA5 pull** using your Copernicus account — orchestrator
   for ERA5 isn't wired yet; that's a small follow-up similar to
   `seed_public_data.py` but using `cdsapi`.
5. **Variable list further additions to consider** (called out earlier
   but not yet shipped): atmospheric stability class, days-since-rain
   decay, blast magnitude as a first-class event, tailings-beach
   moisture, and finer particle sizes (PM1) — none are blockers; ship
   after first real-data round-trip proves the pipeline.

---

## Key references

- **`docs/data-source-registry.md`** — the contract for every public source
- **`docs/rca-seed.md`** — provenance for Los Pelambres + Los Bronces RCAs
- **`data_seed/los_pelambres.yaml` / `los_bronces.yaml`** — the seed
  files; populate `TODO_FROM_RCA` markers from PDFs on sea.gob.cl
- **`scripts/seed_public_data.py`** — SINCA pull orchestrator
- **`scripts/seed_rca.py`** — YAML → DB loader
- **`memory/project_training_features.md`** — feature-engineering coverage map
- **Model contracts:** `docs/model-contracts.md` (lifecycle step 5
  shadow-evaluation usable as soon as real data flows)
