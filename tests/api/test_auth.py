"""Auth API tests (Phase I)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain.auth import hash_password
from app.storage.models import User


def _seed_user(
    session: Session,
    *,
    user_id: str = "U-1",
    username: str = "alice",
    role: str = "shift_supervisor",
    password: str = "secret",
) -> None:
    session.add(
        User(
            user_id=user_id,
            username=username,
            role=role,
            password_hash=hash_password(password),
        )
    )
    session.commit()


def test_login_success_returns_bearer_token(
    client: TestClient, api_session: Session
) -> None:
    _seed_user(api_session)
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "secret"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "shift_supervisor"
    assert body["access_token"]


def test_login_unknown_user_401(client: TestClient) -> None:
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "nobody", "password": "x"},
    )
    assert r.status_code == 401


def test_login_wrong_password_401(
    client: TestClient, api_session: Session
) -> None:
    _seed_user(api_session)
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "WRONG"},
    )
    assert r.status_code == 401


def test_me_requires_token(client: TestClient) -> None:
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_me_returns_user_when_authenticated(
    client: TestClient, api_session: Session
) -> None:
    _seed_user(api_session)
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "secret"},
    )
    token = login.json()["access_token"]
    r = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["username"] == "alice"


def test_me_rejects_garbage_token(client: TestClient) -> None:
    r = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not.a.token"},
    )
    assert r.status_code == 401
