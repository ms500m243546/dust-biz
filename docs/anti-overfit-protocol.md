# Anti-overfit protocol

The binding contract every model evaluation in DustOps must obey.

A "great backtest" is not evidence of a working model. It is a precondition for *one* honest production trial. This protocol exists so that any model promoted past lifecycle step 5 in `docs/model-contracts.md` has cleared a discipline bar — not because the bar is fashionable, but because every "great backtest, terrible production" failure in industry traces back to one of the violations enumerated below.

This protocol is enforced by:
- `app/domain/evaluation_protocol.py` (Python — programmatic check at `evaluate_model` time)
- `scripts/checks/validate-overfit-discipline.js` (agent-check gate — scans persisted `model_performance_metrics.metric_payload` for protocol obedience)
- `docs/anti-hindsight-protocol.md` is its companion; the two are paired and a model must pass both.

---

## Decision rule

A model evaluation is **valid** only if all of:

1. **Split is temporal, not random.** `split_strategy ∈ {walk_forward, expanding_window, sealed_test}`. `random_kfold` is forbidden — time-series leakage destroys the validation signal.
2. **Embargo separates train from validation.** `validation_window_from ≥ train_window_to + embargo_days` (default 7). Embargo absorbs leakage from rolling-window features into the next fold.
3. **Sealed test window exists.** `test_window_from ≥ validation_window_to + embargo_days` AND `test_window_to - test_window_from` covers at least one full seasonal cycle (default 6 months). The window is opened **exactly once** per model_version, at go/no-go.
4. **Baselines are named and beaten.** `baselines_named` includes at minimum: `persistence`, `seasonal_naive`, `regulatory_threshold_classifier`. The candidate model's operationally meaningful metrics (breach precision/recall, false-alarm rate, avoided-shutdowns) must beat all three on out-of-sample data. If it does not, the model is killed regardless of MAE.
5. **Pre-registered.** The protocol object is hashed (`protocol_hash` = SHA-256 of canonical-JSON of the immutable fields) and the hash is recorded in `model_performance_metrics.metric_payload.protocol_hash` before evaluation runs. Hash mismatch on re-eval = pre-registration violation.
6. **Operationally meaningful metrics required.** `metric_payload` must contain: `breach_precision`, `breach_recall`, `false_positive_rate`, `false_negative_rate`, `calibration_error`. MAE alone is not sufficient.
7. **Geographic-generalization claims are blocked while `station_count < 2`.** A model trained on one station cannot claim it generalizes to other receptors. Cross-station claims require leave-one-station-out CV.
8. **Calibration acceptance gate (M.4.1).** Expected Calibration Error (10-bin reliability) must be `≤ protocol.max_ece` (default **0.05**). Violations raise `ProtocolViolation` and persist nothing unless the protocol carries a non-empty `ece_override_reason` — the override is logged on the metric row as a warning so an auditor can find every gate-bypass after the fact. `metric_payload` now also persists `calibration_bins[]` (one entry per 10% bin: `lower`, `upper`, `count`, `avg_predicted`, `actual_frequency`) and the Brier score so the reliability diagram is reproducible from the audit row alone.
9. **Covariate discipline (M.4.1).** The protocol declares the actual `feature_set` used by the model plus optional `required_covariates` and `forbidden_covariates`. Required entries must appear in `feature_set`; forbidden ones must not. All three lists are part of `protocol_hash`, so swapping features without updating the pre-registration is detectable. Use `forbidden_covariates` to lock out post-intervention or hindsight features (e.g. `validated_pm10_col3`); use `required_covariates` to lock in confounders flagged in `docs/bias-register.md` (e.g. `humidity` for B-18 mitigation).

## Failure mode

`validate_protocol_obeyed(protocol, …)` returns a `ValidationResult` with:
- `errors`: hard violations of rules 1–7. `evaluate_model` raises `ProtocolViolation` and persists nothing.
- `warnings`: deferred enforcements (rules that need M.2 PIT schema to actually verify). Logged + persisted on the metric row but do not block.
- `ok`: protocol clean.

The agent-check gate scans `model_performance_metrics` rows committed since the previous run. Any row whose `metric_payload.protocol_hash` is missing, doesn't match its declared protocol, or carries `errors` fails the build.

## Mandatory baselines — definitions

- **Persistence (`pm10[t+horizon] = pm10[t]`):** the dumbest possible forecaster. Beating it proves the model is using *anything* beyond "right now."
- **Seasonal-naive (`pm10[t+horizon] = pm10[same hour, same day-of-year, last year]`):** captures diurnal + annual cycles. Beating it proves the model is using *something the calendar doesn't already give you*.
- **Regulatory-threshold classifier (`breach[t+horizon] = pm10[t] > 100`):** the trivial classifier that fires whenever current PM10 is over the warning threshold. Beating it proves the breach-probability output is more than a thin wrapper around current state.

A candidate model must beat **all three** on:
- Breach precision at the operational decision threshold (default 0.5 probability).
- Breach recall at the same threshold.
- Avoided-shutdowns count.
- Production-loss-tonnes-total (lower is better).

If MAE wins but operational metrics lose to a baseline, the candidate loses. MAE is reported but does not gate.

## Anti-peeking discipline

- The sealed test window's first-use timestamp is recorded on the metric row (`sealed_test_first_use_at`). A second metric row referencing the same `(model_version, sealed_test_window)` pair is forbidden — agent-check fails.
- Threshold tuning happens on the validation fold only. Setting any threshold from sealed-test data is a pre-registration violation.
- Re-evaluating the same `(model_version, protocol_hash, window)` triple is a free cache hit; **changing** the protocol after seeing test results requires a new `protocol_version` AND a new sealed window.

## What this protocol does NOT cover

- **Hindsight bias** (using info that wasn't knowable at decision-time): see `docs/anti-hindsight-protocol.md`.
- **Concept drift / regime change:** a clean backtest on 2014 data is not evidence the model works in 2026. Drift watch is M.4.3.
- **Causal/treatment-effect contamination:** historical PM10 reflects the post-intervention world. Causal layer is M.3.
- **Goodhart's law on deployed metrics:** M.4.2.
- **Receptor fairness (Cuncumén-vs-Caimanes priority asymmetry):** M.4.2.

The full bias surface is enumerated in `docs/bias-register.md`.

## Protocol version

Current: **M.4** (rules 8 + 9 added 2026-05-03). M.1 was the original split-discipline + baselines + sealed-test contract; M.4 extends with calibration + covariate discipline. Pre-M.1 metric rows are tagged `protocol_version="pre-M"` and excluded from the gate. M.1/M.2/M.3 rows persisted before M.4.1 are still legal but the validator emits a warning so the operator knows which rows still need re-evaluation under the calibration gate.
