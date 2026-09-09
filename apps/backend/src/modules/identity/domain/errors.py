"""Domain-level errors for Identity & Authentication.

These map to the error codes already defined in
docs/05-api/api-contracts.md §49 (Error Codes). The API layer
(modules/identity/router.py) translates these into the standard
{"data": null, "error": {"code": ..., "message": ...}, "request_id": ...}
envelope — the domain layer itself has no knowledge of HTTP.
"""

from __future__ import annotations


class IdentityDomainError(Exception):
    """Base class for all Identity domain errors."""

    #: Stable error code — must match an entry in api-contracts.md §49
    #: where one already exists there.
    code: str = "IDENTITY_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidPhoneNumberError(IdentityDomainError):
    code = "VALIDATION_FAILED"


class AccountSuspendedError(IdentityDomainError):
    code = "ACCOUNT_SUSPENDED"


class OtpChallengeNotFoundError(IdentityDomainError):
    """Raised when a challenge_id does not correspond to an active challenge.

    Deliberately mapped to the same OTP_INVALID code an incorrect OTP would
    produce, rather than a distinct "challenge not found" code — returning a
    different error for "wrong OTP" vs. "no such challenge" would let an
    attacker enumerate valid challenge_ids, which security.md §5 ("OTP
    Security") and the general "avoid enumeration risks" principle in
    security.md both require avoiding.
    """

    code = "OTP_INVALID"


class OtpIncorrectError(IdentityDomainError):
    code = "OTP_INVALID"


class OtpExpiredError(IdentityDomainError):
    code = "OTP_EXPIRED"


class OtpMaxAttemptsError(IdentityDomainError):
    code = "OTP_MAX_ATTEMPTS"


class OtpRateLimitedError(IdentityDomainError):
    code = "RATE_LIMITED"


class OtpResendCooldownError(IdentityDomainError):
    code = "RATE_LIMITED"


class RefreshTokenInvalidError(IdentityDomainError):
    code = "AUTH_INVALID"


class RefreshTokenExpiredError(IdentityDomainError):
    code = "AUTH_INVALID"


class AccessTokenInvalidError(IdentityDomainError):
    code = "AUTH_INVALID"


# --- Admin MFA (ADR-0051) ------------------------------------------------


class MfaNotEnrolledError(IdentityDomainError):
    """No identity.mfa_credentials row exists at all for this account —
    /mfa/confirm, /mfa/disable, or /mfa/verify called with nothing to
    confirm/disable/verify against."""

    code = "RESOURCE_NOT_FOUND"


class MfaAlreadyActiveError(IdentityDomainError):
    """/mfa/enroll called while an ACTIVE credential already exists —
    rejected rather than silently replaced (ADR-0051 Decision 4's own
    "prove you still have it" principle for /mfa/disable would be
    pointless if /mfa/enroll could just overwrite an active credential
    with a bearer token alone). Disable first, which itself requires a
    valid current code."""

    code = "INVALID_STATE_TRANSITION"


class MfaNotPendingError(IdentityDomainError):
    """/mfa/confirm called against a credential that isn't PENDING
    (already ACTIVE — confirmed twice)."""

    code = "INVALID_STATE_TRANSITION"


class MfaCodeIncorrectError(IdentityDomainError):
    """The submitted 6-digit code did not verify against the stored
    secret — same OTP_INVALID code the login-OTP flow already uses for
    "the code you gave is wrong," not a new MFA-specific code, since
    it's the identical shape of error from the caller's point of view."""

    code = "OTP_INVALID"


class MfaTokenInvalidError(IdentityDomainError):
    """The pre-auth mfa_token at /mfa/verify is missing, expired, has
    the wrong `purpose` claim, or doesn't correspond to an account with
    an ACTIVE MFA credential."""

    code = "AUTH_INVALID"
