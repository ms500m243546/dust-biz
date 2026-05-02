"""Auth dependencies (Phase I).

`current_user` extracts the bearer token from the Authorization header,
verifies it, and resolves it to a `User` row. `require_role(*roles)`
returns a dependency that 403s when the authenticated user is not in
the allowed-role set.

MVP scope: read-side endpoints stay open (documented intentional gap,
I1-R1). Mutating endpoints attach `Depends(require_role(...))`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.domain.auth import InvalidTokenError, verify_token
from app.storage.models import User
from app.storage.repositories.users import UserRepository

_BEARER = "bearer "


def _extract_token(request: Request) -> str:
    header = request.headers.get("authorization") or request.headers.get("Authorization")
    if not header or not header.lower().startswith(_BEARER):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return header[len(_BEARER) :].strip()


def current_user(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> User:
    token = _extract_token(request)
    try:
        claims = verify_token(token)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = UserRepository(session).get(claims.user_id)
    if user is None or user.role != claims.role:
        # Role drift between token and DB invalidates the token: the
        # operator could have been demoted between issuance and use.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user no longer valid for this token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_role(*allowed_roles: str) -> Callable[[User], User]:
    """Build a dependency that 403s unless the user holds one of the roles."""
    allowed: frozenset[str] = frozenset(allowed_roles)

    def _dep(user: Annotated[User, Depends(current_user)]) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"role '{user.role}' not permitted; "
                    f"requires one of {sorted(allowed)}"
                ),
            )
        return user

    return _dep


def _roles_tuple(roles: Iterable[str]) -> tuple[str, ...]:
    # Helper kept for explicit re-use in tests / scripts.
    return tuple(roles)
