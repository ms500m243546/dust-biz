"""S15 report schemas (Phase K.2).

Three read-only report payloads consumed by the dashboard
Operations / Compliance / Executive views and any external auditor.
Each report carries its own window + a `generated_at` stamp; all
state is derived from append-only repositories so reports are
trivially reproducible.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.model_performance import ModelKind


class ModelPerformanceReportEntry(BaseModel):
    model_version: str
    model_kind: ModelKind
    sample_count: int
    observed_count: int
    unobserved_count: int
    mae_pm10: float | None = None
    breach_precision: float | None = None
    breach_recall: float | None = None
    false_positive_rate: float | None = None
    false_negative_rate: float | None = None
    calibration_error: float | None = None
    avoided_shutdowns_estimate: int = 0
    production_loss_tonnes_total: float = 0.0
    last_evaluated_at: datetime | None = None


class ModelPerformanceReport(BaseModel):
    generated_at: datetime
    window_from: datetime
    window_to: datetime
    entries: list[ModelPerformanceReportEntry] = Field(default_factory=list)


class ROIReport(BaseModel):
    """Cost / value summary for the operations + executive views.

    All currency in USD per docs/data-contracts.md. Conservative by
    design — `avoided_shutdown_value_usd` only counts records the
    operator approved/overrode (not rejected), matching the S14
    avoided-shutdowns estimate.
    """

    model_config = ConfigDict(from_attributes=True)

    generated_at: datetime
    window_from: datetime
    window_to: datetime
    site_id: str | None = None
    tonne_value_usd: float
    avoided_shutdowns_count: int
    avoided_shutdown_value_usd: float
    intervention_cost_usd: float
    realised_production_loss_tonnes: float
    realised_production_loss_usd: float
    net_value_usd: float
    sample_count: int


class ComplianceReportEntry(BaseModel):
    """One station's exceedance state over the window."""

    sensor_id: str
    pm10_breach_count: int
    pm25_breach_count: int
    pm10_warning_count: int
    pm25_warning_count: int
    peak_pm10: float | None = None
    peak_pm25: float | None = None
    pm10_breach_threshold: float
    pm25_breach_threshold: float
    pm10_warning_threshold: float
    pm25_warning_threshold: float


class ComplianceReport(BaseModel):
    generated_at: datetime
    window_from: datetime
    window_to: datetime
    site_id: str | None = None
    stations: list[ComplianceReportEntry] = Field(default_factory=list)
    total_dust_events: int = 0
    total_breach_events: int = 0


__all__ = [
    "ComplianceReport",
    "ComplianceReportEntry",
    "ModelPerformanceReport",
    "ModelPerformanceReportEntry",
    "ROIReport",
]
