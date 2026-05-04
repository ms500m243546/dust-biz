"""CFD-derived source-receptor lookup (Phase BA.6).

Consumes a persisted `DispersionMatrixSchema` (Phase BA.5) and emits
the per-receptor coefficient given current wind regime. Snap-to-grid
on direction (nearest neighbour, since direction wraps at 0/360 and
linear interpolation is awkward) + linear interpolation on speed.
Stability classes off the trained grid use Pasquill-Gifford analytic
rescaling on top of the neutral CFD field.

This is what replaces the AERMOD / CALPUFF placeholder in the Phase BA
plan. Promoted by `app.domain.dispersion_promotion.maybe_promote_cfd_lookup`
when a calibrated matrix exists for the active mine.
"""

from __future__ import annotations

import bisect
import math

from app.schemas.dispersion import DispersionMatrixSchema, RegimeGridSchema

CFD_LOOKUP_VERSION = "dispersion_cfd_lookup_v0.1.0"

# Pasquill-Gifford-style coarse stability multipliers applied on top
# of the neutral-stability CFD field. Values ~ literature; tunable
# per-deployment via constants here.
_STABILITY_MULTIPLIERS: dict[str, float] = {
    "very_unstable": 0.5,   # A
    "unstable":      0.7,   # B
    "slightly_unstable": 0.85,  # C
    "neutral":       1.0,   # D (matches the trained grid)
    "stable":        1.3,   # E
    "very_stable":   1.6,   # F
}


class CFDLookupDispersionModel:
    """Phase BA.6 CFD-derived dispersion model.

    Construct with a `DispersionMatrixSchema`; `predict(...)` resolves
    the regime and returns the per-(source, receptor) coefficient.
    Returns 0.0 when the source/receptor pair isn't in the matrix
    (callers should consult the registry's heuristic baseline as a
    fallback for that pair).
    """

    model_kind: str = "dispersion"

    def __init__(
        self,
        matrix: DispersionMatrixSchema,
        model_version: str = CFD_LOOKUP_VERSION,
    ) -> None:
        self.matrix = matrix
        self.model_version = model_version

    def predict(
        self,
        *,
        source_zone_id: str,
        receptor_id: str,
        wind_direction_from_deg: float,
        wind_speed_ms: float,
        stability: str = "neutral",
    ) -> float:
        """Return the dispersion coefficient under the current regime."""
        grid = self.matrix.regime_grid
        dir_idx = _nearest_direction_idx(grid, wind_direction_from_deg)
        if dir_idx is None:
            return 0.0
        speed_lo, speed_hi, weight_hi = _speed_bracket(grid, wind_speed_ms)
        if speed_lo is None:
            return 0.0
        stability_key = stability if stability in grid.stability_classes else "neutral"

        coef_lo = self._coef_at(
            dir_idx=dir_idx, speed_idx=speed_lo,
            stability=stability_key,
            source=source_zone_id, receptor=receptor_id,
        )
        if speed_hi is None or speed_hi == speed_lo:
            base = coef_lo
        else:
            coef_hi = self._coef_at(
                dir_idx=dir_idx, speed_idx=speed_hi,
                stability=stability_key,
                source=source_zone_id, receptor=receptor_id,
            )
            base = (1.0 - weight_hi) * coef_lo + weight_hi * coef_hi
        # Off-grid stability rescaling (Pasquill-Gifford analytic).
        if stability not in grid.stability_classes:
            base *= _STABILITY_MULTIPLIERS.get(stability, 1.0)
        return base

    def _coef_at(
        self,
        *,
        dir_idx: int,
        speed_idx: int,
        stability: str,
        source: str,
        receptor: str,
    ) -> float:
        regime_id = f"dir{dir_idx:02d}_speed{speed_idx:02d}_{stability}"
        regime = self.matrix.coefficients.get(regime_id) or {}
        sources = regime.get(source) or {}
        return float(sources.get(receptor, 0.0))


def _nearest_direction_idx(
    grid: RegimeGridSchema, wind_direction_from_deg: float
) -> int | None:
    """Snap a meteorological 'from' direction to the nearest grid index."""
    if not grid.directions_deg:
        return None
    wind_norm = wind_direction_from_deg % 360.0
    best_idx = 0
    best_dist = 360.0
    for i, d in enumerate(grid.directions_deg):
        # Direction wraps at 360; minimum of forward and backward delta.
        delta = abs((wind_norm - d + 540.0) % 360.0 - 180.0)
        if delta < best_dist:
            best_dist = delta
            best_idx = i
    return best_idx


def _speed_bracket(
    grid: RegimeGridSchema, wind_speed_ms: float
) -> tuple[int | None, int | None, float]:
    """Return (lo_idx, hi_idx, weight_hi) bracketing wind_speed_ms.

    `weight_hi` is the linear-interpolation weight on the upper bin
    (0.0 means use lower exclusively, 1.0 upper). Off-grid speeds
    clamp to nearest endpoint with weight=0.
    """
    speeds = grid.speeds_ms
    if not speeds:
        return None, None, 0.0
    if wind_speed_ms <= speeds[0]:
        return 0, None, 0.0
    if wind_speed_ms >= speeds[-1]:
        return len(speeds) - 1, None, 0.0
    # bisect_left works on a sorted list; speeds_ms is sorted at
    # matrix-build time (RegimeGridSchema doesn't enforce, but the
    # reduction step writes them in sorted order).
    hi = bisect.bisect_left(speeds, wind_speed_ms)
    lo = max(0, hi - 1)
    span = speeds[hi] - speeds[lo]
    weight = (wind_speed_ms - speeds[lo]) / span if span > 0 else 0.0
    return lo, hi, weight


def stability_multiplier(stability: str) -> float:
    """Public accessor for the Pasquill-Gifford rescaling table."""
    return _STABILITY_MULTIPLIERS.get(stability, 1.0)


__all__ = [
    "CFD_LOOKUP_VERSION",
    "CFDLookupDispersionModel",
    "stability_multiplier",
]


_ = math  # imported but only used implicitly via bisect; keep for future
