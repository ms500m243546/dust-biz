"""AP-42 §13.2.2 unpaved-haul-road emission factor (Phase R.1).

Pure-function physics module for haul-truck dust generation, used by
the Phase R intervention impact model (`app.models.intervention.
ap42_v0_1_0`). Sources:

  EPA AP-42 §13.2.2 (Unpaved Roads), Industrial Roads sub-section.

Formula (lb / vehicle-mile-traveled):

    E = k * (s/12)^a * (W/3)^b

  s : surface material silt content (mass percent < 75 µm)
  W : mean vehicle weight (short tons; 1 short ton ≈ 0.907 metric tonnes)
  k, a, b : particle-size constants

Particle-size constants:

    PM10 :  k = 1.5  a = 0.9  b = 0.45
    PM2.5:  k = 0.15 a = 0.9  b = 0.45

Two intervention impact functions live here, both as pure functions
returning a dimensionless reduction fraction in [0, 1]:

  watering_decay_curve(...) — dust suppression after a watering
    cycle, bounded by wind-driven evaporation. Empirical: a watered
    haul road typically loses 30–60% of its untreated emission for
    1–4 hours depending on humidity + wind speed + temperature.

  speed_reduction_factor(...) — AP-42 says emission is roughly linear
    in speed (Z = 0.5 from §13.2.2 average); reducing speed from
    v_before to v_after gives a `(v_after / v_before)^Z` factor.

Both are conservative defaults; calibration against real outcomes is
Phase R.2 work.
"""

from __future__ import annotations

import math
from typing import Literal

# AP-42 §13.2.2 particle-size constants. Frozen here so any drift in
# the source spec is a deliberate edit, not a silent change.
AP42_K_PM10 = 1.5
AP42_K_PM25 = 0.15
AP42_A = 0.9
AP42_B = 0.45

# Speed-reduction exponent (AP-42 §13.2.2 average industrial-road
# value). Linear-ish: dropping speed in half cuts emission ~30%.
SPEED_REDUCTION_EXPONENT = 0.5

# Watering decay constants — empirical defaults pending Phase R.2
# calibration against operator outcome data.
WATERING_BASE_REDUCTION = 0.55  # reduction at t=0+ on a freshly watered road
WATERING_HALF_LIFE_MIN = 90.0  # minutes; baseline @ moderate wind+humidity

# Tonne conversion (we store metric, AP-42 wants short tons).
METRIC_TONNE_TO_SHORT_TON = 1.10231

ParticleSize = Literal["pm10", "pm25"]


def _k_for(particle: ParticleSize) -> float:
    return AP42_K_PM10 if particle == "pm10" else AP42_K_PM25


def emission_factor_lb_per_vmt(
    *,
    silt_content_pct: float,
    vehicle_weight_metric_tonnes: float,
    particle: ParticleSize = "pm10",
) -> float:
    """AP-42 emission factor in pounds per vehicle-mile-traveled.

    Returns 0 for non-positive vehicle weight or silt content (those
    are physically meaningless inputs and the AP-42 power form is
    undefined at 0/negative bases).
    """
    if vehicle_weight_metric_tonnes <= 0 or silt_content_pct <= 0:
        return 0.0
    weight_short_tons = vehicle_weight_metric_tonnes * METRIC_TONNE_TO_SHORT_TON
    k = _k_for(particle)
    silt_term = (silt_content_pct / 12.0) ** AP42_A
    weight_term = (weight_short_tons / 3.0) ** AP42_B
    return float(k * silt_term * weight_term)


def speed_reduction_factor(
    *,
    speed_before_kmh: float,
    speed_after_kmh: float,
) -> float:
    """Reduction fraction from cutting haul-truck speed.

    Returns the *fractional reduction* in PM emission (1 - ratio),
    bounded to [0, 1]. A reduction from 50 → 25 km/h returns ~0.29
    (29% emission reduction). Increasing speed (after > before)
    yields a 0 reduction (we don't model emission *increases* here;
    the recommendation engine never proposes those).
    """
    if speed_before_kmh <= 0 or speed_after_kmh <= 0:
        return 0.0
    if speed_after_kmh >= speed_before_kmh:
        return 0.0
    ratio = speed_after_kmh / speed_before_kmh
    factor = 1.0 - ratio**SPEED_REDUCTION_EXPONENT
    return float(max(0.0, min(1.0, factor)))


def watering_decay_curve(
    *,
    minutes_since_watering: float,
    wind_speed_ms: float = 5.0,
    humidity_pct: float = 50.0,
    temperature_c: float = 15.0,
) -> float:
    """Fractional dust-emission *reduction* at `minutes_since_watering`.

    Combines:
      - exponential decay (`half_life` modulated by wind / humidity /
        temperature; high wind + low humidity + high temperature
        evaporates water faster, shortens half-life)
      - hard floor at 0 (long after watering, no reduction remains)
      - hard ceiling at WATERING_BASE_REDUCTION (immediately after a
        cycle, the road can't be more than the empirical limit
        suppressed)

    Defaults reflect a moderate Andean afternoon (5 m/s wind, 50%
    humidity, 15 °C). Operators should pass real meteorology when
    available.
    """
    if minutes_since_watering < 0:
        return 0.0
    # Adjust half-life: faster evaporation → shorter half-life.
    # Wind: each m/s above 5 cuts 5 minutes off the half-life.
    # Humidity: each 10% below 50 cuts 5 minutes; above 50 adds.
    # Temperature: each °C above 15 cuts 2 minutes; below 15 adds.
    adj = WATERING_HALF_LIFE_MIN
    adj -= max(0.0, wind_speed_ms - 5.0) * 5.0
    adj -= max(0.0, 50.0 - humidity_pct) * 0.5
    adj += max(0.0, humidity_pct - 50.0) * 0.5
    adj -= max(0.0, temperature_c - 15.0) * 2.0
    adj += max(0.0, 15.0 - temperature_c) * 2.0
    half_life = max(15.0, adj)  # never less than 15 min
    decay = math.exp(-math.log(2.0) * minutes_since_watering / half_life)
    return max(0.0, min(WATERING_BASE_REDUCTION, WATERING_BASE_REDUCTION * decay))


__all__ = [
    "AP42_A",
    "AP42_B",
    "AP42_K_PM10",
    "AP42_K_PM25",
    "METRIC_TONNE_TO_SHORT_TON",
    "SPEED_REDUCTION_EXPONENT",
    "WATERING_BASE_REDUCTION",
    "WATERING_HALF_LIFE_MIN",
    "ParticleSize",
    "emission_factor_lb_per_vmt",
    "speed_reduction_factor",
    "watering_decay_curve",
]
