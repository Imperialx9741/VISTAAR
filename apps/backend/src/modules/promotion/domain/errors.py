"""Domain-level errors for Promotion.

Reuse existing error codes from docs/05-api/api-contracts.md §49 rather
than inventing new ones.
"""

from __future__ import annotations


class PromotionDomainError(Exception):
    code: str = "PROMOTION_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class EntitlementNotFoundError(PromotionDomainError):
    code = "RESOURCE_NOT_FOUND"


class PromotionExpiredError(PromotionDomainError):
    """api-contracts.md §49's documented PROMOTION_EXPIRED — raised when
    a reservation/consumption is attempted against an entitlement past
    its expires_at (BR-062: 30 days) or already EXPIRED status."""

    code = "PROMOTION_EXPIRED"


class PromotionAlreadyUsedError(PromotionDomainError):
    """api-contracts.md §49's documented PROMOTION_ALREADY_USED —
    raised when remaining_uses is exhausted, or a reservation/usage is
    attempted twice for the same (entitlement_id, ride_id)
    (uq_promotion_ride_use)."""

    code = "PROMOTION_ALREADY_USED"


class ReservationNotFoundError(PromotionDomainError):
    code = "RESOURCE_NOT_FOUND"


class InvalidPromotionInputError(PromotionDomainError):
    code = "VALIDATION_FAILED"


# --- Campaign errors (ADR-0041) -------------------------------------------
#
# CAMPAIGN_NOT_ACTIVE/CAMPAIGN_NOT_ELIGIBLE/CAMPAIGN_MINIMUM_FARE_NOT_MET/
# CAMPAIGN_USAGE_LIMIT_EXCEEDED are new entries this feature adds to
# api-contracts.md §49 (documented alongside the new redemption endpoint,
# ADR-0041 Decision 2) — no existing code covers a campaign-code
# redemption's specific failure reasons the way PROMOTION_EXPIRED/
# PROMOTION_ALREADY_USED already cover entitlement reservation/
# consumption. RESOURCE_NOT_FOUND, VALIDATION_FAILED, and
# INVALID_STATE_TRANSITION below are reused as-is (§49 already lists
# them as core errors).


class CampaignNotFoundError(PromotionDomainError):
    code = "RESOURCE_NOT_FOUND"


class InvalidCampaignInputError(PromotionDomainError):
    """Creation/edit-time validation failure (bad discount_type, negative
    discount_value, ends_at before starts_at, duplicate code, etc.)."""

    code = "VALIDATION_FAILED"


class InvalidCampaignStateTransitionError(PromotionDomainError):
    """Raised for both an invalid activate/pause/end transition and a
    PATCH attempted while status != DRAFT (ADR-0041 Decision 4 — editing
    is DRAFT-only, matching Fare Management's own
    never-rewrite-history principle)."""

    code = "INVALID_STATE_TRANSITION"


class CampaignNotActiveError(PromotionDomainError):
    """Redemption attempted while status != ACTIVE, or outside the
    campaign's [starts_at, ends_at) window."""

    code = "CAMPAIGN_NOT_ACTIVE"


class CampaignNotEligibleError(PromotionDomainError):
    """Redemption attempted by a customer the campaign does not cover —
    vehicle_category mismatch, or eligible_scope='SELECTED' and the
    customer is absent from campaign_eligible_customers."""

    code = "CAMPAIGN_NOT_ELIGIBLE"


class CampaignMinimumFareNotMetError(PromotionDomainError):
    code = "CAMPAIGN_MINIMUM_FARE_NOT_MET"


class CampaignUsageLimitExceededError(PromotionDomainError):
    """Either the campaign's total_usage_limit or the caller's own
    per_customer_use_limit has already been reached."""

    code = "CAMPAIGN_USAGE_LIMIT_EXCEEDED"
