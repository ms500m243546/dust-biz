"""Phase BA.6 — dispersion model layer tests."""

from __future__ import annotations

import pytest

from app.models.dispersion.cfd_lookup_v0_1_0 import (
    CFD_LOOKUP_VERSION,
    CFDLookupDispersionModel,
    _nearest_direction_idx,
    _speed_bracket,
    stability_multiplier,
)
from app.models.dispersion.distance_decay_baseline import (
    DEFAULT_DECAY_LENGTH_M,
    DistanceDecayDispersionModel,
)
from app.schemas.dispersion import DispersionMatrixSchema, RegimeGridSchema


def _matrix() -> DispersionMatrixSchema:
    """Synthetic 4-direction x 2-speed neutral grid."""
    return DispersionMatrixSchema(
        mine_id="test-mine",
        model_version=CFD_LOOKUP_VERSION,
        regime_grid=RegimeGridSchema(
            directions_deg=[0.0, 90.0, 180.0, 270.0],
            speeds_ms=[3.0, 9.0],
            stability_classes=["neutral"],
        ),
        coefficients={
            "dir00_speed00_neutral": {"haul_W": {"cuncumen": 0.5}},
            "dir00_speed01_neutral": {"haul_W": {"cuncumen": 0.7}},
            "dir01_speed00_neutral": {"haul_W": {"cuncumen": 0.1}},
            "dir01_speed01_neutral": {"haul_W": {"cuncumen": 0.2}},
            "dir02_speed00_neutral": {"haul_W": {"cuncumen": 0.0}},
            "dir02_speed01_neutral": {"haul_W": {"cuncumen": 0.0}},
            "dir03_speed00_neutral": {"haul_W": {"cuncumen": 0.4}},
            "dir03_speed01_neutral": {"haul_W": {"cuncumen": 0.6}},
        },
    )


def test_nearest_direction_idx_snaps_to_closest() -> None:
    grid = RegimeGridSchema(directions_deg=[0.0, 90.0, 180.0, 270.0])
    assert _nearest_direction_idx(grid, 5.0) == 0
    assert _nearest_direction_idx(grid, 80.0) == 1
    assert _nearest_direction_idx(grid, 170.0) == 2
    # Wrap: 359 should snap to 0, not 270.
    assert _nearest_direction_idx(grid, 359.0) == 0


def test_speed_bracket_clamp_below() -> None:
    grid = RegimeGridSchema(directions_deg=[0.0], speeds_ms=[3.0, 6.0, 9.0])
    lo, hi, w = _speed_bracket(grid, 1.0)
    assert lo == 0 and hi is None and w == 0.0


def test_speed_bracket_clamp_above() -> None:
    grid = RegimeGridSchema(directions_deg=[0.0], speeds_ms=[3.0, 6.0, 9.0])
    lo, hi, w = _speed_bracket(grid, 20.0)
    assert lo == 2 and hi is None and w == 0.0


def test_speed_bracket_interpolates() -> None:
    grid = RegimeGridSchema(directions_deg=[0.0], speeds_ms=[3.0, 9.0])
    lo, hi, w = _speed_bracket(grid, 6.0)
    assert lo == 0 and hi == 1
    assert w == pytest.approx(0.5)


def test_cfd_predict_at_grid_point() -> None:
    m = CFDLookupDispersionModel(_matrix())
    out = m.predict(
        source_zone_id="haul_W",
        receptor_id="cuncumen",
        wind_direction_from_deg=0.0,
        wind_speed_ms=3.0,
    )
    assert out == 0.5


def test_cfd_predict_interpolates_speed() -> None:
    m = CFDLookupDispersionModel(_matrix())
    out = m.predict(
        source_zone_id="haul_W",
        receptor_id="cuncumen",
        wind_direction_from_deg=0.0,
        wind_speed_ms=6.0,  # midpoint of 3 and 9
    )
    assert out == pytest.approx(0.6)  # (0.5 + 0.7) / 2


def test_cfd_predict_snaps_direction() -> None:
    m = CFDLookupDispersionModel(_matrix())
    # Wind from 5 deg should snap to 0 deg bin.
    out = m.predict(
        source_zone_id="haul_W",
        receptor_id="cuncumen",
        wind_direction_from_deg=5.0,
        wind_speed_ms=3.0,
    )
    assert out == 0.5


def test_cfd_predict_returns_zero_for_unknown_pair() -> None:
    m = CFDLookupDispersionModel(_matrix())
    out = m.predict(
        source_zone_id="bogus",
        receptor_id="cuncumen",
        wind_direction_from_deg=0.0,
        wind_speed_ms=3.0,
    )
    assert out == 0.0


def test_cfd_predict_off_grid_stability_rescales() -> None:
    m = CFDLookupDispersionModel(_matrix())
    neutral = m.predict(
        source_zone_id="haul_W", receptor_id="cuncumen",
        wind_direction_from_deg=0.0, wind_speed_ms=3.0,
        stability="neutral",
    )
    stable = m.predict(
        source_zone_id="haul_W", receptor_id="cuncumen",
        wind_direction_from_deg=0.0, wind_speed_ms=3.0,
        stability="stable",
    )
    assert stable == pytest.approx(neutral * stability_multiplier("stable"))


def test_distance_decay_baseline_aligned_wind() -> None:
    m = DistanceDecayDispersionModel()
    # Source -> receptor due south of source (bearing 180 from source).
    # Wind FROM north (0) blows TOWARD south (180) — perfect alignment.
    out = m.predict(
        source_to_receptor_distance_m=1000.0,
        source_to_receptor_bearing_deg=180.0,
        wind_direction_from_deg=0.0,
        wind_speed_ms=5.0,
    )
    assert out > 0.5  # ~exp(-1000/5000) = 0.819 with full alignment


def test_distance_decay_baseline_perpendicular_wind() -> None:
    m = DistanceDecayDispersionModel()
    # Wind perpendicular to source-receptor line -> alignment 0.
    out = m.predict(
        source_to_receptor_distance_m=1000.0,
        source_to_receptor_bearing_deg=180.0,
        wind_direction_from_deg=90.0,  # blows toward 270 (west)
        wind_speed_ms=5.0,
    )
    # Floating-point cosine of 90 deg leaves a tiny residual; assert
    # it's effectively zero.
    assert abs(out) < 1e-12


def test_distance_decay_baseline_zero_wind() -> None:
    m = DistanceDecayDispersionModel()
    out = m.predict(
        source_to_receptor_distance_m=1000.0,
        source_to_receptor_bearing_deg=180.0,
        wind_direction_from_deg=0.0,
        wind_speed_ms=0.0,
    )
    assert out == 0.0


def test_distance_decay_decay_length_constant() -> None:
    assert DEFAULT_DECAY_LENGTH_M > 0
