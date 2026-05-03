"""Phase S.2 — attribution promotion tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from app.models import registry
from app.models.attribution.logreg_v0_1_0 import (
    LOGREG_VERSION,
    LogRegAttributor,
)
from app.models.attribution.rules_baseline import (
    RULES_VERSION,
    CandidateSource,
    RulesBaselineAttributor,
)
from app.training.attribution_training import train_logreg_attributor


@pytest.fixture(autouse=True)
def _isolated_registry() -> Iterator[None]:
    registry.reset()
    yield
    registry.reset()


def _pool() -> list[CandidateSource]:
    out: list[CandidateSource] = []
    for i in range(40):
        is_strong = i % 2 == 0
        out.append(
            CandidateSource(
                source_id=f"c{i}",
                wind_angle_offset_deg=10.0,
                activity_intensity=0.95 if is_strong else 0.05,
                dust_generation_potential="high",
                concurrent_pm_rise=8.0 if is_strong else 1.0,
            )
        )
    return out


def test_promotion_held_when_no_artifact_on_disk(tmp_path: Path) -> None:
    # Patch the artifact path to point at an empty tmp dir.
    with patch(
        "app.domain.attribution_promotion.logreg_artifact_path",
        return_value=tmp_path / "ghost.joblib",
    ):
        from app.domain.attribution_promotion import maybe_promote_logreg

        promoted = maybe_promote_logreg()
    assert promoted is False
    # Rules baseline remains the registered current.
    current = registry.get_current("source_attribution")
    assert current.model_version == RULES_VERSION


def test_promotion_passes_when_artifact_probe_passes(tmp_path: Path) -> None:
    # Train a real artifact in tmp_path; patch logreg_artifact_path
    # so both the trainer and the promotion check see the same path.
    artifact_path = tmp_path / "head.joblib"
    with patch(
        "app.models.attribution.logreg_v0_1_0.logreg_artifact_path",
        return_value=artifact_path,
    ), patch(
        "app.domain.attribution_promotion.logreg_artifact_path",
        return_value=artifact_path,
    ), patch(
        "app.training.attribution_training.logreg_artifact_path",
        return_value=artifact_path,
    ):
        train_logreg_attributor(_pool())
        from app.domain.attribution_promotion import maybe_promote_logreg

        promoted = maybe_promote_logreg()
    assert promoted is True
    current = registry.get_current("source_attribution")
    assert current.model_version == LOGREG_VERSION


def test_promotion_idempotent_under_repeated_calls(tmp_path: Path) -> None:
    artifact_path = tmp_path / "head.joblib"
    with patch(
        "app.models.attribution.logreg_v0_1_0.logreg_artifact_path",
        return_value=artifact_path,
    ), patch(
        "app.domain.attribution_promotion.logreg_artifact_path",
        return_value=artifact_path,
    ), patch(
        "app.training.attribution_training.logreg_artifact_path",
        return_value=artifact_path,
    ):
        train_logreg_attributor(_pool())
        from app.domain.attribution_promotion import maybe_promote_logreg

        for _ in range(3):
            assert maybe_promote_logreg() is True
    # Idempotent — final state still logreg.
    assert registry.get_current("source_attribution").model_version == LOGREG_VERSION


def test_min_labelled_constant_documented() -> None:
    from app.domain.attribution_promotion import MIN_LABELLED_FOR_CALIBRATION

    assert MIN_LABELLED_FOR_CALIBRATION >= 1


def test_unused_imports_silenced() -> None:
    # Defensive: surface that the registered classes are importable
    # without a circular import; lint catches the unused but the test
    # makes the failure mode explicit.
    assert RulesBaselineAttributor.model_kind == "source_attribution"
    assert LogRegAttributor.model_kind == "source_attribution"
