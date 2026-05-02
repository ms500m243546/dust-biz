"""S15 reports domain tests (Phase K.2)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.domain.reports import (
    _bucket_readings,
    build_compliance_report,
    build_model_performance_report,
    build_roi_report,
)
from app.schemas.model_performance import TrainingRecordSchema
from app.storage.models import DustEvent, ModelPerformanceMetric, SensorReading


def _metric(
    *,
    version: str,
    kind: str,
    evaluated_at: datetime,
    payload: dict[str, Any],
) -> ModelPerformanceMetric:
    return ModelPerformanceMetric(
        model_version=version,
        model_kind=kind,
        evaluated_at=evaluated_at,
        window_from=evaluated_at - timedelta(hours=6),
        window_to=evaluated_at,
        sample_count=int(payload.get("sample_count", 0) or 0),
        metric_payload=payload,
    )


def test_model_performance_report_keeps_latest_per_model() -> None:
    metrics = [
        _metric(
            version="df-0.1.0",
            kind="dust_forecast",
            evaluated_at=datetime(2026, 5, 1, 10, 0),
            payload={"sample_count": 10, "mae_pm10": 12.0},
        ),
        _metric(
            version="df-0.1.0",
            kind="dust_forecast",
            evaluated_at=datetime(2026, 5, 1, 12, 0),
            payload={"sample_count": 20, "mae_pm10": 8.0},
        ),
        _metric(
            version="oa-0.1.0",
            kind="optimization",
            evaluated_at=datetime(2026, 5, 1, 11, 0),
            payload={"sample_count": 5, "mae_pm10": None},
        ),
    ]
    rep = build_model_performance_report(
        metrics=metrics,
        generated_at=datetime(2026, 5, 1, 13, 0),
        window_from=datetime(2026, 5, 1, 0, 0),
        window_to=datetime(2026, 5, 1, 13, 0),
    )
    assert len(rep.entries) == 2
    df = next(e for e in rep.entries if e.model_version == "df-0.1.0")
    assert df.mae_pm10 == 8.0
    assert df.sample_count == 20


def _record(
    *,
    breach_prob: float,
    breach_actual: bool | None,
    human_action: str = "approved",
    outcome_status: str = "observed",
    production_loss: float | None = 0.0,
    chosen_rank: int | None = 1,
    override_action: str | None = None,
) -> TrainingRecordSchema:
    return TrainingRecordSchema(
        prediction_id="PRED-X",
        issued_at=datetime(2026, 5, 1, 10, 0),
        target_kind="zone",
        target_id="Z-1",
        forecast_horizon="30m",
        predicted_pm10=120.0,
        predicted_pm25=42.0,
        predicted_breach_probability=breach_prob,
        confidence=0.6,
        model_version="df-0.1.0",
        human_action=human_action,  # type: ignore[arg-type]
        chosen_action_rank=chosen_rank,
        override_action=override_action,
        breach_occurred=breach_actual,
        actual_pm10_peak=110.0,
        intervention_effectiveness="successful" if breach_actual is False else "partial",
        production_loss_tonnes_actual=production_loss,
        outcome_status=outcome_status,  # type: ignore[arg-type]
    )


def test_roi_report_counts_avoided_only_for_approved_or_overridden() -> None:
    records = [
        _record(breach_prob=0.8, breach_actual=False, human_action="approved"),
        _record(breach_prob=0.8, breach_actual=False, human_action="rejected"),
        _record(
            breach_prob=0.8,
            breach_actual=False,
            human_action="overridden",
            override_action="water_road",
        ),
    ]
    cost_curves = {
        "tonne_value_usd": 100.0,
        "intervention_unit_costs_usd": {"default": 50.0, "water_road": 75.0},
    }
    rep = build_roi_report(
        training_records=records,
        cost_curves=cost_curves,
        generated_at=datetime(2026, 5, 1, 14, 0),
        window_from=datetime(2026, 5, 1, 10, 0),
        window_to=datetime(2026, 5, 1, 14, 0),
    )
    assert rep.avoided_shutdowns_count == 2
    assert rep.tonne_value_usd == 100.0
    # 1 approved + 1 overridden -> 50 + 75 = 125 USD
    assert rep.intervention_cost_usd == 125.0
    assert rep.avoided_shutdown_value_usd == 2 * 100.0 * 50.0


def test_roi_report_falls_back_to_default_cost_curves_when_none() -> None:
    rep = build_roi_report(
        training_records=[],
        cost_curves=None,
        generated_at=datetime(2026, 5, 1, 14, 0),
        window_from=datetime(2026, 5, 1, 10, 0),
        window_to=datetime(2026, 5, 1, 14, 0),
    )
    assert rep.tonne_value_usd > 0  # default 80
    assert rep.sample_count == 0
    assert rep.avoided_shutdowns_count == 0


def test_compliance_report_counts_breaches_and_warnings() -> None:
    readings = [
        SensorReading(
            sensor_id="cs1",
            timestamp=datetime(2026, 5, 1, 10, i),
            raw_value={"pm10_ugm3": v, "pm25_ugm3": v / 4},
        )
        for i, v in enumerate([60, 110, 160, 170, 90])
    ]
    rep = build_compliance_report(
        sensor_ids=["cs1"],
        readings_by_sensor=_bucket_readings(readings),
        pm10_thresholds={"warning": 100.0, "breach": 150.0},
        pm25_thresholds={"warning": 25.0, "breach": 35.0},
        dust_events=[],
        generated_at=datetime(2026, 5, 1, 11, 0),
        window_from=datetime(2026, 5, 1, 9, 0),
        window_to=datetime(2026, 5, 1, 11, 0),
    )
    assert len(rep.stations) == 1
    e = rep.stations[0]
    assert e.pm10_breach_count == 2  # 160 + 170
    assert e.pm10_warning_count == 1  # 110
    assert e.peak_pm10 == 170
    assert e.pm10_breach_threshold == 150.0


def test_compliance_report_honors_dust_events_total() -> None:
    rep = build_compliance_report(
        sensor_ids=[],
        readings_by_sensor={},
        pm10_thresholds={"warning": 100.0, "breach": 150.0},
        pm25_thresholds={"warning": 25.0, "breach": 35.0},
        dust_events=[
            DustEvent(
                event_id="EVT-1",
                detected_at=datetime(2026, 5, 1, 10, 0),
                affected_station="cs1",
                peak_pm10=160.0,
                peak_pm25=40.0,
                breach_occurred=True,
                event_source="manual_entry",
            ),
        ],
        generated_at=datetime(2026, 5, 1, 11, 0),
        window_from=datetime(2026, 5, 1, 9, 0),
        window_to=datetime(2026, 5, 1, 11, 0),
    )
    assert rep.total_dust_events == 1
    assert rep.total_breach_events == 1
