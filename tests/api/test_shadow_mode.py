"""Shadow-mode API tests (Phase K.4)."""

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


def test_evaluate_requires_role(client: TestClient) -> None:
    _override_role("shift_supervisor")
    body = {
        "candidate_version": "cand-v2",
        "production_version": "prod-v1",
        "window_from": "2026-05-01T10:00:00",
        "window_to": "2026-05-01T11:00:00",
    }
    r = client.post("/api/v1/shadow-mode/evaluate", json=body)
    assert r.status_code == 403


def test_evaluate_returns_hold_with_no_data(client: TestClient) -> None:
    body = {
        "candidate_version": "cand-v2",
        "production_version": "prod-v1",
        "window_from": "2026-05-01T10:00:00",
        "window_to": "2026-05-01T11:00:00",
    }
    r = client.post("/api/v1/shadow-mode/evaluate", json=body)
    assert r.status_code == 200, r.text
    body_out = r.json()
    assert body_out["recommendation"] == "hold"
    assert body_out["candidate_version"] == "cand-v2"


def test_evaluate_unauthenticated_blocked(unauthed_client: TestClient) -> None:
    r = unauthed_client.post(
        "/api/v1/shadow-mode/evaluate",
        json={
            "candidate_version": "x",
            "production_version": "y",
            "window_from": "2026-05-01T10:00:00",
            "window_to": "2026-05-01T11:00:00",
        },
    )
    assert r.status_code == 401
