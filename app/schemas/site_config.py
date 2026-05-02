"""Site configuration schema.

Per docs/data-contracts.md `site_configurations`. Site config is the
authoritative source for per-deployment thresholds, automation level,
and optimization weights. Precedence: site_configurations wins;
`mines.default_*` is fallback only when no site_config exists for a
mine. The fallback rule is implemented in
`app/domain/site_config_resolver.py`.

Defaults shipped here match `docs/safety-guardrails.md` ("compliance
priority logic") and `docs/compliance-context.md` ("Practical default
for site config").
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.mine import AutomationLevel

DEFAULT_PM10_THRESHOLDS: dict[str, float] = {"warning": 100.0, "breach": 150.0}
DEFAULT_PM25_THRESHOLDS: dict[str, float] = {"warning": 25.0, "breach": 35.0}


class OptimizationWeightsSchema(BaseModel):
    """Weights consumed by the optimization engine (S11, Phase H).

    Defaults map to the "balanced" regime in safety-guardrails.md
    "compliance-priority logic". Per-site overrides land in the JSON
    column on `site_configurations`.
    """

    w_breach: float = Field(default=1.0, ge=0.0)
    w_production: float = Field(default=1.0, ge=0.0)
    w_disruption: float = Field(default=0.5, ge=0.0)
    w_low_confidence: float = Field(default=0.5, ge=0.0)
    w_compliance: float = Field(default=1.0, ge=0.0)


class SiteConfigSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    site_id: str
    mine_id: str
    automation_level: AutomationLevel = "L1"
    pm10_thresholds: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_PM10_THRESHOLDS))
    pm25_thresholds: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_PM25_THRESHOLDS))
    extreme_breach_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    low_confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    approval_expiry_minutes: int = Field(default=15, ge=1, le=24 * 60)
    optimization_weights: OptimizationWeightsSchema = Field(
        default_factory=OptimizationWeightsSchema
    )
    intervention_constraints: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime | None = None
    updated_by: str | None = None

    @field_validator("intervention_constraints", mode="before")
    @classmethod
    def _coerce_none_to_empty(cls, v: Any) -> Any:
        # SQLAlchemy `default=dict` fires on flush, so an unflushed ORM row
        # exposes None; treat that as the empty-constraints case.
        return {} if v is None else v

    @field_validator("approval_expiry_minutes", mode="before")
    @classmethod
    def _coerce_none_expiry(cls, v: Any) -> Any:
        # Same flush-default pattern as intervention_constraints: an
        # unflushed ORM row exposes None even though the column default is 15.
        return 15 if v is None else v
