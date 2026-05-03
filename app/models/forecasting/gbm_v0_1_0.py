"""Gradient-boosted dust forecaster (Phase P).

First trained `DustForecastModel` implementation. Per CLAUDE.md
rule 13 ("heuristics first; deep learning only when justified"),
this is a tabular `HistGradientBoostingRegressor` from sklearn —
not a neural net. It handles missing values natively (essential
for SINCA gaps), is fast on the ~9k-record Cuncumén training set,
and is mypy-friendly with explicit numpy typing.

Phase P.1 ships only the skeleton + registry hookup. The
`predict()` method raises `NotImplementedError` until P.2 produces
a fitted artifact. The Heuristic baseline remains the registered
*current* model until P.3 promotion (and only if calibration
passes the M.4.1 ECE gate).

Artifact layout (filesystem, .gitignore'd):
    data_models/dust_forecast/<model_version>/<station_id>__<horizon>.joblib

Phase P.1: Cuncumén-only, single horizon (60 min).
Phase Q.1: per-station artifacts (one joblib per station).
Phase Q.2: shared multi-station artifact (station_id as categorical).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.schemas.features import FeatureRecordSchema
from app.schemas.forecasts import (
    DustForecastSchema,
    ForecastHorizon,
    ForecastTargetSchema,
)

if TYPE_CHECKING:
    from sklearn.ensemble import HistGradientBoostingRegressor

GBM_VERSION = "dust_forecast_gbm_v0.1.0"
MODEL_KIND = "dust_forecast"

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

    Loads a per-(station, horizon) `HistGradientBoostingRegressor`
    artifact lazily on first `predict()` for that key, then caches
    in-process. If the artifact is missing, raises
    `ModelArtifactNotFoundError` — the caller (registry / fallback
    chain) decides whether to fall back to the heuristic baseline.

    Skeleton phase (P.1): `predict()` raises `NotImplementedError`
    until P.2 lands the trainer + first artifact.
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
        self._artifacts: dict[tuple[str, ForecastHorizon], HistGradientBoostingRegressor] = {}

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
        # P.1 skeleton — fitted weights arrive in P.2.
        _ = (
            features,
            target,
            horizon,
            input_data_quality_score,
            data_quality_warnings,
            input_record_ids,
            now or datetime.now(UTC),
        )
        raise NotImplementedError(
            "GBMForecaster.predict() is a Phase P.1 skeleton. The "
            "fitted artifact + inference path land in Phase P.2."
        )


class ModelArtifactNotFoundError(FileNotFoundError):
    """Raised when a (station, horizon) artifact is requested but missing."""


__all__ = [
    "GBM_VERSION",
    "MODEL_KIND",
    "DEFAULT_ARTIFACT_ROOT",
    "GBMForecaster",
    "ModelArtifactNotFoundError",
    "artifact_path",
]


# Tiny self-test so `Any` import isn't unused under strict mypy when
# the TYPE_CHECKING block isn't taken at runtime.
_ = Any
