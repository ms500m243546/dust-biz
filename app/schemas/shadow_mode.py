"""Shadow-mode evaluation schemas (Phase K.4)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

PromotionRecommendation = Literal["promote", "hold", "regress"]


class ShadowEvaluationRequest(BaseModel):
    candidate_version: str
    production_version: str
    window_from: datetime
    window_to: datetime
    observation_window_minutes: int = Field(default=180, ge=1, le=24 * 60 * 7)


class ShadowEvaluationResponse(BaseModel):
    candidate_version: str
    production_version: str
    window_from: datetime
    window_to: datetime
    candidate_metrics: dict[str, Any]
    production_metrics: dict[str, Any]
    delta: dict[str, float | None]
    recommendation: PromotionRecommendation
    recommendation_reason: str


__all__ = [
    "PromotionRecommendation",
    "ShadowEvaluationRequest",
    "ShadowEvaluationResponse",
]
