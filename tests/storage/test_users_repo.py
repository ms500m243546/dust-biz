"""User repository tests (Phase I)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.storage.models import User
from app.storage.repositories.users import UserRepository


def test_add_and_lookup_by_username(session: Session) -> None:
    repo = UserRepository(session)
    repo.add(
        User(
            user_id="U-1",
            username="alice",
            role="shift_supervisor",
            password_hash="x",
        )
    )
    session.commit()

    found = repo.get_by_username("alice")
    assert found is not None
    assert found.user_id == "U-1"
    assert repo.get("U-1") is not None
    assert repo.get_by_username("unknown") is None
