"""Auth domain unit tests (Phase I)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.auth import (
    InvalidTokenError,
    hash_password,
    issue_token,
    verify_password,
    verify_token,
)


def test_hash_and_verify_roundtrip() -> None:
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong password", h)


def test_hash_password_uses_random_salt() -> None:
    h1 = hash_password("same-password")
    h2 = hash_password("same-password")
    assert h1 != h2


def test_token_roundtrip() -> None:
    token, expires = issue_token(
        user_id="U-1", username="alice", role="shift_supervisor"
    )
    claims = verify_token(token)
    assert claims.user_id == "U-1"
    assert claims.username == "alice"
    assert claims.role == "shift_supervisor"
    assert claims.expires_at == expires


def test_token_rejects_tampered_payload() -> None:
    token, _ = issue_token(user_id="U-1", username="alice", role="dispatcher")
    head, payload, sig = token.split(".")
    bad = f"{head}.{payload}X.{sig}"
    with pytest.raises(InvalidTokenError):
        verify_token(bad)


def test_token_rejects_expired() -> None:
    token, _ = issue_token(
        user_id="U-1", username="alice", role="admin",
        now=datetime.now(UTC) - timedelta(hours=24),
    )
    with pytest.raises(InvalidTokenError):
        verify_token(token)


def test_verify_password_handles_garbage() -> None:
    assert not verify_password("any", "not-a-hash")
    assert not verify_password("any", "pbkdf2_sha256$nope$nope$nope")
