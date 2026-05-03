"""AP-42 intervention model auto-promotion (Phase R.2).

Decides whether to flip the registry's `current` `intervention_impact`
pointer from the heuristic baseline to the AP-42 physics model.

Promotion criteria (in priority order):
  1. If `validate_intervention_calibration` reports `calibrated`
     status, promote iff `mean_abs_error_pct < CALIBRATED_PROMOTION_THRESHOLD`.
  2. If `deferred` (insufficient outcome rows yet — the typical case
     until partnership data lands), fall back to the AP-42 sanity-
     band path: simulate the canonical `water_road` + `reduce_speed`
     interventions and check that the predicted reduction fractions
     fall inside SANITY_BAND_LOWER ≤ frac ≤ SANITY_BAND_UPPER.
  3. If `violated`, do not promote — heuristic stays current.

Layered: this module sits in `app/domain` so it can import both
`app/models` and `app/storage`. Wired into the FastAPI lifespan
hook alongside the GBM auto-promotion.
"""

from __future__ import annotations

import contextlib
import logging

from app.domain.simulation import ensure_models_registered
from app.models import registry
from app.models.intervention.ap42_v0_1_0 import (
    AP42_VERSION,
    AP42InterventionImpact,
)
from app.schemas.interventions import InterventionOptionSchema
from app.storage.database import session_scope
from app.training.intervention_validation import (
    SANITY_BAND_LOWER,
    SANITY_BAND_UPPER,
    validate_intervention_calibration,
)

logger = logging.getLogger(__name__)

CALIBRATED_PROMOTION_THRESHOLD = 0.30


def _sanity_band_pass() -> tuple[bool, str]:
    """Run AP-42 against canonical inputs; check reductions are sensible."""
    model = AP42InterventionImpact()
    failures: list[str] = []
    for iid, label in (
        ("water_road", "watering"),
        ("reduce_speed", "speed reduction"),
    ):
        opt = InterventionOptionSchema(
            intervention_id=iid,
            name=label,
            description=f"sanity-band probe: {label}",
            risk_class="low",
            requires_human_approval=False,
            automation_eligible_levels=["L1"],
            estimated_time_to_effect_minutes=10,
            allowed_zone_types=["haul_road"],
        )
        out = model.simulate(
            intervention=opt,
            target_zone_id="probe-zone",
            predicted_pm10=100.0,
            predicted_pm25=40.0,
            breach_probability_before=0.4,
        )
        frac = out.predicted_pm10_reduction / 100.0
        if not (SANITY_BAND_LOWER <= frac <= SANITY_BAND_UPPER):
            failures.append(
                f"{iid} reduction {frac:.3f} outside "
                f"[{SANITY_BAND_LOWER}, {SANITY_BAND_UPPER}]"
            )
    if failures:
        return False, "; ".join(failures)
    return True, "all canonical interventions in sanity band"


def maybe_promote_ap42() -> bool:
    """Promote AP-42 to current iff calibration passes OR sanity-band passes.

    Tolerant by design: any storage / decode / registry exception
    leaves the heuristic as current and logs INFO. Never raises into
    the bootstrap path.
    """
    try:
        ensure_models_registered()
        # Register AP-42 alongside the heuristic. Idempotent: register
        # is a dict assignment under (kind, version) keys.
        with contextlib.suppress(Exception):
            registry.register(AP42InterventionImpact(), set_as_current=False)
        with session_scope() as session:
            report = validate_intervention_calibration(session)
        if report.status == "violated":
            logger.info(
                "ap42 promotion held: calibration violated (%s rows)",
                report.joined_row_count,
            )
            return False
        if report.status == "calibrated":
            mae = report.mean_abs_error_pct
            if mae is None or mae < CALIBRATED_PROMOTION_THRESHOLD:
                registry.set_current("intervention_impact", AP42_VERSION)
                logger.info(
                    "ap42 promoted to current (calibrated; rows=%s, mae=%s)",
                    report.joined_row_count,
                    mae,
                )
                return True
            logger.info("ap42 promotion held: calibrated MAE %s above threshold", mae)
            return False
        # deferred — use sanity-band fallback
        passed, msg = _sanity_band_pass()
        if not passed:
            logger.info("ap42 promotion held: sanity-band failure: %s", msg)
            return False
        registry.set_current("intervention_impact", AP42_VERSION)
        logger.info(
            "ap42 promoted to current (deferred calibration, sanity-band ok: %s)",
            msg,
        )
        return True
    except Exception as exc:  # broad: bootstrap must never raise
        logger.info("ap42 promotion skipped: %s", exc)
        return False


__all__ = ["CALIBRATED_PROMOTION_THRESHOLD", "maybe_promote_ap42"]
