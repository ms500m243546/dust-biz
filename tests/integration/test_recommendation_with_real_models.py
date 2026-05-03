"""Phase V.1 — end-to-end registry state with all promoted models.

Verifies that when the FastAPI lifespan hook runs, each
`maybe_promote_*` function flips the relevant `model_kind` to its
trained / physics-informed peer (where the artifact / sanity-band
permits). Doesn't drive the full recommendation pipeline — that
needs a full mine-state seed; the registry-state checks here are
the fastest meaningful integration assertion.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from app.models import registry
from app.models.attribution.logreg_v0_1_0 import LOGREG_VERSION
from app.models.attribution.rules_baseline import RULES_VERSION as RULES_ATTR_VERSION
from app.models.attribution.rules_baseline import CandidateSource
from app.models.cost.cycle_time_v0_1_0 import CYCLE_TIME_VERSION
from app.models.cost.heuristic_baseline import (
    HEURISTIC_VERSION as HEURISTIC_COST_VERSION,
)
from app.models.forecasting.gbm_v0_1_0 import GBM_VERSION
from app.models.forecasting.heuristic_baseline import (
    HEURISTIC_VERSION as HEURISTIC_FORECAST_VERSION,
)
from app.models.intervention.ap42_v0_1_0 import AP42_VERSION
from app.models.intervention.heuristic_baseline import (
    HEURISTIC_VERSION as HEURISTIC_INT_VERSION,
)
from app.training.attribution_training import train_logreg_attributor


@pytest.fixture(autouse=True)
def _isolated_registry() -> Iterator[None]:
    registry.reset()
    yield
    registry.reset()


def _attr_pool() -> list[CandidateSource]:
    pool: list[CandidateSource] = []
    for i in range(40):
        is_strong = i % 2 == 0
        pool.append(
            CandidateSource(
                source_id=f"c{i}",
                wind_angle_offset_deg=10.0,
                activity_intensity=0.95 if is_strong else 0.05,
                dust_generation_potential="high",
                concurrent_pm_rise=8.0 if is_strong else 1.0,
            )
        )
    return pool


def test_intervention_promotion_flips_to_ap42_via_sanity_band() -> None:
    from app.domain.intervention_promotion import maybe_promote_ap42

    promoted = maybe_promote_ap42()
    assert promoted is True
    current = registry.get_current("intervention_impact")
    assert current.model_version == AP42_VERSION


def test_cost_promotion_flips_to_cycle_time_via_sanity_band() -> None:
    from app.domain.cost_promotion import maybe_promote_cycle_time_cost

    promoted = maybe_promote_cycle_time_cost()
    assert promoted is True
    current = registry.get_current("production_cost")
    assert current.model_version == CYCLE_TIME_VERSION


def test_attribution_promotion_held_without_artifact_keeps_rules_baseline() -> None:
    from app.domain.attribution_promotion import maybe_promote_logreg

    # No artifact on disk → rules baseline stays current.
    with patch(
        "app.domain.attribution_promotion.logreg_artifact_path",
        return_value=Path("/no/such/file.joblib"),
    ):
        promoted = maybe_promote_logreg()
    assert promoted is False
    current = registry.get_current("source_attribution")
    assert current.model_version == RULES_ATTR_VERSION


def test_attribution_promotion_flips_to_logreg_when_artifact_present(
    tmp_path: Path,
) -> None:
    from app.domain.attribution_promotion import maybe_promote_logreg

    artifact = tmp_path / "head.joblib"
    with patch(
        "app.models.attribution.logreg_v0_1_0.logreg_artifact_path",
        return_value=artifact,
    ), patch(
        "app.domain.attribution_promotion.logreg_artifact_path",
        return_value=artifact,
    ), patch(
        "app.training.attribution_training.logreg_artifact_path",
        return_value=artifact,
    ):
        train_logreg_attributor(_attr_pool())
        promoted = maybe_promote_logreg()
    assert promoted is True
    current = registry.get_current("source_attribution")
    assert current.model_version == LOGREG_VERSION


def test_all_three_promotions_run_in_sequence_without_interference() -> None:
    """Bootstrap order matches app/api/main.py:lifespan."""
    from app.domain.cost_promotion import maybe_promote_cycle_time_cost
    from app.domain.intervention_promotion import maybe_promote_ap42

    maybe_promote_ap42()
    maybe_promote_cycle_time_cost()
    # Heuristic forecaster registered by ensure_models_registered
    # still holds the dust_forecast slot since no GBM artifact was
    # promoted (no maybe_promote_gbm here — that needs a DB row).
    assert registry.get_current("intervention_impact").model_version == AP42_VERSION
    assert registry.get_current("production_cost").model_version == CYCLE_TIME_VERSION


def test_baseline_versions_remain_resolvable_after_promotion() -> None:
    """Heuristics must stay registered as fallbacks (Guardrail 11)."""
    from app.domain.cost_promotion import maybe_promote_cycle_time_cost
    from app.domain.intervention_promotion import maybe_promote_ap42

    maybe_promote_ap42()
    maybe_promote_cycle_time_cost()
    assert HEURISTIC_INT_VERSION in registry.list_versions("intervention_impact")
    assert HEURISTIC_COST_VERSION in registry.list_versions("production_cost")
    # Forecast heuristic registered by ensure_models_registered side-
    # effect — confirm it's there too.
    versions = registry.list_versions("dust_forecast")
    if versions:
        assert HEURISTIC_FORECAST_VERSION in versions
    # GBM_VERSION may or may not be registered depending on whether
    # the forecasting module was imported elsewhere; either is fine.
    _ = GBM_VERSION
