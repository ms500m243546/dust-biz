"""Source attribution models (Phase F + S).

`RulesBaselineAttributor` is the cold-start baseline (Phase F).
`LogRegAttributor` (Phase S.1) is the first trained implementation;
it is registered by `app.domain.attribution.ensure_models_registered`
at first use, alongside the rules baseline. Promotion to current is
decided by the Phase S.2 promotion check.
"""

from app.models.attribution.logreg_v0_1_0 import (
    LOGREG_VERSION,
    LogRegAttributor,
)
from app.models.attribution.rules_baseline import (
    RULES_VERSION,
    RulesBaselineAttributor,
)

__all__ = [
    "LOGREG_VERSION",
    "LogRegAttributor",
    "RULES_VERSION",
    "RulesBaselineAttributor",
]
