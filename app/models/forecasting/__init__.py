"""Dust forecasting models.

`HeuristicBaselineForecaster` (this module) implements
`DustForecastModel` per docs/model-contracts.md. Trained variants
(GBM, neural) plug in later under the same Protocol.
"""

from app.models.forecasting.heuristic_baseline import (
    HEURISTIC_VERSION,
    HeuristicBaselineForecaster,
)

__all__ = ["HEURISTIC_VERSION", "HeuristicBaselineForecaster"]
