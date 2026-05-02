"""Seed a single user for dashboard sign-in.

Usage (PowerShell, venv active):
    python scripts/seed_user.py admin admin123 admin
    python scripts/seed_user.py supervisor pass shift_supervisor

Args: <username> <password> <role>
Roles: shift_supervisor, environmental_manager, operations_manager,
       dispatcher, executive, admin
"""

from __future__ import annotations

import sys
import uuid

from app.domain.auth import hash_password
from app.storage.database import get_engine, session_scope
from app.storage.models import User
from app.storage.models.base import Base
from app.storage.repositories.users import UserRepository


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    username, password, role = sys.argv[1], sys.argv[2], sys.argv[3]

    Base.metadata.create_all(get_engine())

    with session_scope() as session:
        repo = UserRepository(session)
        if repo.get_by_username(username) is not None:
            print(f"user {username!r} already exists")
            return 1
        user = User(
            user_id=str(uuid.uuid4()),
            username=username,
            role=role,
            password_hash=hash_password(password),
        )
        repo.add(user)
        print(f"created user: username={user.username} role={user.role} id={user.user_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
