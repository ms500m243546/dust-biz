# System Map

Suprasystem, system, and subsystem boundaries for DustOps AI.

This document defines **what subsystems exist**. Their I/O contracts are
in `docs/subsystem-contracts.md`. Their data shapes are in
`docs/data-contracts.md`. Their model interfaces are in
`docs/model-contracts.md`.

---

## Suprasystem (the world DustOps lives in)

DustOps AI sits inside an open-pit mining operation that includes:

- **Mine operations**: pit areas, haul roads, trucks, shovels, crushers,
  stockpiles, dumps, drilling, blasting, loading, dumping, watering
  trucks, road grading, dispatch control, shift schedules, maintenance
  windows, production targets.
- **Environmental conditions**: PM10, PM2.5, PM1, wind speed, wind
  direction, gusts, humidity, temperature, pressure, rainfall, solar
  radiation, inversion layers, dry surfaces, exposed terrain, pit
  geometry, elevation, natural wind corridors, nearby communities,
  boundary monitoring stations.
- **Compliance and regulation**: PM10/PM2.5 thresholds, site permit
  limits, boundary monitoring requirements, rolling averages,
  exceedance triggers, warning levels, shutdown triggers, audit
  obligations, reporting requirements.
- **Production economics**: tonnes moved per hour, truck cycle times,
  shovel productivity, crusher throughput, bottlenecks, cost of delay,
  cost of full shutdown, cost of watering, cost of rerouting, cost of
  slowing trucks, cost of pausing work, cost of over-warning, cost of
  under-warning, value of avoided downtime.
- **Human authority system**: environmental manager, mine dispatcher,
  shift supervisor, operations manager, executive team, compliance
  team, maintenance team, field operators.

Suprasystem goal:

> Keep the mine producing safely, legally, and profitably despite dust
> constraints.

Critical insight: dust risk emerges from interactions:

```
work activity + surface condition + wind + geography
+ humidity + compliance boundary + production schedule
```

The same activity can be safe at 8:00 a.m. and dangerous at 11:00 a.m.

---

## System (DustOps AI itself)

System loop:

```
Observe -> Predict -> Attribute -> Simulate -> Optimize
        -> Recommend -> Approve -> Execute -> Learn
```

System objective:

> Given current mine state and forecasted environmental conditions,
> predict dust risk and recommend the minimum effective intervention
> required to avoid dust exceedance while preserving production.

---

## Subsystems (S1-S16)

Each subsystem has one responsibility. Contracts are in
`docs/subsystem-contracts.md`.

### S1 - Sensor and Data Ingestion Harness
Collect, validate, normalize, timestamp-align, and store raw
environmental and operational data plus static spatial data.
Phase: C.

### S2 - Data Quality and Sensor Health
Score sensor reliability and data quality; downgrade downstream
confidence when data is degraded.
Phase: C.

### S3 - Site Configuration and Mine Map
Mine-specific configuration: zones, haul road segments, pit boundaries,
stockpiles, crushers, dumps, sensors, compliance stations, communities,
elevation, thresholds, intervention constraints, allowed automation
level.
Phase: D.

### S4 - Real-Time Mine State Engine
Convert raw data + site config into a live operational map: active
zones, activity intensity, truck density, wind exposure, downwind risk,
production importance, surface dryness, watering status.
Phase: D.

### S5 - Feature Engineering Layer
Build versioned, leakage-safe ML-ready and rules-ready features from
mine state and time-aligned environmental data.
Phase: E.

### S6 - Dust Forecasting Model
Predict PM10/PM2.5 and breach probability at sensors, zones, and
compliance boundaries for 15/30/60/120 min and 24-hr rolling exposure.
Returns confidence, uncertainty explanation, model version.
Phase: E.

### S7 - Source Attribution Engine
Identify and rank likely operational causes of a dust event using
wind-aligned spatial logic, activity timing, and sensor spike timing.
Distinguish internal mine dust from external/background dust where
possible.
Phase: F.

### S8 - Intervention Library
Defines allowed interventions (operational, environmental,
administrative), constraints, expected time-to-effect, risk class,
approval requirement, automation eligibility.
Phase: G.

### S9 - Intervention Simulator
Simulate the dust-reduction effect, time-to-effect, and operational
disruption of candidate interventions. Counterfactual comparison
against doing nothing.
Phase: G.

### S10 - Production Cost Model
Estimate the production cost of an intervention: tonnes delayed,
cycle-time impact, bottleneck risk, qualitative production impact,
optional financial estimate.
Phase: G.

### S11 - Production-Aware Optimization Engine
Choose the lowest-cost effective intervention. Objective:
minimize (breach risk + production loss + operational disruption +
confidence penalty + compliance penalty).
Phase: H.

### S12 - Recommendation Engine
Produce a human-readable recommendation including risk, cause,
recommended action, expected result, production impact, confidence,
approval requirement, reason, time-to-effect, alternatives.
Phase: H.

### S13 - Human Approval and Control Harness
Five automation levels (L0 monitoring through L4 full automation).
Default L1 - Advisory. Approve / reject / override workflow with audit
trail and outcome capture.
Phase: I.

### S14 - Feedback and Learning Loop
Predicted vs actual, recommendation vs outcome, model error, false
positives, false negatives, avoided shutdowns, tonnes delayed vs
tonnes protected, training data assembly.
Phase: K.

### S15 - Audit, Compliance, and ROI Reporting
Dust event history, predictions issued, recommendations made,
approvals/rejections, actions taken, PM trend before/after intervention,
estimated downtime avoided, production saved, compliance risk reduced,
model accuracy, sensor health, intervention effectiveness.
Phase: K.

### S16 - Dashboard UI
Four operational views (control room, environmental compliance,
operations manager, executive). Operational, not decorative. See
`docs/ui-principles.md`.
Phase: J.

---

## Subsystem dependency graph

```
S1 -> S2 -> S4 -> S5 -> S6 -> S11 -> S12 -> S13 -> S14
        ^         ^     ^       ^               |
        |         |     |       |               v
        S3 ---+---+     S7 -----+               S15
                  |     ^
                  +-----+
                  S8 -> S9 -> (S10 + S11)
                  S10 -+

S16 reads from: S2, S4, S6, S7, S11, S12, S13, S15
```

Plain English: ingestion (S1) and quality (S2) feed mine state (S4),
which combines with site config (S3) to feed features (S5).
Forecasting (S6) and attribution (S7) consume features. The intervention
library (S8) feeds the simulator (S9), which combines with the
production cost model (S10) for the optimization engine (S11). S11 feeds
the recommendation engine (S12), which goes through the approval harness
(S13). Outcomes flow back into the feedback loop (S14) and reporting
(S15). The dashboard (S16) reads from many subsystems but writes to none
except via API-level approvals.
