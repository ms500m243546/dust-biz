"""User repository (Phase I)."""

from __future__ import annotations

from sqlalchemy import select

from app.storage.models import User
from app.storage.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    def add(self, user: User) -> User:
        self.session.add(user)
        self.session.flush()
        return user

    def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        return self.session.execute(stmt).scalar_one_or_none()

    def get(self, user_id: str) -> User | None:
        return self.session.get(User, user_id)
