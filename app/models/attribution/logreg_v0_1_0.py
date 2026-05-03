"""Logistic-regression source attribution model (Phase S.1).

Replaces the rule-based scoring in `RulesBaselineAttributor` with a
trained logistic regression over per-candidate features. The
EvidenceClass assigned per attribution is now learned-data-aware
(per `docs/causal-protocol.md`):

  experimental                 — never assigned (no RCT data exists)
  quasi_experimental           — assigned when the model has high
                                 confidence in a feature whose
                                 importance comes from cross-fold
                                 stability (proxied by feature
                                 importance > QE_IMPORTANCE_FLOOR
                                 AND CV std < QE_CV_STD_CEILING from
                                 the artifact metadata)
  observational_correlational  — default; the data is what it is
  expert_judgment              — pure rule fallback (kept for the
                                 cold-start when no artifact exists)

Phase S.1 ships a logistic-regression head over hand-engineered
features so it can run today without an outcome-labelled corpus
(the rules baseline's score function provides the supervision label
for self-distillation; this is a stepping stone toward true
outcome-supervised training in a later phase).

Phase S.2 wires promotion: if the logreg's top-1 attribution accuracy
beats the rules baseline on labelled DustEvent rows AND the
EvidenceClass distribution shifts toward `quasi_experimental`,
register as current.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import joblib  # type: ignore[import-untyped]
import numpy as np

from app.models.attribution.rules_baseline import (
    DUST_POTENTIAL_FACTOR,
    EXTERNAL_BACKGROUND_FLOOR,
    CandidateSource,
)
from app.models.forecasting.gbm_v0_1_0 import DEFAULT_ARTIFACT_ROOT
from app.schemas.attributions import (
    EvidenceClass,
    ProbableSource,
    SourceAttributionSchema,
)

LOGREG_VERSION = "source_attribution_logreg_v0.1.0"
MODEL_KIND = "source_attribution"

# EvidenceClass assignment thresholds. Tightening these makes the
# `quasi_experimental` class harder to earn; loosening makes it
# easier. Calibrate as the corpus grows.
QE_IMPORTANCE_FLOOR = 0.10
QE_CV_STD_CEILING = 0.02

FEATURE_COLUMNS: tuple[str, ...] = (
    "wind_alignment_score",
    "activity_intensity",
    "dust_potential_factor",
    "concurrent_pm_rise",
)


def logreg_artifact_path(
    *,
    artifact_root: Path | None = None,
    model_version: str = LOGREG_VERSION,
) -> Path:
    """Single shared artifact: one logreg head for all stations."""
    root = artifact_root or DEFAULT_ARTIFACT_ROOT
    return root / "source_attribution" / model_version / "head.joblib"


def _wind_alignment_score(angle_offset_deg: float | None) -> float:
    """1.0 for direct downwind alignment, 0.0 at 180°.

    A pure cosine over the 0..180° range so anything beyond 90° (the
    upwind hemisphere) contributes negative-half values clipped to 0.
    """
    if angle_offset_deg is None:
        return 0.0
    a = abs(angle_offset_deg) % 360
    if a > 180:
        a = 360 - a
    if a >= 90:
        return 0.0
    return float(np.cos(np.radians(a)))


def _candidate_to_features(c: CandidateSource) -> list[float]:
    return [
        _wind_alignment_score(c.wind_angle_offset_deg),
        max(0.0, float(c.activity_intensity)),
        DUST_POTENTIAL_FACTOR.get(c.dust_generation_potential, 0.5),
        max(0.0, float(c.concurrent_pm_rise)),
    ]


class LogRegAttributor:
    """Phase S.1 logistic-regression source attributor.

    On `attribute()`:
      1. Project each candidate to a fixed feature vector.
      2. If a fitted logreg artifact exists, score per-candidate
         probabilities with `predict_proba`. Otherwise fall back to
         a uniform sigmoid over a hand-tuned linear combination
         (so the model is usable cold without a fit).
      3. Normalise across candidates so the resulting probabilities
         sum to ≤ 1 (the residual is the implicit "external/unknown"
         attribution).
      4. Emit `evidence_class` per the assignment rules above.
    """

    model_kind: str = MODEL_KIND

    def __init__(
        self,
        *,
        model_version: str = LOGREG_VERSION,
        artifact_root: Path | None = None,
    ) -> None:
        self.model_version = model_version
        self._artifact_root = artifact_root
        self._artifact: dict[str, Any] | None = None

    def _load_or_none(self) -> dict[str, Any] | None:
        if self._artifact is not None:
            return self._artifact
        path = logreg_artifact_path(
            artifact_root=self._artifact_root,
            model_version=self.model_version,
        )
        if not path.exists():
            return None
        loaded: dict[str, Any] = joblib.load(path)
        self._artifact = loaded
        return loaded

    def _per_candidate_score(
        self, c: CandidateSource, artifact: dict[str, Any] | None
    ) -> float:
        x = np.array([_candidate_to_features(c)], dtype=np.float64)
        if artifact is not None and "model" in artifact:
            clf = artifact["model"]
            proba = clf.predict_proba(x)
            return float(proba[0, 1]) if proba.shape[1] >= 2 else float(proba[0, 0])
        # Cold-start: hand-tuned linear combination through a sigmoid.
        # Coefficients reflect the rules-baseline weighting so the
        # cold model is at parity with the rules at registration time.
        x0 = float(x[0, 0])  # wind alignment
        x1 = float(x[0, 1])  # activity intensity
        x2 = float(x[0, 2])  # dust potential
        x3 = float(x[0, 3])  # concurrent rise
        z = -1.0 + 2.0 * x0 + 1.5 * x1 + 1.0 * x2 + 1.5 * x3
        return float(1.0 / (1.0 + np.exp(-z)))

    def _evidence_class(self, artifact: dict[str, Any] | None) -> EvidenceClass:
        if artifact is None:
            return "expert_judgment"
        importances = artifact.get("feature_importances", {}) or {}
        cv_stds = artifact.get("feature_importance_cv_std", {}) or {}
        for feat in FEATURE_COLUMNS:
            imp = importances.get(feat)
            std = cv_stds.get(feat)
            if (
                isinstance(imp, (int, float))
                and isinstance(std, (int, float))
                and imp >= QE_IMPORTANCE_FLOOR
                and std <= QE_CV_STD_CEILING
            ):
                return "quasi_experimental"
        return "observational_correlational"

    def attribute(
        self,
        *,
        attribution_id: str,
        dust_event_id: str,
        affected_station: str,
        candidates: list[CandidateSource],
        issued_at: datetime,
    ) -> SourceAttributionSchema:
        artifact = self._load_or_none()
        evidence_class = self._evidence_class(artifact)

        if not candidates:
            return SourceAttributionSchema(
                attribution_id=attribution_id,
                dust_event_id=dust_event_id,
                issued_at=issued_at,
                affected_station=affected_station,
                probable_sources=[
                    ProbableSource(
                        source="Unknown",
                        confidence=0.0,
                        reason="no candidate sources available",
                    )
                ],
                evidence_fields={"reason": "no candidates"},
                confidence=0.0,
                model_version=self.model_version,
                evidence_class=evidence_class,
            )

        scored = [
            (c, self._per_candidate_score(c, artifact))
            for c in candidates
        ]
        # Add the residual external-background floor; rules-baseline
        # parity for the "unknown internal source" path.
        scored.append((_external_background(), EXTERNAL_BACKGROUND_FLOOR))
        total = sum(s for _, s in scored)
        if total <= 0:
            return SourceAttributionSchema(
                attribution_id=attribution_id,
                dust_event_id=dust_event_id,
                issued_at=issued_at,
                affected_station=affected_station,
                probable_sources=[
                    ProbableSource(
                        source="Unknown",
                        confidence=0.0,
                        reason="all candidate scores collapsed to zero",
                    )
                ],
                evidence_fields={"reason": "zero-score sweep"},
                confidence=0.0,
                model_version=self.model_version,
                evidence_class=evidence_class,
            )
        ranked = sorted(scored, key=lambda t: t[1], reverse=True)
        probable = [
            ProbableSource(
                source=c.source_id,
                confidence=round(s / total, 3),
                reason=(
                    f"logreg score {s:.3f} (wind alignment + activity + "
                    f"dust potential + concurrent rise)"
                ),
            )
            for c, s in ranked
            if s > 0
        ]
        top_share = ranked[0][1] / total
        return SourceAttributionSchema(
            attribution_id=attribution_id,
            dust_event_id=dust_event_id,
            issued_at=issued_at,
            affected_station=affected_station,
            probable_sources=probable,
            evidence_fields={
                "candidate_count": len(candidates),
                "top_source": ranked[0][0].source_id,
                "top_score": round(ranked[0][1], 3),
                "score_total": round(total, 3),
                "model_artifact_present": artifact is not None,
            },
            confidence=round(top_share, 3),
            model_version=self.model_version,
            evidence_class=evidence_class,
        )


def _external_background() -> CandidateSource:
    return CandidateSource(
        source_id="external_background",
        wind_angle_offset_deg=None,
        activity_intensity=0.0,
        dust_generation_potential="unknown",
        concurrent_pm_rise=0.0,
    )


__all__ = [
    "FEATURE_COLUMNS",
    "LOGREG_VERSION",
    "MODEL_KIND",
    "QE_CV_STD_CEILING",
    "QE_IMPORTANCE_FLOOR",
    "LogRegAttributor",
    "logreg_artifact_path",
]
