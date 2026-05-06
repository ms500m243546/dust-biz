"""Dispersion-model auto-promotion (Phase BA.10).

Registers the distance-decay baseline always, then loads the latest
persisted `DispersionMatrix` for the canonical mine and promotes
`CFDLookupDispersionModel` over the baseline when one exists.

Tolerant by design: failures leave the baseline as `current` and log
the cause; never raises into the bootstrap path.

Note on multi-mine: the v0.1.0 promotion path is single-mine (Los
Pelambres pilot). Multi-mine support — distinct dispersion `current`
per mine — is a registry-shape change deferred until a second mine's
campaign lands.
"""

from __future__ import annotations

import logging

from app.domain.dispersion_calibration import decide_dispersion_promotion
from app.models import registry
from app.models.dispersion.cfd_lookup_v0_1_0 import (
    CFD_LOOKUP_VERSION,
    CFDLookupDispersionModel,
)
from app.models.dispersion.distance_decay_baseline import (
    DISPERSION_BASELINE_VERSION,
    DistanceDecayDispersionModel,
)
from app.storage.database import session_scope

DEFAULT_PILOT_MINE_ID = "los-pelambres"

logger = logging.getLogger(__name__)


def ensure_dispersion_baseline_registered() -> None:
    """Guarantee the heuristic baseline is in the registry.

    Idempotent. Sets the baseline as `current` only when no dispersion
    model has been registered yet (so a previously-promoted CFD lookup
    isn't demoted by a re-import).
    """
    try:
        registry.get_current("dispersion")
    except registry.ModelNotFoundError:
        registry.register(DistanceDecayDispersionModel())


def maybe_promote_cfd_lookup(
    pilot_mine_id: str = DEFAULT_PILOT_MINE_ID,
) -> bool:
    """Promote `cfd_lookup_v0.1.0` to current if a matrix exists.

    Returns True when the registry's `current` `dispersion` pointer
    was flipped to the CFD lookup; False when promotion was held.
    """
    ensure_dispersion_baseline_registered()
    try:
        # Lazy import — `app.domain.dispersion_matrix` pulls in storage
        # which we don't want at import time of this module.
        from app.domain.dispersion_matrix import load_latest_for_mine

        with session_scope() as session:
            matrix = load_latest_for_mine(session, pilot_mine_id)
        if matrix is None:
            logger.info(
                "cfd_lookup promotion held: no DispersionMatrix for mine_id=%s",
                pilot_mine_id,
            )
            return False
        if not matrix.coefficients:
            logger.info(
                "cfd_lookup promotion held: matrix for mine_id=%s has empty coefficients",
                pilot_mine_id,
            )
            return False
        # Phase BA.7 / BD.3 — sanity-band probe gates promotion. Deferred
        # mode (no observed-receptor PM10 history) accepts on structural
        # sanity; calibrated mode awaits >= 2 receptors x >= 100 obs.
        decision = decide_dispersion_promotion(matrix)
        if not decision.passed:
            logger.info(
                "cfd_lookup promotion held by calibration probe (mode=%s): %s",
                decision.mode, "; ".join(decision.reasons),
            )
            return False
        model = CFDLookupDispersionModel(matrix=matrix, model_version=CFD_LOOKUP_VERSION)
        registry.register(model, set_as_current=False)
        registry.set_current("dispersion", CFD_LOOKUP_VERSION)
        logger.info(
            "cfd_lookup promoted to current for mine_id=%s (matrix_id=%s, mode=%s)",
            pilot_mine_id, matrix.matrix_id, decision.mode,
        )
        return True
    except Exception as exc:  # broad: bootstrap must never raise
        logger.info("cfd_lookup promotion skipped: %s", exc)
        return False


__all__ = [
    "DEFAULT_PILOT_MINE_ID",
    "DISPERSION_BASELINE_VERSION",
    "CFD_LOOKUP_VERSION",
    "ensure_dispersion_baseline_registered",
    "maybe_promote_cfd_lookup",
]
