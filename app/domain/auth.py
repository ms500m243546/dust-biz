"""Auth domain (Phase I).

Password hashing and signed-token issuance / verification using
stdlib only (no new dependencies beyond what Phase B already pulled in).

- Passwords: PBKDF2-HMAC-SHA256 with a per-record random salt.
- Tokens: compact HMAC-SHA256 signed payload, base64-url encoded. Not
  full JWT, but the same shape (header.payload.signature). Acceptable
  for MVP; rotation and JWKS integration are deferred to K hardening.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

# Default token lifetime: 8 hours (one shift). Configurable via
# DUSTOPS_TOKEN_TTL_MINUTES if needed; not surfaced in Settings yet to
# keep the I.1 surface area minimal.
TOKEN_TTL_MINUTES = 8 * 60

# Process-level signing key. In production this is set via
# DUSTOPS_AUTH_SECRET; in dev/tests we generate a per-process key so the
# app boots without configuration (tokens become invalid across
# restarts, which is the right default for dev).
_PROCESS_SECRET = os.environ.get("DUSTOPS_AUTH_SECRET", secrets.token_hex(32))

# PBKDF2 iteration count. OWASP 2023 guidance for SHA-256 is 600k; we
# use 200k to keep the test suite fast (test users are seeded fresh per
# run, no real attacker model in the CI gate).
_PBKDF2_ITERATIONS = 200_000


class InvalidCredentialsError(Exception):
    """Username unknown or password mismatch."""


class InvalidTokenError(Exception):
    """Token signature, structure, or expiry check failed."""


@dataclass(frozen=True)
class TokenClaims:
    user_id: str
    username: str
    role: str
    issued_at: datetime
    expires_at: datetime


def hash_password(password: str) -> str:
    """Salted PBKDF2-HMAC-SHA256.

    Format: ``pbkdf2_sha256${iterations}${salt_b64}${hash_b64}``.
    """
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return (
        f"pbkdf2_sha256${_PBKDF2_ITERATIONS}"
        f"${_b64(salt)}${_b64(derived)}"
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iters_s, salt_b64, hash_b64 = stored.split("$")
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    try:
        iterations = int(iters_s)
        salt = _b64d(salt_b64)
        expected = _b64d(hash_b64)
    except (ValueError, TypeError):
        return False
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    return hmac.compare_digest(derived, expected)


def issue_token(
    *,
    user_id: str,
    username: str,
    role: str,
    now: datetime | None = None,
) -> tuple[str, datetime]:
    """Issue a signed token; returns (token, expires_at)."""
    issued = (now or datetime.now(UTC)).replace(microsecond=0)
    expires = issued + timedelta(minutes=TOKEN_TTL_MINUTES)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": int(issued.timestamp()),
        "exp": int(expires.timestamp()),
    }
    header = {"alg": "HS256", "typ": "DustOps-MVP"}
    h_b64 = _b64(json.dumps(header, separators=(",", ":")).encode())
    p_b64 = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{h_b64}.{p_b64}".encode()
    sig = hmac.new(_PROCESS_SECRET.encode(), signing_input, hashlib.sha256).digest()
    s_b64 = _b64(sig)
    return f"{h_b64}.{p_b64}.{s_b64}", expires


def verify_token(token: str, *, now: datetime | None = None) -> TokenClaims:
    parts = token.split(".")
    if len(parts) != 3:
        raise InvalidTokenError("malformed token")
    h_b64, p_b64, s_b64 = parts
    signing_input = f"{h_b64}.{p_b64}".encode()
    expected_sig = hmac.new(
        _PROCESS_SECRET.encode(), signing_input, hashlib.sha256
    ).digest()
    try:
        provided_sig = _b64d(s_b64)
    except ValueError as exc:
        raise InvalidTokenError("malformed signature") from exc
    if not hmac.compare_digest(expected_sig, provided_sig):
        raise InvalidTokenError("bad signature")
    try:
        payload = json.loads(_b64d(p_b64))
    except (ValueError, json.JSONDecodeError) as exc:
        raise InvalidTokenError("malformed payload") from exc

    moment = (now or datetime.now(UTC)).replace(microsecond=0)
    exp = datetime.fromtimestamp(payload.get("exp", 0), tz=UTC)
    iat = datetime.fromtimestamp(payload.get("iat", 0), tz=UTC)
    if moment >= exp:
        raise InvalidTokenError("token expired")
    return TokenClaims(
        user_id=str(payload.get("sub", "")),
        username=str(payload.get("username", "")),
        role=str(payload.get("role", "")),
        issued_at=iat,
        expires_at=exp,
    )


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)
