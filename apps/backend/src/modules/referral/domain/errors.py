"""Domain-level errors for Referral.

Reuse existing error codes from docs/05-api/api-contracts.md §49 rather
than inventing new ones.
"""

from __future__ import annotations


class ReferralDomainError(Exception):
    code: str = "REFERRAL_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ReferralCodeNotFoundError(ReferralDomainError):
    """api-contracts.md §49's documented REFERRAL_INVALID."""

    code = "REFERRAL_INVALID"


class SelfReferralError(ReferralDomainError):
    """BR-025 / database-design.md §25.2: "Prevent self-referral at
    application and database policy level where practical." Reuses
    REFERRAL_INVALID — an attempted self-referral is simply not a valid
    referral, not a distinct documented code."""

    code = "REFERRAL_INVALID"


class AlreadyReferredError(ReferralDomainError):
    """api-contracts.md §49's documented REFERRAL_ALREADY_ATTACHED —
    uq_referrals_referred_id: a referred party can only ever be
    referred once."""

    code = "REFERRAL_ALREADY_ATTACHED"


class ReferralNotFoundError(ReferralDomainError):
    code = "RESOURCE_NOT_FOUND"


class ReferralNotAttachedError(ReferralDomainError):
    """Raised when qualification is attempted against a referral not in
    ATTACHED status (e.g. already ACTIVATED)."""

    code = "INVALID_STATE_TRANSITION"


# --- Referral Reward Configuration (ADR-0043) --------------------------


class RewardConfigNotFoundError(ReferralDomainError):
    code = "RESOURCE_NOT_FOUND"


class InvalidRewardConfigInputError(ReferralDomainError):
    code = "VALIDATION_FAILED"


class InvalidRewardConfigStateTransitionError(ReferralDomainError):
    """A submit-for-review/publish call from a status that doesn't allow
    it — same DRAFT/IN_REVIEW/PUBLISHED lifecycle ADR-0042 established
    for pricing.fare_rules."""

    code = "INVALID_STATE_TRANSITION"
