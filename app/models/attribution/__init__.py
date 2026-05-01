"""Source attribution models.

`RulesBaselineAttributor` (this module) implements
SourceAttributionModel per docs/model-contracts.md. Trained
variants plug in later under the same Protocol.
"""

from app.models.attribution.rules_baseline import (
    RULES_VERSION,
    RulesBaselineAttributor,
)

__all__ = ["RULES_VERSION", "RulesBaselineAttributor"]
