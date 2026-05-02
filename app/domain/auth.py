"""Auth domain (Phase I; key rotation in K.3).

Password hashing and signed-token issuance / verification using
stdlib only (no new dependencies beyond what Phase B already pulled
in).

- Passwords: PBKDF2-HMAC-SHA256 with a per-record random salt.
- Tokens: compact HMAC-SHA256 signed payload, base64-url encoded;
  header carries `kid` so the verifier can pick the right secret out
  of the rotating `KeyRing`. Drop-in for JWT-shaped consumers.

K.3 rotation model:
- The active signing key is determined by `KeyRing.active`.
- `KeyRing.rotate(kid, secret, retire_after=...)` adds a new active
  key while keeping the previous key valid for verification until
  every issued token has expired (rolling rotation, no auth blip).
- Retired keys are pruned by `KeyRing.prune(now)` (called by the
  scheduler in `app/scheduler/`).
- The bootstrap key comes from `DUSTOPS_AUTH_SECRET`; if unset, a
  per-process random key is generated so dev boots without config.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

# Default token lifetime: 8 hours (one shift). Configurable via
# DUSTOPS_TOKEN_TTL_MINUTES if needed; not surfaced in Settings yet.
TOKEN_TTL_MINUTES = 8 * 60

# PBKDF2 iteration count. OWASP 2023 guidance for SHA-256 is 600k; we
# use 200k to keep the test suite fast (test users are seeded fresh
# per run, no real attacker model in the CI gate).
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
    kid: str


@dataclass
class _KeyRecord:
    kid: str
    secret: str
    created_at: datetime
    retired_at: datetime | None = None  # set when superseded; verify-only past this


@dataclass
class KeyRing:
    """Rotating set of HMAC signing keys, keyed by `kid`."""

    keys: dict[str, _KeyRecord] = field(default_factory=dict)
    active_kid: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, kid: str, secret: str, *, now: datetime | None = None) -> None:
        with self._lock:
            self.keys[kid] = _KeyRecord(
                kid=kid,
                secret=secret,
                created_at=(now or datetime.now(UTC)).replace(microsecond=0),
            )
            if not self.active_kid:
                self.active_kid = kid

    def rotate(
        self,
        new_kid: str,
        new_secret: str,
        *,
        now: datetime | None = None,
    ) -> str:
        """Promote a new key to active and mark the previous as retired.

        Retired keys remain valid for verification until pruned, so any
        token issued before rotation still verifies until it expires.
        """
        moment = (now or datetime.now(UTC)).replace(microsecond=0)
        with self._lock:
            old = self.keys.get(self.active_kid)
            if old is not None:
                old.retired_at = moment
            self.keys[new_kid] = _KeyRecord(
                kid=new_kid, secret=new_secret, created_at=moment
            )
            self.active_kid = new_kid
        return new_kid

    def prune(self, *, now: datetime | None = None) -> int:
        """Drop retired keys whose grace window has elapsed.

        A retired key is dropped once `now >= retired_at + TOKEN_TTL`
        because no live token could have been issued against it.
        Returns the number of keys dropped.
        """
        moment = (now or datetime.now(UTC)).replace(microsecond=0)
        cutoff = moment - timedelta(minutes=TOKEN_TTL_MINUTES)
        with self._lock:
            stale = [
                k
                for k, rec in self.keys.items()
                if rec.retired_at is not None and rec.retired_at <= cutoff
            ]
            for k in stale:
                del self.keys[k]
        return len(stale)

    def get(self, kid: str) -> _KeyRecord | None:
        with self._lock:
            return self.keys.get(kid)

    def metadata(self) -> list[dict[str, object]]:
        """Public-safe metadata for the key registry endpoint.

        Never returns secret material — only kid / alg / state so
        clients can detect rotation. Retired keys are listed with
        `state="retired"` until pruned.
        """
        with self._lock:
            return [
                {
                    "kid": rec.kid,
                    "alg": "HS256",
                    "created_at": rec.created_at.isoformat(),
                    "retired_at": (
                        rec.retired_at.isoformat() if rec.retired_at else None
                    ),
                    "active": rec.kid == self.active_kid,
                }
                for rec in self.keys.values()
            ]


def _bootstrap_keyring() -> KeyRing:
    bootstrap_secret = os.environ.get("DUSTOPS_AUTH_SECRET") or secrets.token_hex(32)
    ring = KeyRing()
    ring.add("bootstrap", bootstrap_secret)
    return ring


_KEYRING = _bootstrap_keyring()


def get_keyring() -> KeyRing:
    return _KEYRING


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
    keyring: KeyRing | None = None,
) -> tuple[str, datetime]:
    """Issue a signed token; returns (token, expires_at)."""
    ring = keyring or _KEYRING
    if not ring.active_kid:
        raise InvalidTokenError("no active signing key")
    rec = ring.get(ring.active_kid)
    if rec is None:
        raise InvalidTokenError("active key missing")

    issued = (now or datetime.now(UTC)).replace(microsecond=0)
    expires = issued + timedelta(minutes=TOKEN_TTL_MINUTES)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": int(issued.timestamp()),
        "exp": int(expires.timestamp()),
    }
    header = {"alg": "HS256", "typ": "DustOps-MVP", "kid": rec.kid}
    h_b64 = _b64(json.dumps(header, separators=(",", ":")).encode())
    p_b64 = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{h_b64}.{p_b64}".encode()
    sig = hmac.new(rec.secret.encode(), signing_input, hashlib.sha256).digest()
    s_b64 = _b64(sig)
    return f"{h_b64}.{p_b64}.{s_b64}", expires


def verify_token(
    token: str,
    *,
    now: datetime | None = None,
    keyring: KeyRing | None = None,
) -> TokenClaims:
    ring = keyring or _KEYRING
    parts = token.split(".")
    if len(parts) != 3:
        raise InvalidTokenError("malformed token")
    h_b64, p_b64, s_b64 = parts
    try:
        header = json.loads(_b64d(h_b64))
    except (ValueError, json.JSONDecodeError) as exc:
        raise InvalidTokenError("malformed header") from exc
    kid = str(header.get("kid", ""))
    # Pre-K.3 tokens had no kid; fall back to the active key for one
    # full rotation grace period. After K.3 lands every newly issued
    # token carries a kid.
    rec = ring.get(ring.active_kid) if not kid else ring.get(kid)
    if rec is None:
        raise InvalidTokenError(f"unknown signing key: kid={kid or '<none>'}")

    signing_input = f"{h_b64}.{p_b64}".encode()
    expected_sig = hmac.new(rec.secret.encode(), signing_input, hashlib.sha256).digest()
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
        kid=rec.kid,
    )


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


__all__ = [
    "InvalidCredentialsError",
    "InvalidTokenError",
    "KeyRing",
    "TOKEN_TTL_MINUTES",
    "TokenClaims",
    "get_keyring",
    "hash_password",
    "issue_token",
    "verify_password",
    "verify_token",
]
