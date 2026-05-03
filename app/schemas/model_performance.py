"""Model performance + training-record schemas (Phase K, S14; M.1 protocol).

Wire shapes:

- `TrainingRecordSchema` is the assembled S14 join row: prediction +
  recommendation + approval + outcome, plus a derived `outcome_status`
  field. Records with no actual outcome past the configured window are
  emitted with `outcome_status="unobserved"` per the S14 failure mode
  in docs/subsystem-contracts.md.
- `ModelPerformanceMetricSchema` is the persisted aggregate per
  docs/data-contracts.md `model_performance_metrics` (lines 241-248).
- `EvaluationProtocolSchema` (new in M.1) — wire-shape mirror of
  `app.domain.evaluation_protocol.EvaluationProtocol`. Carries the
  pre-registered split discipline + baselines + hindsight rules per
  docs/anti-overfit-protocol.md and docs/anti-hindsight-protocol.md.
- `EvaluateModelRequest` now requires the protocol field. POST-M.1
  callers without a protocol get HTTP 422.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.outcomes import InterventionEffectiveness

OutcomeStatus = Literal["observed", "unobserved"]
HumanAction = Literal[
    "approved", "rejected", "overridden", "expired", "no_recommendation"
]
ModelKind = Literal[
    "dust_forecast",
    "source_attribution",
    "intervention_impact",
    "production_cost",
    "optimization",
]
SplitStrategy = Literal["walk_forward", "expanding_window", "sealed_test"]


class EvaluationProtocolSchema(BaseModel):
    """Wire-shape mirror of `domain.evaluation_protocol.EvaluationProtocol`.

    See docs/anti-overfit-protocol.md and docs/anti-hindsight-protocol.md
    for binding semantics. Field names match the dataclass exactly so
    `EvaluationProtocol(**schema.model_dump())` round-trips.
    """

    split_strategy: SplitStrategy
    train_window_from: datetime
    train_window_to: datetime
    validation_window_from: datetime
    validation_window_to: datetime
    test_window_from: datetime
    test_window_to: datetime
    embargo_days: int = Field(default=7, ge=0, le=365)
    sealed_test_used: bool = False
    baselines_named: list[str] = Field(
        default_factory=lambda: [
            "persistence",
            "seasonal_naive",
            "regulatory_threshold_classifier",
        ]
    )
    sinca_validated_legal_only_after_days: int = Field(default=7, ge=0, le=90)
    realtime_proxy_required: bool = True
    protocol_version: str = "M.4"
    intended_for_realtime: bool = True
    causal_intent: bool = False
    feature_set: list[str] = Field(default_factory=list)
    required_covariates: list[str] = Field(default_factory=list)
    forbidden_covariates: list[str] = Field(default_factory=list)
    max_ece: float = Field(default=0.05, ge=0.0, le=1.0)
    ece_override_reason: str = ""
    notes: str = ""


class TrainingRecordSchema(BaseModel):
    """Assembled S14 row: prediction × recommendation × approval × outcome."""

    prediction_id: str
    recommendation_id: str | None = None
    approval_id: str | None = None
    outcome_id: int | None = None

    issued_at: datetime
    target_kind: str
    target_id: str
    forecast_horizon: str

    predicted_pm10: float
    predicted_pm25: float
    predicted_breach_probability: float
    confidence: float
    model_version: str

    human_action: HumanAction
    chosen_action_rank: int | None = None
    override_action: str | None = None

    actual_pm10_peak: float | None = None
    actual_pm25_peak: float | None = None
    breach_occurred: bool | None = None
    intervention_effectiveness: InterventionEffectiveness | None = None
    production_loss_tonnes_actual: float | None = None
    model_error: str | None = None

    outcome_status: OutcomeStatus
    recorded_at: datetime | None = None


class ModelPerformanceMetricSchema(BaseModel):
    """Wire format for a persisted performance row."""

    model_config = ConfigDict(from_attributes=True)

    metric_id: int
    model_version: str
    model_kind: ModelKind
    evaluated_at: datetime
    window_from: datetime
    window_to: datetime
    sample_count: int
    metric_payload: dict[str, Any]


class EvaluateModelRequest(BaseModel):
    """Body for POST /api/v1/model-performance/evaluate.

    Selects the prediction window, the model_version filter, the
    outcome-observation window past which a missing outcome flips the
    record to `outcome_status="unobserved"`, AND (M.1 onward) the
    binding evaluation protocol per docs/anti-overfit-protocol.md +
    docs/anti-hindsight-protocol.md. Missing protocol → HTTP 422.
    """

    model_version: str
    model_kind: ModelKind = "dust_forecast"
    window_from: datetime
    window_to: datetime
    outcome_observation_minutes: int = Field(default=180, ge=1, le=24 * 60 * 7)
    protocol: EvaluationProtocolSchema
