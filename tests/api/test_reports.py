"""S15 reports API tests (Phase K.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.storage.models import (
    ActionOutcome,
    DustPrediction,
    Mine,
    ModelPerformanceMetric,
    Recommendation,
    RecommendationApproval,
    Sensor,
    SensorReading,
    SiteConfiguration,
)


def _seed_min(session: Session) -> None:
    session.add(Mine(mine_id="m1", name="Demo"))
    session.add(Sensor(sensor_id="cs1", mine_id="m1", sensor_type="pm10"))
    session.commit()


def test_model_performance_report_returns_latest_per_model(
    client: TestClient, api_session: Session
) -> None:
    _seed_min(api_session)
    api_session.add(
        ModelPerformanceMetric(
            model_version="df-0.1.0",
            model_kind="dust_forecast",
            evaluated_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1),
            window_from=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=7),
            window_to=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1),
            sample_count=20,
            metric_payload={
                "sample_count": 20,
                "observed_count": 18,
                "unobserved_count": 2,
                "mae_pm10": 11.0,
            },
        )
    )
    api_session.commit()
    r = client.get("/api/v1/reports/model-performance")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["entries"]) == 1
    assert body["entries"][0]["mae_pm10"] == 11.0


def test_roi_report_uses_site_cost_curves_when_site_provided(
    client: TestClient, api_session: Session
) -> None:
    _seed_min(api_session)
    api_session.add(
        SiteConfiguration(
            site_id="demo-site",
            mine_id="m1",
            automation_level="L1",
            pm10_thresholds={"warning": 100.0, "breach": 150.0},
            pm25_thresholds={"warning": 25.0, "breach": 35.0},
            extreme_breach_threshold=0.85,
            low_confidence_threshold=0.5,
            approval_expiry_minutes=15,
            optimization_weights={
                "w_breach": 1.0,
                "w_production": 1.0,
                "w_disruption": 0.5,
                "w_low_confidence": 0.5,
                "w_compliance": 1.0,
            },
            intervention_constraints={},
            cost_curves={
                "tonne_value_usd": 200.0,
                "intervention_unit_costs_usd": {},
            },
            updated_by="t",
        )
    )
    api_session.commit()
    r = client.get("/api/v1/reports/roi?site_id=demo-site")
    assert r.status_code == 200, r.text
    assert r.json()["tonne_value_usd"] == 200.0


def test_roi_report_uses_defaults_without_site(
    client: TestClient, api_session: Session
) -> None:
    _seed_min(api_session)
    r = client.get("/api/v1/reports/roi")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tonne_value_usd"] > 0  # falls back to schema default
    assert body["sample_count"] == 0


def test_compliance_report_counts_breaches(
    client: TestClient, api_session: Session
) -> None:
    _seed_min(api_session)
    now = datetime.now(UTC).replace(tzinfo=None)
    for i, v in enumerate([60, 110, 160, 170, 90]):
        api_session.add(
            SensorReading(
                sensor_id="cs1",
                timestamp=now - timedelta(minutes=10 - i),
                raw_value={"pm10_ugm3": v, "pm25_ugm3": v / 4},
            )
        )
    api_session.commit()
    r = client.get("/api/v1/reports/compliance?mine_id=m1")
    assert r.status_code == 200, r.text
    stations = r.json()["stations"]
    assert len(stations) == 1
    assert stations[0]["pm10_breach_count"] == 2


def test_reports_require_auth(unauthed_client: TestClient) -> None:
    for path in (
        "/api/v1/reports/model-performance",
        "/api/v1/reports/roi",
        "/api/v1/reports/compliance",
    ):
        r = unauthed_client.get(path)
        assert r.status_code == 401, path


def test_roi_report_with_observed_record(
    client: TestClient, api_session: Session
) -> None:
    _seed_min(api_session)
    issued = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=30)
    api_session.add_all(
        [
            DustPrediction(
                prediction_id="PRED-R-001",
                issued_at=issued,
                target_kind="zone",
                target_id="Z-1",
                forecast_horizon="30m",
                predicted_pm10=160.0,
                predicted_pm25=40.0,
                breach_probability=0.85,
                confidence=0.6,
                main_risk_window="30m",
                main_uncertainty="x",
                model_version="df-0.1.0",
                feature_pipeline_version="fp-0.1",
                input_data_quality_score=0.9,
                data_quality_warnings=[],
                source="orchestrator",
                input_record_ids=[],
            ),
            Recommendation(
                recommendation_id="REC-R-001",
                issued_at=issued + timedelta(minutes=1),
                target_zone_id="Z-1",
                risk_event="dust",
                current_breach_probability=0.85,
                target_probability=0.3,
                recommended_actions=[],
                requires_human_review=True,
                compliance_priority_triggered=False,
                confidence=0.6,
                reason="x",
                model_version="oa-0.1.0",
                feature_pipeline_version="fp-0.1",
                input_data_quality_score=0.9,
                data_quality_warnings=[],
                linked_prediction_ids=["PRED-R-001"],
                linked_attribution_id=None,
                automation_level="L1",
            ),
            RecommendationApproval(
                approval_id="APR-R-001",
                recommendation_id="REC-R-001",
                approved_by="alice",
                approver_role="environmental_manager",
                decided_at=issued + timedelta(minutes=5),
                approval_status="approved",
                chosen_action_rank=1,
                override_action=None,
                human_reason=None,
                automation_level_at_decision="L1",
            ),
            ActionOutcome(
                recommendation_id="REC-R-001",
                prediction_id=None,
                actual_pm10_peak=120.0,
                actual_pm25_peak=None,
                breach_occurred=False,
                production_loss_tonnes_actual=50.0,
                intervention_effectiveness="successful",
                model_error="ok",
                recorded_at=issued + timedelta(minutes=20),
                recorded_by="alice",
            ),
        ]
    )
    api_session.commit()
    r = client.get("/api/v1/reports/roi?observation_window_minutes=15")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["avoided_shutdowns_count"] == 1
    assert body["realised_production_loss_tonnes"] == 50.0
