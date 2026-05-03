"""Gradient-boosted dust forecaster (Phase P).

First trained `DustForecastModel` implementation. Per CLAUDE.md
rule 13 ("heuristics first; deep learning only when justified"),
this is a tabular `HistGradientBoostingRegressor` from sklearn —
not a neural net. It handles missing values natively (essential
for SINCA gaps), is fast on the ~9k-record Cuncumén training set,
and is mypy-friendly with explicit numpy typing.

The fitted artifact bundles a regressor (PM10 µg/m³) plus a
classifier (P(breach)) trained jointly on the same feature matrix,
plus the protocol hash that produced them. The classifier output
goes through the M.4.1 ECE gate during training (see
`app.training.dust_forecast_training.train_one`); a fitted artifact
on disk is therefore *known* to be calibrated.

Artifact layout (filesystem, .gitignore'd):
    data_models/dust_forecast/<model_version>/<station_id>__<horizon>.joblib

Phase P.1: Cuncumén-only, single horizon (60 min).
Phase Q.1: per-station artifacts (one joblib per station).
Phase Q.2: shared multi-station artifact (station_id as categorical).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib  # type: ignore[import-untyped]
import numpy as np

from app.schemas.features import FeatureRecordSchema
from app.schemas.forecasts import (
    DustForecastSchema,
    ForecastHorizon,
    ForecastTargetSchema,
)

GBM_VERSION = "dust_forecast_gbm_v0.1.0"
MODEL_KIND = "dust_forecast"
PM10_BREACH_THRESHOLD = 150.0

# Filesystem layout for persisted artifacts. Repo root is computed at
# import time; in tests, callers can override `ARTIFACT_ROOT` via the
# constructor.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ARTIFACT_ROOT = _REPO_ROOT / "data_models"


def artifact_path(
    *,
    artifact_root: Path | None = None,
    model_version: str = GBM_VERSION,
    station_id: str,
    horizon: ForecastHorizon = "60min",
) -> Path:
    """Resolve the on-disk path for one trained-model artifact.

    Centralised so the trainer (writer) and the predictor (reader)
    cannot drift on the convention.
    """
    root = artifact_root or DEFAULT_ARTIFACT_ROOT
    return root / "dust_forecast" / model_version / f"{station_id}__{horizon}.joblib"


class GBMForecaster:
    """First trained implementation of `DustForecastModel`.

    Loads a per-(station, horizon) artifact lazily on first
    `predict()` for that key, then caches in-process. If the
    artifact is missing, raises `ModelArtifactNotFoundError` — the
    caller (registry / fallback chain) decides whether to fall back
    to the heuristic baseline.
    """

    model_kind: str = MODEL_KIND

    def __init__(
        self,
        *,
        model_version: str = GBM_VERSION,
        artifact_root: Path | None = None,
    ) -> None:
        self.model_version = model_version
        self._artifact_root = artifact_root
        self._artifacts: dict[tuple[str, ForecastHorizon], dict[str, Any]] = {}

    def _load(self, station_id: str, horizon: ForecastHorizon) -> dict[str, Any]:
        key = (station_id, horizon)
        cached = self._artifacts.get(key)
        if cached is not None:
            return cached
        path = artifact_path(
            artifact_root=self._artifact_root,
            model_version=self.model_version,
            station_id=station_id,
            horizon=horizon,
        )
        if not path.exists():
            raise ModelArtifactNotFoundError(
                f"no GBM artifact for station={station_id} horizon={horizon} "
                f"at {path}. Train via scripts/train_dust_forecast.py."
            )
        loaded: dict[str, Any] = joblib.load(path)
        self._artifacts[key] = loaded
        return loaded

    def predict(
        self,
        *,
        features: FeatureRecordSchema,
        target: ForecastTargetSchema,
        horizon: ForecastHorizon,
        input_data_quality_score: float = 1.0,
        data_quality_warnings: list[str] | None = None,
        input_record_ids: list[str] | None = None,
        now: datetime | None = None,
    ) -> DustForecastSchema:
        warnings = list(data_quality_warnings or [])
        record_ids = list(input_record_ids or [])
        issued_at = now or datetime.now(UTC)

        artifact = self._load(target.target_id, horizon)
        feature_columns: list[str] = artifact["feature_columns"]
        regressor = artifact["model"]["regressor"]
        classifier = artifact["model"]["classifier"]

        x = np.array(
            [[features.feature_payload.get(c, float("nan")) for c in feature_columns]],
            dtype=np.float64,
        )
        predicted_pm10 = float(regressor.predict(x)[0])
        proba = classifier.predict_proba(x)
        breach_prob = float(proba[0, 1]) if proba.shape[1] >= 2 else float(proba[0, 0])

        # Confidence reuses the heuristic's data-quality multiplier:
        # the artifact is M.4.1-calibrated so we anchor the raw
        # confidence at 0.75 and let DQ scale it down.
        raw_conf = 0.75
        confidence = round(raw_conf * input_data_quality_score, 3)

        return DustForecastSchema(
            issued_at=issued_at,
            target_kind=target.target_kind,
            target_id=target.target_id,
            forecast_horizon=horizon,
            predicted_pm10=round(max(predicted_pm10, 0.0), 1),
            predicted_pm25=round(max(predicted_pm10 * 0.4, 0.0), 1),
            breach_probability=round(max(min(breach_prob, 1.0), 0.0), 3),
            confidence=confidence,
            main_risk_window=f"+{horizon}",
            main_uncertainty=(
                f"GBM v{self.model_version}; trained on protocol "
                f"{artifact.get('training_protocol_hash', '?')[:12]}…"
            ),
            model_version=self.model_version,
            feature_pipeline_version=features.feature_pipeline_version,
            input_data_quality_score=round(input_data_quality_score, 3),
            data_quality_warnings=warnings,
            source="model",
            input_record_ids=record_ids,
        )


class ModelArtifactNotFoundError(FileNotFoundError):
    """Raised when a (station, horizon) artifact is requested but missing."""


__all__ = [
    "GBM_VERSION",
    "MODEL_KIND",
    "PM10_BREACH_THRESHOLD",
    "DEFAULT_ARTIFACT_ROOT",
    "GBMForecaster",
    "ModelArtifactNotFoundError",
    "artifact_path",
]
