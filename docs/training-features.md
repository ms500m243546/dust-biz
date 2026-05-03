# Training-feature mapping

The variables a real DustOps forecast model needs to consume, and the
columns / sources that supply each one. This is the contract between
the data layer and the eventual real model that replaces the heuristic
`DustForecastModel` (Phase E baseline).

Each entry is one of:

- **available** — column exists, populated for at least one real-data mine
- **schema-ready** — column exists, awaiting back-fill (per-mine spec or
  partnership data)
- **gap** — neither column nor connector exists yet

---

## Atmospheric

| Feature | Source | Status |
|---|---|---|
| `air_density_kgm3` | derived from temperature + pressure + humidity (Open-Meteo / ERA5) | available (derive at feature-pipeline time) |
| `humidity_pct` | `weather_readings.humidity_pct` | available (Open-Meteo backfilled 2026-05-03) |
| `temperature_c` | `weather_readings.temperature_c` | available |
| `wind_speed_ms` | `weather_readings.wind_speed_ms` | available |
| `wind_direction_deg` | `weather_readings.wind_direction_deg` | available |
| `pressure_hpa` | `weather_readings.pressure_hpa` | available |
| `rainfall_mm_15min` | `weather_readings.rainfall_mm_15min` | available |
| `mixing_height_m` | `weather_readings.mixing_height_m` | available (ERA5 only; Open-Meteo NULL) |

## Particulate ground truth

| Feature | Source | Status |
|---|---|---|
| `pm10_ugm3` | `sensor_readings` for `sensor_type='pm10'` | available (5 SINCA stations across 4 mines / 2 regions, Phase O.2) |
| `pm25_ugm3` | `sensor_readings` for `sensor_type='pm25'` | available at Cuncumén from 2020-01-01 |

### SINCA-public PM10 stations adopted (Phase O.2)

| sensor_id | mine | station code | macro_id | param code | region | density (12mo) |
|---|---|---|---|---|---|---|
| `lp-em05-cuncumen` | Los Pelambres | 424 | 424 | PM10 | RIV | ~98% (8,603 / 8,784) |
| `lb-las-condes` | Los Bronces | 239 | D13 | PM10 | RM | ~79% (6,959 / 8,785) |
| `chq-club-23-marzo` | Chuquicamata | 207 | 233 | 0001 | RII | ~99% (8,670 / 8,785) |
| `chq-calama-centro` | Chuquicamata | 275 | 236 | 0001 | RII | ~66% (5,764 / 8,785) |
| `cnt-sierra-gorda` | Centinela | 255 | 204 | PM10 | RII | ~80% (7,017 / 8,785) |

The `macro_id` and `param_code` columns are SINCA-internal taxonomy:
the public station code (in the URL `index.php/estacion/index/id/N`)
is *not* the same as the macro identifier used in the data-gateway
path. Two parameter encodings co-exist: legacy stations use the
string `PM10`, newer stations use the numeric `0001`. Both are
supported by `app.ingestion.public.sinca.build_url` via the
`macro_id` + `param_code` overrides (Phase O.2).

## Haul-truck dust generation (AP-42 unpaved-haul-road)

EPA AP-42 §13.2.2 emission factor for unpaved industrial haul roads:

```
E (lb/VMT) = k * (s/12)^a * (W/3)^b
```

where:

- `E` = emission factor per vehicle-mile-traveled
- `s` = surface material silt content (mass percent < 75 µm)
- `W` = mean vehicle weight (tonnes), **loaded** = empty + payload
- `k`, `a`, `b` = particle-size constants (PM10: k=1.5, a=0.9, b=0.45)

| Feature | Source | Status |
|---|---|---|
| `silt_content_pct` (s) | `haul_road_segment_silt.silt_content_pct` | schema-ready (Phase L.7); needs per-segment quarterly samples |
| `empty_weight_tonnes` | `equipment.empty_weight_tonnes` | schema-ready (Phase O.1); back-fill from manufacturer datasheets |
| `payload_tonnes` | `equipment_activity.tonnage` | schema-ready; back-fill from operator telematics |
| `total_weight_tonnes` (W) | derived: `empty_weight_tonnes + tonnage` | feature-pipeline derive |
| `vehicle_kilometers_traveled` | derived from `equipment_activity` GPS trace | gap — needs operator telematics |
| `tire_contact_area_m2` | `equipment.tire_contact_area_m2` | schema-ready (Phase O.1); alternative dust proxy when AP-42 unsuitable |
| `tire_count` | `equipment.tire_count` | schema-ready (Phase O.1); haul-truck default = 6 |
| `axle_count` | `equipment.axle_count` | schema-ready (Phase O.1) |

### Per-mine back-fill convention

When a new mine's fleet is configured, populate `empty_weight_tonnes`
and `tire_*` from the OEM datasheet. Reference values for the most
common Chilean copper-mine haul trucks:

| Model | empty_weight_tonnes | nominal_capacity_t | tire_count | axle_count |
|---|---|---|---|---|
| Komatsu 930E-4 | 199 | 290 | 6 | 2 |
| Komatsu 980E-4 | 257 | 360 | 6 | 2 |
| Caterpillar 797F | 280 | 400 | 6 | 2 |
| Caterpillar 793F | 165 | 250 | 6 | 2 |

These values are provisional defaults — verify against the operator's
actual fleet roster before training a model that uses them.

## Mine state

| Feature | Source | Status |
|---|---|---|
| `activity_type` per zone | `equipment_activity.activity_type` aggregated in `mine_state` | available (mocked) |
| `equipment_count` per zone | `mine_state.zones[].equipment_active` | available |
| `production_rate_tph` | `mine_state.zones[].production_rate_tph` | available (mocked) |
| `dust_generation_potential` | `mine_state.zones[].dust_generation_potential` | available |
| `wind_exposure` | `mine_state.zones[].wind_exposure` | available |
| `downwind_assets` | `mine_state.zones[].downwind_assets` | available |

## Currently still gap

- **Vehicle kilometers traveled (VKT)** — needs operator GPS telemetry;
  currently mocked. Blocked on Antofagasta partnership.
- **Real per-segment silt samples** — `haul_road_segment_silt` table
  exists, no rows. Needs operational sampling cadence (typically
  quarterly to biannual).
- **Multi-receptor PM10** — only Cuncumén has data; Phase O.2 unblocks.
- **Atmospheric stability class** — Pasquill-Gifford categorization for
  AERMOD/CALPUFF; derivable from wind + solar + cloud cover but not
  currently a stored feature.

---

## Status legend

- **available** = column populated and queryable today
- **schema-ready** = column exists, NULL until back-filled per-mine or
  per partnership
- **gap** = neither column nor source exists; needs net-new engineering
