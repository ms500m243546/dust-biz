"""Shared multi-station GBM forecaster (Phase Q.2).

Single trained model that handles all stations via a `station_id`
one-hot encoding tacked onto the feature vector. Contrasts with
`GBMForecaster` (Phase P.2 / Q.1), which keeps one fitted artifact
per (station, horizon).

The shared model can transfer signal across stations — useful when
some stations have thin data (Calama 275 at 66% density), and the
hope is the receptor-specific patterns are still learned via the
one-hot. The cost is that station-specific quirks bleed into the
global representation.

Q.2 trains both architectures so M.4.2 per-receptor fairness can
pick the better one. The promotion criterion is: shared wins iff
`max(per_receptor_ece) < max(per_station_per_receptor_ece)` AND
aggregate `breach_recall` is non-worse.

Artifact layout:
    data_models/dust_forecast/<model_version>/__shared__/all__<horizon>.joblib
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib  # type: ignore[import-untyped]
import numpy as np

from app.models.forecasting.gbm_v0_1_0 import (
    DEFAULT_ARTIFACT_ROOT,
    ModelArtifactNotFoundError,
)
from app.schemas.features import FeatureRecordSchema
from app.schemas.forecasts import (
    DustForecastSchema,
    ForecastHorizon,
    ForecastTargetSchema,
)

GBM_SHARED_VERSION = "dust_forecast_gbm_shared_v0.1.0"
MODEL_KIND = "dust_forecast"


def shared_artifact_path(
    *,
    artifact_root: Path | None = None,
    model_version: str = GBM_SHARED_VERSION,
    horizon: ForecastHorizon = "60min",
) -> Path:
    """Single shared artifact path — one file for all stations.

    Distinct dir layout from `GBMForecaster.artifact_path` so the
    two architectures can co-exist on disk without colliding.
    """
    root = artifact_root or DEFAULT_ARTIFACT_ROOT
    return (
        root
        / "dust_forecast"
        / model_version
        / "__shared__"
        / f"all__{horizon}.joblib"
    )


class GBMSharedForecaster:
    """Phase Q.2 shared multi-station forecaster.

    One regressor + one classifier per horizon. The training-time
    one-hot vocabulary is persisted in the artifact so `predict()`
    can correctly encode the requested station_id at inference time.
    Stations not in the vocabulary fall through with all-zero one-hot
    columns — the model degrades to "average behaviour" rather than
    raising; we surface that in `data_quality_warnings`.
    """

    model_kind: str = MODEL_KIND

    def __init__(
        self,
        *,
        model_version: str = GBM_SHARED_VERSION,
        artifact_root: Path | None = None,
    ) -> None:
        self.model_version = model_version
        self._artifact_root = artifact_root
        self._artifacts: dict[ForecastHorizon, dict[str, Any]] = {}

    def _load(self, horizon: ForecastHorizon) -> dict[str, Any]:
        cached = self._artifacts.get(horizon)
        if cached is not None:
            return cached
        path = shared_artifact_path(
            artifact_root=self._artifact_root,
            model_version=self.model_version,
            horizon=horizon,
        )
        if not path.exists():
            raise ModelArtifactNotFoundError(
                f"no shared GBM artifact for horizon={horizon} at {path}. "
                f"Train via scripts/train_dust_forecast.py --shared."
            )
        loaded: dict[str, Any] = joblib.load(path)
        self._artifacts[horizon] = loaded
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

        artifact = self._load(horizon)
        feature_columns: list[str] = artifact["feature_columns"]
        station_vocab: list[str] = artifact["station_vocab"]
        regressor = artifact["model"]["regressor"]
        classifier = artifact["model"]["classifier"]

        x_features = [
            features.feature_payload.get(c, float("nan")) for c in feature_columns
        ]
        x_one_hot = [
            1.0 if target.target_id == s else 0.0 for s in station_vocab
        ]
        if target.target_id not in station_vocab:
            warnings.append(
                f"shared_model_unknown_station:{target.target_id}"
            )
        x = np.array([x_features + x_one_hot], dtype=np.float64)

        predicted_pm10 = float(regressor.predict(x)[0])
        proba = classifier.predict_proba(x)
        breach_prob = float(proba[0, 1]) if proba.shape[1] >= 2 else float(proba[0, 0])

        confidence = round(0.7 * input_data_quality_score, 3)

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
                f"GBM-shared v{self.model_version}; trained on "
                f"{len(station_vocab)} stations"
            ),
            model_version=self.model_version,
            feature_pipeline_version=features.feature_pipeline_version,
            input_data_quality_score=round(input_data_quality_score, 3),
            data_quality_warnings=warnings,
            source="model",
            input_record_ids=record_ids,
        )


__all__ = [
    "GBM_SHARED_VERSION",
    "MODEL_KIND",
    "GBMSharedForecaster",
    "shared_artifact_path",
]
