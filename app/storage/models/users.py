"""User and Role ORMs (Phase I).

Per docs/data-contracts.md `users`, `roles`. MVP shape only: enough to
authenticate and authorize the S13 approve / reject / override flow.
Full IdP / SSO integration is out of scope; rotation, refresh tokens,
and password policies land in the K hardening pass.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.storage.models.base import Base

# Roles defined in docs/data-contracts.md "users, roles". Stored as a
# string column on `User` to keep MVP simple - the data contract notes
# multi-role per user is post-MVP.
ROLES = (
    "shift_supervisor",
    "environmental_manager",
    "operations_manager",
    "dispatcher",
    "executive",
    "admin",
)


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
