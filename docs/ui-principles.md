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
