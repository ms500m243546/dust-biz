"""Phase P.1 skeleton tests for the GBM forecaster.

These confirm wire-compatibility with the registry + Protocol shape
without requiring a fitted artifact. The fit-path tests land in P.2
under tests/training/.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest

from app.models import registry
from app.models.forecasting.gbm_v0_1_0 import (
    DEFAULT_ARTIFACT_ROOT,
    GBM_VERSION,
    MODEL_KIND,
    GBMForecaster,
    artifact_path,
)
from app.models.forecasting.heuristic_baseline import (
    HEURISTIC_VERSION,
    HeuristicBaselineForecaster,
)
from app.schemas.features import FeatureRecordSchema
from app.schemas.forecasts import ForecastTargetSchema


@pytest.fixture(autouse=True)
def _isolated_registry() -> Iterator[None]:
    """Process-global registry quirk — sibling tests can reset it.

    Re-establish the same state `app/models/forecasting/__init__.py`
    sets up at import: heuristic registered as current, GBM
    registered alongside.
    """
    registry.reset()
    registry.register(HeuristicBaselineForecaster())
    registry.register(GBMForecaster(), set_as_current=False)
    yield
    registry.reset()


def test_gbm_forecaster_advertises_correct_kind_and_version() -> None:
    f = GBMForecaster()
    assert f.model_kind == "dust_forecast"
    assert f.model_version == GBM_VERSION
    assert MODEL_KIND == "dust_forecast"


def test_gbm_forecaster_registered_alongside_heuristic_but_not_current() -> None:
    # Both versions resolvable; current is still the heuristic baseline
    # until Phase P.3 promotion.
    versions = registry.list_versions("dust_forecast")
    assert GBM_VERSION in versions
    assert HEURISTIC_VERSION in versions
    current = registry.get_current("dust_forecast")
    assert current.model_version == HEURISTIC_VERSION


def test_artifact_path_is_under_data_models_root() -> None:
    p = artifact_path(station_id="lp-em05-cuncumen", horizon="60min")
    # Must live under data_models/ and carry the version + station + horizon
    assert "data_models" in p.parts
    assert GBM_VERSION in p.parts
    assert p.name == "lp-em05-cuncumen__60min.joblib"


def test_artifact_path_respects_caller_supplied_root(tmp_path: Path) -> None:
    p = artifact_path(
        artifact_root=tmp_path,
        station_id="cnt-sierra-gorda",
        horizon="60min",
    )
    assert tmp_path in p.parents


def test_predict_skeleton_raises_until_p2_lands() -> None:
    # P.1 contract: predict raises NotImplementedError. The error
    # message names Phase P.2 so future readers know where to look.
    f = GBMForecaster()
    target = ForecastTargetSchema(target_kind="sensor", target_id="lp-em05-cuncumen")
    features = FeatureRecordSchema(
        timestamp=datetime(2026, 5, 3, 12, 0),
        zone_id="z",
        feature_pipeline_version="feature_pipeline_v0.1.0",
        feature_payload={},
        missing_inputs=[],
    )
    with pytest.raises(NotImplementedError, match="P.2"):
        f.predict(features=features, target=target, horizon="60min")


def test_default_artifact_root_resolves_to_repo_data_models() -> None:
    # The constant is computed at import time; smoke-test it.
    assert DEFAULT_ARTIFACT_ROOT.name == "data_models"
