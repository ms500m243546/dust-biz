"""Auth schemas (Phase I).

Wire formats for login, the bearer token, and the current-user payload.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal[
    "shift_supervisor",
    "environmental_manager",
    "operations_manager",
    "dispatcher",
    "executive",
    "admin",
]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    role: Role


class UserSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    username: str
    role: Role
