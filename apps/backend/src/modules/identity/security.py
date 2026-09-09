"""JWT access-token issuance/verification and refresh-token generation.

Access tokens: JWT (HS256, via PyJWT — added as a dependency in this
change; see the task's final report). Chosen because it lets any service
verify a token locally without a network call to the identity module,
which matters once matching/ride/wallet/etc. become separate call paths
per technical-architecture.md's domain-ownership model.

Refresh tokens: an opaque, cryptographically random string (NOT a JWT).
Only its SHA-256 hash is persisted (modules/identity/models.py
SessionORM.refresh_token_hash), so a database read alone cannot be used to
impersonate a session, and revocation is a simple row update rather than
requiring a JWT denylist for every refresh token ever issued.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from modules.identity.config import identity_settings
from modules.identity.domain.entities import AccountType
from modules.identity.domain.errors import AccessTokenInvalidError

MFA_PENDING_TOKEN_EXPIRE_MINUTES = 5

# ADR-0051 Decision 4 — every access token issued anywhere in this
# codebase carries this claim from now on. get_current_account()
# (dependencies.py) rejects any token whose "purpose" isn't this exact
# value, so an MFA pre-auth token (see issue_mfa_pending_token() below)
# can never be misused as a real access token even if leaked.
_PURPOSE_ACCESS = "access"
_PURPOSE_MFA_PENDING = "mfa_pending"


def issue_access_token(
    *, account_id: uuid.UUID, account_type: AccountType, now: datetime | None = None
) -> tuple[str, str, datetime]:
    """Returns (token, jti, expires_at)."""
    now = now or datetime.now(UTC)
    jti = str(uuid.uuid4())
    expires_at = now + timedelta(
        minutes=identity_settings.jwt_access_token_expire_minutes
    )
    payload: dict[str, Any] = {
        "sub": str(account_id),
        "account_type": account_type.value,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "purpose": _PURPOSE_ACCESS,
    }
    token = jwt.encode(
        payload, identity_settings.jwt_secret, algorithm=identity_settings.jwt_algorithm
    )
    return token, jti, expires_at


def issue_mfa_pending_token(
    *, account_id: uuid.UUID, now: datetime | None = None
) -> str:
    """ADR-0051 — returned by POST /api/v1/auth/otp/verify instead of a
    real token pair when the account has an ACTIVE MFA credential.
    Short-lived (5 minutes — long enough to open an authenticator app
    and type a code, short enough that a leaked one is useless soon
    after). No `jti`/denylist entry: unlike a real access token, this
    is single-purpose and self-expiring, and revoking a 5-minute token
    via a Redis round-trip on every login would be pure overhead."""
    now = now or datetime.now(UTC)
    expires_at = now + timedelta(minutes=MFA_PENDING_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(account_id),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "purpose": _PURPOSE_MFA_PENDING,
    }
    return jwt.encode(
        payload, identity_settings.jwt_secret, algorithm=identity_settings.jwt_algorithm
    )


def decode_mfa_pending_token(token: str) -> uuid.UUID:
    """Decodes and verifies an mfa_pending token, returning the
    account_id it was issued for. Raises AccessTokenInvalidError (same
    error a bad access token raises — decode_access_token() reuses this
    exact exception type, and this function reuses its decoding logic)
    on any failure: bad signature, expired, or wrong purpose."""
    payload = decode_access_token(token)
    if payload.get("purpose") != _PURPOSE_MFA_PENDING:
        raise AccessTokenInvalidError("Not a valid MFA pending token.")
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise AccessTokenInvalidError("Not a valid MFA pending token.") from exc


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and verify signature + expiry. Raises AccessTokenInvalidError
    on any failure (invalid signature, malformed token, or expired) —
    callers should not need to know PyJWT's specific exception hierarchy."""
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            identity_settings.jwt_secret,
            algorithms=[identity_settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise AccessTokenInvalidError("Access token is invalid or expired.") from exc
    return payload


def generate_refresh_token() -> str:
    """A high-entropy opaque token — not a JWT, see module docstring."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
