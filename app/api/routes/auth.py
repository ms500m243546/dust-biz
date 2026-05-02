"""Auth endpoints (Phase I; key registry in K.3).

POST /api/v1/auth/login   - exchange username + password for a bearer token.
GET  /api/v1/auth/me      - return the current authenticated user.
GET  /api/v1/auth/keys    - public key registry metadata (no secret material);
                            lets clients detect rotation.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import current_user
from app.api.deps import get_session
from app.domain.auth import get_keyring, issue_token, verify_password
from app.schemas.auth import LoginRequest, TokenResponse, UserSchema
from app.storage.models import User
from app.storage.repositories.users import UserRepository

router = APIRouter(prefix="/auth", tags=["auth"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, session: SessionDep) -> TokenResponse:
    user = UserRepository(session).get_by_username(payload.username)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid username or password",
        )
    token, expires_at = issue_token(
        user_id=user.user_id, username=user.username, role=user.role
    )
    return TokenResponse(
        access_token=token,
        expires_at=expires_at,
        role=user.role,  # type: ignore[arg-type]
    )


@router.get("/me", response_model=UserSchema)
def me(user: Annotated[User, Depends(current_user)]) -> UserSchema:
    return UserSchema.model_validate(user)


@router.get("/keys")
def keys() -> dict[str, Any]:
    """Public key registry metadata (no secret material).

    Open by design — clients (including the dashboard) read this to
    detect rotation events; auditors confirm the active kid matches
    the kid embedded in recent tokens. Never returns the HMAC secret.
    """
    ring = get_keyring()
    return {"active_kid": ring.active_kid, "keys": ring.metadata()}
