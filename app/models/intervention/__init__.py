"""Intervention impact models (S9, Phase G + R).

Implementations register themselves via `app.domain.simulation.
ensure_models_registered()` at first use. Phase R.1 adds the AP-42
physics-informed `AP42InterventionImpact` alongside the heuristic
baseline; the registry can resolve both versions.
"""

from app.models.intervention.ap42_v0_1_0 import (
    AP42_VERSION,
    AP42InterventionImpact,
)
from app.models.intervention.heuristic_baseline import (
    HEURISTIC_VERSION,
    HeuristicInterventionImpact,
)

__all__ = [
    "AP42_VERSION",
    "AP42InterventionImpact",
    "HEURISTIC_VERSION",
    "HeuristicInterventionImpact",
]
