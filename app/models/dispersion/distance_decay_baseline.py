"""Distance-decay heuristic dispersion baseline (Phase BA.6).

Always-registered fallback used when no calibrated CFD matrix is
available for a mine. Models the receptor concentration share as

    coefficient = wind_alignment * exp(-distance / decay_length)

where:
- `wind_alignment` is `max(0, cos(wind_to_receptor_bearing - wind_to_dir))`,
  i.e. 1 when the wind blows the source-to-receptor line and 0 when
  the wind is perpendicular or blowing the opposite way.
- `decay_length` is a tunable scalar (default 5 km) — distance at
  which the coefficient drops by 1/e.

This is intentionally crude. It exists so the recommendation engine
has *something* to consult before partnership / CFD data lands;
calibration always prefers `cfd_lookup_v0_1_0` once promoted.
"""

from __future__ import annotations

import math

DISPERSION_BASELINE_VERSION = "dispersion_distance_decay_v0.1.0"

DEFAULT_DECAY_LENGTH_M = 5_000.0


class DistanceDecayDispersionModel:
    """Heuristic dispersion baseline."""

    model_kind: str = "dispersion"

    def __init__(
        self,
        model_version: str = DISPERSION_BASELINE_VERSION,
        decay_length_m: float = DEFAULT_DECAY_LENGTH_M,
    ) -> None:
        self.model_version = model_version
        self.decay_length_m = float(decay_length_m)

    def predict(
        self,
        *,
        source_to_receptor_distance_m: float,
        source_to_receptor_bearing_deg: float,
        wind_direction_from_deg: float,
        wind_speed_ms: float,
        stability: str = "neutral",
    ) -> float:
        """Return concentration coefficient (0..1).

        `source_to_receptor_bearing_deg` is the *meteorological*
        bearing from source to receptor (0 = receptor due north of
        source, 90 = east, ...). `wind_direction_from_deg` is the
        wind's "from" direction; the wind blows TOWARD
        `(wind_from + 180) % 360`, so alignment = cos(bearing -
        (wind_from + 180)).
        """
        if source_to_receptor_distance_m < 0:
            return 0.0
        if wind_speed_ms <= 0:
            return 0.0
        wind_to_deg = (wind_direction_from_deg + 180.0) % 360.0
        diff_rad = math.radians(source_to_receptor_bearing_deg - wind_to_deg)
        alignment = max(0.0, math.cos(diff_rad))
        decay = math.exp(-source_to_receptor_distance_m / self.decay_length_m)
        # Stability scaling — neutral is the baseline; stable concentrates,
        # unstable disperses. Coarse Pasquill multipliers ~ literature.
        stability_multiplier = {
            "stable": 1.4,
            "neutral": 1.0,
            "unstable": 0.7,
        }.get(stability, 1.0)
        return alignment * decay * stability_multiplier


__all__ = [
    "DEFAULT_DECAY_LENGTH_M",
    "DISPERSION_BASELINE_VERSION",
    "DistanceDecayDispersionModel",
]
