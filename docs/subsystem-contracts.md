# Subsystem Contracts

Typed I/O contracts for each subsystem. The data shapes are defined in
`docs/data-contracts.md`. Model interfaces are in
`docs/model-contracts.md`. Subsystem identity and dependencies are in
`docs/system-map.md`.

Each subsystem has:
- **Responsibility** (one sentence)
- **Inputs** (typed, references data contracts)
- **Outputs** (typed, references data contracts)
- **Failure mode** (what happens when inputs are missing or invalid)
- **Phase** (when it lands)

---

## S1 - Sensor and Data Ingestion Harness

**Responsibility:** receive, validate, normalize, and persist raw
environmental, operational, and static spatial data.

**Inputs (from external sources):**
- environmental readings (PM10/PM2.5/PM1, wind, gusts, humidity, temp,
  pressure, rainfall, solar, visibility)
- operational readings (truck GPS, truck speed, truck count, dispatch,
  shovel activity, crusher throughput, dumping, drilling, blasting
  schedule, watering trucks, road maintenance, shift schedule)
- static spatial data (mine map, haul road geometry, pit boundaries,
  stockpile/crusher/dump locations, elevation, compliance station
  locations, community/boundary locations)

**Outputs:**
- `RawSensorReading`, `RawWeatherReading`, `RawEquipmentActivity`
  records persisted (see data contracts)
- normalized event objects (see example below)

**Failure mode:** invalid records logged to `ingest_errors`; processing
continues for valid records in the batch.

**Phase:** C.

Example normalized object:

```json
{
  "timestamp": "2026-04-30T14:32:00Z",
  "zone_id": "Haul_Road_C",
  "pm10": 118,
  "pm25": 41,
  "wind_speed": 14.2,
  "wind_direction": 72,
  "truck_count_15min": 34,
  "avg_truck_speed": 31,
  "watering_last_30min": false,
  "surface_dryness_score": 0.81,
  "data_quality_score": 0.92
}
```

---

## S2 - Data Quality and Sensor Health

**Responsibility:** continuously score sensor reliability and emit a
multiplier that downstream consumers must apply to confidence.

**Inputs:** recent raw readings per sensor; historical baseline.

**Outputs:** `SensorHealthStatus` per sensor:

```json
{
  "sensor_id": "PM10_STATION_2",
  "status": "degraded",
  "quality_score": 0.71,
  "issues": ["missing_readings_last_10min", "high_variance_spike"],
  "downstream_confidence_multiplier": 0.75
}
```

**Failure mode:** if S2 cannot run, downstream defaults to multiplier
0.5 and a warning is emitted.

**Phase:** C.

---

## S3 - Site Configuration and Mine Map

**Responsibility:** authoritative source for site-specific
configuration: zones, road segments, pit boundaries, stockpiles,
crushers, dumps, sensors, compliance stations, communities, elevation,
thresholds, intervention constraints, allowed automation level.

**Inputs:** `site_configurations` table; admin endpoints (Phase
B/D).

**Outputs:** typed `SiteConfig` and per-zone `ZoneConfig` records.

**Failure mode:** if site config is missing for a referenced zone, S4
must fail loudly (do not invent defaults).

**Phase:** D.

---

## S4 - Real-Time Mine State Engine

**Responsibility:** synthesize live raw streams + site config into a
queryable mine state.

**Inputs:** recent normalized readings; `SiteConfig`; `ZoneConfig`.

**Outputs:** `MineState` snapshot per zone:

```json
{
  "zone_id": "Pit_North_Bench_4",
  "activity": "loading",
  "equipment_active": ["Shovel_3", "Truck_17", "Truck_22"],
  "production_rate_tph": 820,
  "dust_generation_potential": "high",
  "wind_exposure": "high",
  "downwind_assets": ["Boundary_Station_2", "Community_North"],
  "operational_importance": "high"
}
```

Plus aggregate views: active dust-generating zones, truck density per
road segment, wind-exposed zones, downwind risk, current bottlenecks,
surface dryness estimates, watering status per road segment.

**Failure mode:** if a contributing stream is stale, the affected
fields are marked `stale` rather than fabricated.

**Phase:** D.

---

## S5 - Feature Engineering Layer

**Responsibility:** produce versioned, leakage-safe features for
forecasting, attribution, and intervention models.

**Inputs:** mine state snapshots; recent raw + normalized readings;
site config; rolling windows.

**Outputs:** `FeatureRecord` keyed by `(timestamp, zone_id,
feature_pipeline_version)`. Feature list non-exhaustive: rolling PM10
averages (5/15/30/60), PM2.5 averages, PM trend velocity, PM
acceleration, wind vector x/y, gust intensity, wind-aligned source
distance, downwind exposure score, truck density, average truck speed,
time since watering, surface dryness, activity intensity,
humidity-adjusted dust potential, temperature effect, time-of-day,
shift phase, road segment exposure, production importance, compliance
station sensitivity.

**Failure mode:** if a required input is missing, the feature is
emitted as null with a `missing_inputs` annotation; downstream models
must handle nulls.

**Phase:** E.

---

## S6 - Dust Forecasting Model

**Responsibility:** predict PM10/PM2.5 and breach probability per
sensor / zone / compliance station for 15/30/60/120 min and 24-hr
exposure.

**Inputs:** `FeatureRecord` set; site thresholds; sensor health
multipliers from S2.

**Outputs:** `DustForecast` records (see data contracts). Per the
`DustForecastModel` interface in `docs/model-contracts.md`. Required
fields include:

```json
{
  "station_id": "Boundary_Station_2",
  "forecast_horizon": "60min",
  "predicted_pm10": 142,
  "predicted_pm25": 48,
  "breach_probability": 0.74,
  "confidence": 0.82,
  "main_risk_window": "14:50-15:30",
  "main_uncertainty": "wind gust instability",
  "model_version": "dust_forecast_baseline_v0.1.0"
}
```

**Failure mode:** falls back to documented heuristic (Guardrail 11),
output flagged `source = "heuristic_fallback"`.

**Phase:** E.

---

## S7 - Source Attribution Engine

**Responsibility:** rank likely operational sources of a dust event;
distinguish internal mine sources from external/background.

**Inputs:** `DustForecast` (or observed `DustEvent`); recent
`MineState`; weather; `SiteConfig`.

**Outputs:** `SourceAttribution`:

```json
{
  "dust_event_id": "EVT-20260430-001",
  "affected_station": "Boundary_Station_2",
  "probable_sources": [
    {"source": "Haul_Road_C", "confidence": 0.68,
     "reason": "High truck count aligned with NE wind corridor"},
    {"source": "Crusher_1", "confidence": 0.21,
     "reason": "Moderate throughput but weaker wind alignment"},
    {"source": "External background dust", "confidence": 0.11,
     "reason": "Regional sensor baseline elevated"}
  ]
}
```

**Failure mode:** returns single entry "Unknown" with confidence 0 and
a reason explaining the data gap.

**Phase:** F.

---

## S8 - Intervention Library

**Responsibility:** static (configurable) catalog of allowed
interventions. Source of truth for `risk_class`,
`requires_human_approval`, `automation_eligible`, allowed zone types,
expected time-to-effect.

**Inputs:** library file or DB table (`intervention_options`).

**Outputs:** `InterventionOption` records:

```json
{
  "intervention_id": "reduce_speed",
  "name": "Reduce truck speed",
  "description": "Temporarily reduce truck speed on selected haul road segment",
  "risk_class": "medium",
  "requires_human_approval": true,
  "estimated_time_to_effect_minutes": 10,
  "allowed_zone_types": ["haul_road"],
  "automation_eligible": false
}
```

**Failure mode:** unknown intervention IDs from the recommendation
engine raise a hard error (no silent dropping).

**Phase:** G.

---

## S9 - Intervention Simulator

**Responsibility:** estimate the impact of a candidate intervention on
predicted dust and on operations, including a "do nothing"
counterfactual.

**Inputs:** `InterventionOption`; current `MineState`; `DustForecast`;
`SiteConfig`.

**Outputs:** `InterventionSimulation`:

```json
{
  "scenario": "Reduce truck flow on Haul_Road_C by 20% for 45min",
  "predicted_pm10_reduction": 23,
  "breach_probability_after_action": 0.19,
  "production_loss_tonnes": 410,
  "time_to_effect_minutes": 20,
  "confidence": 0.76
}
```

**Failure mode:** if the model cannot simulate, returns a heuristic
estimate flagged `source = "heuristic"` with low confidence.

**Phase:** G.

---

## S10 - Production Cost Model

**Responsibility:** estimate the operational cost of an intervention.

**Inputs:** `InterventionOption`; current `MineState`; `SiteConfig`.

**Outputs:** `ProductionCostEstimate`:

```json
{
  "intervention_id": "reroute_trucks",
  "affected_zone": "Haul_Road_C",
  "estimated_tonnes_delayed": 520,
  "cycle_time_increase_percent": 8.5,
  "bottleneck_risk": "medium",
  "production_impact": "medium",
  "confidence": 0.74
}
```

**Failure mode:** if financial values are not configured, returns
tonnes/cycle-time only with `production_impact` qualitative.

**Phase:** G.

---

## S11 - Production-Aware Optimization Engine

**Responsibility:** rank interventions by the lowest cost that brings
breach probability below the configured target.

**Inputs:** `DustForecast`; available `InterventionOption` set;
`InterventionSimulation` and `ProductionCostEstimate` per option;
`SiteConfig` weights.

**Outputs:** `RankedRecommendations` (see S12 example below).

**Failure mode:** if no intervention reduces risk below target, returns
"escalate to human" recommendation with reason.

**Phase:** H.

---

## S12 - Recommendation Engine

**Responsibility:** wrap the ranked output of S11 in a human-readable
recommendation that a shift supervisor can act on in under 30 seconds.

**Inputs:** `RankedRecommendations`; `SourceAttribution`;
`SiteConfig`.

**Outputs:** `Recommendation`:

```json
{
  "risk_event": "Boundary_Station_2 PM10 breach risk",
  "current_breach_probability": 0.74,
  "target_probability": 0.25,
  "recommended_actions": [
    {
      "rank": 1,
      "action": "Water Haul_Road_C and reduce speed by 10%",
      "breach_probability_after": 0.22,
      "production_loss": "low",
      "estimated_tonnes_delayed": 280,
      "confidence": 0.81,
      "reason": "Low production impact with sufficient predicted PM10 reduction"
    },
    {
      "rank": 2,
      "action": "Reroute 30% of trucks from Road C to Road F",
      "breach_probability_after": 0.18,
      "production_loss": "medium",
      "estimated_tonnes_delayed": 520,
      "confidence": 0.74,
      "reason": "Strong reduction but higher cycle-time penalty"
    }
  ]
}
```

Recommendation text template (rendered for the dashboard):

```
Risk:
PM10 breach likely at Station 2 within 45 minutes.

Cause:
High truck density on Haul Road C, dry road surface, NE wind alignment.

Recommended action:
Water Road C now and reduce speed by 10% for 45 minutes.

Expected result:
Breach probability drops from 74% to 22%.

Production impact:
Low. Estimated 280 tonnes delayed, not lost.

Confidence:
81%.
```

**Failure mode:** if no actions can be ranked, returns "monitor
closely; no safe automated action available" with a flagged escalation.

**Phase:** H.

---

## S13 - Human Approval and Control Harness

**Responsibility:** enforce automation level; capture approve / reject
/ override decisions; record outcomes.

**Inputs:** `Recommendation`; user identity + role.

**Outputs:** `RecommendationApproval`:

```json
{
  "recommendation_id": "REC-20260430-00192",
  "issued_at": "2026-04-30T14:32:00Z",
  "risk": "PM10 breach at Boundary_Station_2",
  "recommended_action": "Reduce speed on Haul_Road_C by 10%",
  "approved_by": "Shift Supervisor",
  "approved_at": "2026-04-30T14:37:00Z",
  "approval_status": "approved",
  "actual_outcome": "PM10 stabilized below threshold",
  "production_impact": "low"
}
```

**Failure mode:** if approval is required but no human responds in a
configurable window, the recommendation expires and an escalation
event is created.

**Phase:** I.

---

## S14 - Feedback and Learning Loop

**Responsibility:** join predictions, recommendations, approvals, and
actual outcomes to compute model error and assemble training data.

**Inputs:** all of the above.

**Outputs:** `ActionOutcome`:

```json
{
  "prediction_id": "PRED-20260430-0091",
  "recommendation_id": "REC-20260430-00192",
  "predicted_breach_probability": 0.74,
  "recommendation": "Water Road C and reduce speed 10%",
  "human_action": "approved",
  "actual_pm10_peak": 119,
  "breach_occurred": false,
  "production_loss_tonnes": 280,
  "model_error": "overpredicted by 11%",
  "intervention_effectiveness": "successful"
}
```

**Failure mode:** if outcome data is missing past a window, mark the
record `outcome = "unobserved"` and exclude from training assembly.

**Phase:** K.

---

## S15 - Audit, Compliance, and ROI Reporting

**Responsibility:** produce reports against persisted data.

**Inputs:** repositories (read-only).

**Outputs:** report payloads via `GET /api/v1/reports/*`.

**Failure mode:** report generation never blocks the operational loop.

**Phase:** K.

---

## S16 - Dashboard UI

**Responsibility:** present operational state clearly to humans across
four views.

**Inputs:** `GET` endpoints only. The UI never embeds business logic;
it composes views from API responses.

**Outputs:** approve / reject / override calls to S13 endpoints.

**Failure mode:** if an API call fails, the affected card shows a
bordered error state with retry; the rest of the dashboard keeps
working.

**Phase:** J.
