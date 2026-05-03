"""Shadow-mode API tests (Phase K.4; M.1 protocol gate)."""

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


def _good_protocol_body() -> dict[str, object]:
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
        "protocol_version": "M.1",
        "intended_for_realtime": True,
        "notes": "test",
    }


def test_evaluate_requires_role(client: TestClient) -> None:
    _override_role("shift_supervisor")
    body = {
        "candidate_version": "cand-v2",
        "production_version": "prod-v1",
        "window_from": "2026-05-01T10:00:00",
        "window_to": "2026-05-01T11:00:00",
        "protocol": _good_protocol_body(),
    }
    r = client.post("/api/v1/shadow-mode/evaluate", json=body)
    assert r.status_code == 403


def test_evaluate_returns_hold_with_no_data(client: TestClient) -> None:
    body = {
        "candidate_version": "cand-v2",
        "production_version": "prod-v1",
        "window_from": "2026-05-01T10:00:00",
        "window_to": "2026-05-01T11:00:00",
        "protocol": _good_protocol_body(),
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
            "protocol": _good_protocol_body(),
        },
    )
    assert r.status_code == 401


def test_evaluate_without_protocol_returns_422(client: TestClient) -> None:
    body = {
        "candidate_version": "cand-v2",
        "production_version": "prod-v1",
        "window_from": "2026-05-01T10:00:00",
        "window_to": "2026-05-01T11:00:00",
    }
    r = client.post("/api/v1/shadow-mode/evaluate", json=body)
    assert r.status_code == 422
