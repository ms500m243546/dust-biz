"""Drift-watch schemas (Phase M.4.3, B-12 mitigation).

Wire shape for the GET /api/v1/drift endpoint. Pure derived view —
no storage model. The API computes alerts on read against
`model_performance_metrics` rows.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DriftAlertSchema(BaseModel):
    """One detected per-metric drift between baseline and recent windows.

    `delta` is `|recent_value - baseline_value|`, in the metric's own
    units (probability points for recall/precision/FPR/FNR/ece/cal-err;
    µg/m³ for mae_pm10). `threshold` is the DRIFT_THRESHOLDS value the
    metric crossed.
    """

    model_version: str
    metric_name: str
    baseline_value: float
    recent_value: float
    delta: float = Field(ge=0.0)
    threshold: float = Field(ge=0.0)
    baseline_sample_count: int = Field(ge=0)
    recent_sample_count: int = Field(ge=0)
    detected_at: datetime
