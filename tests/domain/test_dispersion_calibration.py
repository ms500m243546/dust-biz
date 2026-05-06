"""Phase BA.7 / BD.3 — calibration probe tests."""

from __future__ import annotations

from app.domain.dispersion_calibration import (
    MIN_REGIMES,
    N_MIN_OBSERVATIONS,
    decide_dispersion_promotion,
)
from app.schemas.dispersion import DispersionMatrixSchema, RegimeGridSchema


def _matrix(*, n_regimes: int = 4, populated: bool = True) -> DispersionMatrixSchema:
    coeffs: dict[str, dict[str, dict[str, float]]] = {}
    for i in range(n_regimes):
        rid = f"dir{i:02d}_speed00_neutral"
        if populated:
            coeffs[rid] = {"src-1": {"rec-A": 0.4, "rec-B": 0.3}}
        else:
            coeffs[rid] = {}
    return DispersionMatrixSchema(
        mine_id="probe-mine",
        model_version="dispersion_cfd_lookup_v0.1.0",
        regime_grid=RegimeGridSchema(
            directions_deg=[0.0, 90.0, 180.0, 270.0][:n_regimes],
            speeds_ms=[5.0],
        ),
        coefficients=coeffs,
    )


def test_passes_in_deferred_mode_with_clean_matrix() -> None:
    decision = decide_dispersion_promotion(_matrix())
    assert decision.passed
    assert decision.mode == "deferred"
    assert any("structural checks passed" in r for r in decision.reasons)


def test_blocks_when_too_few_regimes() -> None:
    decision = decide_dispersion_promotion(_matrix(n_regimes=MIN_REGIMES - 1))
    assert not decision.passed
    assert decision.mode == "blocked"
    assert any("regimes" in r for r in decision.reasons)


def test_blocks_when_regime_blocks_empty() -> None:
    decision = decide_dispersion_promotion(_matrix(populated=False))
    assert not decision.passed
    assert decision.mode == "blocked"
    assert any("empty coefficient" in r for r in decision.reasons)


def test_escalates_to_calibrated_when_two_receptors_meet_observation_floor() -> None:
    decision = decide_dispersion_promotion(
        _matrix(),
        receptor_observations={
            "rec-A": N_MIN_OBSERVATIONS,
            "rec-B": N_MIN_OBSERVATIONS + 50,
        },
    )
    assert decision.passed
    assert decision.mode == "calibrated"


def test_stays_in_deferred_when_only_one_receptor_meets_floor() -> None:
    decision = decide_dispersion_promotion(
        _matrix(),
        receptor_observations={
            "rec-A": N_MIN_OBSERVATIONS,
            "rec-B": N_MIN_OBSERVATIONS - 1,  # below floor
        },
    )
    assert decision.passed
    assert decision.mode == "deferred"


def test_blocks_when_no_sources() -> None:
    matrix = DispersionMatrixSchema(
        mine_id="x", model_version="v",
        regime_grid=RegimeGridSchema(directions_deg=[0.0, 90.0, 180.0, 270.0], speeds_ms=[5.0]),
        coefficients={f"dir{i:02d}_speed00_neutral": {} for i in range(4)},
    )
    decision = decide_dispersion_promotion(matrix)
    assert not decision.passed
