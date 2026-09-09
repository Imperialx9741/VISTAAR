"""Unit tests for IdentityService (the application layer), using in-memory
fake implementations of every port (ports.py) instead of real
Postgres/Redis — fast, deterministic, and able to control "now" precisely
for expiry testing.

Real-infrastructure integration coverage (actual Postgres + Redis + HTTP)
lives in tests/test_identity_api.py; this file is the "unit" half of the
"unit + integration testing" the task requires, not a replacement for it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pyotp
import pytest

from modules.identity.domain.entities import (
    Account,
    AccountStatus,
    AccountType,
    MfaCredential,
    MfaCredentialStatus,
    OtpChallenge,
    OtpChallengeStatus,
    Session,
)
from modules.identity.domain.errors import (
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
    RefreshTokenInvalidError,
)
from modules.identity.domain.mfa import verify_totp_code
from modules.identity.service import (
    IdentityService,
    MfaRequiredResult,
    TokenPairResult,
)


class FakeAccountRepository:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, Account] = {}

    def get_by_phone(self, phone: str) -> Account | None:
        return next((a for a in self.by_id.values() if a.phone == phone), None)

    def get_by_id(self, account_id: uuid.UUID) -> Account | None:
        return self.by_id.get(account_id)

    def create(self, *, account_type: AccountType, phone: str) -> Account:
        now = datetime.now(UTC)
        account = Account(
            id=uuid.uuid4(),
            account_type=account_type,
            phone=phone,
            status=AccountStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        self.by_id[account.id] = account
        return account


class FakeOtpChallengeRepository:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, OtpChallenge] = {}

    def create(self, challenge: OtpChallenge) -> OtpChallenge:
        self.by_id[challenge.id] = challenge
        return challenge

    def get_by_id(self, challenge_id: uuid.UUID) -> OtpChallenge | None:
        return self.by_id.get(challenge_id)

    def invalidate_active_for_phone(self, phone: str) -> None:
        for c in self.by_id.values():
            if c.phone == phone and c.status == OtpChallengeStatus.ACTIVE:
                c.status = OtpChallengeStatus.INVALIDATED

    def save(self, challenge: OtpChallenge) -> None:
        self.by_id[challenge.id] = challenge

    def count_active_for_phone_since(self, phone: str, since: datetime) -> int:
        return sum(
            1 for c in self.by_id.values() if c.phone == phone and c.created_at >= since
        )


class FakeSessionRepository:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, Session] = {}

    def create(self, session: Session) -> Session:
        self.by_id[session.id] = session
        return session

    def get_by_id(self, session_id: uuid.UUID) -> Session | None:
        return self.by_id.get(session_id)

    def get_by_refresh_token_hash(self, token_hash: str) -> Session | None:
        return next(
            (s for s in self.by_id.values() if s.refresh_token_hash == token_hash),
            None,
        )

    def save(self, session: Session) -> None:
        self.by_id[session.id] = session

    def revoke(self, session_id: uuid.UUID) -> None:
        s = self.by_id[session_id]
        s.revoked_at = datetime.now(UTC)


class FakeSmsProvider:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_otp(self, phone_number: str, otp: str) -> None:
        self.sent.append((phone_number, otp))


class FakeRateLimiter:
    """No-op: rate limiting itself is covered by dedicated tests against
    the real Redis-backed implementation in test_identity_api.py."""

    async def check_and_increment_request(self, phone: str) -> None:
        return None

    async def check_and_increment_verify_attempt(self, phone: str) -> None:
        return None

    async def check_and_increment_request_ip(self, ip_address: str) -> None:
        return None

    async def check_and_increment_verify_attempt_ip(self, ip_address: str) -> None:
        return None


class FakeDenylist:
    def __init__(self) -> None:
        self.revoked: dict[str, int] = {}

    async def revoke(self, jti: str, *, ttl_seconds: int) -> None:
        self.revoked[jti] = ttl_seconds

    async def is_revoked(self, jti: str) -> bool:
        return jti in self.revoked


class FakeMfaCredentialRepository:
    def __init__(self) -> None:
        self.by_account: dict[uuid.UUID, MfaCredential] = {}

    def get(self, account_id: uuid.UUID) -> MfaCredential | None:
        return self.by_account.get(account_id)

    def get_for_update(self, account_id: uuid.UUID) -> MfaCredential | None:
        return self.by_account.get(account_id)

    def upsert(self, credential: MfaCredential) -> MfaCredential:
        self.by_account[credential.account_id] = credential
        return credential

    def save(self, credential: MfaCredential) -> None:
        self.by_account[credential.account_id] = credential

    def delete(self, account_id: uuid.UUID) -> None:
        self.by_account.pop(account_id, None)


@pytest.fixture
def wiring() -> dict[str, object]:
    return {
        "accounts": FakeAccountRepository(),
        "challenges": FakeOtpChallengeRepository(),
        "sessions": FakeSessionRepository(),
        "sms": FakeSmsProvider(),
        "rate_limiter": FakeRateLimiter(),
        "denylist": FakeDenylist(),
        "mfa_credentials": FakeMfaCredentialRepository(),
    }


@pytest.fixture
def service(wiring: dict[str, object]) -> IdentityService:
    return IdentityService(**wiring)  # type: ignore[arg-type]


PHONE = "+919999999999"


@pytest.mark.anyio
async def test_1_otp_request_flow_sends_otp_and_returns_challenge(
    service: IdentityService, wiring: dict[str, object]
) -> None:
    result = await service.request_otp(
        raw_phone=PHONE, account_type=AccountType.CUSTOMER
    )

    assert result.expires_in_seconds > 0
    sms: FakeSmsProvider = wiring["sms"]  # type: ignore[assignment]
    assert len(sms.sent) == 1
    assert sms.sent[0][0] == PHONE
    assert sms.sent[0][1].isdigit()


@pytest.mark.anyio
async def test_2_otp_verification_succeeds_and_issues_tokens(
    service: IdentityService, wiring: dict[str, object]
) -> None:
    request_result = await service.request_otp(
        raw_phone=PHONE, account_type=AccountType.CUSTOMER
    )
    sms: FakeSmsProvider = wiring["sms"]  # type: ignore[assignment]
    _, otp = sms.sent[-1]

    tokens = await service.verify_otp(
        challenge_id=request_result.challenge_id,
        otp=otp,
    )

    assert isinstance(tokens, TokenPairResult)  # no MFA credential enrolled
    assert tokens.access_token
    assert tokens.refresh_token
    assert tokens.expires_in_seconds > 0


@pytest.mark.anyio
async def test_3_expired_otp_is_rejected(
    service: IdentityService, wiring: dict[str, object]
) -> None:
    request_result = await service.request_otp(
        raw_phone=PHONE, account_type=AccountType.CUSTOMER
    )
    sms: FakeSmsProvider = wiring["sms"]  # type: ignore[assignment]
    _, otp = sms.sent[-1]

    challenges: FakeOtpChallengeRepository = wiring["challenges"]  # type: ignore[assignment]
    stored = challenges.get_by_id(request_result.challenge_id)
    assert stored is not None
    stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)

    with pytest.raises(OtpExpiredError):
        await service.verify_otp(
            challenge_id=request_result.challenge_id,
            otp=otp,
        )


@pytest.mark.anyio
async def test_4_otp_cannot_be_reused_after_successful_verification(
    service: IdentityService, wiring: dict[str, object]
) -> None:
    request_result = await service.request_otp(
        raw_phone=PHONE, account_type=AccountType.CUSTOMER
    )
    sms: FakeSmsProvider = wiring["sms"]  # type: ignore[assignment]
    _, otp = sms.sent[-1]

    await service.verify_otp(
        challenge_id=request_result.challenge_id,
        otp=otp,
    )

    with pytest.raises(OtpChallengeNotFoundError):
        await service.verify_otp(
            challenge_id=request_result.challenge_id,
            otp=otp,
        )


@pytest.mark.anyio
async def test_5_invalid_otp_is_rejected_and_counts_as_an_attempt(
    service: IdentityService, wiring: dict[str, object]
) -> None:
    request_result = await service.request_otp(
        raw_phone=PHONE, account_type=AccountType.CUSTOMER
    )

    with pytest.raises(OtpIncorrectError):
        await service.verify_otp(
            challenge_id=request_result.challenge_id,
            otp="000000",
        )

    challenges: FakeOtpChallengeRepository = wiring["challenges"]  # type: ignore[assignment]
    stored = challenges.get_by_id(request_result.challenge_id)
    assert stored is not None
    assert stored.attempts == 1


@pytest.mark.anyio
async def test_max_attempts_exhausted_rejects_further_verification(
    service: IdentityService, wiring: dict[str, object]
) -> None:
    request_result = await service.request_otp(
        raw_phone=PHONE, account_type=AccountType.CUSTOMER
    )
    challenges: FakeOtpChallengeRepository = wiring["challenges"]  # type: ignore[assignment]
    stored = challenges.get_by_id(request_result.challenge_id)
    assert stored is not None
    stored.attempts = stored.max_attempts

    with pytest.raises(OtpMaxAttemptsError):
        await service.verify_otp(
            challenge_id=request_result.challenge_id,
            otp="000000",
        )


@pytest.mark.anyio
async def test_6_access_token_is_issued_and_decodable(
    service: IdentityService, wiring: dict[str, object]
) -> None:
    request_result = await service.request_otp(
        raw_phone=PHONE, account_type=AccountType.CUSTOMER
    )
    sms: FakeSmsProvider = wiring["sms"]  # type: ignore[assignment]
    _, otp = sms.sent[-1]

    tokens = await service.verify_otp(
        challenge_id=request_result.challenge_id,
        otp=otp,
    )
    assert isinstance(tokens, TokenPairResult)  # no MFA credential enrolled

    from modules.identity.security import decode_access_token

    payload = decode_access_token(tokens.access_token)
    assert payload["account_type"] == AccountType.CUSTOMER.value
    assert "jti" in payload


@pytest.mark.anyio
async def test_7_refresh_flow_issues_a_new_token_pair_and_revokes_the_old_session(
    service: IdentityService, wiring: dict[str, object]
) -> None:
    request_result = await service.request_otp(
        raw_phone=PHONE, account_type=AccountType.CUSTOMER
    )
    sms: FakeSmsProvider = wiring["sms"]  # type: ignore[assignment]
    _, otp = sms.sent[-1]
    first = await service.verify_otp(
        challenge_id=request_result.challenge_id,
        otp=otp,
    )
    assert isinstance(first, TokenPairResult)  # no MFA credential enrolled

    second = await service.refresh(refresh_token=first.refresh_token)
    assert second.refresh_token != first.refresh_token

    with pytest.raises(RefreshTokenInvalidError):
        await service.refresh(refresh_token=first.refresh_token)


@pytest.mark.anyio
async def test_8_logout_revokes_session_and_denies_the_access_token(
    service: IdentityService, wiring: dict[str, object]
) -> None:
    request_result = await service.request_otp(
        raw_phone=PHONE, account_type=AccountType.CUSTOMER
    )
    sms: FakeSmsProvider = wiring["sms"]  # type: ignore[assignment]
    _, otp = sms.sent[-1]
    tokens = await service.verify_otp(
        challenge_id=request_result.challenge_id,
        otp=otp,
    )
    assert isinstance(tokens, TokenPairResult)  # no MFA credential enrolled

    await service.logout(
        access_token=tokens.access_token, refresh_token=tokens.refresh_token
    )

    denylist: FakeDenylist = wiring["denylist"]  # type: ignore[assignment]
    from modules.identity.security import decode_access_token

    payload = decode_access_token(tokens.access_token)
    assert await denylist.is_revoked(payload["jti"]) is True

    with pytest.raises(RefreshTokenInvalidError):
        await service.refresh(refresh_token=tokens.refresh_token)


@pytest.mark.anyio
async def test_suspended_account_cannot_request_otp(
    service: IdentityService, wiring: dict[str, object]
) -> None:
    accounts: FakeAccountRepository = wiring["accounts"]  # type: ignore[assignment]
    account = accounts.create(account_type=AccountType.CUSTOMER, phone=PHONE)
    account.status = AccountStatus.SUSPENDED

    with pytest.raises(AccountSuspendedError):
        await service.request_otp(raw_phone=PHONE, account_type=AccountType.CUSTOMER)


@pytest.mark.anyio
async def test_new_phone_number_is_registered_on_first_successful_verification(
    service: IdentityService, wiring: dict[str, object]
) -> None:
    accounts: FakeAccountRepository = wiring["accounts"]  # type: ignore[assignment]
    assert accounts.get_by_phone(PHONE) is None

    request_result = await service.request_otp(
        raw_phone=PHONE, account_type=AccountType.CUSTOMER
    )
    sms: FakeSmsProvider = wiring["sms"]  # type: ignore[assignment]
    _, otp = sms.sent[-1]

    await service.verify_otp(
        challenge_id=request_result.challenge_id,
        otp=otp,
    )

    assert accounts.get_by_phone(PHONE) is not None


# --- Admin MFA (ADR-0051) ----------------------------------------------

NOW = datetime(2026, 8, 28, 10, 0, 0, tzinfo=UTC)


async def _new_account(wiring: dict[str, object]) -> uuid.UUID:
    accounts: FakeAccountRepository = wiring["accounts"]  # type: ignore[assignment]
    account = accounts.create(account_type=AccountType.ADMIN, phone=PHONE)
    return account.id


async def _login(service: IdentityService, wiring: dict[str, object]) -> object:
    """Full OTP login — returns either TokenPairResult or
    MfaRequiredResult depending on whether MFA is active."""
    request_result = await service.request_otp(
        raw_phone=PHONE, account_type=AccountType.ADMIN
    )
    sms: FakeSmsProvider = wiring["sms"]  # type: ignore[assignment]
    _, otp = sms.sent[-1]
    return await service.verify_otp(challenge_id=request_result.challenge_id, otp=otp)


@pytest.mark.anyio
async def test_enroll_mfa_returns_a_pending_secret_and_uri(
    service: IdentityService, wiring: dict[str, object]
) -> None:
    account_id = await _new_account(wiring)

    result = service.enroll_mfa(account_id=account_id, now=NOW)

    assert result.secret
    assert result.otpauth_uri.startswith("otpauth://totp/")
    credentials: FakeMfaCredentialRepository = wiring["mfa_credentials"]  # type: ignore[assignment]
    stored = credentials.get(account_id)
    assert stored is not None
    assert stored.status is MfaCredentialStatus.PENDING


@pytest.mark.anyio
async def test_enroll_mfa_rejects_when_already_active(
    service: IdentityService, wiring: dict[str, object]
) -> None:
    account_id = await _new_account(wiring)
    result = service.enroll_mfa(account_id=account_id, now=NOW)
    code = pyotp.TOTP(result.secret).now()
    service.confirm_mfa(account_id=account_id, code=code, now=NOW)

    with pytest.raises(MfaAlreadyActiveError):
        service.enroll_mfa(account_id=account_id, now=NOW)


@pytest.mark.anyio
async def test_confirm_mfa_activates_with_correct_code(
    service: IdentityService, wiring: dict[str, object]
) -> None:
    account_id = await _new_account(wiring)
    result = service.enroll_mfa(account_id=account_id, now=NOW)
    code = pyotp.TOTP(result.secret).now()

    service.confirm_mfa(account_id=account_id, code=code, now=NOW)

    credentials: FakeMfaCredentialRepository = wiring["mfa_credentials"]  # type: ignore[assignment]
    stored = credentials.get(account_id)
    assert stored is not None
    assert stored.status is MfaCredentialStatus.ACTIVE
    assert stored.confirmed_at == NOW


@pytest.mark.anyio
async def test_confirm_mfa_rejects_incorrect_code(
    service: IdentityService, wiring: dict[str, object]
) -> None:
    account_id = await _new_account(wiring)
    service.enroll_mfa(account_id=account_id, now=NOW)

    with pytest.raises(MfaCodeIncorrectError):
        service.confirm_mfa(account_id=account_id, code="000000", now=NOW)


@pytest.mark.anyio
async def test_confirm_mfa_rejects_when_nothing_enrolled(
    service: IdentityService, wiring: dict[str, object]
) -> None:
    account_id = await _new_account(wiring)

    with pytest.raises(MfaNotEnrolledError):
        service.confirm_mfa(account_id=account_id, code="123456", now=NOW)


@pytest.mark.anyio
async def test_confirm_mfa_rejects_when_already_active(
    service: IdentityService, wiring: dict[str, object]
) -> None:
    account_id = await _new_account(wiring)
    result = service.enroll_mfa(account_id=account_id, now=NOW)
    code = pyotp.TOTP(result.secret).now()
    service.confirm_mfa(account_id=account_id, code=code, now=NOW)

    with pytest.raises(MfaNotPendingError):
        service.confirm_mfa(account_id=account_id, code=code, now=NOW)


@pytest.mark.anyio
async def test_login_returns_mfa_required_once_active(
    service: IdentityService, wiring: dict[str, object]
) -> None:
    account_id = await _new_account(wiring)
    result = service.enroll_mfa(account_id=account_id, now=NOW)
    code = pyotp.TOTP(result.secret).now()
    service.confirm_mfa(account_id=account_id, code=code, now=NOW)

    outcome = await _login(service, wiring)

    assert isinstance(outcome, MfaRequiredResult)
    assert outcome.mfa_token
    assert outcome.expires_in_seconds > 0


@pytest.mark.anyio
async def test_verify_mfa_issues_real_tokens_with_correct_code(
    service: IdentityService, wiring: dict[str, object]
) -> None:
    account_id = await _new_account(wiring)
    result = service.enroll_mfa(account_id=account_id, now=NOW)
    secret = result.secret
    code = pyotp.TOTP(secret).now()
    service.confirm_mfa(account_id=account_id, code=code, now=NOW)

    outcome = await _login(service, wiring)
    assert isinstance(outcome, MfaRequiredResult)

    tokens = await service.verify_mfa(
        mfa_token=outcome.mfa_token, code=pyotp.TOTP(secret).now()
    )

    assert tokens.access_token
    assert tokens.refresh_token


@pytest.mark.anyio
async def test_verify_mfa_rejects_incorrect_code(
    service: IdentityService, wiring: dict[str, object]
) -> None:
    account_id = await _new_account(wiring)
    result = service.enroll_mfa(account_id=account_id, now=NOW)
    code = pyotp.TOTP(result.secret).now()
    service.confirm_mfa(account_id=account_id, code=code, now=NOW)
    outcome = await _login(service, wiring)
    assert isinstance(outcome, MfaRequiredResult)

    with pytest.raises(MfaCodeIncorrectError):
        await service.verify_mfa(mfa_token=outcome.mfa_token, code="000000")


@pytest.mark.anyio
async def test_verify_mfa_rejects_a_garbage_token(
    service: IdentityService, wiring: dict[str, object]
) -> None:
    with pytest.raises(MfaTokenInvalidError):
        await service.verify_mfa(mfa_token="not-a-real-token", code="123456")


@pytest.mark.anyio
async def test_verify_mfa_rejects_a_real_access_token(
    service: IdentityService, wiring: dict[str, object]
) -> None:
    """ADR-0051 Decision 4 — the purpose claim distinguishes an
    mfa_pending token from a real access token; a real one must not
    work here either."""
    account_id = await _new_account(wiring)
    result = service.enroll_mfa(account_id=account_id, now=NOW)
    code = pyotp.TOTP(result.secret).now()
    service.confirm_mfa(account_id=account_id, code=code, now=NOW)

    from modules.identity.security import issue_access_token

    access_token, _jti, _exp = issue_access_token(
        account_id=account_id, account_type=AccountType.ADMIN, now=NOW
    )

    with pytest.raises(MfaTokenInvalidError):
        await service.verify_mfa(
            mfa_token=access_token, code=pyotp.TOTP(result.secret).now()
        )


@pytest.mark.anyio
async def test_disable_mfa_removes_credential_with_correct_code(
    service: IdentityService, wiring: dict[str, object]
) -> None:
    account_id = await _new_account(wiring)
    result = service.enroll_mfa(account_id=account_id, now=NOW)
    secret = result.secret
    code = pyotp.TOTP(secret).now()
    service.confirm_mfa(account_id=account_id, code=code, now=NOW)

    service.disable_mfa(account_id=account_id, code=pyotp.TOTP(secret).now())

    credentials: FakeMfaCredentialRepository = wiring["mfa_credentials"]  # type: ignore[assignment]
    assert credentials.get(account_id) is None

    # Login no longer requires a second factor.
    outcome = await _login(service, wiring)
    assert isinstance(outcome, TokenPairResult)


@pytest.mark.anyio
async def test_disable_mfa_rejects_incorrect_code(
    service: IdentityService, wiring: dict[str, object]
) -> None:
    account_id = await _new_account(wiring)
    result = service.enroll_mfa(account_id=account_id, now=NOW)
    code = pyotp.TOTP(result.secret).now()
    service.confirm_mfa(account_id=account_id, code=code, now=NOW)

    with pytest.raises(MfaCodeIncorrectError):
        service.disable_mfa(account_id=account_id, code="000000")

    credentials: FakeMfaCredentialRepository = wiring["mfa_credentials"]  # type: ignore[assignment]
    assert credentials.get(account_id) is not None


@pytest.mark.anyio
async def test_disable_mfa_rejects_when_not_enrolled(
    service: IdentityService, wiring: dict[str, object]
) -> None:
    account_id = await _new_account(wiring)

    with pytest.raises(MfaNotEnrolledError):
        service.disable_mfa(account_id=account_id, code="123456")


def test_verify_totp_code_rejects_a_wrong_secret() -> None:
    """Direct domain-layer sanity check — not routed through the
    service, so it needs no fake repositories."""
    secret_a = pyotp.random_base32()
    secret_b = pyotp.random_base32()
    code = pyotp.TOTP(secret_a).now()

    assert verify_totp_code(secret=secret_a, code=code) is True
    assert verify_totp_code(secret=secret_b, code=code) is False
