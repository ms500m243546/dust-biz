"""ActionOutcome schemas (Phase I, S14 feeder).

Per docs/data-contracts.md `action_outcomes`. Phase I covers manual
entry by environmental_manager / operations_manager. The Phase K full
join (S14) reads these rows alongside predictions and recommendations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

InterventionEffectiveness = Literal[
    "successful", "partial", "unsuccessful", "not_applicable"
]


class ActionOutcomeCreate(BaseModel):
    """Body for POST /api/v1/action-outcomes."""

    recommendation_id: str | None = None
    prediction_id: str | None = None
    actual_pm10_peak: float = Field(ge=0.0)
    actual_pm25_peak: float | None = Field(default=None, ge=0.0)
    breach_occurred: bool
    production_loss_tonnes_actual: float | None = Field(default=None, ge=0.0)
    intervention_effectiveness: InterventionEffectiveness
    model_error: str | None = Field(default=None, max_length=2000)


class ActionOutcomeSchema(BaseModel):
    """Wire format for a persisted outcome."""

    model_config = ConfigDict(from_attributes=True)

    outcome_id: int
    recommendation_id: str | None = None
    prediction_id: str | None = None
    actual_pm10_peak: float
    actual_pm25_peak: float | None = None
    breach_occurred: bool
    production_loss_tonnes_actual: float | None = None
    intervention_effectiveness: InterventionEffectiveness
    model_error: str | None = None
    recorded_at: datetime
    recorded_by: str
