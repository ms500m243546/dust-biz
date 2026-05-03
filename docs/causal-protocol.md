# Causal protocol

The binding contract for what *kind of evidence* DustOps claims, by subsystem.

This protocol pairs with `docs/anti-overfit-protocol.md` (no fitting to the test set) and `docs/anti-hindsight-protocol.md` (no using future data). Those handle the **temporal** half of honest training. This document handles the **counterfactual** half: when the system says "doing X causes Y," what evidence supports that claim?

The hard truth: at single-station, single-mine, observational-only data scale, DustOps cannot manufacture causal evidence. What this protocol does — and **all it does** — is prevent the system from *claiming* causal evidence it doesn't have. Real causal-grade work (RCT, propensity scores, IV) requires data that is currently deferred (≥ 2 receptors, operator-real intervention timestamps, ability to run controlled trials at a producing mine — the last one being unrealistic).

---

## Evidence-class hierarchy

Strongest → weakest:

| Class | Definition | Available now? |
|---|---|---|
| `experimental` | Operator alternated between intervention and control on otherwise-comparable shifts (RCT or A/B). | No. Production-loss-tonnes-tied operator KPIs make controlled trials at a producing mine unrealistic; reserved for the future / controlled side-by-side haul-road segments. |
| `quasi_experimental` | Natural experiment, instrumental variable, regression discontinuity, propensity-score matched. | Not until ≥ 2 stations land + operator-real intervention timestamps capture treatment-vs-control. |
| `observational_correlational` | Historical correlation. **The realistic class for everything DustOps produces today.** | Yes. Default for all S7 attributions and S9 simulations. |
| `expert_judgment` | RCA-derived attribution where humans labeled cause-of-event using post-event analysis. | Per anti-hindsight rule 4 + M.2 `derivation` column, evaluation-only. May not be used as a training feature. |

## Per-subsystem rules

### S6 — Dust forecasting

May use any evidence class for *prediction* — correlation suffices to answer "what will PM10 be in 60 minutes?" The forecaster does not claim causality, so no `evidence_class` field on `DustForecast`.

What changes in M.3: a forecaster that consumes operator-reactive features (truck speed, watering events) at training time may be silently learning the post-intervention world. Mitigation: training pipelines for S6 should use `pit_query.features_pre_intervention(...)` to filter out features that fall within the operator's typical reaction window.

### S7 — Source attribution

**Must emit `evidence_class` per probable source.**

`SourceAttribution.evidence_class` defaults to `observational_correlational`. Stronger classes (`quasi_experimental`, `experimental`) require corresponding evidence in the row's `evidence_fields` JSON; the validator (M.3.1+) does not yet inspect `evidence_fields` content but the column is reserved.

The S12 recommendation engine reads `evidence_class` per source and surfaces it on the wire so S16 can show operators "we think Haul Road C caused this — based on observational correlation."

### S9 — Intervention simulator

**Must emit `simulation_method` and `counterfactual_assumption`.**

`InterventionSimulation.simulation_method ∈ {naive_correlation, dispersion_model, propensity_matched, rct}`:
- `naive_correlation` (default): the simulator extrapolated PM10 reduction from historical periods that resemble the proposed scenario. Biased — historical periods reflect operator reactions, not no-op baselines.
- `dispersion_model`: AERMOD / CALPUFF physics-based estimate. Available only after Phase L.N (terrain + dispersion modeling) lands.
- `propensity_matched`: matched comparison against historical no-action periods with similar covariates. Requires operator-real intervention timestamps (M.3.3+).
- `rct`: side-by-side controlled trial. Reserved.

`InterventionSimulation.counterfactual_assumption` is a required free-text field describing what world-model the simulator assumed. **Empty string is treated as "no assumption disclosed" and capped at confidence 0.5 by the validator.** Naive simulations should populate this with the explicit caveat — e.g.:

> "We assume the operator's typical reaction window is the no-op baseline. This is biased: the operator's typical action was *also* slowing trucks, so 'no action' periods in the calibration set are also lower-PM10. Effect size is therefore likely overestimated."

**Confidence cap**: `naive_correlation` simulations have `confidence` automatically clamped at 0.7 by the validator. The cap is configurable per `SiteConfiguration` (default 0.7); production deploys may lift it with explicit operator sign-off + audit log entry.

### S10 — Production cost model

**Must emit `selection_bias_caveat`.** (Implemented as a column on `InterventionSimulation` since cost lives on that table — see [docs/data-contracts.md](data-contracts.md).)

`selection_bias_caveat: bool = True` by default. True means the cost calibration set covers only operator-acted interventions — i.e., we do not have data on what happened on shifts where the operator chose NOT to act. This biases cost estimates toward "interventions that worked at preserving production" because rejected interventions weren't recorded.

Setting `selection_bias_caveat=False` requires a documented calibration set that includes operator-rejected intervention windows. Currently impossible without operator-real telematics; deferred.

### S12 — Recommendation engine

**Must emit `causal_confidence`** distinct from `confidence`.

- `Recommendation.confidence`: predictive confidence (how sure we are PM10 will breach).
- `Recommendation.causal_confidence`: confidence in the *causal claim* that the recommended action will produce the predicted reduction.

Computed as `min(predictive_confidence, simulation_confidence_after_evidence_class_penalty)`. The penalty:
- `experimental` simulation: 0% penalty.
- `quasi_experimental`: 10% penalty.
- `observational_correlational`: 30% penalty (and confidence ceiling 0.7 per S9 cap).
- `expert_judgment`: not eligible for recommendations (training-only).

`causal_confidence` surfaces on the wire so S16 can display both numbers; approval gates may require `causal_confidence` above a configurable threshold separately from predictive confidence.

## Causal-intent probe in `validate_protocol_obeyed`

`EvaluationProtocol.causal_intent: bool = False` (M.3.1). When True, the evaluator declares this run is making a causal claim (e.g., "model X has higher recall than model Y, *and* this is because X uses better features, not because Y trained on a noisier window"). The new SQL probe enforces:

1. Training data must include at least one source with `evidence_class != observational_correlational`. Otherwise: hard error.
2. S9 simulations in the protocol's training window must not be all `naive_correlation`. Otherwise: hard error.

Default is `causal_intent=False` because most evaluations are predictive, not causal. Models claiming causality must opt in.

## Pre-intervention feature filter

`app/domain/pit_query.py:features_pre_intervention(prediction_time, intervention_lag_minutes=180)` is the canonical filter for any pipeline that wants to learn the *natural* PM10 trajectory rather than the post-intervention one. Drops feature rows that fall within `intervention_lag_minutes` of any logged operator approval (`RecommendationApproval.decided_at + duration`).

This is a **best-effort heuristic at M.3.1**: it catches DustOps-mediated interventions but misses operator-initiated actions outside the system. Tightens to a hard cutoff in M.3.3 once `ActionOutcome.intervention_window` lands.

## Failure mode

`validate_causal_claim(...)` returns a `CausalValidationResult` with `errors` (block) and `warnings` (logged on the metric row). Errors at M.3.1:
- S9 simulation with empty `counterfactual_assumption` AND `simulation_method=naive_correlation`: hard error.
- Confidence > 0.7 on a `naive_correlation` simulation that has not been overridden via `SiteConfiguration.naive_simulation_confidence_cap`: hard error.
- `EvaluationProtocol.causal_intent=True` with all-observational training data: hard error.

## What this protocol does NOT cover

- **Real causal inference engine** — propensity scoring, DAG / do-calculus, structural equation modeling. Deferred indefinitely; depends on data we don't have.
- **UI surfacing of `evidence_class`** — M.3.2.
- **`ActionOutcome.intervention_window`** capture — M.3.3, depends on operator-real adapter.
- **Running RCT-grade trials at the mine** — out of scope for this product.

## Protocol version

Current: **M.3.1** (lands 2026-05-03).
