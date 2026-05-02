# Data-source registry

Canonical inventory of every external data source DustOps ingests.
The registry is the contract: each source has a connector module, a
license obligation, a refresh cadence, a schema mapping, and a
test fixture. The `validate-data-sources` check asserts the
connectors and the registry agree.

Last updated: **2026-05-02 (Phase L.1)**.

---

## Strategic priority

DustOps targets **Chilean copper mines with adjacent towns**, where
RCA (Resolución de Calificación Ambiental) conditions impose stricter
PM thresholds at residential receptors than the generic D.S. 12/2011
norms. Data sources are prioritized accordingly.

**Pilot mine: Los Pelambres** (Antofagasta Minerals; Choapa Province,
Coquimbo Region). Insider partner-data path expected via the
`source = "operator_real"` discriminator on `RawSensorReading`.
**Mine #2: Los Bronces** (Anglo American; Región Metropolitana,
~3,500 m altitude in the Andes; sits upwind of eastern Santiago).

---

## Sources by data bucket

### PM10 / PM2.5 air quality

| Source | Authority | License | Coverage | Cadence | Connector |
|---|---|---|---|---|---|
| **SINCA** (Sistema de Información Nacional de Calidad del Aire) | MMA (Ministerio del Medio Ambiente, Chile) | Public — open access via portal | Regulatory monitors nationwide; dense in mining corridors | Hourly + historical archive | `app/ingestion/public/sinca.py` (L.2) |
| **Community / faena monitoring** (operator-reported to SMA) | SMA enforcement filings + RCA-mandated stations | Public — published in compliance reports | Per-mine; close-in to mine fence; varies | Operator-reported (typically hourly) | `app/ingestion/public/community_stations.py` (L.2) |
| **OpenAQ v3** (global aggregator; ingests SINCA upstream) | OpenAQ Inc. | CC0 | Global; useful as comparative cross-check | Near-real-time | `app/ingestion/public/openaq.py` (deferred — SINCA is upstream) |

**SINCA endpoint pattern (CSV, no key):** `https://sinca.mma.gob.cl/cgi-bin/APUB-MMA/apub.tsindico2.cgi?...`. Rate limit observed empirically; cache aggressively.

### Weather (wind, temperature, humidity, pressure, rainfall, solar)

| Source | Authority | License | Coverage | Cadence | Connector |
|---|---|---|---|---|---|
| **ERA5 reanalysis** (Copernicus CDS) | ECMWF / Copernicus | Free with registration; commercial use OK | Global; hourly back to 1940; **load-bearing for high-altitude mines (Los Bronces 3,500 m)** because surface stations don't represent the operating regime | Hourly (3-month latency for definitive data) | `app/ingestion/public/era5.py` (L.3) — primary |
| **DGA** (Dirección General de Aguas) | DGA Chile | Public | Hydromet stations nationwide; better in valleys than at altitude | Hourly + daily | `app/ingestion/public/dga.py` (L.3) |
| **DMC** (Dirección Meteorológica de Chile) | DMC | Public | Official met service; surface stations | Hourly | (Optional; DGA covers most of what we need) |
| **Open-Meteo** | Open-Meteo (OSS) | **CC-BY-NC** — non-commercial only | Global free fallback | Hourly | `app/ingestion/public/open_meteo.py` (L.3) — fallback only; production must use ERA5 |

**Open-Meteo license note:** explicitly non-commercial. Acceptable
during prototyping; **production deploys must swap to ERA5 or a
commercial weather provider before any paying customer.**

### Mine static spatial (pits, haul roads, boundaries, zones)

| Source | Authority | License | Coverage | Cadence | Connector |
|---|---|---|---|---|---|
| **OpenStreetMap Overpass** | OSM Foundation | ODbL | Global; Chuquicamata + Escondida + Los Bronces + Los Pelambres + El Teniente + Collahuasi all digitized | One-shot import; manual refresh | `app/ingestion/public/osm_mine.py` (L.4) |
| **IDE Chile** (Infraestructura de Datos Geoespaciales) | Various Chilean state agencies | Public | Cadastral + topographic | One-shot | (Used as cross-check on OSM) |

OSM mine geometry maps directly to the K.3 GeoJSON contract on
`Zone.geometry` (Polygon) and `HaulRoadSegment.geometry` (LineString).

### Population exposure / receptors

| Source | Authority | License | Coverage | Cadence | Connector |
|---|---|---|---|---|---|
| **INE** (Instituto Nacional de Estadísticas) | INE Chile | Public | Census + populated-place geometries (manzanas, localidades) | Census-cycle (5–10y) | `app/ingestion/public/ine_populated_places.py` (L.4) |

This is a **first-class data layer** because RCA stringency at a mine
is a function of receptor population + distance + wind alignment.
Every `Zone` resolves to a list of nearby `PopulatedPlace` records
with distance + bearing.

### Permit thresholds / RCAs

| Source | Authority | License | Coverage | Cadence | Connector |
|---|---|---|---|---|---|
| **SEA** (Servicio de Evaluación Ambiental) | SEA Chile | Public | Per-mine RCAs and amendments | Per-RCA event | Hand-digitized into `SiteConfiguration` rows + `StationThresholdOverride` rows; URL cited per row |

**Required reading before L.4 digitization:**
- **Los Pelambres** original RCA (1997) + El Mauro tailings consent
  + supreme court rulings on the Caimanes case. Key URLs to be
  captured in the digitized rows.
- **Los Bronces Integrado** SEA evaluation (2020 rejection) — the
  case file is the canonical guide for how community-impact is
  weighted in Chilean PM thresholds.

### Breach event labels

| Source | Authority | License | Coverage | Cadence | Connector |
|---|---|---|---|---|---|
| **SMA sanction records** | Superintendencia del Medio Ambiente | Public | Enforcement notices, fines, formulación de cargos | Per-event | Hand-curated; loaded as labelled `DustEvent` rows |
| Mine-level annual environmental performance reports | Operators (filed with SMA) | Public | Per-operator | Annual | (Optional; provides aggregate-level context) |

### Production telemetry (coarse)

| Source | Authority | License | Coverage | Cadence | Connector |
|---|---|---|---|---|---|
| **CMF** (Comisión para el Mercado Financiero) | CMF Chile | Public | Listed Chilean miners (Antofagasta plc parent: AHK, SQM, etc.) | Quarterly + annual | (Used to calibrate synthetic equipment generators in L.5) |
| **USGS Mineral Yearbook** | USGS | Public domain | Global; coarse but consistent | Annual | (Cross-check) |

### Equipment activity (truck GPS, shovel, crusher, blast, watering)

**No public source.** Synthetic only until insider data flows from
Los Pelambres.

- L.5 calibrates `app/ingestion/mock_streams.py` against published
  Caterpillar 793F + Komatsu 930E cycle-time curves and CMF
  production tonnages so the synthetic data is grounded in real
  industry numbers.
- The `RawSensorReading.source` discriminator gets a new value
  `"operator_real"` so when partnership data lands, it slots in
  alongside `"sinca"` / `"mock"` without domain-layer changes.

---

## Connector protocol

All public-source ingest modules implement the `Connector` protocol
defined in `app/ingestion/public/__init__.py`. Connectors are pure
fetchers — they never write to the database. Persistence is the
orchestrator's job (`scripts/seed_mock_data.py` extended in L.2).

```python
class Connector(Protocol):
    source_name: str  # discriminator used in raw_value.source
    def fetch(self, *, window_from: datetime, window_to: datetime, **filters) -> Iterable[Mapping]:
        ...
```

Each connector:
1. Reads from the public API (or disk cache via
   `app/ingestion/public/cache.py`).
2. Returns an iterable of records ready to be passed to the
   matching `Raw*ReadingSchema`.
3. Records every fetch in `data_cache/<source>/<window>.json` so
   re-runs don't hammer the upstream API.

---

## Refresh cadence policy

- **PM data (SINCA):** hourly pull during dev; nightly batch in production.
- **Weather (ERA5):** monthly historical pull; daily forecast pull.
- **Static (OSM, INE):** one-shot; refresh annually or when an RCA changes.
- **Permits (SEA RCAs):** event-driven (when an RCA is amended).
- **Breach labels (SMA):** monthly.

---

## License obligations

| Source | Attribution required? | Notes |
|---|---|---|
| SINCA / MMA | No formal requirement; cite as courtesy | Public data |
| ERA5 / Copernicus | Yes — "Generated using Copernicus Climate Change Service information" | Required in product copy if displayed |
| Open-Meteo | Yes + **non-commercial only** | Drop before any paid deployment |
| OpenStreetMap | Yes — "© OpenStreetMap contributors" + ODbL | Required in any UI displaying OSM-derived geometry |
| INE | Yes | Cite "Fuente: INE Chile" |
| SEA / SMA / CMF | No | Public regulatory data |

The dashboard (web/) must surface these attributions in its footer
once L.4 lands.

---

## Drift protection

`scripts/checks/validate-data-sources.js` asserts that every entry
in this registry's "Connector" column maps to an importable module
under `app/ingestion/public/` and vice-versa. Adding a connector
without registering it here (or vice versa) fails the agent-check
gate.
