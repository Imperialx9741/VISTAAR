"""Identity domain entities and value objects.

Field/table shapes are kept intentionally aligned with
docs/04-database/database-design.md §5 (identity.accounts,
identity.otp_challenges), with two additive extensions recorded in this
same change (see database-design.md's own update and the task's final
report for the exact diff) — nothing here contradicts an existing table:

- identity.otp_challenges gains an ``account_type`` column. Without it,
  the client would have to resend account_type on the Verify OTP call so
  a brand-new account could be created with the right type — but
  docs/05-api/api-contracts.md §7's documented Verify OTP request body is
  only {"challenge_id", "otp"}. Storing the account_type chosen at
  request time on the challenge itself (rather than trusting the client
  to resend, and possibly change, it at verify time) keeps the
  implementation faithful to the already-documented API contract.
- identity.sessions is an entirely new table for refresh-token/session
  tracking, which database-design.md did not yet define.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class AccountType(StrEnum):
    """Matches database-design.md §5.1 "Allowed account types"."""

    CUSTOMER = "CUSTOMER"
    DRIVER = "DRIVER"
    ADMIN = "ADMIN"


class AccountStatus(StrEnum):
    """ACTIVE is database-design.md §5.1's documented default.

    SUSPENDED is added here because api-contracts.md §7 already documents
    an ACCOUNT_SUSPENDED error code and domain-design.md §5.3 already
    defines SuspendAccount/ReactivateAccount commands — both imply this
    status must exist, even though database-design.md's CREATE TABLE
    example only shows the default. No other status (e.g. a distinct
    "PENDING"/"UNVERIFIED" state) is introduced: no source document
    describes one, and OTP-based auth in this system does not have a
    separate registration step (see service.py's module docstring).
    """

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class OtpChallengeStatus(StrEnum):
    """ACTIVE is database-design.md §5.2's documented default.

    VERIFIED / EXPIRED / INVALIDATED follow the same lifecycle pattern
    business-rules.md BR-084 already defines for ride-start OTP ("When a
    new OTP is generated, the previous OTP becomes invalid") and
    technical-architecture.md §41 ("Only the latest valid OTP is
    accepted") — reused here for login OTP rather than inventing a new
    pattern, since no separate login-OTP lifecycle is documented anywhere.
    """

    ACTIVE = "ACTIVE"
    VERIFIED = "VERIFIED"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"


@dataclass(slots=True)
class Account:
    id: uuid.UUID
    account_type: AccountType
    phone: str
    status: AccountStatus
    created_at: datetime
    updated_at: datetime

    def is_suspended(self) -> bool:
        return self.status is AccountStatus.SUSPENDED


@dataclass(slots=True)
class OtpChallenge:
    id: uuid.UUID
    account_id: uuid.UUID | None
    account_type: AccountType
    phone: str
    otp_hash: str
    expires_at: datetime
    attempts: int
    max_attempts: int
    status: OtpChallengeStatus
    created_at: datetime

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def attempts_exhausted(self) -> bool:
        return self.attempts >= self.max_attempts


@dataclass(slots=True)
class Session:
    """A refresh-token-backed session.

    The refresh token itself is never stored in plaintext — only its hash
    (``refresh_token_hash``), following the same "never stored in
    plaintext where avoidable" principle security.md §4 applies to OTPs.
    """

    id: uuid.UUID
    account_id: uuid.UUID
    refresh_token_hash: str
    device_metadata: str | None
    expires_at: datetime
    revoked_at: datetime | None
    created_at: datetime

    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def is_valid(self, now: datetime) -> bool:
        return not self.is_revoked() and not self.is_expired(now)


@dataclass(slots=True)
class NewOtpChallenge:
    """Return value of issuing a new OTP challenge: the record to persist,
    plus the plaintext OTP that must be sent via SmsProvider and must never
    be persisted or returned by the API (security.md §5: "OTP must never
    be returned by the API")."""

    challenge: OtpChallenge
    plaintext_otp: str = field(repr=False)


class MfaCredentialStatus(StrEnum):
    """PENDING: enrolled, not yet confirmed with a real code from the
    authenticator app — mirrors this codebase's own established
    Driver/Vehicle "submit, then confirm" verification-status shape
    rather than activating on enrollment alone (ADR-0051 Decision 2)."""

    PENDING = "PENDING"
    ACTIVE = "ACTIVE"


@dataclass(slots=True)
class MfaCredential:
    """One row per account, at most one (ADR-0051) — identity.
    mfa_credentials.account_id is the primary key, not a separate id
    column, since an account can only ever have a single TOTP secret at
    a time (re-enrolling replaces it, see MfaService.enroll())."""

    account_id: uuid.UUID
    secret: str = field(repr=False)  # never logged/repr'd — see repr=False
    status: MfaCredentialStatus
    created_at: datetime
    confirmed_at: datetime | None

    @property
    def is_active(self) -> bool:
        return self.status is MfaCredentialStatus.ACTIVE
