"""S15 report schema tests (Phase K.2)."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.reports import (
    ComplianceReport,
    ComplianceReportEntry,
    ModelPerformanceReport,
    ModelPerformanceReportEntry,
    ROIReport,
)


def test_model_performance_report_round_trip() -> None:
    rep = ModelPerformanceReport(
        generated_at=datetime(2026, 5, 1, 12, 0),
        window_from=datetime(2026, 5, 1, 0, 0),
        window_to=datetime(2026, 5, 1, 12, 0),
        entries=[
            ModelPerformanceReportEntry(
                model_version="df-0.1.0",
                model_kind="dust_forecast",
                sample_count=10,
                observed_count=8,
                unobserved_count=2,
            )
        ],
    )
    assert rep.entries[0].model_version == "df-0.1.0"


def test_roi_report_required_fields() -> None:
    rep = ROIReport(
        generated_at=datetime(2026, 5, 1, 12, 0),
        window_from=datetime(2026, 5, 1, 0, 0),
        window_to=datetime(2026, 5, 1, 12, 0),
        tonne_value_usd=80.0,
        avoided_shutdowns_count=0,
        avoided_shutdown_value_usd=0.0,
        intervention_cost_usd=0.0,
        realised_production_loss_tonnes=0.0,
        realised_production_loss_usd=0.0,
        net_value_usd=0.0,
        sample_count=0,
    )
    assert rep.site_id is None


def test_compliance_entry_thresholds_required() -> None:
    with pytest.raises(ValidationError):
        ComplianceReportEntry(  # type: ignore[call-arg]
            sensor_id="cs1",
            pm10_breach_count=0,
            pm25_breach_count=0,
            pm10_warning_count=0,
            pm25_warning_count=0,
        )


def test_compliance_report_default_empty_stations() -> None:
    rep = ComplianceReport(
        generated_at=datetime(2026, 5, 1, 12, 0),
        window_from=datetime(2026, 5, 1, 0, 0),
        window_to=datetime(2026, 5, 1, 12, 0),
    )
    assert rep.stations == []
    assert rep.total_dust_events == 0
