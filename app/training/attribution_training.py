"""Source-attribution training pipeline (Phase S.1 / S.2).

S.1 ships a training scaffolding that fits a `LogisticRegression` head
over the four hand-engineered candidate features. The supervision
label is self-distilled from the rules-baseline scoring (a temporary
stepping stone — once labelled DustEvent rows accumulate, S.2's
`train()` will switch to outcome-based supervision).

The artifact bundles the fitted classifier plus
`feature_importances` + `feature_importance_cv_std` so the
EvidenceClass assignment in `LogRegAttributor` can decide whether
to upgrade observational → quasi_experimental per the rule:

    feature_importance >= QE_IMPORTANCE_FLOOR
    AND CV std <= QE_CV_STD_CEILING
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib  # type: ignore[import-untyped]
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import KFold

from app.models.attribution.logreg_v0_1_0 import (
    FEATURE_COLUMNS,
    LOGREG_VERSION,
    logreg_artifact_path,
)
from app.models.attribution.rules_baseline import CandidateSource


@dataclass(frozen=True)
class AttributionTrainingResult:
    model_version: str
    n_candidates: int
    feature_importances: dict[str, float]
    feature_importance_cv_std: dict[str, float]
    artifact_path: Path | None


def _features_for(candidates: list[CandidateSource]) -> np.ndarray:
    from app.models.attribution.logreg_v0_1_0 import _candidate_to_features

    return np.array([_candidate_to_features(c) for c in candidates], dtype=np.float64)


def _self_distilled_labels(candidates: list[CandidateSource]) -> np.ndarray:
    """Use the rules-baseline score as the supervision label.

    Each candidate is labelled 1 iff its rules-baseline score puts
    it above the median of the batch — a coarse but stable signal
    that lets the logreg head learn the *shape* of the rules
    function without an outcome-labelled corpus. S.2 replaces this
    with real outcome labels once DustEvent ground truth lands.
    """
    from app.models.attribution.rules_baseline import _score_candidate

    scores = np.array([_score_candidate(c)[0] for c in candidates])
    # Avoid the all-equal degenerate case (all labels collapse to 0)
    # by ranking — top half gets label 1, bottom half gets 0.
    order = np.argsort(scores)
    cutoff = len(scores) // 2
    labels = np.zeros(len(scores), dtype=np.int64)
    labels[order[cutoff:]] = 1
    return labels


def train_logreg_attributor(
    candidates: list[CandidateSource],
    *,
    artifact_root: Path | None = None,
    persist: bool = True,
    cv_folds: int = 4,
    random_state: int = 0,
) -> AttributionTrainingResult:
    """Fit a logistic-regression head + return importances with CV std.

    `candidates` should be a non-trivial training pool; in dev with
    no real corpus the caller can synthesise from historical
    DustEvent attributions.
    """
    if len(candidates) < 8:
        raise ValueError(
            f"need >=8 candidates to fit logreg + run {cv_folds}-fold CV; "
            f"got {len(candidates)}"
        )
    X = _features_for(candidates)
    y = _self_distilled_labels(candidates)

    main = LogisticRegression(max_iter=200, random_state=random_state).fit(X, y)
    importances = {
        name: float(abs(coef))
        for name, coef in zip(FEATURE_COLUMNS, main.coef_[0], strict=True)
    }

    fold_coefs: list[np.ndarray] = []
    kf = KFold(n_splits=cv_folds, shuffle=True, random_state=random_state)
    for train_idx, _ in kf.split(X):
        if len(np.unique(y[train_idx])) < 2:
            continue
        fold = LogisticRegression(max_iter=200, random_state=random_state).fit(
            X[train_idx], y[train_idx]
        )
        fold_coefs.append(np.abs(fold.coef_[0]))
    if fold_coefs:
        stacked = np.vstack(fold_coefs)
        cv_std = {
            name: float(stacked[:, i].std())
            for i, name in enumerate(FEATURE_COLUMNS)
        }
    else:
        cv_std = {name: float("nan") for name in FEATURE_COLUMNS}

    out_artifact_path: Path | None = None
    if persist:
        out_artifact_path = logreg_artifact_path(artifact_root=artifact_root)
        out_artifact_path.parent.mkdir(parents=True, exist_ok=True)
        bundle: dict[str, Any] = {
            "model": main,
            "feature_columns": list(FEATURE_COLUMNS),
            "feature_importances": importances,
            "feature_importance_cv_std": cv_std,
            "trained_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
            "n_candidates": len(candidates),
        }
        joblib.dump(bundle, out_artifact_path)
    return AttributionTrainingResult(
        model_version=LOGREG_VERSION,
        n_candidates=len(candidates),
        feature_importances=importances,
        feature_importance_cv_std=cv_std,
        artifact_path=out_artifact_path,
    )


__all__ = ["AttributionTrainingResult", "train_logreg_attributor"]
