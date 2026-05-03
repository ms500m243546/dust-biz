"""Dust forecasting models.

`HeuristicBaselineForecaster` is the cold-start fallback (Phase E,
Guardrail 11). `GBMForecaster` (Phase P) is the first trained
implementation. Both are registered here; promotion of the GBM to
`current` is decided by `app.domain.dust_forecast_promotion.
maybe_promote_gbm`, which is called from the API lifespan hook
(layered: api → domain → storage; models stay pure).
"""

from app.models import registry
from app.models.forecasting.gbm_shared_v0_1_0 import (
    GBM_SHARED_VERSION,
    GBMSharedForecaster,
)
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
# behaviour preserved. The trained variants are registered as
# additional versions (set_as_current=False); promotion is decided
# by app.domain.dust_forecast_promotion.
registry.register(HeuristicBaselineForecaster())
registry.register(GBMForecaster(), set_as_current=False)
registry.register(GBMSharedForecaster(), set_as_current=False)


__all__ = [
    "GBM_SHARED_VERSION",
    "GBM_VERSION",
    "GBMForecaster",
    "GBMSharedForecaster",
    "HEURISTIC_VERSION",
    "HeuristicBaselineForecaster",
    "ModelArtifactNotFoundError",
]
