"""Abstract interfaces (ports) the application layer depends on.

Concrete implementations live in repositories.py, sms.py, rate_limit.py,
and token_denylist.py. Defining these as Protocols keeps service.py
(the application layer) decoupled from SQLAlchemy/Redis/any specific SMS
vendor — exactly the boundary packages/domain/README.md §3
("Architectural Boundaries") describes between domain and infrastructure.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol

from modules.identity.domain.entities import (
    Account,
    AccountType,
    MfaCredential,
    OtpChallenge,
    Session,
)


class Clock(Protocol):
    """Injectable time source so tests can control "now" deterministically."""

    def now(self) -> datetime: ...


class SmsProvider(Protocol):
    """Provider-neutral SMS abstraction.

    ADR-0031 wired in MSG91 behind this seam (send_otp only); ADR-0034
    (Notification Domain Foundation) added send_message() alongside it —
    both DevConsoleSmsProvider and Msg91SmsProvider (sms.py) implement
    both. Structurally identical to modules.notification.ports.
    SmsMessageProvider's own (narrower, send_message-only) protocol —
    modules/notification/dependencies.py reuses this module's own SMS
    provider dependency rather than constructing a second one.
    """

    async def send_otp(self, phone_number: str, otp: str) -> None: ...
    async def send_message(self, phone_number: str, message: str) -> str | None: ...


class AccountRepository(Protocol):
    def get_by_phone(self, phone: str) -> Account | None: ...
    def get_by_id(self, account_id: uuid.UUID) -> Account | None: ...
    def create(self, *, account_type: AccountType, phone: str) -> Account: ...


class OtpChallengeRepository(Protocol):
    def create(self, challenge: OtpChallenge) -> OtpChallenge: ...
    def get_by_id(self, challenge_id: uuid.UUID) -> OtpChallenge | None: ...
    def invalidate_active_for_phone(self, phone: str) -> None:
        """Mark every currently-ACTIVE challenge for this phone as
        INVALIDATED. Called before issuing a new challenge, so that
        "generating a new OTP invalidates the previous one" (BR-084,
        reused per entities.py's OtpChallengeStatus docstring) holds for
        login OTP too."""
        ...

    def save(self, challenge: OtpChallenge) -> None: ...
    def count_active_for_phone_since(self, phone: str, since: datetime) -> int:
        """Used for OTP request rate limiting as a Postgres-backed
        fallback/audit trail; the primary rate-limit enforcement path is
        Redis (see rate_limit.py) for performance, per the task's REDIS
        section ("OTP temporary state, rate-limiting state")."""
        ...


class SessionRepository(Protocol):
    def create(self, session: Session) -> Session: ...
    def get_by_id(self, session_id: uuid.UUID) -> Session | None: ...
    def get_by_refresh_token_hash(self, token_hash: str) -> Session | None: ...
    def save(self, session: Session) -> None: ...
    def revoke(self, session_id: uuid.UUID) -> None: ...


class OtpRateLimiter(Protocol):
    """Redis-backed OTP request/verify abuse protection.

    The phone-number dimension was enforced first (the original
    foundational task); the IP-address dimension was added in Phase 2's
    Identity-hardening pass (security.md §5 lists phone number, IP
    address, and device/session as the three documented dimensions).
    Device/session is deliberately still not implemented: unlike IP
    (available from the request's own connection, no contract change
    needed), a meaningful device/session dimension needs a client-
    generated identifier api-contracts.md's OTP request/verify bodies do
    not document — adding one would mean inventing a new public API
    contract, which is its own explicit stop condition (roadmap §0.3),
    independent of how simple the rate-limiting logic itself would be.
    """

    async def check_and_increment_request(self, phone: str) -> None:
        """Raises OtpRateLimitedError or OtpResendCooldownError (from
        modules.identity.domain.errors) if the phone number has exceeded
        its configured request rate or is still within its resend
        cooldown."""
        ...

    async def check_and_increment_verify_attempt(self, phone: str) -> None:
        """Raises OtpRateLimitedError if verification attempts for this
        phone (independent of any single challenge's own attempt counter)
        have exceeded the configured rate."""
        ...

    async def check_and_increment_request_ip(self, ip_address: str) -> None:
        """Raises OtpRateLimitedError if this IP address has exceeded its
        configured OTP-request rate — catches a single source flooding
        many *different* phone numbers, which the phone-keyed limit above
        cannot see on its own. No resend-cooldown concept at this
        dimension (that's inherently per-phone, not per-IP)."""
        ...

    async def check_and_increment_verify_attempt_ip(self, ip_address: str) -> None:
        """Raises OtpRateLimitedError if verification attempts from this
        IP address (across any phone number/challenge) have exceeded the
        configured rate — catches distributed guessing against many
        challenges from one source."""
        ...


class MfaCredentialRepository(Protocol):
    """ADR-0051 — at most one row per account (account_id is the
    primary key, not a separate id column)."""

    def get(self, account_id: uuid.UUID) -> MfaCredential | None: ...
    def get_for_update(self, account_id: uuid.UUID) -> MfaCredential | None:
        """Row-locked, for the confirm/disable transactions."""
        ...

    def upsert(self, credential: MfaCredential) -> MfaCredential:
        """Creates the row if none exists yet, otherwise replaces it in
        place (re-enrollment over a PENDING-but-never-confirmed
        credential — MfaService.enroll() already rejects re-enrollment
        over an ACTIVE one before this is ever called for that case)."""
        ...

    def save(self, credential: MfaCredential) -> None: ...
    def delete(self, account_id: uuid.UUID) -> None: ...


class AccessTokenDenylist(Protocol):
    """Redis-backed denylist so a logged-out access token cannot be reused
    for the remainder of its natural lifetime, even though it is a
    stateless JWT (security.md §6: access tokens must "Be revocable when
    necessary")."""

    async def revoke(self, jti: str, *, ttl_seconds: int) -> None: ...
    async def is_revoked(self, jti: str) -> bool: ...
