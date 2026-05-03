"""Cycle-time cost model auto-promotion (Phase U.2).

Promotes `CycleTimeProductionCost` to current iff the canonical
intervention probes produce sensible numbers within a documented
sanity band. Same pattern as `intervention_promotion.py`: this is
honest-deferral until calibration against `ActionOutcome.
production_loss_tonnes_actual` is feasible.

Layered: this module sits in `app/domain` so it can import both
`app/models` and (future) `app/storage`. Wired into the FastAPI
lifespan hook.
"""

from __future__ import annotations

import contextlib
import logging

from app.domain.simulation import ensure_models_registered
from app.models import registry
from app.models.cost.cycle_time_v0_1_0 import (
    CYCLE_TIME_VERSION,
    CycleTimeProductionCost,
)
from app.schemas.interventions import InterventionOptionSchema

logger = logging.getLogger(__name__)

# Sanity band on tonnes_delayed at the canonical 1000 t/h * 60 min
# probe. A reduce_speed result outside this band suggests a parameter
# bug; do not promote.
PROBE_PRODUCTION_RATE_TPH = 1000.0
PROBE_DURATION_MINUTES = 60
SANITY_TONNES_LOWER = 50.0
SANITY_TONNES_UPPER = 800.0


def _probe_intervention(intervention_id: str) -> InterventionOptionSchema:
    return InterventionOptionSchema(
        intervention_id=intervention_id,
        name=intervention_id,
        description=f"sanity-band probe: {intervention_id}",
        risk_class="low",
        requires_human_approval=False,
        automation_eligible_levels=["L1"],
        estimated_time_to_effect_minutes=10,
        allowed_zone_types=["haul_road"],
    )


def _sanity_band_pass() -> tuple[bool, str]:
    """Run the cycle-time model against canonical inputs.

    Passes iff tonnes_delayed for both `water_road` and
    `reduce_speed` falls inside the documented sanity band.
    """
    model = CycleTimeProductionCost()
    failures: list[str] = []
    for iid in ("reduce_speed", "water_road"):
        out = model.estimate_cost(
            intervention=_probe_intervention(iid),
            target_zone_id="probe-zone",
            production_rate_tph=PROBE_PRODUCTION_RATE_TPH,
            duration_minutes=PROBE_DURATION_MINUTES,
        )
        t = out.estimated_tonnes_delayed
        if not (SANITY_TONNES_LOWER <= t <= SANITY_TONNES_UPPER):
            failures.append(
                f"{iid} tonnes_delayed={t:.1f} outside "
                f"[{SANITY_TONNES_LOWER}, {SANITY_TONNES_UPPER}]"
            )
    if failures:
        return False, "; ".join(failures)
    return True, "all canonical interventions in sanity band"


def maybe_promote_cycle_time_cost() -> bool:
    """Promote CycleTimeProductionCost iff sanity-band probe passes.

    Tolerant by design: any exception leaves the heuristic baseline
    as current and logs INFO. Never raises into the bootstrap path.
    """
    try:
        ensure_models_registered()
        with contextlib.suppress(Exception):
            registry.register(CycleTimeProductionCost(), set_as_current=False)
        passed, msg = _sanity_band_pass()
        if not passed:
            logger.info("cycle-time cost promotion held: %s", msg)
            return False
        registry.set_current("production_cost", CYCLE_TIME_VERSION)
        logger.info("cycle-time cost promoted to current (%s)", msg)
        return True
    except Exception as exc:  # broad: bootstrap must never raise
        logger.info("cycle-time cost promotion skipped: %s", exc)
        return False


__all__ = [
    "PROBE_DURATION_MINUTES",
    "PROBE_PRODUCTION_RATE_TPH",
    "SANITY_TONNES_LOWER",
    "SANITY_TONNES_UPPER",
    "maybe_promote_cycle_time_cost",
]
