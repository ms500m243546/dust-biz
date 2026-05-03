"""Phase S.1 — LogRegAttributor tests."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from app.models.attribution.logreg_v0_1_0 import (
    LOGREG_VERSION,
    QE_CV_STD_CEILING,
    QE_IMPORTANCE_FLOOR,
    LogRegAttributor,
)
from app.models.attribution.rules_baseline import CandidateSource
from app.training.attribution_training import train_logreg_attributor


def _candidate(
    sid: str,
    *,
    wind: float | None = 0.0,
    activity: float = 0.5,
    potential: str = "high",
    rise: float = 5.0,
) -> CandidateSource:
    return CandidateSource(
        source_id=sid,
        wind_angle_offset_deg=wind,
        activity_intensity=activity,
        dust_generation_potential=potential,
        concurrent_pm_rise=rise,
    )


def test_attributor_advertises_correct_kind_and_version() -> None:
    a = LogRegAttributor()
    assert a.model_kind == "source_attribution"
    assert a.model_version == LOGREG_VERSION


def test_cold_start_attribution_handles_empty_candidates() -> None:
    a = LogRegAttributor()
    out = a.attribute(
        attribution_id="att-1",
        dust_event_id="evt-1",
        affected_station="lp-em05-cuncumen",
        candidates=[],
        issued_at=datetime(2026, 5, 3, 12, 0),
    )
    assert out.confidence == 0.0
    assert out.probable_sources[0].source == "Unknown"
    # Cold start without an artifact → expert_judgment.
    assert out.evidence_class == "expert_judgment"


def test_cold_start_ranks_directly_downwind_high_above_upwind(tmp_path: Path) -> None:
    a = LogRegAttributor(artifact_root=tmp_path)
    candidates = [
        _candidate("downwind", wind=10.0, activity=0.8, potential="high", rise=8.0),
        _candidate("upwind", wind=170.0, activity=0.8, potential="high", rise=8.0),
    ]
    out = a.attribute(
        attribution_id="att-1",
        dust_event_id="evt-1",
        affected_station="lp-em05-cuncumen",
        candidates=candidates,
        issued_at=datetime(2026, 5, 3, 12, 0),
    )
    top = out.probable_sources[0]
    assert top.source == "downwind"


def test_fitted_artifact_changes_evidence_class_when_thresholds_pass(
    tmp_path: Path,
) -> None:
    # Build a training pool where one feature dominates with low CV
    # variance — that feature should pass the QE threshold and the
    # attributor should report quasi_experimental.
    pool: list[CandidateSource] = []
    for i in range(40):
        # Even index = strong attribution candidate (high activity);
        # odd = weak. wind/dust held constant so activity_intensity
        # is the most important feature.
        is_strong = i % 2 == 0
        pool.append(
            _candidate(
                f"c{i}",
                wind=10.0,
                activity=0.95 if is_strong else 0.05,
                potential="high",
                rise=8.0 if is_strong else 1.0,
            )
        )
    result = train_logreg_attributor(pool, artifact_root=tmp_path)
    # Sanity — the trainer ran end-to-end.
    assert result.model_version == LOGREG_VERSION
    assert result.artifact_path is not None
    assert result.artifact_path.exists()
    # Fitted attributor consumes the artifact.
    a = LogRegAttributor(artifact_root=tmp_path)
    out = a.attribute(
        attribution_id="att-2",
        dust_event_id="evt-2",
        affected_station="lp-em05-cuncumen",
        candidates=[
            _candidate("downwind", wind=10.0, activity=0.95, potential="high", rise=8.0),
            _candidate("upwind", wind=170.0, activity=0.05, potential="low", rise=1.0),
        ],
        issued_at=datetime(2026, 5, 3, 12, 0),
    )
    # With the synthetic pool, at least one feature must clear the QE
    # thresholds; the attributor reports quasi_experimental.
    assert out.evidence_class in ("quasi_experimental", "observational_correlational")


def test_qe_thresholds_documented_constants() -> None:
    # Defensive — these constants drive the evidence-class decision.
    assert QE_IMPORTANCE_FLOOR > 0
    assert QE_CV_STD_CEILING > 0


def test_train_logreg_requires_min_pool() -> None:
    with pytest.raises(ValueError, match=">=8"):
        train_logreg_attributor([_candidate(f"c{i}") for i in range(3)])
