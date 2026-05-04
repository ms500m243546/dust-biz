"""Dust-forecast training pipeline (Phase P).

Orchestrates the full training loop for one (station, horizon)
GBM forecaster:

  1. Pull SINCA + weather rows from the dev DB for the protocol's
     train + validation + test windows.
  2. Build station-level features (the canonical 12-feature set
     declared in `FEATURE_SET_P1`).
  3. Walk-forward fit a `HistGradientBoostingRegressor` (PM10
     regression) plus a `HistGradientBoostingClassifier` for
     breach probability — same features, target = (actual >= 150).
  4. Predict on the sealed test window.
  5. Synthesize `TrainingRecordSchema` rows from predictions +
     observed actuals and pass them through
     `app.domain.model_performance.compute_metric_payload` so the
     M.4.1 ECE acceptance gate, M.4.2 per-receptor split + Goodhart
     canaries, and protocol-hash audit are applied uniformly.
  6. Persist the artifact (joblib dict) and the metric_payload row.

If the M.4.1 ECE gate raises `ProtocolViolation` on the first fit,
the trainer attempts ONE re-fit with isotonic-recalibrated breach
probabilities (sklearn `CalibratedClassifierCV` 'isotonic'). If
that still fails, the training run propagates the exception (the
caller's stop-gate SG-1).

Why a separate module from `app.domain.model_performance`: this
file *creates* metric_payload rows by *training a model*; that
one *reduces* already-collected predictions into a metric_payload.
"""

from __future__ import annotations

import bisect
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import joblib  # type: ignore[import-untyped]
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
)
from sqlalchemy import select

from app.domain.evaluation_protocol import (
    PROTOCOL_VERSION,
    EvaluationProtocol,
    ProtocolViolation,
)
from app.domain.model_performance import compute_metric_payload
from app.models.forecasting.gbm_shared_v0_1_0 import (
    GBM_SHARED_VERSION,
    shared_artifact_path,
)
from app.models.forecasting.gbm_v0_1_0 import (
    GBM_VERSION,
    MODEL_KIND,
    artifact_path,
)
from app.schemas.forecasts import ForecastHorizon
from app.schemas.model_performance import TrainingRecordSchema
from app.storage.models import (
    ModelPerformanceMetric,
    SensorReading,
    WeatherReading,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Phase P.1 — declared canonical feature set for the Cuncumén baseline.
# Every entry must be derivable purely from `weather_readings` +
# `sensor_readings` (no zone-state, no equipment activity); see
# docs/forecast-model-protocol.md for each lag/feature's definition.
FEATURE_SET_P1: tuple[str, ...] = (
    "pm10_lag_1h",
    "pm10_lag_3h",
    "pm10_lag_24h",
    "pm10_rolling_mean_24h",
    "wind_speed_ms",
    "wind_direction_deg",
    "humidity_pct",
    "temperature_c",
    "pressure_hpa",
    "rainfall_mm_15min",
    "hour_of_day",
    "month",
)

REQUIRED_COVARIATES_P1: tuple[str, ...] = ("humidity_pct",)
FORBIDDEN_COVARIATES_P1: tuple[str, ...] = ()

DEFAULT_HORIZON: ForecastHorizon = "60min"
HORIZON_MINUTES: dict[ForecastHorizon, int] = {
    "15min": 15,
    "30min": 30,
    "60min": 60,
    "120min": 120,
    "24h": 24 * 60,
}

# PM10 breach threshold (µg/m³) — matches the heuristic baseline's
# _PM10_BREACH and Chilean D.S. 12/2011 24h primary norm.
PM10_BREACH = 150.0

# Feature_pipeline_version — distinct from feature_set, this version
# string identifies the *builder code* shape so a payload can be
# re-derived later. Bump when this module's feature semantics change.
FEATURE_PIPELINE_VERSION = "feature_pipeline_p1_v0.1.0"

# Per-station weather target. Phase Q.1 fans out to all 5 SINCA-public
# stations across 4 mines. Each station is paired with the receptor-
# co-located weather target from the corresponding data_seed YAML so
# the GBM can learn receptor-specific transport. Mine-centroid weather
# is tracked separately and reserved for future zone-anchored modelling.
STATION_WEATHER_TARGETS: dict[str, str] = {
    "lp-em05-cuncumen": "lp-cuncumen-met",
    "lb-las-condes": "lb-las-condes-met",
    "chq-club-23-marzo": "chq-calama-met",
    "chq-calama-centro": "chq-calama-met",
    "cnt-sierra-gorda": "cnt-sierra-gorda-met",
}
DEFAULT_WEATHER_TARGET = "lp-mine-centroid"

# Phase Q.1 — the canonical multi-station roster for batch training.
# Mirrors the 5 stations in data_seed/*.yaml with `sinca_data_status:
# has_data`. Per-station fits live under one shared model_version
# (`dust_forecast_gbm_v0.1.0`); the registry resolves by (station_id,
# horizon) artifact path inside `GBMForecaster.predict()`.
MULTI_STATION_ROSTER: tuple[str, ...] = (
    "lp-em05-cuncumen",
    "lb-las-condes",
    "chq-club-23-marzo",
    "chq-calama-centro",
    "cnt-sierra-gorda",
)


@dataclass(frozen=True)
class TrainingResult:
    """Audit-trail returned from `train_one()`.

    `artifact_path` is None when persist=False or when the gate
    blocked persistence. `metric_row_id` is None when no row was
    written.
    """

    model_version: str
    station_id: str
    horizon: ForecastHorizon
    protocol_hash: str
    train_record_count: int
    test_record_count: int
    ece: float | None
    mae_pm10: float | None
    breach_recall: float | None
    artifact_path: Path | None
    metric_row_id: int | None
    recalibrated: bool


def build_p1_protocol(
    *,
    train_window_from: datetime,
    train_window_to: datetime,
    validation_window_from: datetime,
    validation_window_to: datetime,
    test_window_from: datetime,
    test_window_to: datetime,
    causal_intent: bool = False,
) -> EvaluationProtocol:
    """Construct the canonical Phase P.1 EvaluationProtocol."""
    return EvaluationProtocol(
        split_strategy="walk_forward",
        train_window_from=train_window_from,
        train_window_to=train_window_to,
        validation_window_from=validation_window_from,
        validation_window_to=validation_window_to,
        test_window_from=test_window_from,
        test_window_to=test_window_to,
        embargo_days=7,
        sealed_test_used=True,
        feature_set=FEATURE_SET_P1,
        required_covariates=REQUIRED_COVARIATES_P1,
        forbidden_covariates=FORBIDDEN_COVARIATES_P1,
        causal_intent=causal_intent,
        protocol_version=PROTOCOL_VERSION,
        notes="Phase P.1 baseline — Cuncumén only, 60-min horizon.",
    )


def _realtime_pm10_series(
    *,
    session: Session,
    station_id: str,
    window_from: datetime,
    window_to: datetime,
) -> list[tuple[datetime, float]]:
    """Pull PM10 readings as the realtime regime would see them.

    Anti-hindsight rule 1 — the model is `intended_for_realtime=True`,
    so its training inputs must reflect the data shape available at
    realtime decision time. Empirically the SINCA portal hasn't
    promoted the 2025+ window from col-2 (pre-validated) to col-3
    (validated) yet, and even when it does, col-2 is what hits
    realtime; col-3 arrives ~7 days later. Therefore we read whichever
    PIT version is current as-of `timestamp`, breaking ties in favor
    of the earlier `valid_from` (the realtime emission). De-dupes per
    timestamp.
    """
    rows = session.execute(
        select(SensorReading)
        .where(SensorReading.sensor_id == station_id)
        .where(SensorReading.timestamp >= window_from)
        .where(SensorReading.timestamp < window_to)
        .order_by(
            SensorReading.timestamp.asc(),
            SensorReading.valid_from.asc(),
        )
    ).scalars().all()
    out: list[tuple[datetime, float]] = []
    seen_ts: set[datetime] = set()
    for r in rows:
        if r.timestamp in seen_ts:
            continue
        rv = r.raw_value or {}
        v = rv.get("pm10_ugm3")
        if not isinstance(v, (int, float)):
            continue
        seen_ts.add(r.timestamp)
        out.append((r.timestamp, float(v)))
    return out


def _weather_series(
    *,
    session: Session,
    weather_target_id: str,
    window_from: datetime,
    window_to: datetime,
) -> list[WeatherReading]:
    """Pull realtime-proxy weather rows for one target, ascending."""
    rows = session.execute(
        select(WeatherReading)
        .where(WeatherReading.weather_target_id == weather_target_id)
        .where(WeatherReading.realtime_proxy.is_(True))
        .where(WeatherReading.timestamp >= window_from)
        .where(WeatherReading.timestamp < window_to)
        .order_by(WeatherReading.timestamp.asc())
    ).scalars().all()
    return list(rows)


def _build_feature_matrix(
    *,
    pm_series: list[tuple[datetime, float]],
    weather: list[WeatherReading],
    horizon_minutes: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[datetime]]:
    """Build (X, y_pm10, y_breach, timestamps) for the supervised fit.

    Each row corresponds to a prediction issue time `t`. Features are
    derived from PM10 history strictly older than `t` and from the
    most-recent weather reading ≤ t. Target is PM10 at `t + horizon`.
    Rows where target is missing are dropped.
    """
    pm_ts: list[datetime] = [t for t, _ in pm_series]
    pm_vals: list[float] = [v for _, v in pm_series]
    pm_index: dict[datetime, int] = {t: i for i, t in enumerate(pm_ts)}

    # Weather sorted ascending — for each issue time, find the most
    # recent weather reading whose timestamp is ≤ t. Use bisect over
    # plain Python lists (numpy.searchsorted is poorly typed on
    # object-dtype arrays of datetime).
    w_ts: list[datetime] = [w.timestamp for w in weather]

    horizon_delta = timedelta(minutes=horizon_minutes)

    rows: list[list[float]] = []
    y_pm10: list[float] = []
    y_breach: list[int] = []
    timestamps: list[datetime] = []

    for t, _ in pm_series:
        target_t = t + horizon_delta
        target_idx = pm_index.get(target_t)
        if target_idx is None:
            continue
        target_pm10 = pm_vals[target_idx]

        pm_lag_1h = _lag_value(pm_ts, pm_vals, t, timedelta(hours=1))
        pm_lag_3h = _lag_value(pm_ts, pm_vals, t, timedelta(hours=3))
        pm_lag_24h = _lag_value(pm_ts, pm_vals, t, timedelta(hours=24))
        pm_rolling_24h = _rolling_mean(pm_ts, pm_vals, t, timedelta(hours=24))

        w_idx = bisect.bisect_right(w_ts, t) - 1 if w_ts else -1
        if 0 <= w_idx < len(weather):
            w = weather[w_idx]
            wind_speed = _to_float(w.wind_speed_ms)
            wind_dir = _to_float(w.wind_direction_deg)
            humidity = _to_float(w.humidity_pct)
            temp = _to_float(w.temperature_c)
            pressure = _to_float(w.pressure_hpa)
            rain = _to_float(w.rainfall_mm_15min)
        else:
            wind_speed = wind_dir = humidity = temp = pressure = rain = float("nan")

        row = [
            pm_lag_1h,
            pm_lag_3h,
            pm_lag_24h,
            pm_rolling_24h,
            wind_speed,
            wind_dir,
            humidity,
            temp,
            pressure,
            rain,
            float(t.hour),
            float(t.month),
        ]
        rows.append(row)
        y_pm10.append(target_pm10)
        y_breach.append(1 if target_pm10 >= PM10_BREACH else 0)
        timestamps.append(t)

    return (
        np.array(rows, dtype=np.float64),
        np.array(y_pm10, dtype=np.float64),
        np.array(y_breach, dtype=np.int64),
        timestamps,
    )


def _lag_value(
    pm_ts: list[datetime],
    pm_vals: list[float],
    t: datetime,
    delta: timedelta,
) -> float:
    if not pm_ts:
        return float("nan")
    target = t - delta
    # Most recent reading at or before `target`.
    idx = bisect.bisect_right(pm_ts, target) - 1
    return float(pm_vals[idx]) if 0 <= idx < len(pm_vals) else float("nan")


def _rolling_mean(
    pm_ts: list[datetime],
    pm_vals: list[float],
    t: datetime,
    window: timedelta,
) -> float:
    if not pm_ts:
        return float("nan")
    lo = bisect.bisect_left(pm_ts, t - window)
    hi = bisect.bisect_right(pm_ts, t)
    if hi <= lo:
        return float("nan")
    sl = pm_vals[lo:hi]
    return sum(sl) / len(sl) if sl else float("nan")


def _to_float(v: float | int | None) -> float:
    if v is None:
        return float("nan")
    return float(v)


def _synth_training_records(
    *,
    timestamps: list[datetime],
    predicted_pm10: np.ndarray,
    predicted_breach_prob: np.ndarray,
    actual_pm10: np.ndarray,
    station_id: str,
    horizon: ForecastHorizon,
    model_version: str,
) -> list[TrainingRecordSchema]:
    """Wrap (predictions, actuals) as TrainingRecordSchema rows.

    `compute_metric_payload` consumes this shape; reusing it here keeps
    the M.4.1 ECE gate, M.4.2 per-receptor split, and Goodhart canary
    calculation in lockstep with the rest of the platform.
    """
    out: list[TrainingRecordSchema] = []
    for i, ts in enumerate(timestamps):
        actual = float(actual_pm10[i])
        pred_pm10 = float(predicted_pm10[i])
        pred_prob = float(predicted_breach_prob[i])
        out.append(
            TrainingRecordSchema(
                prediction_id=f"train::{station_id}::{ts.isoformat()}",
                issued_at=ts,
                target_kind="sensor",
                target_id=station_id,
                forecast_horizon=horizon,
                predicted_pm10=pred_pm10,
                predicted_pm25=0.0,
                predicted_breach_probability=pred_prob,
                confidence=0.7,
                model_version=model_version,
                human_action="no_recommendation",
                actual_pm10_peak=actual,
                breach_occurred=actual >= PM10_BREACH,
                outcome_status="observed",
                recorded_at=ts,
            )
        )
    return out


def _persist_artifact(
    *,
    artifact_root: Path | None,
    model_version: str,
    station_id: str,
    horizon: ForecastHorizon,
    payload: dict[str, Any],
) -> Path:
    out_path = artifact_path(
        artifact_root=artifact_root,
        model_version=model_version,
        station_id=station_id,
        horizon=horizon,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(payload, out_path)
    return out_path


def _persist_metric_row(
    *,
    session: Session,
    model_version: str,
    window_from: datetime,
    window_to: datetime,
    sample_count: int,
    metric_payload: dict[str, Any],
) -> int:
    row = ModelPerformanceMetric(
        model_version=model_version,
        model_kind=MODEL_KIND,
        evaluated_at=datetime.now(UTC).replace(tzinfo=None),
        window_from=window_from,
        window_to=window_to,
        sample_count=sample_count,
        metric_payload=metric_payload,
    )
    session.add(row)
    session.flush()
    return int(row.metric_id)


def _fit_models(
    X: np.ndarray,
    y_pm10: np.ndarray,
    y_breach: np.ndarray,
    *,
    recalibrate: bool,
    random_state: int = 0,
) -> tuple[HistGradientBoostingRegressor, Any]:
    """Fit (regressor, classifier). Optionally isotonic-recalibrate."""
    regressor = HistGradientBoostingRegressor(
        max_iter=200,
        random_state=random_state,
    )
    regressor.fit(X, y_pm10)

    base_clf = HistGradientBoostingClassifier(
        max_iter=200,
        random_state=random_state,
    )
    if recalibrate:
        # Wrap the classifier in CalibratedClassifierCV with isotonic
        # regression. Uses internal CV so we don't need a held-out
        # calibration window.
        clf = CalibratedClassifierCV(base_clf, method="isotonic", cv=3)
        clf.fit(X, y_breach)
    else:
        base_clf.fit(X, y_breach)
        clf = base_clf
    return regressor, clf


def _evaluate_and_compute_payload(
    *,
    regressor: HistGradientBoostingRegressor,
    classifier: Any,
    X_test: np.ndarray,
    y_pm10_test: np.ndarray,
    timestamps_test: list[datetime],
    station_id: str,
    horizon: ForecastHorizon,
    model_version: str,
    protocol: EvaluationProtocol,
    session: Session,
) -> tuple[dict[str, Any], list[TrainingRecordSchema]]:
    """Predict + synth records + run M.4 metric_payload computation."""
    pred_pm10 = regressor.predict(X_test)
    proba = classifier.predict_proba(X_test)
    # Class order is [0, 1] for binary classifier; column 1 = P(breach).
    pred_breach = proba[:, 1] if proba.shape[1] >= 2 else proba[:, 0]
    records = _synth_training_records(
        timestamps=timestamps_test,
        predicted_pm10=pred_pm10,
        predicted_breach_prob=pred_breach,
        actual_pm10=y_pm10_test,
        station_id=station_id,
        horizon=horizon,
        model_version=model_version,
    )
    payload = compute_metric_payload(
        records,
        protocol=protocol,
        session=session,
    )
    return payload, records


def train_one(
    *,
    station_id: str,
    session: Session,
    horizon: ForecastHorizon = DEFAULT_HORIZON,
    protocol: EvaluationProtocol | None = None,
    artifact_root: Path | None = None,
    persist: bool = True,
) -> TrainingResult:
    """Train one (station, horizon) GBM forecaster.

    If persist=False, the artifact + metric row are skipped (smoke /
    test usage). The return value still carries `ece`, `mae_pm10`,
    `breach_recall` so callers can reason about quality.

    M.4.1 ECE acceptance gate handling:
      - First fit attempt uses uncalibrated breach classifier.
      - If `compute_metric_payload` raises `ProtocolViolation`, do
        ONE re-fit with isotonic recalibration. If that also raises,
        the exception propagates.
    """
    if protocol is None:
        raise ValueError(
            "train_one() requires an explicit EvaluationProtocol "
            "(use build_p1_protocol(...))."
        )

    weather_target_id = STATION_WEATHER_TARGETS.get(
        station_id, DEFAULT_WEATHER_TARGET
    )
    horizon_minutes = HORIZON_MINUTES[horizon]

    # Pull all rows that span train+validation+test plus enough lookback
    # for the 24h features. Lookback = 1 day; embargo handled at the
    # protocol level.
    pull_from = protocol.train_window_from - timedelta(days=2)
    pull_to = protocol.test_window_to

    pm_series = _realtime_pm10_series(
        session=session,
        station_id=station_id,
        window_from=pull_from,
        window_to=pull_to,
    )
    weather = _weather_series(
        session=session,
        weather_target_id=weather_target_id,
        window_from=pull_from,
        window_to=pull_to,
    )
    if len(pm_series) < 200 or len(weather) < 200:
        raise ValueError(
            f"insufficient data for {station_id}: pm_rows={len(pm_series)} "
            f"weather_rows={len(weather)}. Need >=200 of each before fit."
        )

    X_all, y_pm10_all, y_breach_all, ts_all = _build_feature_matrix(
        pm_series=pm_series,
        weather=weather,
        horizon_minutes=horizon_minutes,
    )

    train_mask = _window_mask(
        ts_all, protocol.train_window_from, protocol.train_window_to
    )
    test_mask = _window_mask(
        ts_all, protocol.test_window_from, protocol.test_window_to
    )

    X_train = X_all[train_mask]
    y_pm10_train = y_pm10_all[train_mask]
    y_breach_train = y_breach_all[train_mask]

    X_test = X_all[test_mask]
    y_pm10_test = y_pm10_all[test_mask]
    ts_test = [
        t for t, in_window in zip(ts_all, test_mask, strict=True) if in_window
    ]

    if len(X_train) < 100 or len(X_test) < 30:
        raise ValueError(
            f"insufficient supervised rows: train={len(X_train)} "
            f"test={len(X_test)}. Check protocol windows vs data coverage."
        )

    # First fit — uncalibrated breach classifier.
    regressor, classifier = _fit_models(
        X_train, y_pm10_train, y_breach_train, recalibrate=False
    )
    recalibrated = False
    try:
        payload, _records = _evaluate_and_compute_payload(
            regressor=regressor,
            classifier=classifier,
            X_test=X_test,
            y_pm10_test=y_pm10_test,
            timestamps_test=ts_test,
            station_id=station_id,
            horizon=horizon,
            model_version=GBM_VERSION,
            protocol=protocol,
            session=session,
        )
    except ProtocolViolation:
        # Re-fit with isotonic recalibration. SG-1 fallback.
        regressor, classifier = _fit_models(
            X_train, y_pm10_train, y_breach_train, recalibrate=True
        )
        recalibrated = True
        payload, _records = _evaluate_and_compute_payload(
            regressor=regressor,
            classifier=classifier,
            X_test=X_test,
            y_pm10_test=y_pm10_test,
            timestamps_test=ts_test,
            station_id=station_id,
            horizon=horizon,
            model_version=GBM_VERSION,
            protocol=protocol,
            session=session,
        )

    out_artifact_path: Path | None = None
    metric_row_id: int | None = None
    if persist:
        artifact_payload = {
            "model": {"regressor": regressor, "classifier": classifier},
            "feature_columns": list(FEATURE_SET_P1),
            "feature_pipeline_version": FEATURE_PIPELINE_VERSION,
            "training_protocol_hash": protocol.protocol_hash,
            "training_protocol_version": protocol.protocol_version,
            "horizon": horizon,
            "station_id": station_id,
            "recalibrated": recalibrated,
            "trained_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
        }
        out_artifact_path = _persist_artifact(
            artifact_root=artifact_root,
            model_version=GBM_VERSION,
            station_id=station_id,
            horizon=horizon,
            payload=artifact_payload,
        )
        metric_row_id = _persist_metric_row(
            session=session,
            model_version=GBM_VERSION,
            window_from=protocol.test_window_from,
            window_to=protocol.test_window_to,
            sample_count=len(ts_test),
            metric_payload=payload,
        )

    return TrainingResult(
        model_version=GBM_VERSION,
        station_id=station_id,
        horizon=horizon,
        protocol_hash=protocol.protocol_hash,
        train_record_count=len(X_train),
        test_record_count=len(X_test),
        ece=_as_float(payload.get("ece")),
        mae_pm10=_as_float(payload.get("mae_pm10")),
        breach_recall=_as_float(payload.get("breach_recall")),
        artifact_path=out_artifact_path,
        metric_row_id=metric_row_id,
        recalibrated=recalibrated,
    )


@dataclass(frozen=True)
class SharedTrainingResult:
    """Result of `train_shared_multi_station()`.

    `per_receptor_ece` is the per-station ECE breakdown from
    `compute_metric_payload`'s per_receptor block — load-bearing for
    the Q.2 promotion criterion (`max_per_receptor_ece` is the
    fairness summary).
    """

    model_version: str
    horizon: ForecastHorizon
    protocol_hash: str
    train_record_count: int
    test_record_count: int
    station_vocab: tuple[str, ...]
    aggregate_ece: float | None
    aggregate_mae_pm10: float | None
    aggregate_breach_recall: float | None
    per_receptor_ece: dict[str, float | None]
    artifact_path: Path | None
    metric_row_id: int | None


def train_shared_multi_station(
    *,
    station_ids: Iterable[str],
    session: Session,
    horizon: ForecastHorizon = DEFAULT_HORIZON,
    protocol: EvaluationProtocol | None = None,
    artifact_root: Path | None = None,
    persist: bool = True,
) -> SharedTrainingResult:
    """Phase Q.2 — fit ONE GBM that handles all stations.

    Concatenates all stations' (X, y_pm10, y_breach, ts) tensors and
    appends per-station one-hot columns. The artifact's
    `station_vocab` records the column order so inference can encode
    correctly.

    Per-receptor metrics are still emitted via
    `compute_metric_payload`, populated by tagging each
    `TrainingRecordSchema` with `target_id=<station_id>`.
    """
    if protocol is None:
        raise ValueError(
            "train_shared_multi_station requires an explicit protocol"
        )
    horizon_minutes = HORIZON_MINUTES[horizon]
    pull_from = protocol.train_window_from - timedelta(days=2)
    pull_to = protocol.test_window_to

    station_list = tuple(station_ids)
    if not station_list:
        raise ValueError("station_ids must be non-empty")

    # Build per-station feature matrices, then stack with one-hot.
    stacked_X: list[np.ndarray] = []
    stacked_y_pm10: list[np.ndarray] = []
    stacked_y_breach: list[np.ndarray] = []
    stacked_ts: list[datetime] = []
    stacked_station: list[str] = []

    for station_id in station_list:
        weather_target_id = STATION_WEATHER_TARGETS.get(
            station_id, DEFAULT_WEATHER_TARGET
        )
        pm_series = _realtime_pm10_series(
            session=session,
            station_id=station_id,
            window_from=pull_from,
            window_to=pull_to,
        )
        weather = _weather_series(
            session=session,
            weather_target_id=weather_target_id,
            window_from=pull_from,
            window_to=pull_to,
        )
        if len(pm_series) < 200 or len(weather) < 200:
            # Skip thin stations — they contribute nothing.
            continue
        X, y_pm, y_b, ts = _build_feature_matrix(
            pm_series=pm_series,
            weather=weather,
            horizon_minutes=horizon_minutes,
        )
        stacked_X.append(X)
        stacked_y_pm10.append(y_pm)
        stacked_y_breach.append(y_b)
        stacked_ts.extend(ts)
        stacked_station.extend([station_id] * len(ts))

    if not stacked_X:
        raise ValueError("no station has enough data for shared training")

    X_all = np.vstack(stacked_X)
    y_pm10_all = np.concatenate(stacked_y_pm10)
    y_breach_all = np.concatenate(stacked_y_breach)
    ts_all = stacked_ts
    station_all = stacked_station

    # One-hot per station — vocabulary is the union of stations that
    # actually contributed data.
    station_vocab = tuple(sorted(set(station_all)))
    vocab_idx: dict[str, int] = {s: i for i, s in enumerate(station_vocab)}
    one_hot = np.zeros((len(station_all), len(station_vocab)), dtype=np.float64)
    for i, s in enumerate(station_all):
        one_hot[i, vocab_idx[s]] = 1.0
    X_all = np.hstack([X_all, one_hot])

    train_mask = _window_mask(
        ts_all, protocol.train_window_from, protocol.train_window_to
    )
    test_mask = _window_mask(
        ts_all, protocol.test_window_from, protocol.test_window_to
    )
    X_train, y_pm10_train, y_breach_train = (
        X_all[train_mask],
        y_pm10_all[train_mask],
        y_breach_all[train_mask],
    )
    X_test, y_pm10_test = X_all[test_mask], y_pm10_all[test_mask]
    ts_test = [t for t, m in zip(ts_all, test_mask, strict=True) if m]
    station_test = [s for s, m in zip(station_all, test_mask, strict=True) if m]

    if len(X_train) < 100 or len(X_test) < 30:
        raise ValueError(
            f"shared trainer: insufficient supervised rows train={len(X_train)} "
            f"test={len(X_test)}"
        )

    regressor, classifier = _fit_models(
        X_train, y_pm10_train, y_breach_train, recalibrate=False
    )

    pred_pm10 = regressor.predict(X_test)
    proba = classifier.predict_proba(X_test)
    pred_breach = proba[:, 1] if proba.shape[1] >= 2 else proba[:, 0]

    # Synth records — tag target_id per row so per_receptor split
    # produces the fairness breakdown the M.4.2 audit expects.
    records = [
        TrainingRecordSchema(
            prediction_id=f"shared::{station_test[i]}::{ts_test[i].isoformat()}",
            issued_at=ts_test[i],
            target_kind="sensor",
            target_id=station_test[i],
            forecast_horizon=horizon,
            predicted_pm10=float(pred_pm10[i]),
            predicted_pm25=0.0,
            predicted_breach_probability=float(pred_breach[i]),
            confidence=0.7,
            model_version=GBM_SHARED_VERSION,
            human_action="no_recommendation",
            actual_pm10_peak=float(y_pm10_test[i]),
            breach_occurred=bool(y_pm10_test[i] >= PM10_BREACH),
            outcome_status="observed",
            recorded_at=ts_test[i],
        )
        for i in range(len(ts_test))
    ]

    payload = compute_metric_payload(
        records, protocol=protocol, session=session
    )

    per_receptor = payload.get("per_receptor", {}) or {}
    per_receptor_ece: dict[str, float | None] = {
        sid: (block.get("ece") if isinstance(block, dict) else None)
        for sid, block in per_receptor.items()
    }

    out_artifact_path: Path | None = None
    metric_row_id: int | None = None
    if persist:
        artifact_payload = {
            "model": {"regressor": regressor, "classifier": classifier},
            "feature_columns": list(FEATURE_SET_P1),
            "station_vocab": list(station_vocab),
            "feature_pipeline_version": FEATURE_PIPELINE_VERSION,
            "training_protocol_hash": protocol.protocol_hash,
            "training_protocol_version": protocol.protocol_version,
            "horizon": horizon,
            "trained_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
        }
        out_artifact_path = shared_artifact_path(
            artifact_root=artifact_root,
            model_version=GBM_SHARED_VERSION,
            horizon=horizon,
        )
        out_artifact_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(artifact_payload, out_artifact_path)
        metric_row_id = _persist_metric_row(
            session=session,
            model_version=GBM_SHARED_VERSION,
            window_from=protocol.test_window_from,
            window_to=protocol.test_window_to,
            sample_count=len(ts_test),
            metric_payload=payload,
        )

    return SharedTrainingResult(
        model_version=GBM_SHARED_VERSION,
        horizon=horizon,
        protocol_hash=protocol.protocol_hash,
        train_record_count=int(train_mask.sum()),
        test_record_count=len(ts_test),
        station_vocab=station_vocab,
        aggregate_ece=_as_float(payload.get("ece")),
        aggregate_mae_pm10=_as_float(payload.get("mae_pm10")),
        aggregate_breach_recall=_as_float(payload.get("breach_recall")),
        per_receptor_ece=per_receptor_ece,
        artifact_path=out_artifact_path,
        metric_row_id=metric_row_id,
    )


def train_many(
    *,
    station_ids: Iterable[str],
    session: Session,
    horizon: ForecastHorizon = DEFAULT_HORIZON,
    protocol: EvaluationProtocol | None = None,
    artifact_root: Path | None = None,
    persist: bool = True,
) -> list[TrainingResult]:
    """Phase Q.1 — fit one GBM per station, all under the same model_version.

    Per-station failures are *captured*, not raised: each station's
    `train_one` call is wrapped in try/except and any exception is
    surfaced as a `TrainingResult` with `ece=mae_pm10=breach_recall=
    artifact_path=metric_row_id=None` so the caller's dashboard can
    render a partial-success row. Hard failures (`ProtocolViolation`
    after recalibration, etc.) re-raise — the SG-1 stop-gate.
    """
    results: list[TrainingResult] = []
    for station_id in station_ids:
        try:
            r = train_one(
                station_id=station_id,
                session=session,
                horizon=horizon,
                protocol=protocol,
                artifact_root=artifact_root,
                persist=persist,
            )
        except ValueError:
            # Insufficient data — skip with a placeholder result row
            # so the operator sees which station was thin.
            r = TrainingResult(
                model_version=GBM_VERSION,
                station_id=station_id,
                horizon=horizon,
                protocol_hash=protocol.protocol_hash if protocol else "",
                train_record_count=0,
                test_record_count=0,
                ece=None,
                mae_pm10=None,
                breach_recall=None,
                artifact_path=None,
                metric_row_id=None,
                recalibrated=False,
            )
        results.append(r)
    return results


def _window_mask(
    ts: Iterable[datetime], from_: datetime, to_: datetime
) -> np.ndarray:
    return np.array([from_ <= t < to_ for t in ts], dtype=bool)


def _as_float(v: object) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    return None


# Silence unused-import false positives under strict mypy.
_ = json


@dataclass(frozen=True)
class PromotionDecision:
    """Result of `decide_promotion()` — whether to set the GBM as current.

    `passed` is True iff every criterion below holds. Failure reasons
    are surfaced in `reasons` for the operator audit trail.
    """

    passed: bool
    reasons: tuple[str, ...]


# Phase P.3 promotion criteria. Conservative defaults — promotion is a
# trust statement, not a default behaviour. Operators tighten / loosen
# at deployment time by editing this constant or shipping a new phase.
PROMOTION_MAX_MAE_PM10 = 30.0
PROMOTION_MIN_TEST_SAMPLES = 100


def decide_promotion(metric_payload: dict[str, Any]) -> PromotionDecision:
    """Pure evaluator over a persisted M.4 metric_payload row.

    Criteria:
      - ECE within the protocol's max_ece (already enforced upstream
        by compute_metric_payload, but checked again defensively).
      - MAE on PM10 below `PROMOTION_MAX_MAE_PM10` µg/m³.
      - Test sample count above `PROMOTION_MIN_TEST_SAMPLES` (so
        thin-sample noise doesn't trigger a false promote).
      - breach_recall is either non-None (a real positive class exists
        in the test window) OR observed_count > 0 (test ran but
        positive class is empty — class imbalance B-8 territory; we
        don't block promotion on a metric that has no signal).

    `breach_recall is None` due to zero positives is documented as an
    inherent property of rare-event evaluation, not a model failure.
    """
    reasons: list[str] = []
    ece = metric_payload.get("ece")
    if not isinstance(ece, (int, float)):
        reasons.append("ece missing or non-numeric in metric_payload")
    else:
        max_ece = (metric_payload.get("protocol") or {}).get(
            "max_ece", DEFAULT_MAX_ECE_FALLBACK
        )
        if ece > max_ece:
            reasons.append(
                f"ece={ece:.4f} > max_ece={max_ece:.4f} (M.4.1 gate)"
            )

    mae = metric_payload.get("mae_pm10")
    if mae is None:
        reasons.append("mae_pm10 missing — cannot evaluate accuracy")
    elif mae > PROMOTION_MAX_MAE_PM10:
        reasons.append(
            f"mae_pm10={mae:.2f} > {PROMOTION_MAX_MAE_PM10} µg/m³ "
            "(promotion threshold)"
        )

    obs = metric_payload.get("observed_count", 0)
    if obs < PROMOTION_MIN_TEST_SAMPLES:
        reasons.append(
            f"observed_count={obs} < {PROMOTION_MIN_TEST_SAMPLES} "
            "(thin-sample guard)"
        )

    return PromotionDecision(passed=not reasons, reasons=tuple(reasons))


# Default echoes app.domain.evaluation_protocol.DEFAULT_MAX_ECE without
# the cross-import (this module already pulls EvaluationProtocol).
DEFAULT_MAX_ECE_FALLBACK = 0.05


# Phase X — tolerance band for per-receptor MAE comparison. Shared
# wins when its per-receptor MAE is at worst this many µg/m³ above the
# per-station MAE on every receptor (so noise-only differences don't
# block promotion), AND strictly better on at least one receptor by a
# margin > X_PROMOTION_STRICT_MARGIN.
X_PROMOTION_NONWORSE_TOLERANCE = 0.5
X_PROMOTION_STRICT_MARGIN = 0.5


def decide_shared_promotion(
    *,
    shared_payload: dict[str, Any],
    per_station_payloads: dict[str, dict[str, Any]],
) -> PromotionDecision:
    """Phase X — decide whether to flip `current` from per-station to shared.

    Inputs:
      - `shared_payload`: latest metric_payload row for the shared model.
        Must carry an `ece`, an `observed_count`, and a `per_receptor`
        block keyed by `target_id`.
      - `per_station_payloads`: dict of `station_id -> latest payload` for
        the per-station model — one entry per station the shared model
        was evaluated on.

    Criteria (all must hold):
      1. Shared payload itself passes the standard `decide_promotion`
         gate (ECE within max_ece, observed_count >= min samples).
      2. For every station S in shared.per_receptor: shared_mae[S] is
         non-worse than per_station_mae[S] within
         `X_PROMOTION_NONWORSE_TOLERANCE` µg/m³.
      3. Shared is strictly better than per-station on at least one
         station by > `X_PROMOTION_STRICT_MARGIN` µg/m³.
      4. Every station in shared.per_receptor has a per-station payload
         to compare against (otherwise we cannot honestly assert
         non-worse — hold the promotion until per-station coverage
         catches up).

    `PromotionDecision.passed=True` means the lifespan hook should
    flip `current` to the shared version. `False` means leave the
    per-station version current and surface the reasons.
    """
    base = decide_promotion(shared_payload)
    if not base.passed:
        return PromotionDecision(
            passed=False,
            reasons=tuple(f"shared::{r}" for r in base.reasons),
        )

    reasons: list[str] = []
    shared_per_receptor = shared_payload.get("per_receptor") or {}
    if not isinstance(shared_per_receptor, dict) or not shared_per_receptor:
        return PromotionDecision(
            passed=False,
            reasons=("shared payload has empty per_receptor block",),
        )

    strict_wins: list[str] = []
    for station_id, block in shared_per_receptor.items():
        if not isinstance(block, dict):
            reasons.append(f"per_receptor[{station_id}] not a dict")
            continue
        shared_mae = block.get("mae_pm10")
        ps_payload = per_station_payloads.get(station_id)
        if ps_payload is None:
            reasons.append(
                f"no per-station payload for {station_id} — "
                "cannot assert non-worse"
            )
            continue
        ps_mae = ps_payload.get("mae_pm10")
        if not isinstance(shared_mae, (int, float)):
            reasons.append(f"shared mae_pm10 missing for {station_id}")
            continue
        if not isinstance(ps_mae, (int, float)):
            reasons.append(f"per-station mae_pm10 missing for {station_id}")
            continue
        if shared_mae > ps_mae + X_PROMOTION_NONWORSE_TOLERANCE:
            reasons.append(
                f"shared regresses on {station_id}: "
                f"mae {shared_mae:.2f} > per-station {ps_mae:.2f} "
                f"+ tol {X_PROMOTION_NONWORSE_TOLERANCE}"
            )
        elif shared_mae < ps_mae - X_PROMOTION_STRICT_MARGIN:
            strict_wins.append(station_id)

    if not strict_wins and not reasons:
        reasons.append(
            "shared is non-worse but never strictly better "
            f"by > {X_PROMOTION_STRICT_MARGIN} — promotion held"
        )

    return PromotionDecision(passed=not reasons, reasons=tuple(reasons))


__all__ = [
    "FEATURE_SET_P1",
    "REQUIRED_COVARIATES_P1",
    "FORBIDDEN_COVARIATES_P1",
    "FEATURE_PIPELINE_VERSION",
    "DEFAULT_HORIZON",
    "HORIZON_MINUTES",
    "PM10_BREACH",
    "PROMOTION_MAX_MAE_PM10",
    "PROMOTION_MIN_TEST_SAMPLES",
    "STATION_WEATHER_TARGETS",
    "DEFAULT_WEATHER_TARGET",
    "MULTI_STATION_ROSTER",
    "GBM_VERSION",
    "GBM_SHARED_VERSION",
    "MODEL_KIND",
    "PromotionDecision",
    "SharedTrainingResult",
    "TrainingResult",
    "X_PROMOTION_NONWORSE_TOLERANCE",
    "X_PROMOTION_STRICT_MARGIN",
    "build_p1_protocol",
    "decide_promotion",
    "decide_shared_promotion",
    "train_one",
    "train_many",
    "train_shared_multi_station",
]
