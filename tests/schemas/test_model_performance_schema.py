"""ModelPerformance + TrainingRecord schema tests (Phase K)."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.model_performance import (
    EvaluateModelRequest,
    ModelPerformanceMetricSchema,
    TrainingRecordSchema,
)


def test_training_record_minimum_fields() -> None:
    rec = TrainingRecordSchema(
        prediction_id="PRED-20260501-0001",
        issued_at=datetime(2026, 5, 1, 12, 0),
        target_kind="zone",
        target_id="Z-1",
        forecast_horizon="30m",
        predicted_pm10=120.0,
        predicted_pm25=42.0,
        predicted_breach_probability=0.74,
        confidence=0.6,
        model_version="df-0.1.0",
        human_action="approved",
        outcome_status="observed",
    )
    assert rec.outcome_id is None
    assert rec.intervention_effectiveness is None


def test_training_record_rejects_bad_outcome_status() -> None:
    with pytest.raises(ValidationError):
        TrainingRecordSchema(
            prediction_id="PRED-20260501-0001",
            issued_at=datetime(2026, 5, 1, 12, 0),
            target_kind="zone",
            target_id="Z-1",
            forecast_horizon="30m",
            predicted_pm10=120.0,
            predicted_pm25=42.0,
            predicted_breach_probability=0.74,
            confidence=0.6,
            model_version="df-0.1.0",
            human_action="approved",
            outcome_status="maybe",  # type: ignore[arg-type]
        )


def test_metric_schema_round_trip() -> None:
    schema = ModelPerformanceMetricSchema(
        metric_id=1,
        model_version="df-0.1.0",
        model_kind="dust_forecast",
        evaluated_at=datetime(2026, 5, 1, 12, 0),
        window_from=datetime(2026, 5, 1, 6, 0),
        window_to=datetime(2026, 5, 1, 12, 0),
        sample_count=10,
        metric_payload={"mae_pm10": 11.3},
    )
    dumped = schema.model_dump()
    assert dumped["metric_payload"]["mae_pm10"] == 11.3


def test_evaluate_request_rejects_bad_kind() -> None:
    with pytest.raises(ValidationError):
        EvaluateModelRequest(
            model_version="df-0.1.0",
            model_kind="banana",  # type: ignore[arg-type]
            window_from=datetime(2026, 5, 1, 6, 0),
            window_to=datetime(2026, 5, 1, 12, 0),
        )
