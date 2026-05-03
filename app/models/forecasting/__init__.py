"""Dust forecasting models.

`HeuristicBaselineForecaster` is the cold-start fallback (Phase E,
Guardrail 11). `GBMForecaster` (Phase P) is the first trained
implementation. Both are registered here; promotion of the GBM to
`current` is decided by `app.domain.dust_forecast_promotion.
maybe_promote_gbm`, which is called from the API lifespan hook
(layered: api → domain → storage; models stay pure).
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

# Heuristic baseline is registered first AND set as current — Phase E
# behaviour preserved. The trained GBM is registered as an additional
# version (set_as_current=False); promotion is decided downstream.
registry.register(HeuristicBaselineForecaster())
registry.register(GBMForecaster(), set_as_current=False)


__all__ = [
    "GBM_VERSION",
    "GBMForecaster",
    "HEURISTIC_VERSION",
    "HeuristicBaselineForecaster",
    "ModelArtifactNotFoundError",
]
