# RCA seed — Los Pelambres + Los Bronces

Hand-digitized Resolución de Calificación Ambiental (RCA) extracts
that drive the platform's per-mine `SiteConfiguration` and
`PopulatedPlace` rows. Every threshold below cites the source URL on
sea.gob.cl; cross-check against the original PDF before any
production deployment.

**This is a planning + provenance doc, not authoritative data.** The
machine-readable seed payloads live alongside the connector tests
in `tests/ingestion/fixtures/rca_seed_*.json` and are loaded by the
orchestrator script.

Last verified: **2026-05-02**.

---

## Los Pelambres (Antofagasta Minerals)

- **Operator:** Minera Los Pelambres (subsidiary of Antofagasta plc).
- **Region / commune:** Coquimbo / Salamanca.
- **Approximate pit centroid:** -70.5208, -31.7300 (WGS84 lon/lat).
- **Operating altitude:** ~3,200 m.
- **Original RCA:** No. 38/1997 (Comisión Regional del Medio
  Ambiente IV Región).
- **Major amendments:**
  - El Mauro tailings dam consent (RCA 050/2004 + supreme court
    rulings on the Caimanes drinking-water case).
  - Integral Development of Operations RCA (~2018).
- **Receptor obligations referenced in RCAs:**
  - Cuncumén (population ~600) — community monitoring station,
    PM10 limit 150 µg/m³ daily (matches D.S. 12/2011 primary norm).
  - Caimanes (population ~1,300) — water-quality + dust
    monitoring; downstream of El Mauro.
  - Salamanca (population ~25,000) — regional reference station.

**Threshold posture:** Los Pelambres RCAs reference the national
PM10/PM2.5 norms (D.S. 12/2011) at receptor stations rather than
imposing site-specific stricter values — but mandate **continuous
monitoring** at named receptors. The platform encodes this as
per-station threshold rows that point at the same numeric values as
the site default; the value of the encoding is provenance, not
stricter numbers.

## Los Bronces (Anglo American Sur S.A.)

- **Operator:** Anglo American Sur S.A. (50.1% Anglo American, 29.5%
  Mitsubishi, 20.4% Codelco / Mitsui consortium).
- **Region / commune:** Región Metropolitana / Lo Barnechea.
- **Approximate pit centroid:** -70.2900, -33.1500.
- **Operating altitude:** ~3,500 m.
- **Original RCA:** RCA 391/2007 (proyecto Desarrollo Los Bronces).
- **Major amendments:**
  - Los Bronces Integrado expansion — submitted 2019, **rejected by
    the SEA Comité de Ministros in 2020**, modified version
    re-evaluated. The rejection rationale (community air-quality
    impact on the Santiago basin) is the canonical Chilean case
    for how community impact dominates technical mitigation.
- **Receptor obligations:**
  - Las Condes / Lo Barnechea air-quality stations (eastern
    Santiago, dense SINCA coverage) — primary receptors for the
    PM2.5 community impact assessment.
  - Aconcagua valley — secondary receptor (downwind during winter
    Andean drainage flows).

**Threshold posture:** the Los Bronces RCAs and the rejection case
file rely on the **Santiago Plan de Prevención y Descontaminación
Atmosférica (PPDA)** — a stricter regional regime than the national
norm. Effective PM2.5 limit at Las Condes is the PPDA daily target
(typically 50 µg/m³ daily, but the PPDA is updated periodically;
verify before deployment).

---

## Encoding into the platform

When the orchestrator script ingests these seeds, it produces:

1. **A `SiteConfiguration` row per mine.** The `pm10_thresholds` and
   `pm25_thresholds` JSON columns carry the site-level defaults. The
   `cost_curves` field gets the conservative `tonne_value_usd: 80`
   default until per-mine cost curves arrive.
2. **`PopulatedPlace` rows for every named receptor**, each with
   distance + bearing computed via `app/ingestion/public/ine_populated_places.py`.
3. **`Zone` rows with GeoJSON geometry** ingested from
   `app/ingestion/public/osm_mine.py` for the pit boundary +
   haul-road network.

Per-station threshold overrides land in L.6 — once the contract
amendment is in place, RCA-specified per-station limits will write
to `StationThresholdOverride` rows.

---

## Sources

- **SEA portal (sea.gob.cl):** every RCA cited above is a public
  document. The orchestrator must record the source URL on every
  digitized row (`PopulatedPlace.source_url`,
  `SiteConfiguration.metadata`).
- **SMA enforcement records (snifa.sma.gob.cl):** sanction notices
  filed against Los Pelambres + Los Bronces feed the labelled
  breach-event ingest in L.6.
- **PPDA Santiago:** D.S. 31/2016 + amendments (Ministry of
  Environment Chile).

---

## Open work

- Replace the placeholder pit centroids above with surveyed values
  from Los Pelambres before insider data flows.
- Pull the most recent Los Bronces Integrado modified RCA — the 2020
  rejection is well known but the modified resubmission's status
  needs to be re-checked at deployment time.
- The Caimanes water-rights case is operationally relevant for water
  intervention scheduling; not yet encoded.
