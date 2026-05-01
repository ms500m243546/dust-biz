"""S6 Dust Forecast schemas.

Per docs/data-contracts.md `dust_predictions` (Phase E),
docs/subsystem-contracts.md S6, and docs/model-contracts.md
DustForecastModel.

This is the first safety-relevant schema in the repo: the
`validate-safety` scanner activates on any class with `Forecast` /
`Prediction` in its name and requires `confidence` and
`model_version` (Guardrails 2 and 15). `data_quality_warnings`
satisfies Guardrail 5; `source` and the `heuristic_fallback`
literal satisfy Guardrail 11.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ForecastHorizon = Literal["15min", "30min", "60min", "120min", "24h"]
ForecastSource = Literal["model", "heuristic_fallback"]


class ForecastTargetSchema(BaseModel):
    """The thing being forecast.

    Either a sensor (compliance station) or a zone. Forecast horizon
    is independent and supplied alongside.
    """

    target_kind: Literal["sensor", "zone"]
    target_id: str


class DustForecastSchema(BaseModel):
    """Wire format for an issued forecast.

    Mandatory safety fields per safety-guardrails.md:
      - confidence (G2)
      - model_version (G15)
      - feature_pipeline_version (G15)
      - data_quality_warnings (G5)
      - source (G11; "heuristic_fallback" when model failed)
    """

    model_config = ConfigDict(from_attributes=True)

    issued_at: datetime
    target_kind: Literal["sensor", "zone"]
    target_id: str
    forecast_horizon: ForecastHorizon
    predicted_pm10: float
    predicted_pm25: float
    breach_probability: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    main_risk_window: str
    main_uncertainty: str
    model_version: str
    feature_pipeline_version: str
    input_data_quality_score: float = Field(ge=0.0, le=1.0)
    data_quality_warnings: list[str] = Field(default_factory=list)
    source: ForecastSource = "model"
    input_record_ids: list[str] = Field(default_factory=list)
