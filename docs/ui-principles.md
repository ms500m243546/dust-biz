# UI Principles

Standards for the DustOps AI dashboard. The UI exists to help a shift
supervisor or environmental manager make good decisions under pressure.
Everything else is secondary.

---

## North star

A shift supervisor with one minute and a radio in their hand should be
able to:

1. See whether dust is becoming a problem.
2. See where and when.
3. See the most likely cause.
4. See the recommended action and its production cost.
5. Approve, reject, or override.

If the dashboard cannot do this in five seconds of glance time, it is
the wrong design.

---

## Anti-goals

The dashboard is **not**:

- a generic IoT visualization
- a marketing surface
- a chatbot wrapper
- an "AI showcase"
- a pure compliance reporting view (that is one of four views, not the
  whole product)

If a UI element does not help an operator decide, remove it.

---

## Four views

### 1. Control room view (S16)
- Current dust risk per station / zone, with breach probability and
  confidence
- Forecast window: 15 / 30 / 60 / 120 min
- Likely cause (top 1-3 with reasons)
- Recommended action with approve / reject / override controls
- Mine heatmap: zones, road segments, sensors, wind direction, risk
  levels
- Sensor health strip
- Event timeline

### 2. Environmental compliance view
- PM10 and PM2.5 trends
- Rolling averages against thresholds (sourced from
  `docs/compliance-context.md`)
- Compliance risk score
- Sensor health detail
- Event reports
- Audit trail

### 3. Operations manager view
- Current production impact of any active intervention
- Intervention cost summary (tonnes delayed)
- Tonnes protected
- Shutdowns avoided
- ROI estimate

### 4. Executive view
- Downtime avoided (rolling)
- Compliance incidents avoided
- Monthly savings
- Environmental performance trend

### Annex: Phase T model-evidence cards

The Compliance view gains three real-model surfaces (Phase T):

- **Per-receptor fairness (M.4.2 / Q.3)** — table of per-station mae_pm10 / breach_recall / precision / FPR, sorted worst-MAE first; each row tinted yellow / red when metrics fall outside the configured thresholds. Backed by `metric_payload.per_receptor`.
- **Multi-station caveat banners (Q.3)** — yellow warning rows for `survivor_caveat` (B-5), `selection_caveat` (B-6), and `cross_mine_eval` (B-14). Renders nothing when all three are null. Surfaced in both Compliance and Drift views.
- **Attribution evidence distribution (S.1)** — horizontal-stacked bar of EvidenceClass counts across recent attributions, with a per-class legend. Strong tier (experimental, quasi_experimental) tinted green; weak tier (observational, expert_judgment) tinted yellow. Backed by `api.attributions()`.

These surfaces are *evidence cards*, not decision controls — operators read them to decide whether to trust the model's recommendations, not to take action directly.

### Annex: Drift view (Phase N — env_manager + admin only)

A role-restricted, model-trust surface mounted at `/drift`. Not one of
the four primary operator views — visible only to
`environmental_manager` and `admin`; other roles get the calibration
badge (M.4.1) on the recommendation card for per-decision trust.

- One card surfacing detected metric drift for the selected
  `model_version` over the selected window (14 / 30 / 90 days).
- Polled at 60s (same cadence as Compliance).
- Alert rows: metric name, baseline median, recent median, |Δ|,
  threshold, baseline / recent sample counts, detection time.
- Severity tier per row: yellow ≥ 1× threshold ("NOTICE"), red ≥ 2×
  threshold ("ACT"). Card-level border tracks the worst tier present.
- Empty states are explicit: "No model_performance rows yet" (cannot
  compute drift) vs "No drift detected in window" (computed, clean).
- Detection-only. The view never executes a retrain or rollback — that
  is the operational playbook's job (post-M). No approve/reject
  buttons; this is a monitoring surface, not a decision surface.

---

## Design rules

### Hierarchy
Each view has at most three primary cards. Secondary detail lives one
click away.

### Status colors
- Green: nominal
- Yellow: elevated risk
- Red: breach likely or in progress
- Grey: data unavailable / sensor degraded
Never use red for anything other than risk. No marketing red.

### Confidence display
Every prediction or recommendation card shows a confidence percentage
and a one-line uncertainty note. Never hide confidence.

For recommendations (M.3.1+), show **two** confidences side-by-side:
the predictive `confidence` and the causal-protocol `causal_confidence`
(penalty-adjusted per `docs/causal-protocol.md`). The pairing exposes
the gap between "the model thinks this will work" and "the model has
causal evidence it will work" — load-bearing while we operate on
single-station observational data.

### Evidence-class chip
Every attribution card and recommendation card surfaces an
`EvidenceChip` (M.3.1). The chip labels the evidence class
(`EXPERIMENTAL`, `QUASI-EXPERIMENTAL`, `OBSERVATIONAL`,
`EXPERT JUDGMENT`) and tiers it visually (strong = green, weak =
yellow). Hover tooltip explains what causal claims the class can and
cannot support. Never collapse the chip into a row that hides at
narrow widths — operators making intervention decisions must see it.

### Calibration badge
Every recommendation card and the compliance dashboard surface a
`CalibrationBadge` (M.4.1) driven by the latest persisted
`model_performance_metrics.metric_payload.ece` for the active model.
Three tiers: `CAL OK` (ECE ≤ 50% of `max_ece`), `CAL MARGINAL`
(in-gate but high), `CAL OVERRIDE` (over-gate; only possible when an
operator override reason was supplied — the override reason is shown
in the tooltip). Defensive `CAL UNKNOWN` when no metric row exists.

### Reason display
Every recommendation shows the human-readable reason from S12. Never
collapse it into a tooltip. The operator must see it.

### Approve / reject / override
- Three buttons. Plain labels. Visible at glance.
- Override opens a small modal asking for chosen action + free-text
  reason (required).
- Approval action is logged immediately (S13).

### Data quality warnings
If `data_quality_warnings` is non-empty on a card, render a small
warning row above the card body listing the affected sensors. Do not
hide.

### Stale data
If a card's underlying data is older than its expected refresh window,
show a stale badge with the age. Do not silently render stale numbers.

### No business logic in components
Components render API responses. They do not compute breach
probabilities, do not compute attribution, do not call models, do not
mutate state beyond approval calls.

### Map
- Must show wind direction.
- Must show active dust-generating zones.
- Must show downwind sensors / communities.
- Must allow click-to-drill-into-zone.
- The map is one card, not the whole page; if it crashes the rest of
  the dashboard keeps working (Architecture rule 2 - fault isolation).

---

## Accessibility minimums

- Color is never the only signal (icons + text accompany status colors).
- Text size adjustable (operator stations vary).
- High-contrast mode supported.
- Keyboard navigable (control-room operators may use keyboard
  shortcuts).

---

## What to defer

- Animated transitions beyond what helps perception.
- 3D mine views.
- AI-generated narrative summaries (the recommendation engine already
  produces text; a chat layer is not needed for MVP).
- Custom drag-to-build dashboards (post-MVP).
- Mobile-optimized layout (post-MVP; control rooms are first).

---

## Phase

J. UI scaffolding may appear in Phase B for health endpoints, but the
operational views land in Phase J.
