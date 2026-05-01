# Compliance Context

PM10 and PM2.5 thresholds and compliance logic for DustOps AI.

> **Replace per site.** The numbers in this document are widely-cited
> reference values and should be treated as **defaults that must be
> overridden by site-specific permit limits** in `site_configurations`.
> Real deployments require validating every threshold with the site's
> environmental team and the local regulator.

---

## Reference thresholds (defaults)

These defaults are conservative, internationally-recognized values.
They are not a substitute for the permit limit at any specific site.

### WHO 2021 Air Quality Guidelines (health-based, ambient)

| Pollutant | Averaging period | WHO 2021 AQG  |
|-----------|------------------|---------------|
| PM2.5     | 24-hour          | 15 ug/m^3     |
| PM2.5     | Annual           | 5 ug/m^3      |
| PM10      | 24-hour          | 45 ug/m^3     |
| PM10      | Annual           | 15 ug/m^3     |

Source: WHO global air quality guidelines (2021).

### US EPA NAAQS (regulatory, ambient)

| Pollutant | Averaging period | NAAQS                       |
|-----------|------------------|-----------------------------|
| PM2.5     | 24-hour          | 35 ug/m^3 (98th percentile) |
| PM2.5     | Annual           | 9 ug/m^3 (primary, 2024)    |
| PM10      | 24-hour          | 150 ug/m^3 (not to be exceeded > 1x/yr on avg over 3 yrs) |

Source: US EPA NAAQS (PM2.5 primary annual standard updated 2024).

### Practical default for site config (until overridden)

| Threshold class | PM10 (ug/m^3) | PM2.5 (ug/m^3) | Period   |
|-----------------|---------------|----------------|----------|
| `warning`       | 100           | 25             | 1-hour   |
| `breach`        | 150           | 35             | 24-hour rolling |

These are defaults shipped with the system to make development and
demo safe. Every real deployment overrides them via
`site_configurations.pm10_thresholds` and `pm25_thresholds`.

---

## Other jurisdictions (representative; replace per site)

The following are illustrative only and should be confirmed against
the current text of the relevant regulation at deployment time:

- **EU** (Directive 2008/50/EC, under revision): PM10 24-hour 50 ug/m^3
  (max 35 exceedances/yr); PM10 annual 40 ug/m^3; PM2.5 annual 25 ug/m^3.
- **Australia** (NEPM Ambient Air Quality, current standard): PM10
  24-hour 50 ug/m^3; PM2.5 24-hour 25 ug/m^3; PM2.5 annual 8 ug/m^3.
- **Chile** (DS 59 / DS 12): PM10 24-hour 150 ug/m^3, annual 50 ug/m^3;
  PM2.5 24-hour 50 ug/m^3, annual 20 ug/m^3.

These values change. The deployment team is responsible for sourcing
the current binding limit.

---

## Rolling averages and exceedance logic

Compliance logic in DustOps is configurable per site, but the system
provides these primitives:

- **Instantaneous reading.** Single sensor sample.
- **Rolling average.** Configurable windows (default: 1-hour, 8-hour,
  24-hour). Computed continuously.
- **Threshold class.** `warning` and `breach` per pollutant per
  averaging window.
- **Exceedance.** Rolling average crosses a threshold.
- **Predicted exceedance.** Forecast (S6) projects rolling average to
  cross a threshold within the forecast horizon.

The forecasting model targets *predicted* exceedance, not just current
readings. The optimization engine (S11) optimizes against
`breach_probability` (probability the rolling average breaches within
the forecast horizon).

---

## Boundary monitoring vs in-pit monitoring

- **Boundary monitoring stations** are the regulatory reference points
  in many permits. They live at the property boundary (often on the
  side facing communities). Compliance is typically measured here.
- **In-pit sensors** measure activity-side dust and are crucial for
  attribution (S7) but typically not for compliance.

DustOps treats both, but `recommendations` are primarily framed
against boundary station risk because that is what triggers regulator
exposure.

---

## Audit obligations

Most permits require:

- Continuous PM monitoring at compliance stations.
- Recordkeeping for a regulator-defined retention period (often
  multi-year).
- Reportable exceedances within a regulator-defined window.
- Evidence of mitigation measures taken.

DustOps satisfies the evidence side via the audit log
(`audit_logs`, `recommendations`, `recommendation_approvals`,
`action_outcomes`). The reporting layer (S15) renders these into
exportable summaries.

DustOps does **not** replace any required regulator reporting. It
provides the operational evidence that supports it.

---

## Interaction with safety guardrails

The `extreme_breach_threshold` in `safety-guardrails.md` (default
0.85) shifts the optimization weights toward compliance. The default
is set conservatively because the cost asymmetry favors avoiding
exceedance even at moderate production cost. Site config can adjust
this threshold up or down based on the permit's tolerance and the
site's production sensitivity.

---

## What not to do

- Do not invent thresholds in code. They live only in
  `site_configurations`.
- Do not assume a single number applies to all sites. Different
  jurisdictions, different permits, different averaging windows.
- Do not collapse PM2.5 and PM10 logic. They are separate pollutants
  with separate health bases and separate permit numbers.
- Do not hide compliance state from the operator. The compliance view
  exists for a reason; it must show the rolling-average state and
  trajectory.
