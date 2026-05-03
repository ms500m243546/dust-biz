# Safety Guardrails

Mandatory operational and architectural safety rules for DustOps AI.

These are enforced by:
- Schema validation (`app/schemas/`)
- The `validate-safety` step in `npm run agent-check` (Phase B onward)
- The safety-reviewer subagent
- The architect protocol (planning, approval, audit)

If a guardrail is violated, the change is not done.

---

## Automation levels (S13)

DustOps operates at one of five automation levels per site, configured
in site config:

### L0 - Monitoring only
System observes and reports. No recommendations issued to operators
beyond raw monitoring.

### L1 - Advisory (DEFAULT)
System generates recommendations. A human decides. Nothing executes
without explicit approval.

### L2 - Assisted execution
Human approves a recommendation; system then dispatches the instruction
(e.g. notifies the watering team, posts a job to dispatch). The human
remains the decision-maker; the system is the messenger.

### L3 - Semi-automated low-risk controls
System may automatically trigger only **low-risk** actions classified as
such in the intervention library (e.g. raising an alert, increasing
monitoring frequency, requesting an additional sensor reading). All
high-impact actions still require human approval.

### L4 - Full automation
**Not recommended for early deployments.** Requires written sign-off in
site config and an explicit approval-bypass record per intervention
class. This level is intentionally hard to enable.

The default level **must** be L1 unless site config explicitly raises it.

---

## The 15 mandatory guardrails

Every change must preserve these. The validation gate fails the change
if any are missing.

### 1. No high-impact automation without human approval
Any intervention in a `risk_class` of `medium` or `high` requires a
human approval record (see S13). The optimization engine and
recommendation engine must mark these explicitly. The execution path
must check the approval record before acting.

### 2. Always show confidence
Every forecast, attribution, simulation, and recommendation carries a
`confidence` field (0.0-1.0). Schema-enforced via Pydantic.

### 3. Always show reason for recommendation
Every recommendation carries a human-readable `reason` string aimed at
a shift supervisor. See the template in `docs/subsystem-contracts.md`
(S12).

### 4. Low data quality downgrades confidence
The data-quality subsystem (S2) emits a `downstream_confidence_multiplier`
that the forecasting model must apply. Forecast confidence cannot exceed
`raw_model_confidence * downstream_confidence_multiplier`.

### 5. Missing sensor data warns the user
Any forecast or recommendation produced when input sensors are degraded
or missing must include a `data_quality_warnings` field listing affected
sensors. The dashboard must surface this.

### 6. Low confidence -> recommend human review, not action
If recommendation confidence < a configurable threshold (default 0.5),
the recommendation engine must label the recommendation
`requires_human_review = true` and avoid suggesting high-impact actions.

### 7. Extreme breach risk prioritizes compliance over production
If predicted breach probability exceeds a configurable
"extreme" threshold (default 0.85), the optimization engine must shift
its objective weight toward compliance (i.e. accept higher production
cost) and surface this shift in the recommendation reason.

### 8. Store all recommendation decisions
Every recommendation is persisted, regardless of whether it was
approved, rejected, overridden, or expired. See `docs/data-contracts.md`
- `recommendations`, `recommendation_approvals`.

### 9. Store all human overrides
An override (operator chose a different action than the recommendation)
must capture: who, when, what they chose instead, free-text reason.

### 10. Keep raw data for audit
Raw sensor readings are never overwritten. Derived features and
quality-adjusted values live in separate tables (see
`docs/data-contracts.md`).

### 11. Fallback mode if model fails
If the ML model raises or returns an invalid output, the system falls
back to a documented heuristic (e.g. "PM10 trend over last 30 min plus
wind alignment to nearest dust source") and marks the forecast as
`source = "heuristic_fallback"` with reduced confidence.

### 12. Manual event entry supported
An operator can manually log a dust event (e.g. observed visible dust
plume) even when sensors miss it. This entry feeds S14 and S15.

### 13. High-impact interventions require explicit automation config
Even at L3, interventions tagged `risk_class = high` or `risk_class =
medium` cannot auto-execute. Site config controls which intervention
classes are eligible at each automation level.

### 14. Every action has an approval-requirement classification
Each entry in the intervention library declares `requires_human_approval`
(bool) and `automation_eligible` (bool, per level). Missing fields
fail the contract validator.

### 15. Every recommendation is auditable
Each recommendation includes `model_version`, `feature_pipeline_version`,
`input_data_quality_score`, and a list of input record IDs sufficient
to reconstruct what the model saw.

---

## Goodhart-canary discipline (M.4.2)

A KPI used to gate model promotion or operational decisions is, by definition, a target — and any target can be gamed. This guardrail prevents silent gaming.

Every persisted `model_performance_metrics.metric_payload` row at protocol_version M.4+ must include a `canary_metrics` block. The block pairs each KPI an operator might deploy against with a paired *counter-metric* whose movement reveals the gaming:

| KPI | Counter-metric | What gaming would look like |
|---|---|---|
| `breach_precision` | `breach_recall` | Under-firing → precision↑, recall↓ |
| `false_positive_rate` | `breach_recall` | Same: under-firing → FPR↓, recall↓ |
| `avoided_shutdowns_estimate` | `false_negative_rate` | Inflating "avoided" by missing real breaches → FNR↑ |
| `production_loss_tonnes_total` | `breach_recall` | "Low loss" because the model isn't firing → recall↓ |

The pairs are encoded in `app.domain.model_performance.GOODHART_CANARY_PAIRS`. The agent-check gate enforces presence; alerting on drift between KPI and canary is M.4.3 (drift watch).

A model is **not promoted to a higher automation level** unless its canary metrics for the target KPI are also acceptable. This rule is binding on all promotion decisions per `docs/safety-guardrails.md` rule 13.

## Per-receptor fairness audit (M.4.2)

`metric_payload.per_receptor` carries the same headline metrics as the aggregate, split by `target_id`. Operators reviewing model performance must check that the worst-receptor metrics are within tolerance — an aggregate-good model can still be unfair to a specific receptor (Cuncumén-vs-Caimanes asymmetry, B-32). M.4.2 supplies the data; flagging logic for "worst-receptor breach rate exceeds threshold" is operator-side until M.4.3.

---

## Mandatory audit list

The audit log (S15) must persist:

- Raw sensor readings (immutable).
- Derived features (with feature pipeline version).
- Predictions (with model version + confidence + uncertainty notes).
- Source attributions (with confidence + reasoning).
- Intervention simulations (inputs + outputs).
- Recommendations (full payload).
- Approvals, rejections, overrides (who, when, why).
- Action outcomes (what actually happened).
- Model version changes (when a model was deployed).
- Confidence scores at every step.
- Data-quality warnings.
- Safety decisions (e.g. "extreme threshold triggered, compliance
  weight raised").

---

## Compliance-priority logic (rule 7 expanded)

The optimization engine receives weights:

```
w_breach          - cost per unit breach probability
w_production      - cost per tonne delayed
w_disruption      - cost per unit operational disruption
w_low_confidence  - penalty multiplier for low-confidence predictions
w_compliance      - extra weight when breach probability is extreme
```

Default behavior:

- breach_prob < 0.5: balanced production / compliance weights.
- 0.5 <= breach_prob < 0.85: production weight reduced 30%.
- breach_prob >= 0.85: production weight reduced 70%, w_compliance
  doubled. Recommendation reason must explicitly say "extreme breach
  risk - compliance prioritized over production."

These thresholds are configurable per site in `site_config`.

---

## Safety-reviewer subagent triggers

When changes touch any of the following paths, the safety-reviewer
subagent must run before merge:

- `app/domain/recommendations/`
- `app/domain/approvals/`
- `app/domain/optimization/`
- `app/api/routes/recommendations.py`
- `app/api/routes/approvals.py`
- `app/api/routes/outcomes.py`
- `app/audit/`
- `app/config/site_config.py`

The reviewer flags issues; it does not auto-fix unless explicitly
approved.
