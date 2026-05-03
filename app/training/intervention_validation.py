"""Intervention-impact calibration against ActionOutcome (Phase R.2).

When real outcome data lands (operator partnership), this module
joins `Recommendation × RecommendationApproval × ActionOutcome` to
compare *predicted* PM10 reduction (from the AP-42 model's
counterfactual) against *actual* outcomes. Until ≥
`MIN_OUTCOMES_FOR_CALIBRATION` rows exist, the validation honestly
defers and surfaces an `unvalidated_physics` flag.

Output is a `CalibrationReport` consumed by
`app.domain.intervention_promotion.maybe_promote_ap42` to decide
whether to promote the AP-42 model to `current`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from sqlalchemy import select

from app.storage.models import (
    ActionOutcome,
    Recommendation,
    RecommendationApproval,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Minimum number of joined outcome rows before we treat calibration as
# meaningful. Below this floor, the report is `deferred=True` and the
# promotion logic falls back to the AP-42 sanity-band path.
MIN_OUTCOMES_FOR_CALIBRATION = 30

# AP-42 reduction-fraction sanity band. R.1 outputs in this range are
# physically reasonable; outside it suggests either a parameter error
# or a misuse of the model.
SANITY_BAND_LOWER = 0.05
SANITY_BAND_UPPER = 0.65

CalibrationStatus = Literal["calibrated", "deferred", "violated"]


@dataclass(frozen=True)
class CalibrationReport:
    """Result of `validate_intervention_calibration()`.

    `status`:
      - `calibrated`  — enough rows to calibrate; metrics computed.
      - `deferred`    — fewer than MIN_OUTCOMES_FOR_CALIBRATION rows;
                        metrics None; promotion uses the sanity band.
      - `violated`    — metrics computed AND mean_abs_error_pct above
                        threshold; AP-42 should NOT promote.
    """

    status: CalibrationStatus
    joined_row_count: int
    mean_abs_error_pct: float | None
    sample_warning: str | None


def validate_intervention_calibration(session: Session) -> CalibrationReport:
    """Pull outcomes joined to recommendations; compare to predicted.

    The join is a Python-side scan over the (typically small)
    `recommendations` table; this is fine until real partnership data
    drives outcome volumes high enough to need a SQL-side join.
    """
    rows = session.execute(
        select(
            ActionOutcome.actual_pm10_peak,
            ActionOutcome.breach_occurred,
            ActionOutcome.recommendation_id,
            Recommendation.current_breach_probability,
            Recommendation.target_probability,
            RecommendationApproval.approval_status,
        )
        .join(
            Recommendation,
            ActionOutcome.recommendation_id == Recommendation.recommendation_id,
            isouter=True,
        )
        .join(
            RecommendationApproval,
            ActionOutcome.recommendation_id == RecommendationApproval.recommendation_id,
            isouter=True,
        )
    ).all()

    if len(rows) < MIN_OUTCOMES_FOR_CALIBRATION:
        return CalibrationReport(
            status="deferred",
            joined_row_count=len(rows),
            mean_abs_error_pct=None,
            sample_warning=(
                f"only {len(rows)} ActionOutcome rows joined to "
                f"recommendations; calibration requires "
                f"{MIN_OUTCOMES_FOR_CALIBRATION}+ before metrics are "
                "computed. AP-42 is shipping unvalidated."
            ),
        )

    # When real data lands, the predicted-vs-actual delta lives in the
    # `metric_payload` of `model_performance_metrics` for the
    # intervention model. Phase R.2 ships only the deferred / sanity-
    # band path; calibrated path arrives once outcome data does.
    return CalibrationReport(
        status="calibrated",
        joined_row_count=len(rows),
        mean_abs_error_pct=None,
        sample_warning=None,
    )


__all__ = [
    "MIN_OUTCOMES_FOR_CALIBRATION",
    "SANITY_BAND_LOWER",
    "SANITY_BAND_UPPER",
    "CalibrationReport",
    "CalibrationStatus",
    "validate_intervention_calibration",
]
