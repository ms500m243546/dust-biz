"""Model-performance API tests (Phase K)."""

from __future__ import annotations

from datetime import datetime, timedelta

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


def _override_role(role: str) -> None:
    def _u() -> User:
        return User(
            user_id="U-T", username=f"t-{role}", role=role, password_hash="x"
        )

    app.dependency_overrides[current_user] = _u


def _seed(session: Session, issued_at: datetime) -> None:
    pred = DustPrediction(
        prediction_id="PRED-MP-001",
        issued_at=issued_at,
        target_kind="zone",
        target_id="Z-1",
        forecast_horizon="30m",
        predicted_pm10=120.0,
        predicted_pm25=42.0,
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
    )
    rec = Recommendation(
        recommendation_id="REC-MP-001",
        issued_at=issued_at + timedelta(minutes=1),
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
        linked_prediction_ids=["PRED-MP-001"],
        linked_attribution_id=None,
        automation_level="L1",
    )
    appr = RecommendationApproval(
        approval_id="APR-MP-001",
        recommendation_id="REC-MP-001",
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
        recommendation_id="REC-MP-001",
        prediction_id=None,
        actual_pm10_peak=130.0,
        actual_pm25_peak=None,
        breach_occurred=True,
        production_loss_tonnes_actual=400.0,
        intervention_effectiveness="partial",
        model_error="ok",
        recorded_at=issued_at + timedelta(minutes=30),
        recorded_by="alice",
    )
    session.add_all([pred, rec, appr, outcome])
    session.commit()


def _good_protocol_body() -> dict[str, object]:
    """A minimally valid M.1 EvaluationProtocol for test bodies."""
    return {
        "split_strategy": "walk_forward",
        "train_window_from": "2025-01-01T00:00:00",
        "train_window_to": "2025-06-01T00:00:00",
        "validation_window_from": "2025-06-08T00:00:00",
        "validation_window_to": "2025-09-01T00:00:00",
        "test_window_from": "2025-09-08T00:00:00",
        "test_window_to": "2026-03-01T00:00:00",
        "embargo_days": 7,
        "sealed_test_used": False,
        "baselines_named": [
            "persistence",
            "seasonal_naive",
            "regulatory_threshold_classifier",
        ],
        "sinca_validated_legal_only_after_days": 7,
        "realtime_proxy_required": True,
        "protocol_version": "M.4",
        "intended_for_realtime": True,
        "max_ece": 1.0,
        "notes": "test fixture: max_ece=1.0 disables M.4.1 gate",
    }


def test_evaluate_persists_metric_row(
    client: TestClient, api_session: Session
) -> None:
    issued = datetime(2026, 5, 1, 10, 0)
    _seed(api_session, issued_at=issued)
    body = {
        "model_version": "df-0.1.0",
        "model_kind": "dust_forecast",
        "window_from": issued.isoformat(),
        "window_to": (issued + timedelta(hours=1)).isoformat(),
        "outcome_observation_minutes": 60,
        "protocol": _good_protocol_body(),
    }
    r = client.post("/api/v1/model-performance/evaluate", json=body)
    assert r.status_code == 201, r.text
    row = r.json()
    assert row["model_version"] == "df-0.1.0"
    assert row["sample_count"] == 1
    assert row["metric_payload"]["observed_count"] == 1
    # 0.85 >= 0.5 + breach_actual=True -> TP
    assert row["metric_payload"]["breach_precision"] == 1.0
    # M.1+: protocol block persisted on the metric row (M.4 after the
    # calibration / covariate fields landed in M.4.1).
    assert row["metric_payload"]["protocol"]["protocol_version"] == "M.4"
    assert row["metric_payload"]["protocol"]["split_strategy"] == "walk_forward"


def test_evaluate_requires_role(client: TestClient) -> None:
    _override_role("shift_supervisor")
    body = {
        "model_version": "df-0.1.0",
        "model_kind": "dust_forecast",
        "window_from": "2026-05-01T10:00:00",
        "window_to": "2026-05-01T11:00:00",
        "protocol": _good_protocol_body(),
    }
    r = client.post("/api/v1/model-performance/evaluate", json=body)
    assert r.status_code == 403


def test_evaluate_without_protocol_returns_422(client: TestClient) -> None:
    body = {
        "model_version": "df-0.1.0",
        "model_kind": "dust_forecast",
        "window_from": "2026-05-01T10:00:00",
        "window_to": "2026-05-01T11:00:00",
        # `protocol` field missing -> Pydantic 422
    }
    r = client.post("/api/v1/model-performance/evaluate", json=body)
    assert r.status_code == 422


def test_evaluate_with_random_kfold_protocol_returns_422(
    client: TestClient, api_session: Session
) -> None:
    issued = datetime(2026, 5, 1, 10, 0)
    _seed(api_session, issued_at=issued)
    bad_protocol = _good_protocol_body()
    bad_protocol["split_strategy"] = "random_kfold"  # forbidden
    body = {
        "model_version": "df-0.1.0",
        "model_kind": "dust_forecast",
        "window_from": issued.isoformat(),
        "window_to": (issued + timedelta(hours=1)).isoformat(),
        "outcome_observation_minutes": 60,
        "protocol": bad_protocol,
    }
    r = client.post("/api/v1/model-performance/evaluate", json=body)
    # Pydantic Literal mismatch surfaces as 422 before reaching the handler.
    assert r.status_code == 422


def test_evaluate_with_missing_baseline_returns_422(
    client: TestClient, api_session: Session
) -> None:
    issued = datetime(2026, 5, 1, 10, 0)
    _seed(api_session, issued_at=issued)
    bad_protocol = _good_protocol_body()
    bad_protocol["baselines_named"] = ["persistence"]  # missing two
    body = {
        "model_version": "df-0.1.0",
        "model_kind": "dust_forecast",
        "window_from": issued.isoformat(),
        "window_to": (issued + timedelta(hours=1)).isoformat(),
        "outcome_observation_minutes": 60,
        "protocol": bad_protocol,
    }
    r = client.post("/api/v1/model-performance/evaluate", json=body)
    # Pydantic accepts the list, but ProtocolViolation surfaces as 422
    # at the handler.
    assert r.status_code == 422
    assert "missing required baseline" in r.json()["detail"]


def test_list_recent_returns_persisted_rows(
    client: TestClient, api_session: Session
) -> None:
    issued = datetime(2026, 5, 1, 10, 0)
    _seed(api_session, issued_at=issued)
    body = {
        "model_version": "df-0.1.0",
        "model_kind": "dust_forecast",
        "window_from": issued.isoformat(),
        "window_to": (issued + timedelta(hours=1)).isoformat(),
        "outcome_observation_minutes": 60,
        "protocol": _good_protocol_body(),
    }
    client.post("/api/v1/model-performance/evaluate", json=body)
    r = client.get("/api/v1/model-performance?since_minutes=43200")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 1
    assert any(row["model_version"] == "df-0.1.0" for row in rows)


def test_list_unauthenticated_blocked(unauthed_client: TestClient) -> None:
    r = unauthed_client.get("/api/v1/model-performance")
    assert r.status_code == 401
