"""Action outcome API tests (Phase I)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.dependencies.auth import current_user
from app.api.main import app
from app.storage.models import User


def _override_role(role: str) -> None:
    def _u() -> User:
        return User(
            user_id="U-T", username=f"t-{role}", role=role, password_hash="x"
        )

    app.dependency_overrides[current_user] = _u


def test_record_outcome_requires_elevated_role(client: TestClient) -> None:
    _override_role("shift_supervisor")
    r = client.post(
        "/api/v1/action-outcomes",
        json={
            "actual_pm10_peak": 120.0,
            "breach_occurred": False,
            "intervention_effectiveness": "successful",
        },
    )
    assert r.status_code == 403


def test_record_outcome_environmental_manager(client: TestClient) -> None:
    _override_role("environmental_manager")
    r = client.post(
        "/api/v1/action-outcomes",
        json={
            "actual_pm10_peak": 120.0,
            "breach_occurred": False,
            "intervention_effectiveness": "successful",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["intervention_effectiveness"] == "successful"
    assert body["recorded_by"] == "t-environmental_manager"


def test_list_outcomes(client: TestClient) -> None:
    _override_role("operations_manager")
    client.post(
        "/api/v1/action-outcomes",
        json={
            "actual_pm10_peak": 100.0,
            "breach_occurred": False,
            "intervention_effectiveness": "partial",
        },
    )
    r = client.get("/api/v1/action-outcomes")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_unknown_recommendation_404(client: TestClient) -> None:
    _override_role("environmental_manager")
    r = client.post(
        "/api/v1/action-outcomes",
        json={
            "recommendation_id": "REC-NOTHERE",
            "actual_pm10_peak": 110.0,
            "breach_occurred": False,
            "intervention_effectiveness": "successful",
        },
    )
    assert r.status_code == 404


def test_unauthenticated_post_blocked(unauthed_client: TestClient) -> None:
    r = unauthed_client.post(
        "/api/v1/action-outcomes",
        json={
            "actual_pm10_peak": 100.0,
            "breach_occurred": False,
            "intervention_effectiveness": "partial",
        },
    )
    assert r.status_code == 401
