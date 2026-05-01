"""Intervention library schemas (Phase G, S8).

Per docs/data-contracts.md `intervention_options` and
docs/subsystem-contracts.md S8. The library is the source of truth for
which actions are allowed, who can authorize them, and which automation
levels may dispatch them. Guardrail 14 (`docs/safety-guardrails.md`)
makes `requires_human_approval` and `automation_eligible_levels`
mandatory; missing values fail the contract validator at the schema
boundary rather than at the recommendation engine.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.mine import AutomationLevel, ZoneType

RiskClass = Literal["low", "medium", "high"]


class InterventionOptionSchema(BaseModel):
    """Wire format for one entry in the intervention library."""

    model_config = ConfigDict(from_attributes=True)

    intervention_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str
    risk_class: RiskClass
    requires_human_approval: bool
    automation_eligible_levels: list[AutomationLevel] = Field(default_factory=list)
    estimated_time_to_effect_minutes: int = Field(ge=0)
    allowed_zone_types: list[ZoneType] = Field(default_factory=list)
