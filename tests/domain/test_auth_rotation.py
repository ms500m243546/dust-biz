"""KeyRing rotation tests (Phase K.3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.auth import (
    TOKEN_TTL_MINUTES,
    InvalidTokenError,
    KeyRing,
    issue_token,
    verify_token,
)


def test_issue_then_verify_round_trip() -> None:
    ring = KeyRing()
    ring.add("k1", "secret-aaa", now=datetime(2026, 5, 2, 10, 0, tzinfo=UTC))
    token, _ = issue_token(
        user_id="u",
        username="alice",
        role="admin",
        now=datetime(2026, 5, 2, 10, 0, tzinfo=UTC),
        keyring=ring,
    )
    claims = verify_token(
        token, now=datetime(2026, 5, 2, 10, 5, tzinfo=UTC), keyring=ring
    )
    assert claims.kid == "k1"
    assert claims.role == "admin"


def test_token_issued_with_old_key_still_verifies_after_rotation() -> None:
    ring = KeyRing()
    ring.add("k1", "secret-aaa", now=datetime(2026, 5, 2, 10, 0, tzinfo=UTC))
    token, _ = issue_token(
        user_id="u",
        username="alice",
        role="admin",
        now=datetime(2026, 5, 2, 10, 0, tzinfo=UTC),
        keyring=ring,
    )

    ring.rotate("k2", "secret-bbb", now=datetime(2026, 5, 2, 11, 0, tzinfo=UTC))
    assert ring.active_kid == "k2"

    claims = verify_token(
        token, now=datetime(2026, 5, 2, 11, 30, tzinfo=UTC), keyring=ring
    )
    assert claims.kid == "k1"


def test_new_token_after_rotation_uses_new_key() -> None:
    ring = KeyRing()
    ring.add("k1", "secret-aaa", now=datetime(2026, 5, 2, 10, 0, tzinfo=UTC))
    ring.rotate("k2", "secret-bbb", now=datetime(2026, 5, 2, 11, 0, tzinfo=UTC))

    token, _ = issue_token(
        user_id="u",
        username="alice",
        role="admin",
        now=datetime(2026, 5, 2, 11, 5, tzinfo=UTC),
        keyring=ring,
    )
    claims = verify_token(
        token, now=datetime(2026, 5, 2, 11, 30, tzinfo=UTC), keyring=ring
    )
    assert claims.kid == "k2"


def test_prune_drops_retired_keys_past_grace_window() -> None:
    ring = KeyRing()
    ring.add("k1", "secret-aaa", now=datetime(2026, 5, 2, 10, 0, tzinfo=UTC))
    ring.rotate("k2", "secret-bbb", now=datetime(2026, 5, 2, 11, 0, tzinfo=UTC))

    # Right at the grace boundary - k1 still kept.
    just_inside = datetime(2026, 5, 2, 11, 0, tzinfo=UTC) + timedelta(
        minutes=TOKEN_TTL_MINUTES - 1
    )
    dropped = ring.prune(now=just_inside)
    assert dropped == 0
    assert ring.get("k1") is not None

    # Past the grace boundary - k1 gone.
    past = datetime(2026, 5, 2, 11, 0, tzinfo=UTC) + timedelta(
        minutes=TOKEN_TTL_MINUTES + 1
    )
    dropped = ring.prune(now=past)
    assert dropped == 1
    assert ring.get("k1") is None
    assert ring.get("k2") is not None


def test_token_with_unknown_kid_rejected() -> None:
    ring = KeyRing()
    ring.add("k1", "secret-aaa")
    token, _ = issue_token(
        user_id="u", username="a", role="admin", keyring=ring
    )

    other_ring = KeyRing()
    other_ring.add("k9", "different")
    with pytest.raises(InvalidTokenError):
        verify_token(token, keyring=other_ring)


def test_metadata_does_not_leak_secret() -> None:
    ring = KeyRing()
    ring.add("k1", "super-secret-do-not-leak")
    meta = ring.metadata()
    serialised = str(meta)
    assert "super-secret-do-not-leak" not in serialised
    assert meta[0]["active"] is True
    assert meta[0]["alg"] == "HS256"
