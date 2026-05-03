# Forecast-model training protocol (Phase P+)

The binding contract for any *trained* dust-forecast model that ships
in this repo. Built on top of `docs/anti-overfit-protocol.md`,
`docs/anti-hindsight-protocol.md`, and `docs/causal-protocol.md`.

The Phase E heuristic baseline (`HeuristicBaselineForecaster`) is
exempt from training-time protocols — it has no fit step. Every other
forecast model must:

1. Declare an `EvaluationProtocol` (M.4 shape) before training.
2. Train on a walk-forward split, embargo-respecting.
3. Persist the artifact to `data_models/dust_forecast/<model_version>/<station_id>__<horizon>.joblib`.
4. Write exactly one `model_performance_metrics` row per trained
   (station, horizon) artifact, carrying the M.4 metric_payload
   (calibration_bins, ece, brier_score, per_receptor, canary_metrics,
   plus protocol_hash + protocol_version).
5. Pass the M.4.1 ECE gate (`ece <= max_ece`, default 0.05) before
   the trainer is permitted to *promote* the model to `current` via
   `app.models.registry.set_current`.

If step 5 fails, the trainer must:
- still write the metric row (so the failure is auditable)
- leave `current` pointing at whichever model was current before
- emit a clear failure message naming the gate

---

## Phase P.1 — Cuncumén baseline declaration

The single canonical EvaluationProtocol used by the first trained
model (Cuncumén only, 60-min horizon):

| Field | Value |
|---|---|
| `split_strategy` | `walk_forward` |
| `train_window_from` → `train_window_to` | `2025-05-03` → `2026-02-03` (~9 mo) |
| `validation_window_from` → `validation_window_to` | `2026-02-10` → `2026-03-25` (~6 wk) |
| `test_window_from` → `test_window_to` | `2026-04-01` → `2026-05-03` (~5 wk, sealed) |
| `embargo_days` | 7 |
| `sealed_test_used` | `True` |
| `feature_set` | see below |
| `required_covariates` | `("humidity_pct",)` |
| `forbidden_covariates` | `()` |
| `max_ece` | 0.05 |
| `causal_intent` | `False` (predictive only) |
| `protocol_version` | `M.4` |

### Feature set

Every feature must be derivable from `weather_readings` +
`sensor_readings` alone (no `MineStateZoneSchema` activity inputs
— Cuncumén is a SINCA receptor with no associated zone).

| Feature | Definition |
|---|---|
| `pm10_lag_1h` | PM10 reading 1 hour before `as_of` |
| `pm10_lag_3h` | PM10 reading 3 hours before `as_of` |
| `pm10_lag_24h` | PM10 reading 24 hours before `as_of` |
| `pm10_rolling_mean_24h` | mean of PM10 in [as_of − 24h, as_of) |
| `wind_speed_ms` | most recent `weather_readings.wind_speed_ms` ≤ as_of |
| `wind_direction_deg` | as above |
| `humidity_pct` | as above |
| `temperature_c` | as above |
| `pressure_hpa` | as above |
| `rainfall_mm_15min` | as above |
| `hour_of_day` | `as_of.hour` (categorical, 0–23) |
| `month` | `as_of.month` (categorical, 1–12) |

### Target

`pm10_at_(as_of + 60min)` — the next-hour PM10 reading at the same
station.

### Algorithm

`sklearn.ensemble.HistGradientBoostingRegressor` with default
hyper-parameters except `max_iter=200`, `random_state=0`. Categorical
features (`hour_of_day`, `month`) are passed via the native
`categorical_features` argument so the encoder is part of the saved
model.

### Persistence

```
data_models/dust_forecast/dust_forecast_gbm_v0.1.0/lp-em05-cuncumen__60min.joblib
```

The artifact is a `joblib.dump` of a small dict:
`{"model": <fitted regressor>, "feature_columns": [...], "training_protocol_hash": "<sha256>"}`.

---

## Phase Q+ — Multi-station extensions

Q.1 adds one (station, horizon) artifact per SINCA station, all
keyed by the same `model_version`. Q.2 adds a *shared* model with
`station_id` as a categorical, persisted as
`data_models/dust_forecast/<model_version>__shared/all__60min.joblib`.

Per-receptor metrics (`per_receptor` block in metric_payload) become
non-trivial in Q.1 — Phase P.1's single-station case populates a
single-key dict so the M.4.2 audit machinery is exercised end-to-end.

---

## What this protocol does NOT cover

- Cost / production-impact models (S10).
- Source-attribution models (S7) — see `docs/causal-protocol.md`.
- Intervention-impact models (S9) — see `docs/intervention-physics.md`
  (Phase R).
- Optimization (S11).

These have their own model-contracts and gate machinery, and they
plug into the same registry but with different evaluation protocols.
