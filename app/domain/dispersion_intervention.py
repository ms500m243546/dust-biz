"""Phase BA.9 / BD.2 — dispersion-aware intervention-impact uplift.

The existing AP-42 / heuristic intervention-impact models compute a
source-side emission reduction and translate it to a receptor PM10
reduction with a fixed coupling. When the CFD lookup model is
`current`, we have a per-(source, receptor) coupling that respects
terrain channeling + pit recirculation; the receptor-side reduction
should reflect that.

This module provides `compute_dispersion_uplift(...)` — a pure scalar
the simulator post-multiplies onto `predicted_pm10_reduction` and the
breach-probability delta. Falls through to 1.0 (no scaling) when:

* No `dispersion` model is registered, or
* The current model is the heuristic baseline (interface mismatch), or
* No wind state / no source zones / no receptor coefficient available.

Magnitude is clamped to [MIN_UPLIFT, MAX_UPLIFT] so a wildly off
matrix can't push recommendations into nonsense territory. This
matches the cautious-clamp pattern used by Phase AA's slack rescale.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.dispersion_attribution import latest_wind_state
from app.models import registry
from app.storage.models import Zone

logger = logging.getLogger(__name__)

# Reference coupling magnitude. Calibrated post-BA.7 once real
# observed-vs-predicted data lands; until then 0.10 is a plausible
# default for "moderate dispersion to a receptor 1-3 km from the
# source under neutral stability".
REFERENCE_COUPLING = 0.10

# Clamp range for the multiplier. Tight enough that a bad matrix
# can't double-scale a recommendation past the trust horizon.
MIN_UPLIFT = 0.5
MAX_UPLIFT = 2.0


def compute_dispersion_uplift(
    session: Session,
    *,
    mine_id: str,
    receptor_id: str,
    as_of: datetime,
    stability: str = "neutral",
) -> float | None:
    """Return the multiplier or None.

    None means "no dispersion model in play; leave the impact alone".
    A float means "scale predicted_pm10_reduction by this".
    """
    try:
        model = registry.get_current("dispersion")
    except registry.ModelNotFoundError:
        return None
    predict = getattr(model, "predict", None)
    if not callable(predict):
        return None

    wind = latest_wind_state(session, as_of=as_of)
    if wind is None:
        return None
    wind_dir, wind_speed = wind

    zones = list(
        session.execute(
            select(Zone).where(Zone.mine_id == mine_id)
        ).scalars()
    )
    if not zones:
        return None

    # Top-contributing source under current wind = the source whose
    # emission reduction is most leverageful at the receptor.
    best_share = 0.0
    for zone in zones:
        share = _safe_predict(
            predict,
            source_zone_id=zone.zone_id,
            receptor_id=receptor_id,
            wind_direction_from_deg=wind_dir,
            wind_speed_ms=wind_speed,
            stability=stability,
        )
        if share > best_share:
            best_share = share

    if best_share <= 0.0:
        return None
    raw = best_share / REFERENCE_COUPLING
    return max(MIN_UPLIFT, min(MAX_UPLIFT, raw))


def apply_dispersion_uplift(
    *,
    predicted_pm10_reduction: float,
    breach_probability_before: float,
    breach_probability_after: float,
    uplift: float | None,
) -> tuple[float, float]:
    """Apply uplift to the impact tuple.

    Returns the corrected (predicted_pm10_reduction, breach_probability_after).
    `uplift = None` -> passthrough; the simulator should not call this
    when uplift is None, but the function tolerates it for callers.

    Breach probability scaling: scale the delta from before, not the
    after value directly. So if uplift = 1.5 and the heuristic shaved
    30% off the breach probability, we shave 45% off (clamped to 0).
    """
    if uplift is None or uplift == 1.0:
        return predicted_pm10_reduction, breach_probability_after
    new_reduction = max(0.0, predicted_pm10_reduction * uplift)
    delta = breach_probability_before - breach_probability_after
    new_after = breach_probability_before - (delta * uplift)
    new_after = max(0.0, min(1.0, new_after))
    return new_reduction, new_after


def _safe_predict(predict: Any, **kwargs: Any) -> float:
    try:
        out = predict(**kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.debug("dispersion predict raised in intervention uplift: %s", exc)
        return 0.0
    if isinstance(out, (int, float)):
        return float(out)
    return 0.0


__all__ = [
    "MIN_UPLIFT",
    "MAX_UPLIFT",
    "REFERENCE_COUPLING",
    "apply_dispersion_uplift",
    "compute_dispersion_uplift",
]
