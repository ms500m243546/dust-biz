# Mining Domain

Operational background that DustOps AI is built around. This is the
working knowledge that informs subsystem design, contract fields, and
the language used in recommendations.

This document is a working summary, not an authoritative reference. It
should be replaced or supplemented with site-specific documentation in
real deployments. For a deployment, validate every assumption here
with the mine's own operations and environmental teams.

---

## Open-pit mine roles

- **Shift supervisor.** Front-line decision-maker for the current
  shift. Approves or rejects DustOps recommendations. Has authority to
  pause work in their area.
- **Mine dispatcher.** Routes trucks, assigns shovels, balances
  cycles. Operational owner of haul road usage.
- **Environmental manager.** Owns PM monitoring, compliance
  reporting, and exceedance response. Long-term owner of dust
  performance.
- **Operations manager.** Owns production targets and cost. Trade-off
  authority between compliance and throughput at non-extreme risk
  levels.
- **Compliance team.** Liaison with regulators; report owner; audit
  consumer.
- **Maintenance team.** Watering trucks, road grading, equipment
  health.
- **Field operators.** Truck, shovel, drill, crusher operators.
  Recipients of dispatched instructions.
- **Executive.** Outcomes consumer (downtime avoided, compliance
  incidents).

DustOps recommendations target the shift supervisor and environmental
manager. The dispatcher is the typical executor.

---

## Equipment and zones

- **Pit / bench.** Active mining face. Loading and drilling generate
  dust at the source.
- **Haul road.** Truck route from pit to crusher / dump. Dominant
  source of road dust under traffic on dry surfaces.
- **Stockpile.** Exposed material; wind-driven dust when dry.
- **Dump.** Waste / overburden disposal area; dust on dumping.
- **Crusher.** Fixed structure; dust from feed / discharge / transfer
  points.
- **Loading area.** Shovel + truck interface; dust at the bucket and
  truck box.
- **Boundary monitoring station.** Fixed sensor at the property
  boundary; the compliance reference point.

Trucks, shovels, drills, dozers, graders, water trucks. Each has a
typical activity and dust signature.

---

## Dust generation mechanisms

Dust comes from several distinct mechanisms; the model needs them
because intervention efficacy varies by mechanism.

### 1. Mechanical disturbance
Loading, dumping, drilling, blasting, dozing. Source dust at the
activity location. Reduced by: pausing the activity, watering at the
activity, enclosure (where applicable).

### 2. Traffic on unpaved surfaces
Trucks on haul roads. The dominant operational dust source on most
sites. Strongly modulated by:
- Truck speed (dust ~ speed^2.5 in many empirical models)
- Truck count
- Surface dryness
- Surface fines content
- Vehicle weight
Reduced by: speed reduction, traffic reduction, watering, surface
treatment, grading.

### 3. Wind erosion
Exposed dry surfaces (stockpiles, idle pit areas, dumps) under wind.
Modulated by: wind speed (with a threshold below which little erosion
occurs, around 5-8 m/s for many materials), surface moisture, surface
crust, particle size.
Reduced by: surface watering, dust suppressant, covering.

### 4. Material transfer
Crusher feed / discharge points, conveyor transfers. Modulated by drop
height and material moisture.
Reduced by: enclosure, misting, reduced throughput, increased material
moisture.

### 5. External / background dust
Regional dust events (dry weather, wildfires, regional construction).
The model must distinguish external sources to avoid blaming the mine
for non-mine dust.

---

## What the mine controls

DustOps interventions correspond to what operations can change:

- Watering (per road segment, per zone)
- Truck speed (per road segment)
- Truck count / routing (per road segment)
- Activity timing (delay loading, dumping, drilling, blasting)
- Equipment selection (pause or substitute equipment)
- Dust suppressant application (slower-acting; treat as an
  intervention with hours-scale time-to-effect)
- Surface grading (minutes-to-hours time-to-effect)

What the mine **does not** control: wind, rain, ambient humidity,
inversion layers, regional background.

---

## Production economics in a sentence

For most open-pit operations, an unscheduled stoppage of any duration
is more expensive than a controlled throttle that prevents the
stoppage. DustOps optimizes around this asymmetry: small preventive
adjustments beat large reactive ones.

That asymmetry is the moat of the wedge. If DustOps recommends "stop
everything" every time, it is no better than the regulatory limit
itself.

---

## Time scales

| Mechanism                      | Effect onset       | Decay       |
|--------------------------------|--------------------|-------------|
| Watering haul road             | Minutes            | 30-90 min depending on surface, traffic, temperature, wind |
| Speed reduction                | Immediate at next pass | Reverts on speed return |
| Truck flow reduction / reroute | Minutes            | Recovers on resume |
| Pausing shovel / loading       | Immediate          | Recovers on resume |
| Surface grading                | Tens of minutes    | Hours-days |
| Dust suppressant               | Hours              | Days-weeks |
| Wind shift                     | Minutes-hours (uncontrollable) | n/a |

These are working baselines. Site-specific calibration goes in site
config.

---

## Common operator language

DustOps recommendations should sound like an experienced
field-engineer's plain English, not a model report. Examples:

- "Water Road C now and reduce speed by 10% for 45 minutes."
- "Pause Shovel 3 for 30 minutes; restart when wind drops below 12 m/s."
- "Reroute 30% of trucks from Road C to Road F until 14:30."
- "Increase monitoring frequency at Boundary Station 2 for the next
  hour; no action needed yet."

Bad recommendations sound like model output:
- "Model predicts elevated PM10 risk due to multivariate nonlinear
  interactions."
- "Apply dispersion-mitigating intervention vector v3 to source
  cluster 7."

The human-readable `reason` field on every recommendation is enforced
by Guardrail 3 in `safety-guardrails.md`.
