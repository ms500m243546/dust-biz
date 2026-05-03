"""Logreg attribution model auto-promotion (Phase S.2).

Decides whether to flip the registry's `current` `source_attribution`
pointer from the rules baseline to the trained logreg.

Promotion criteria (in priority order):
  1. If a fitted artifact exists on disk AND a probe attribution
     against a clear downwind/upwind scenario both ranks correctly
     and reports EvidenceClass != `expert_judgment`, promote.
  2. If no artifact exists OR the probe fails, leave rules baseline
     as current.
  3. Any storage / compute exception → rules baseline stays current,
     INFO log; never raises into the bootstrap path.

The bootstrap deliberately does NOT fit the logreg — fitting is an
operator action via `scripts/train_attribution.py` (Phase S.3+).
This keeps process startup cheap and avoids overwriting a deliberate
artifact with synthetic-pool weights.

When labelled `SourceAttribution` rows accumulate (≥
MIN_LABELLED_FOR_CALIBRATION), Phase S.3 will replace the probe
with real top-1-accuracy comparison vs the rules baseline.

Layered: this module sits in `app/domain` so it can import both
`app/models` and `app/storage`.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime

from sqlalchemy import func, select

from app.models import registry
from app.models.attribution.logreg_v0_1_0 import (
    LOGREG_VERSION,
    LogRegAttributor,
    logreg_artifact_path,
)
from app.models.attribution.rules_baseline import (
    CandidateSource,
    RulesBaselineAttributor,
)
from app.storage.database import session_scope
from app.storage.models import SourceAttribution

logger = logging.getLogger(__name__)

MIN_LABELLED_FOR_CALIBRATION = 30


def _probe_artifact() -> tuple[bool, str]:
    """Probe the on-disk artifact against a clear downwind scenario.

    Passes iff the loaded attributor:
      - reports `evidence_class != "expert_judgment"` (artifact
        metadata loaded; feature-importance + CV std present)
      - ranks the directly-downwind, high-activity candidate first
    """
    a = LogRegAttributor()
    out = a.attribute(
        attribution_id="probe-att",
        dust_event_id="probe-evt",
        affected_station="probe-station",
        candidates=[
            CandidateSource(
                source_id="downwind",
                wind_angle_offset_deg=10.0,
                activity_intensity=0.95,
                dust_generation_potential="high",
                concurrent_pm_rise=8.0,
            ),
            CandidateSource(
                source_id="upwind",
                wind_angle_offset_deg=170.0,
                activity_intensity=0.05,
                dust_generation_potential="low",
                concurrent_pm_rise=1.0,
            ),
        ],
        issued_at=datetime(2026, 5, 3, 12, 0),
    )
    if out.evidence_class == "expert_judgment":
        return False, "no fitted artifact (cold-start evidence_class)"
    if not out.probable_sources or out.probable_sources[0].source != "downwind":
        return (
            False,
            "downwind not ranked first "
            f"(top: {out.probable_sources[0].source if out.probable_sources else None!r})",
        )
    return True, f"probe ok (evidence_class={out.evidence_class})"


def maybe_promote_logreg() -> bool:
    """Promote logreg to current iff probe passes against a real artifact.

    Tolerant by design: any exception leaves the rules baseline as
    current and logs INFO. Never raises into the bootstrap path.
    """
    try:
        registry.register(RulesBaselineAttributor(), set_as_current=True)
        with contextlib.suppress(Exception):
            registry.register(LogRegAttributor(), set_as_current=False)
        if not logreg_artifact_path().exists():
            logger.info(
                "logreg promotion held: no fitted artifact at %s",
                logreg_artifact_path(),
            )
            return False
        with session_scope() as session:
            n_attr = session.execute(
                select(func.count()).select_from(SourceAttribution)
            ).scalar() or 0
        if n_attr >= MIN_LABELLED_FOR_CALIBRATION:
            # Future Phase S.3: compare logreg vs rules accuracy on
            # labelled rows. With 0 today, we fall through to probe.
            logger.info(
                "logreg promotion: %d labelled rows present; calibration "
                "comparison deferred to S.3",
                n_attr,
            )
        passed, msg = _probe_artifact()
        if not passed:
            logger.info("logreg promotion held: %s", msg)
            return False
        registry.set_current("source_attribution", LOGREG_VERSION)
        logger.info("logreg promoted to current (%s)", msg)
        return True
    except Exception as exc:  # broad: bootstrap must never raise
        logger.info("logreg promotion skipped: %s", exc)
        return False


__all__ = ["MIN_LABELLED_FOR_CALIBRATION", "maybe_promote_logreg"]
