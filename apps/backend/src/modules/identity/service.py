"""Application services (use cases) for Identity & Authentication.

Registration and login are unified into a single OTP flow, matching
docs/05-api/api-contracts.md §6-7 (only "Request OTP" and "Verify OTP" are
documented — there is no separate "/register" endpoint) and
docs/04-domain-design/domain-design.md §5.3, whose command list
(RegisterAccount, RequestOTP, VerifyOTP, ...) is read here as: requesting
an OTP for a phone number VISTAAR has not seen before implicitly registers
that phone as a new account (RegisterAccount), rather than requiring a
separate prior registration step nothing in the documented API surface
supports. AccountRegistered fires the first time an account is created;
AccountVerified fires on every successful OTP verification for that
account (there is no documented "unverified" account status distinct from
ACTIVE — see domain/entities.py's AccountStatus docstring — so
AccountVerified is modeled as "phone ownership was reconfirmed this
authentication event", not a one-time state transition).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from modules.identity.config import identity_settings
from modules.identity.domain.entities import (
    Account,
    AccountType,
    MfaCredential,
    MfaCredentialStatus,
    OtpChallenge,
    OtpChallengeStatus,
    Session,
)
from modules.identity.domain.errors import (
    AccessTokenInvalidError,
    AccountSuspendedError,
    MfaAlreadyActiveError,
    MfaCodeIncorrectError,
    MfaNotEnrolledError,
    MfaNotPendingError,
    MfaTokenInvalidError,
    OtpChallengeNotFoundError,
    OtpExpiredError,
    OtpIncorrectError,
    OtpMaxAttemptsError,
    RefreshTokenExpiredError,
    RefreshTokenInvalidError,
)
from modules.identity.domain.mfa import (
    generate_totp_secret,
    totp_provisioning_uri,
    verify_totp_code,
)
from modules.identity.domain.otp import generate_numeric_otp, hash_otp, verify_otp
from modules.identity.domain.phone_number import PhoneNumber
from modules.identity.ports import (
    AccessTokenDenylist,
    AccountRepository,
    MfaCredentialRepository,
    OtpChallengeRepository,
    OtpRateLimiter,
    SessionRepository,
    SmsProvider,
)
from modules.identity.security import (
    MFA_PENDING_TOKEN_EXPIRE_MINUTES,
    decode_access_token,
    decode_mfa_pending_token,
    generate_refresh_token,
    hash_refresh_token,
    issue_access_token,
    issue_mfa_pending_token,
)


@dataclass(slots=True)
class OtpRequestResult:
    challenge_id: uuid.UUID
    expires_in_seconds: int


@dataclass(slots=True)
class TokenPairResult:
    access_token: str
    refresh_token: str
    expires_in_seconds: int


@dataclass(slots=True)
class MfaRequiredResult:
    """ADR-0051 — returned by verify_otp() instead of TokenPairResult
    when the account has an ACTIVE MFA credential. The caller (router)
    must present `mfa_token` + a TOTP code to POST /api/v1/auth/mfa/
    verify to actually obtain a token pair."""

    mfa_token: str
    expires_in_seconds: int


OtpVerifyResult = TokenPairResult | MfaRequiredResult


@dataclass(slots=True)
class MfaEnrollResult:
    secret: str
    otpauth_uri: str


class IdentityService:
    def __init__(
        self,
        *,
        accounts: AccountRepository,
        challenges: OtpChallengeRepository,
        sessions: SessionRepository,
        sms: SmsProvider,
        rate_limiter: OtpRateLimiter,
        denylist: AccessTokenDenylist,
        mfa_credentials: MfaCredentialRepository | None = None,
    ) -> None:
        self._accounts = accounts
        self._challenges = challenges
        self._sessions = sessions
        self._sms = sms
        self._rate_limiter = rate_limiter
        self._denylist = denylist
        # Optional (default None), same reasoning modules.notification.
        # service.NotificationService's own sms_provider param already
        # established: callers that never touch MFA (every existing
        # customer/driver login, and every admin who hasn't enrolled)
        # don't need it wired.
        self._mfa_credentials = mfa_credentials

    # ------------------------------------------------------------------
    # OTP request
    # ------------------------------------------------------------------
    async def request_otp(
        self,
        *,
        raw_phone: str,
        account_type: AccountType,
        ip_address: str | None = None,
    ) -> OtpRequestResult:
        phone = PhoneNumber.parse(raw_phone).value

        # IP dimension first (Phase 2 Identity hardening, security.md §5)
        # — catches a single source flooding many different phone numbers
        # before even touching per-phone state. Optional: callers that
        # cannot determine a client IP (tests, non-HTTP callers) simply
        # skip this dimension rather than being forced to fabricate one.
        if ip_address is not None:
            await self._rate_limiter.check_and_increment_request_ip(ip_address)

        await self._rate_limiter.check_and_increment_request(phone)

        account = self._accounts.get_by_phone(phone)
        if account is not None and account.is_suspended():
            raise AccountSuspendedError("This account is suspended.")

        # BR-084's "generating a new OTP invalidates the previous one"
        # pattern, reused for login OTP (see domain/entities.py).
        self._challenges.invalidate_active_for_phone(phone)

        plaintext_otp = generate_numeric_otp(identity_settings.otp_length)
        now = datetime.now(UTC)
        new_challenge = OtpChallenge(
            id=uuid.uuid4(),
            account_id=account.id if account else None,
            account_type=account.account_type if account else account_type,
            phone=phone,
            otp_hash=hash_otp(plaintext_otp, pepper=identity_settings.otp_hash_secret),
            expires_at=now + timedelta(seconds=identity_settings.otp_expiry_seconds),
            attempts=0,
            max_attempts=identity_settings.otp_max_verify_attempts,
            status=OtpChallengeStatus.ACTIVE,
            created_at=now,
        )
        persisted = self._challenges.create(new_challenge)

        # OTP is only ever handed to the SmsProvider — never returned to
        # the caller of this service (security.md §5).
        await self._sms.send_otp(phone, plaintext_otp)

        return OtpRequestResult(
            challenge_id=persisted.id,
            expires_in_seconds=identity_settings.otp_expiry_seconds,
        )

    # ------------------------------------------------------------------
    # OTP verification -> tokens
    # ------------------------------------------------------------------
    async def verify_otp(
        self,
        *,
        challenge_id: uuid.UUID,
        otp: str,
        device_metadata: str | None = None,
        ip_address: str | None = None,
    ) -> OtpVerifyResult:
        challenge = self._challenges.get_by_id(challenge_id)
        if challenge is None or challenge.status not in (OtpChallengeStatus.ACTIVE,):
            # Same error as "incorrect OTP" — see
            # OtpChallengeNotFoundError's docstring (avoids enumeration).
            raise OtpChallengeNotFoundError("Invalid or already-used OTP challenge.")

        # IP dimension first, same reasoning as request_otp() above —
        # catches distributed guessing against many challenges from one
        # source before touching per-phone state.
        if ip_address is not None:
            await self._rate_limiter.check_and_increment_verify_attempt_ip(ip_address)

        await self._rate_limiter.check_and_increment_verify_attempt(challenge.phone)

        now = datetime.now(UTC)
        if challenge.is_expired(now):
            challenge.status = OtpChallengeStatus.EXPIRED
            self._challenges.save(challenge)
            raise OtpExpiredError("This OTP has expired. Request a new one.")

        if challenge.attempts_exhausted():
            raise OtpMaxAttemptsError(
                "Maximum verification attempts exceeded for this OTP."
            )

        if not verify_otp(
            otp,
            pepper=identity_settings.otp_hash_secret,
            expected_hash=challenge.otp_hash,
        ):
            challenge.attempts += 1
            self._challenges.save(challenge)
            raise OtpIncorrectError("Incorrect OTP.")

        # One-time use: mark VERIFIED immediately so it cannot be replayed.
        challenge.status = OtpChallengeStatus.VERIFIED
        self._challenges.save(challenge)

        account = self._accounts.get_by_phone(challenge.phone)
        if account is None:
            account = self._accounts.create(
                account_type=challenge.account_type, phone=challenge.phone
            )
            # AccountRegistered would be published here once event-contracts.md
            # defines an identity.* event family — see this task's final
            # report, section S, for why that is not implemented yet.
        elif account.is_suspended():
            raise AccountSuspendedError("This account is suspended.")
        # AccountVerified would be published here — same caveat as above.

        # ADR-0051 Decision 1 — a brand-new account (just created above)
        # can never have an MFA credential yet, but checking
        # unconditionally rather than only for existing accounts keeps
        # this one code path instead of two.
        if self._mfa_credentials is not None:
            credential = self._mfa_credentials.get(account.id)
            if credential is not None and credential.is_active:
                mfa_token = issue_mfa_pending_token(account_id=account.id, now=now)
                return MfaRequiredResult(
                    mfa_token=mfa_token,
                    expires_in_seconds=MFA_PENDING_TOKEN_EXPIRE_MINUTES * 60,
                )

        return await self._issue_tokens(
            account=account, device_metadata=device_metadata
        )

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------
    async def refresh(self, *, refresh_token: str) -> TokenPairResult:
        token_hash = hash_refresh_token(refresh_token)
        session = self._find_session_by_hash(token_hash)
        now = datetime.now(UTC)
        if session is None or not session.is_valid(now):
            raise RefreshTokenInvalidError("Refresh token is invalid or revoked.")
        if session.is_expired(now):
            raise RefreshTokenExpiredError("Refresh token has expired.")

        account = self._accounts.get_by_id(session.account_id)
        if account is None or account.is_suspended():
            raise AccountSuspendedError("This account is suspended.")

        # Rotate: revoke the old session, issue a brand new one. Refresh
        # tokens are single-use — security.md §6 ("Refresh tokens must be
        # ... Rotated where supported").
        self._sessions.revoke(session.id)

        return await self._issue_tokens(
            account=account, device_metadata=session.device_metadata
        )

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------
    async def logout(self, *, access_token: str, refresh_token: str | None) -> None:
        payload = decode_access_token(access_token)
        # ADR-0051 Decision 4: an mfa_pending token has no `jti` at all
        # (see issue_mfa_pending_token()'s own docstring) — reject it
        # here with the same AUTH_INVALID a bad access token already
        # gets, rather than letting `payload["jti"]` raise a raw
        # KeyError below.
        if payload.get("purpose") != "access":
            raise AccessTokenInvalidError("Not a valid access token.")
        jti = payload["jti"]
        exp = payload["exp"]
        now = datetime.now(UTC)
        ttl = max(0, exp - int(now.timestamp()))
        await self._denylist.revoke(jti, ttl_seconds=ttl)

        if refresh_token:
            token_hash = hash_refresh_token(refresh_token)
            session = self._find_session_by_hash(token_hash)
            if session is not None:
                self._sessions.revoke(session.id)

    # ------------------------------------------------------------------
    # Admin MFA (ADR-0051) — a generic identity-layer capability (see the
    # ADR's Decision 1 for why this lives here, not in modules.admin).
    # Enrollment is reachable by any authenticated account at the router
    # layer today it's gated to ADMIN via require_admin, since that's
    # the only account type asked for; nothing here assumes ADMIN.
    # ------------------------------------------------------------------

    def enroll_mfa(self, *, account_id: uuid.UUID, now: datetime) -> MfaEnrollResult:
        """Generates a fresh PENDING secret, replacing any existing
        PENDING one — but rejects re-enrollment over an ACTIVE
        credential (MfaAlreadyActiveError): call disable_mfa() first,
        which itself requires a valid current code, so a stolen bearer
        token alone can never downgrade an admin's existing MFA
        protection (ADR-0051 Decision 4)."""
        assert self._mfa_credentials is not None, "enroll_mfa() needs mfa_credentials"
        existing = self._mfa_credentials.get(account_id)
        if existing is not None and existing.is_active:
            raise MfaAlreadyActiveError(
                "MFA is already active for this account. Disable it before "
                "re-enrolling."
            )

        secret = generate_totp_secret()
        credential = self._mfa_credentials.upsert(
            MfaCredential(
                account_id=account_id,
                secret=secret,
                status=MfaCredentialStatus.PENDING,
                created_at=now,
                confirmed_at=None,
            )
        )
        account = self._accounts.get_by_id(account_id)
        label = account.phone if account is not None else str(account_id)
        return MfaEnrollResult(
            secret=credential.secret,
            otpauth_uri=totp_provisioning_uri(
                secret=credential.secret, account_label=label
            ),
        )

    def confirm_mfa(self, *, account_id: uuid.UUID, code: str, now: datetime) -> None:
        """PENDING -> ACTIVE, once the admin proves they actually
        recorded the secret correctly by producing a real code from it."""
        assert self._mfa_credentials is not None, "confirm_mfa() needs mfa_credentials"
        credential = self._mfa_credentials.get_for_update(account_id)
        if credential is None:
            raise MfaNotEnrolledError("No MFA enrollment in progress for this account.")
        if credential.status is not MfaCredentialStatus.PENDING:
            raise MfaNotPendingError("This MFA credential is already active.")
        if not verify_totp_code(secret=credential.secret, code=code):
            raise MfaCodeIncorrectError("Incorrect code.")

        credential.status = MfaCredentialStatus.ACTIVE
        credential.confirmed_at = now
        self._mfa_credentials.save(credential)

    async def verify_mfa(self, *, mfa_token: str, code: str) -> TokenPairResult:
        """The second step of login for an account with an ACTIVE MFA
        credential — mfa_token is what verify_otp() returned instead of
        a real token pair. Issues real tokens exactly as verify_otp()
        would have without MFA."""
        assert self._mfa_credentials is not None, "verify_mfa() needs mfa_credentials"
        try:
            account_id = decode_mfa_pending_token(mfa_token)
        except AccessTokenInvalidError as exc:
            raise MfaTokenInvalidError(
                "This MFA challenge is invalid or expired."
            ) from exc

        credential = self._mfa_credentials.get(account_id)
        if credential is None or not credential.is_active:
            raise MfaTokenInvalidError("This MFA challenge is invalid or expired.")

        # Reuses the same phone-keyed abuse protection OTP verification
        # already has — a 6-digit code is the identical brute-force
        # shape whether it's an OTP or a TOTP code.
        account = self._accounts.get_by_id(account_id)
        if account is None:
            raise MfaTokenInvalidError("This MFA challenge is invalid or expired.")
        await self._rate_limiter.check_and_increment_verify_attempt(account.phone)

        if not verify_totp_code(secret=credential.secret, code=code):
            raise MfaCodeIncorrectError("Incorrect code.")
        if account.is_suspended():
            raise AccountSuspendedError("This account is suspended.")

        return await self._issue_tokens(account=account, device_metadata=None)

    def disable_mfa(self, *, account_id: uuid.UUID, code: str) -> None:
        """Requires a valid current code, not just a bearer token —
        proves the caller still holds the second factor before removing
        it (ADR-0051 Decision 4)."""
        assert self._mfa_credentials is not None, "disable_mfa() needs mfa_credentials"
        credential = self._mfa_credentials.get_for_update(account_id)
        if credential is None:
            raise MfaNotEnrolledError("No MFA credential exists for this account.")
        if not verify_totp_code(secret=credential.secret, code=code):
            raise MfaCodeIncorrectError("Incorrect code.")

        self._mfa_credentials.delete(account_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _issue_tokens(
        self, *, account: Account, device_metadata: str | None
    ) -> TokenPairResult:
        access_token, _jti, _exp = issue_access_token(
            account_id=account.id, account_type=account.account_type
        )

        refresh_token = generate_refresh_token()
        now = datetime.now(UTC)
        session = Session(
            id=uuid.uuid4(),
            account_id=account.id,
            refresh_token_hash=hash_refresh_token(refresh_token),
            device_metadata=device_metadata,
            expires_at=now
            + timedelta(days=identity_settings.refresh_token_expire_days),
            revoked_at=None,
            created_at=now,
        )
        self._sessions.create(session)

        return TokenPairResult(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in_seconds=identity_settings.jwt_access_token_expire_minutes * 60,
        )

    def _find_session_by_hash(self, token_hash: str) -> Session | None:
        return self._sessions.get_by_refresh_token_hash(token_hash)
