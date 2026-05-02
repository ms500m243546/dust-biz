"""Training-data API tests (Phase K)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies.auth import current_user
from app.api.main import app
from app.storage.models import (
    ActionOutcome,
    DustPrediction,
    Recommendation,
    RecommendationApproval,
    User,
)


def _seed(session: Session, *, issued_at: datetime) -> None:
    pred = DustPrediction(
        prediction_id="PRED-T-001",
        issued_at=issued_at,
        target_kind="zone",
        target_id="Z-1",
        forecast_horizon="30m",
        predicted_pm10=120.0,
        predicted_pm25=42.0,
        breach_probability=0.74,
        confidence=0.6,
        main_risk_window="30m",
        main_uncertainty="wind variability",
        model_version="df-0.1.0",
        feature_pipeline_version="fp-0.1",
        input_data_quality_score=0.9,
        data_quality_warnings=[],
        source="orchestrator",
        input_record_ids=[],
    )
    rec = Recommendation(
        recommendation_id="REC-T-001",
        issued_at=issued_at + timedelta(minutes=1),
        target_zone_id="Z-1",
        risk_event="dust",
        current_breach_probability=0.74,
        target_probability=0.3,
        recommended_actions=[],
        requires_human_review=True,
        compliance_priority_triggered=False,
        confidence=0.6,
        reason="wind aligned",
        model_version="oa-0.1.0",
        feature_pipeline_version="fp-0.1",
        input_data_quality_score=0.9,
        data_quality_warnings=[],
        linked_prediction_ids=["PRED-T-001"],
        linked_attribution_id=None,
        automation_level="L1",
    )
    appr = RecommendationApproval(
        approval_id="APR-T-001",
        recommendation_id="REC-T-001",
        approved_by="alice",
        approver_role="environmental_manager",
        decided_at=issued_at + timedelta(minutes=5),
        approval_status="approved",
        chosen_action_rank=1,
        override_action=None,
        human_reason=None,
        automation_level_at_decision="L1",
    )
    outcome = ActionOutcome(
        recommendation_id="REC-T-001",
        prediction_id=None,
        actual_pm10_peak=119.0,
        actual_pm25_peak=None,
        breach_occurred=False,
        production_loss_tonnes_actual=200.0,
        intervention_effectiveness="successful",
        model_error="overpredicted by 1%",
        recorded_at=issued_at + timedelta(minutes=30),
        recorded_by="alice",
    )
    session.add_all([pred, rec, appr, outcome])
    session.commit()


def test_training_data_returns_assembled_record(
    client: TestClient, api_session: Session
) -> None:
    _seed(api_session, issued_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=20))
    r = client.get("/api/v1/training-data")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 1
    row = body[0]
    assert row["prediction_id"] == "PRED-T-001"
    assert row["recommendation_id"] == "REC-T-001"
    assert row["outcome_status"] == "observed"
    assert row["human_action"] == "approved"


def test_training_data_filter_by_outcome_status(
    client: TestClient, api_session: Session
) -> None:
    # Old prediction past observation window, no outcome
    old = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=10)
    pred = DustPrediction(
        prediction_id="PRED-T-002",
        issued_at=old,
        target_kind="zone",
        target_id="Z-2",
        forecast_horizon="30m",
        predicted_pm10=120.0,
        predicted_pm25=42.0,
        breach_probability=0.6,
        confidence=0.6,
        main_risk_window="30m",
        main_uncertainty="x",
        model_version="df-0.1.0",
        feature_pipeline_version="fp-0.1",
        input_data_quality_score=0.9,
        data_quality_warnings=[],
        source="orchestrator",
        input_record_ids=[],
    )
    api_session.add(pred)
    api_session.commit()

    r = client.get("/api/v1/training-data?outcome_status=unobserved")
    assert r.status_code == 200, r.text
    body = r.json()
    assert all(row["outcome_status"] == "unobserved" for row in body)
    assert any(row["prediction_id"] == "PRED-T-002" for row in body)


def test_training_data_requires_auth(unauthed_client: TestClient) -> None:
    r = unauthed_client.get("/api/v1/training-data")
    assert r.status_code == 401


def _override_role(role: str) -> None:
    def _u() -> User:
        return User(
            user_id="U-T", username=f"t-{role}", role=role, password_hash="x"
        )

    app.dependency_overrides[current_user] = _u
