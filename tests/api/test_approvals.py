"""Approval API tests (Phase I, S13)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies.auth import current_user
from app.api.main import app
from app.storage.models import Recommendation, User


def _recent_issued_at() -> datetime:
    return (datetime.now(UTC) - timedelta(minutes=1)).replace(
        microsecond=0, tzinfo=None
    )


def _seed_rec(
    session: Session,
    *,
    rec_id: str = "REC-20260501-00001",
    risk_class: str = "medium",
) -> None:
    actions: list[dict[str, Any]] = [
        {
            "rank": 1,
            "intervention_id": "reduce_speed",
            "action": "Reduce speed",
            "breach_probability_after": 0.2,
            "production_loss": "low",
            "estimated_tonnes_delayed": 100.0,
            "confidence": 0.8,
            "reason": "ok",
            "requires_human_approval": True,
            "risk_class": risk_class,
            "simulation_id": "SIM-1",
        },
    ]
    session.add(
        Recommendation(
            recommendation_id=rec_id,
            issued_at=_recent_issued_at(),
            target_zone_id="Z1",
            risk_event="r",
            current_breach_probability=0.7,
            target_probability=0.25,
            recommended_actions=actions,
            requires_human_review=False,
            compliance_priority_triggered=False,
            confidence=0.8,
            reason="r",
            model_version="optimization_weighted_v0.1.0",
            feature_pipeline_version="f",
            input_data_quality_score=0.9,
            data_quality_warnings=[],
            linked_prediction_ids=[],
            linked_attribution_id=None,
            automation_level="L1",
            top_production_impact="low",
        )
    )
    session.commit()


def _override_role(role: str) -> None:
    def _u() -> User:
        return User(
            user_id="U-T",
            username=f"test-{role}",
            role=role,
            password_hash="x",
        )

    app.dependency_overrides[current_user] = _u


def test_approve_endpoint(client: TestClient, api_session: Session) -> None:
    _seed_rec(api_session)
    _override_role("shift_supervisor")
    r = client.post(
        "/api/v1/recommendations/REC-20260501-00001/approve",
        json={"chosen_action_rank": 1, "human_reason": "ok"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["approval_status"] == "approved"


def test_reject_endpoint(client: TestClient, api_session: Session) -> None:
    _seed_rec(api_session)
    _override_role("shift_supervisor")
    r = client.post(
        "/api/v1/recommendations/REC-20260501-00001/reject",
        json={"human_reason": "won't help"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["approval_status"] == "rejected"


def test_override_endpoint_requires_elevated_role(
    client: TestClient, api_session: Session
) -> None:
    _seed_rec(api_session)
    _override_role("shift_supervisor")
    r = client.post(
        "/api/v1/recommendations/REC-20260501-00001/override",
        json={
            "override_action": "hold trucks 5min",
            "human_reason": "plume already visible",
        },
    )
    assert r.status_code == 403


def test_override_endpoint_environmental_manager(
    client: TestClient, api_session: Session
) -> None:
    _seed_rec(api_session)
    _override_role("environmental_manager")
    r = client.post(
        "/api/v1/recommendations/REC-20260501-00001/override",
        json={
            "override_action": "hold trucks 5min",
            "human_reason": "plume already visible",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["approval_status"] == "overridden"


def test_double_decision_returns_409(
    client: TestClient, api_session: Session
) -> None:
    _seed_rec(api_session)
    _override_role("shift_supervisor")
    client.post(
        "/api/v1/recommendations/REC-20260501-00001/approve",
        json={"chosen_action_rank": 1},
    )
    r = client.post(
        "/api/v1/recommendations/REC-20260501-00001/reject",
        json={"human_reason": "x"},
    )
    assert r.status_code == 409


def test_high_risk_action_403(client: TestClient, api_session: Session) -> None:
    _seed_rec(api_session, risk_class="high")
    _override_role("shift_supervisor")
    r = client.post(
        "/api/v1/recommendations/REC-20260501-00001/approve",
        json={"chosen_action_rank": 1},
    )
    assert r.status_code == 403


def test_get_latest_decision(client: TestClient, api_session: Session) -> None:
    _seed_rec(api_session)
    _override_role("shift_supervisor")
    r = client.get("/api/v1/recommendations/REC-20260501-00001/approval")
    assert r.status_code == 200
    assert r.json() is None

    client.post(
        "/api/v1/recommendations/REC-20260501-00001/approve",
        json={"chosen_action_rank": 1},
    )
    r = client.get("/api/v1/recommendations/REC-20260501-00001/approval")
    assert r.status_code == 200
    assert r.json()["approval_status"] == "approved"


def test_list_recent_approvals(client: TestClient, api_session: Session) -> None:
    _seed_rec(api_session)
    _override_role("shift_supervisor")
    client.post(
        "/api/v1/recommendations/REC-20260501-00001/approve",
        json={"chosen_action_rank": 1},
    )
    r = client.get("/api/v1/approvals")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_sweep_expired_admin_only(client: TestClient, api_session: Session) -> None:
    _override_role("shift_supervisor")
    r = client.post("/api/v1/approvals/sweep-expired")
    assert r.status_code == 403
    _override_role("admin")
    r = client.post("/api/v1/approvals/sweep-expired")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_unauthenticated_approve_blocked(
    unauthed_client: TestClient, api_session: Session
) -> None:
    _seed_rec(api_session)
    r = unauthed_client.post(
        "/api/v1/recommendations/REC-20260501-00001/approve",
        json={"chosen_action_rank": 1},
    )
    assert r.status_code == 401


def test_unauthenticated_post_recommendation_blocked(
    unauthed_client: TestClient,
) -> None:
    r = unauthed_client.post(
        "/api/v1/recommendations", json={"target_zone_id": "Z1"}
    )
    assert r.status_code == 401


def test_unauthenticated_post_sensor_reading_blocked(
    unauthed_client: TestClient,
) -> None:
    r = unauthed_client.post(
        "/api/v1/sensor-readings",
        json={
            "sensor_id": "S1",
            "timestamp": "2026-05-01T12:00:00Z",
            "raw_value": {"pm10": 120},
        },
    )
    assert r.status_code == 401
