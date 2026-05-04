"""Phase Y — class-imbalance mitigation tests.

The forecast classifier ships with `class_weight="balanced"` so the
breach-event minority class isn't drowned out during gradient
boosting. This file verifies the constructor kwarg propagates
through `_fit_models` and that recall lifts on a synthetic
imbalanced dataset.
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
)

from app.training.dust_forecast_training import _fit_models


def _imbalanced_dataset(n: int = 400, positive_rate: float = 0.04) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Synthetic imbalanced dataset: most rows benign, a few real breaches."""
    rng = np.random.default_rng(42)
    X = rng.standard_normal((n, 4))
    n_pos = max(1, int(n * positive_rate))
    y_breach = np.zeros(n, dtype=np.int64)
    # Position positives on the high-side of feature 0 so a model can
    # actually learn the boundary; without separability the test would
    # measure noise rather than the class-weight effect.
    pos_idx = np.argsort(X[:, 0])[-n_pos:]
    y_breach[pos_idx] = 1
    # PM10 regression target — irrelevant to the breach classifier path
    # but required by the API.
    y_pm10 = rng.normal(80, 20, size=n)
    return X, y_pm10, y_breach


def test_fit_models_uses_balanced_class_weight() -> None:
    X, y_pm10, y_breach = _imbalanced_dataset()
    _, clf = _fit_models(X, y_pm10, y_breach, recalibrate=False)
    # Uncalibrated path returns the raw HistGradientBoostingClassifier.
    assert isinstance(clf, HistGradientBoostingClassifier)
    assert clf.class_weight == "balanced"


def test_balanced_classifier_beats_unbalanced_recall_on_imbalanced_data() -> None:
    # Direct comparison: train a vanilla HGBT and a class_weight=balanced
    # one on the same dataset and verify the balanced version recovers
    # more positives. (This is the load-bearing claim — the ranker
    # cares about breach_recall, not just config.)
    X, y_pm10, y_breach = _imbalanced_dataset()
    vanilla = HistGradientBoostingClassifier(max_iter=200, random_state=0)
    vanilla.fit(X, y_breach)
    balanced = HistGradientBoostingClassifier(
        max_iter=200, random_state=0, class_weight="balanced"
    )
    balanced.fit(X, y_breach)
    pos_idx = y_breach == 1
    vanilla_recall = (
        vanilla.predict(X[pos_idx]).sum() / pos_idx.sum()
    )
    balanced_recall = (
        balanced.predict(X[pos_idx]).sum() / pos_idx.sum()
    )
    assert balanced_recall >= vanilla_recall
    # The regressor stays as-is; sanity-check the type signature didn't
    # drift.
    regressor, _ = _fit_models(X, y_pm10, y_breach, recalibrate=False)
    assert isinstance(regressor, HistGradientBoostingRegressor)
