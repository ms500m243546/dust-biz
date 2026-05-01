"""Rule-based source attribution baseline (S7 first implementation).

Per docs/model-contracts.md "rule-based combining (a) wind-aligned
spatial proximity to active sources, (b) activity-time / spike-time
correlation, (c) source baseline dust potential."

Coefficients are intentionally simple and uncalibrated; this is
the cold-start model. Trained variants (gradient boosting,
spatial graph) plug into the same Protocol later.

Inputs are kept as plain typed structures rather than session-
bound ORM rows so the model stays a pure function (per
docs/model-contracts.md universal rule 5: models do not mutate
database records).

Each candidate source receives a score in [0, 1] computed from:
  proximity_score x time_correlation_score x dust_potential_factor
plus a constant `external_background_floor` candidate so an
"unknown internal source" path has a non-zero attribution.

Returns a SourceAttributionSchema with a normalized ranked list
and an `evidence_fields` dict carrying the underlying numbers a
reviewer can audit.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.schemas.attributions import ProbableSource, SourceAttributionSchema

RULES_VERSION = "source_attribution_rules_v0.1.0"

EXTERNAL_BACKGROUND_FLOOR = 0.10
DUST_POTENTIAL_FACTOR: dict[str, float] = {
    "high": 1.0,
    "medium": 0.7,
    "low": 0.4,
    "unknown": 0.5,
}


class CandidateSource:
    """Plain-data candidate the orchestrator hands to `attribute()`."""

    __slots__ = (
        "source_id",
        "wind_angle_offset_deg",
        "activity_intensity",
        "dust_generation_potential",
        "concurrent_pm_rise",
    )

    def __init__(
        self,
        *,
        source_id: str,
        wind_angle_offset_deg: float | None,
        activity_intensity: float,
        dust_generation_potential: str,
        concurrent_pm_rise: float,
    ) -> None:
        self.source_id = source_id
        self.wind_angle_offset_deg = wind_angle_offset_deg
        self.activity_intensity = activity_intensity
        self.dust_generation_potential = dust_generation_potential
        self.concurrent_pm_rise = concurrent_pm_rise


class RulesBaselineAttributor:
    """First implementation of SourceAttributionModel.

    `model_kind` is typed `str` rather than `Literal["source_attribution"]`
    for Protocol-compatibility with the registry; the assigned string
    value enforces the kind at runtime.
    """

    model_kind: str = "source_attribution"

    def __init__(self, model_version: str = RULES_VERSION) -> None:
        self.model_version = model_version

    def attribute(
        self,
        *,
        attribution_id: str,
        dust_event_id: str,
        affected_station: str,
        candidates: list[CandidateSource],
        issued_at: datetime,
    ) -> SourceAttributionSchema:
        if not candidates:
            return self._unknown(
                attribution_id=attribution_id,
                dust_event_id=dust_event_id,
                affected_station=affected_station,
                issued_at=issued_at,
                reason="no candidate sources available",
            )

        scored: list[tuple[CandidateSource, float, str]] = []
        for c in candidates:
            score, reason = _score_candidate(c)
            scored.append((c, score, reason))

        # Add the always-present external/background floor.
        scored.append(
            (
                _external_background(),
                EXTERNAL_BACKGROUND_FLOOR,
                "regional / external dust baseline",
            )
        )

        total = sum(s for _, s, _ in scored)
        if total <= 0:
            return self._unknown(
                attribution_id=attribution_id,
                dust_event_id=dust_event_id,
                affected_station=affected_station,
                issued_at=issued_at,
                reason="all candidate scores collapsed to zero",
            )

        ranked = sorted(scored, key=lambda t: t[1], reverse=True)
        probable = [
            ProbableSource(
                source=c.source_id,
                confidence=round(score / total, 3),
                reason=reason,
            )
            for (c, score, reason) in ranked
            if score > 0
        ]

        # Overall confidence: high when one source clearly dominates,
        # low when many sources score similarly. Use the top share.
        top_share = ranked[0][1] / total

        evidence: dict[str, Any] = {
            "candidate_count": len(candidates),
            "top_source": ranked[0][0].source_id,
            "top_score": round(ranked[0][1], 3),
            "score_total": round(total, 3),
            "wind_angle_offsets_deg": {
                c.source_id: c.wind_angle_offset_deg for c in candidates
            },
            "activity_intensities": {c.source_id: c.activity_intensity for c in candidates},
            "concurrent_pm_rises": {c.source_id: c.concurrent_pm_rise for c in candidates},
        }

        return SourceAttributionSchema(
            attribution_id=attribution_id,
            dust_event_id=dust_event_id,
            issued_at=issued_at,
            affected_station=affected_station,
            probable_sources=probable,
            evidence_fields=evidence,
            confidence=round(top_share, 3),
            model_version=self.model_version,
        )

    def _unknown(
        self,
        *,
        attribution_id: str,
        dust_event_id: str,
        affected_station: str,
        issued_at: datetime,
        reason: str,
    ) -> SourceAttributionSchema:
        return SourceAttributionSchema(
            attribution_id=attribution_id,
            dust_event_id=dust_event_id,
            issued_at=issued_at,
            affected_station=affected_station,
            probable_sources=[
                ProbableSource(source="Unknown", confidence=0.0, reason=reason)
            ],
            evidence_fields={"reason": reason},
            confidence=0.0,
            model_version=self.model_version,
        )


def _external_background() -> CandidateSource:
    return CandidateSource(
        source_id="external_background",
        wind_angle_offset_deg=None,
        activity_intensity=0.0,
        dust_generation_potential="unknown",
        concurrent_pm_rise=0.0,
    )


def _proximity_score(wind_angle_offset_deg: float | None) -> float:
    """Wind-aligned spatial proximity.

    The orchestrator computes `wind_angle_offset_deg` as the angle
    between the station-to-source bearing and the wind ray
    direction. 0 deg = directly upwind of the station (ideal
    suspect); 180 deg = directly downwind (unlikely). None = no
    wind data; flat 0.5.
    """
    if wind_angle_offset_deg is None:
        return 0.5
    offset = abs(_normalize_deg(wind_angle_offset_deg))
    if offset >= 90.0:
        return 0.1
    return round(1.0 - (offset / 90.0) * 0.9, 3)


def _normalize_deg(deg: float) -> float:
    """Map to [-180, 180]."""
    d = ((deg + 180.0) % 360.0) - 180.0
    return d


def _score_candidate(c: CandidateSource) -> tuple[float, str]:
    proximity = _proximity_score(c.wind_angle_offset_deg)
    time_corr = max(0.0, min(1.0, c.concurrent_pm_rise))
    activity = max(0.0, min(1.0, c.activity_intensity))
    potential = DUST_POTENTIAL_FACTOR.get(c.dust_generation_potential, 0.5)

    # Weighted geometric-style mean: each factor pulls the score
    # down. Activity and time-correlation are co-required (if there
    # was no activity AND no PM rise correlated, the source is
    # implausible).
    score = proximity * (0.4 + 0.6 * max(time_corr, activity)) * potential

    parts: list[str] = []
    if c.wind_angle_offset_deg is None:
        parts.append("no wind data")
    elif proximity >= 0.7:
        parts.append("strong wind alignment")
    elif proximity >= 0.4:
        parts.append("partial wind alignment")
    else:
        parts.append("poor wind alignment")

    if activity >= 0.5:
        parts.append("active dust-generating equipment")
    elif activity > 0:
        parts.append("low activity")

    if time_corr >= 0.5:
        parts.append("PM rise correlated in time")

    if c.dust_generation_potential == "high":
        parts.append("high baseline dust potential")
    elif c.dust_generation_potential == "low":
        parts.append("low baseline dust potential")

    return round(score, 4), "; ".join(parts) or "weak overall signal"
