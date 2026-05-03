# Anti-hindsight protocol

The binding contract that ensures DustOps never trains, evaluates, or recommends using information that would not have been available at decision-time.

Hindsight bias is more dangerous than generic overfit because it can hide *inside* a clean walk-forward backtest. A perfect train/test temporal split still leaks when the test-time data is the *post-hoc QC'd* version of what the model would have actually seen.

This protocol is paired with `docs/anti-overfit-protocol.md`. Both must pass.

---

## Decision rule

Every feature, label, and weather record consumed by training or evaluation must answer:

> **"Was this value, in this form, knowable at the prediction's `issued_at` timestamp?"**

If the answer is no — or if the protocol cannot determine the answer — the record is illegal for training and may only be used for *evaluation* (with the contamination explicitly logged).

## Specific rules

### Rule 1 — SINCA validated/realtime split

The SINCA portal exposes two columns per hour ([app/ingestion/public/sinca.py:84](../app/ingestion/public/sinca.py)):
- **col 2 — pre-validated:** the operator's reading at `t`. Available immediately. The model would have seen this value at decision-time.
- **col 3 — validated:** SMA/MMA QA-stamped value, lags col 2 by ~7 days.

**Training / realtime evaluation:**
- Use col 2 only for hours within the last `sinca_validated_legal_only_after_days` (default 7) of the prediction's `issued_at`.
- Use col 3 only for hours where `issued_at - hour ≥ 7 days`.

**Post-hoc evaluation reports** (S15 audit, retrospective analysis): col 3 is preferred. Tag the report `view=retrospective`.

**Implementation status:**
- M.1: protocol declares the rule, `evaluate_model` warns if it cannot verify (no PIT schema yet).
- M.2: `SensorReading` gains `valid_from` / `valid_to` columns; the rule is enforced at the SQL level.

### Rule 2 — ERA5 reanalysis is evaluation-only

ERA5 has a ~3-month QC latency ([app/ingestion/public/era5.py:13](../app/ingestion/public/era5.py)). Training a *realtime* forecaster on ERA5 features means the model uses data that wasn't available when the forecast would have had to fire.

**Rule:**
- Every weather record carries `realtime_proxy: bool`. ERA5 records → `False`. Open-Meteo realtime / forecast records → `True`. NASA POWER records → `False` (also reanalysis).
- Models declaring `intended_for_realtime=True` must filter `WHERE realtime_proxy = True` in their training data SQL. The protocol object's `realtime_proxy_required` flag pins this expectation.
- Realtime models may use ERA5 *only* for evaluation against historical truth — never as a feature.
- Post-hoc / climatological analyses may use ERA5 freely.

**Implementation status:**
- M.1: protocol declares the rule. The Open-Meteo connector ships `realtime_proxy=True` semantically; ERA5 ships `realtime_proxy=False` semantically. M.1 logs a warning if a realtime-flagged model evaluation cannot prove its training data filtered correctly.
- M.2: `WeatherReading.realtime_proxy` becomes a column; SQL-level enforcement.

### Rule 3 — Labeled-at vs event-at

A breach label says "PM10 > 150 over the 24-hr rolling avg ending at midnight." A 14:00 prediction labeled "breach=True" using that label has 10 hours of data the 14:00 model didn't see.

**Rule:**
- Every label-emitting domain module (`DustEvent`, `SourceAttribution`, `ActionOutcome`, `RecommendationApproval`) declares a `labeled_at` timestamp distinct from `event_at` / `recorded_at`.
- A label is **legal as a training feature for prediction `p`** only if `labeled_at ≤ p.issued_at`. Otherwise it is evaluation-only.
- `decision_horizon` is the model's forecast horizon; labels with `labeled_at > issued_at + decision_horizon` cannot be inputs at all (they exist after the model's relevant decision window).

**Implementation status:**
- M.1: protocol declares the rule. The S14 join (`load_and_assemble`) is annotated to flag rows where `labeled_at` is unknown.
- M.2: `labeled_at` becomes a non-null column on the affected tables.

### Rule 4 — Attribution-label provenance

When humans (or LLMs) attribute cause-of-event using post-event analysis, those labels are only valid for *evaluation*. Training S7 (`SourceAttribution`) on them teaches the model to use evidence operators wouldn't have had.

**Rule:**
- `SourceAttribution.derivation` ∈ `{realtime_predicted, post_event_analysis, regulatory_report}`. Only `realtime_predicted` rows are legal training inputs.
- `post_event_analysis` rows are evaluation-only.
- Cross-validation: when both exist for the same event, the divergence is logged in S14's `metric_payload.attribution_drift`.

**Implementation status:**
- M.1: protocol declares the rule. S7 attribution logic flags the field.
- M.2: schema column added.

### Rule 5 — Threshold-tuning timing

Operational thresholds (e.g., breach probability ≥ 0.5) set after seeing test-window outcomes are post-hoc by definition. Anti-overfit rule 5 (pre-registration) covers this from the model side. The hindsight-side restatement:

- Thresholds are an artifact of the validation fold and the **calibration plot built on validation data only**.
- A threshold change after sealed-test outcomes are seen requires bumping `protocol_version` and using a new sealed window.

### Rule 6 — Drift detection cannot read sealed test data

Production drift watchers compare *new* outcomes against *new* predictions. They cannot peek at the sealed test window for "ground truth" comparisons; doing so contaminates the next sealed window for the next model version.

## Failure mode

`validate_protocol_obeyed(...)` returns:
- `errors` for rules 1–5 violations the M.1 protocol can verify (e.g., `realtime_proxy_required=True` set but training query reads ERA5 rows). Hard fail; nothing persists.
- `warnings` for rules whose enforcement is M.2-deferred (e.g., SINCA col-3 filtering before PIT schema lands). The metric row carries the warnings; agent-check shows them but does not fail.

Once M.2 lands, all warnings become errors.

## Implementation timeline

| Rule | M.1 | M.2 (current) |
|---|---|---|
| 1. SINCA col-2/col-3 split | Protocol + warning | **Enforced** via `SensorReading.valid_from / valid_to` columns + SQL probe in `validate_protocol_obeyed`. Parser emits dual rows when both columns present (`parse_sinca_csv(emit_all_versions=True)` + `expand_to_pit_records`). |
| 2. ERA5 evaluation-only | Protocol + warning | **Enforced** via `WeatherReading.realtime_proxy` column + SQL probe. Realtime-intended training rejects rows with `realtime_proxy=False`. Use `pit_query.weather_readings_as_of(..., realtime_only=True)` at the read side. |
| 3. Labeled-at vs event-at | Protocol + warning | **Enforced** via `labeled_at` columns on `dust_events`, `recommendations`, `recommendation_approvals`, `action_outcomes`, `source_attributions`. Read-side filter via `pit_query.labels_as_of(...)`. |
| 4. Attribution provenance | Protocol + warning | **Enforced** via `SourceAttribution.derivation` column with default `realtime_predicted`. Training queries restrict to that value; `post_event_analysis` is evaluation-only. |
| 5. Threshold-tuning timing | Hard rule (errors) — pre-registered protocol_hash | unchanged |
| 6. Drift watcher isolation | Hard rule (errors) — sealed_test_used flag | unchanged |

## Read-side helpers (M.2)

`app/domain/pit_query.py` exposes the canonical as-of filters every
domain caller must use when consuming PIT-tracked tables:

- `sensor_readings_as_of(prediction_time)` — applies `valid_from <= prediction_time AND (valid_to IS NULL OR valid_to > prediction_time)`.
- `weather_readings_as_of(prediction_time, realtime_only=True)` — applies `timestamp <= prediction_time AND realtime_proxy=True`.
- `labels_as_of(label_model, prediction_time)` — applies `labeled_at <= prediction_time` to any of the five label tables.

Domain modules MUST import from `pit_query` rather than constructing
their own as-of WHERE-clauses; this keeps the filter consistent and
audit-traceable.

## Protocol version

Current: **M.2** (lands 2026-05-03). Supersedes M.1.
