"""Dust forecasting models.

`HeuristicBaselineForecaster` is the cold-start fallback (Phase E,
Guardrail 11). `GBMForecaster` (Phase P) is the first trained
implementation; it is registered alongside but is NOT promoted to
current until Phase P.3 — and only if it passes the M.4.1 ECE gate
on Cuncumén.
"""

from app.models import registry
from app.models.forecasting.gbm_v0_1_0 import (
    GBM_VERSION,
    GBMForecaster,
    ModelArtifactNotFoundError,
)
from app.models.forecasting.heuristic_baseline import (
    HEURISTIC_VERSION,
    HeuristicBaselineForecaster,
)

# Heuristic baseline is registered first AND set as current — Phase
# E behaviour preserved. The trained GBM is registered as an
# additional version (set_as_current=False) so the registry can
# resolve it by version string but the live model stays heuristic
# until P.3 promotion.
registry.register(HeuristicBaselineForecaster())
registry.register(GBMForecaster(), set_as_current=False)

__all__ = [
    "GBM_VERSION",
    "GBMForecaster",
    "HEURISTIC_VERSION",
    "HeuristicBaselineForecaster",
    "ModelArtifactNotFoundError",
]
