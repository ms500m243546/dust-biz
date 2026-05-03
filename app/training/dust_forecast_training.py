"""Dust-forecast training pipeline (Phase P).

Orchestrates: pull SINCA + weather rows from the dev DB → build
station-level features → walk-forward fit a `HistGradientBoostingRegressor`
→ persist the artifact under `data_models/dust_forecast/<version>/<station>__<horizon>.joblib`
→ write one M.4-tagged `model_performance_metrics` row.

Phase P.1 ships only the public function signature + the
EvaluationProtocol declaration. The actual fit lands in P.2.

Why a separate module from `app.domain.model_performance`: this file
*creates* metric_payload rows by *training a model*; that one *reduces*
already-collected predictions into a metric_payload. Different
responsibilities — keep them un-tangled even though both end up
writing to `model_performance_metrics`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.domain.evaluation_protocol import (
    PROTOCOL_VERSION,
    EvaluationProtocol,
)
from app.models.forecasting.gbm_v0_1_0 import (
    GBM_VERSION,
    MODEL_KIND,
)
from app.schemas.forecasts import ForecastHorizon

# Phase P.1 — declared canonical feature set for the Cuncumén baseline.
# Every entry here must be derivable purely from `weather_readings` +
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
FORBIDDEN_COVARIATES_P1: tuple[str, ...] = ()  # no SINCA col-3 leakage etc.

DEFAULT_HORIZON: ForecastHorizon = "60min"


@dataclass(frozen=True)
class TrainingResult:
    """Return shape from `train_one()` — the trainer's audit trail.

    `artifact_path` is None when the trainer ran in dry-run mode.
    `metric_row_id` is None when the trainer ran without persisting
    (P.1 skeleton case).
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
    """Construct the canonical Phase P.1 EvaluationProtocol.

    Centralised so trainer + tests + audit reports cannot drift on
    the protocol shape. The hash is what M.4.1 pre-registers.
    """
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


def train_one(
    *,
    station_id: str,
    horizon: ForecastHorizon = DEFAULT_HORIZON,
    protocol: EvaluationProtocol | None = None,
    artifact_root: Path | None = None,
    persist: bool = True,
) -> TrainingResult:
    """Train one (station, horizon) GBM forecaster against the dev DB.

    P.1 skeleton: declares the public signature + protocol surface
    but raises `NotImplementedError`. The actual fit + persist lands
    in P.2.
    """
    _ = (station_id, horizon, protocol, artifact_root, persist)
    raise NotImplementedError(
        "train_one() is a Phase P.1 skeleton. The fit + persist + "
        "metric_payload-write path lands in Phase P.2."
    )


__all__ = [
    "FEATURE_SET_P1",
    "REQUIRED_COVARIATES_P1",
    "FORBIDDEN_COVARIATES_P1",
    "DEFAULT_HORIZON",
    "GBM_VERSION",
    "MODEL_KIND",
    "TrainingResult",
    "build_p1_protocol",
    "train_one",
]
