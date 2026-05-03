"""Production cost models (S10, Phase G + U).

Implementations register themselves into `app.models.registry` under
`model_kind = "production_cost"`. The Domain layer obtains a cost
model exclusively via the registry. Phase U.1 adds the cycle-time
physics-informed `CycleTimeProductionCost` alongside the heuristic
baseline; the registry can resolve both versions.
"""

from app.models.cost.cycle_time_v0_1_0 import (
    CYCLE_TIME_VERSION,
    CycleTimeProductionCost,
)
from app.models.cost.heuristic_baseline import (
    HEURISTIC_VERSION,
    HeuristicProductionCost,
)

__all__ = [
    "CYCLE_TIME_VERSION",
    "CycleTimeProductionCost",
    "HEURISTIC_VERSION",
    "HeuristicProductionCost",
]
