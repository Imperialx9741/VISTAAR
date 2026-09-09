"""Domain-level errors for Pricing."""

from __future__ import annotations


class PricingDomainError(Exception):
    code: str = "PRICING_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class FareRuleNotFoundError(PricingDomainError):
    """Raised when no active pricing.fare_rules row exists for a given
    vehicle_category key — should never happen in practice given the
    migration seeds all 5 documented keys (ADR-0020 Decision 5), but a
    clean domain error is preferable to a raw None-related crash if a
    rule is ever deactivated without a replacement."""

    code = "RESOURCE_NOT_FOUND"


class PreviousFareQuoteNotFoundError(PricingDomainError):
    """ADR-0033. Raised by calculate_destination_change_fare() when no
    prior fare_quotes row exists for the ride — should never happen in
    practice (every ride gets a version-1 quote at creation, ADR-0020),
    same defensive treatment FareRuleNotFoundError above already gets.
    (Pickup change had its own caller of this error until ADR-0056,
    2026-08-31, removed the whole chargeable pickup-change path.)"""

    code = "RESOURCE_NOT_FOUND"


# --- Fare Management workflow errors (ADR-0042) ----------------------


class InvalidFareRuleInputError(PricingDomainError):
    """Creation-time validation failure (non-positive rate, unknown
    vehicle_category shape, etc.)."""

    code = "VALIDATION_FAILED"


class InvalidFareRuleStateTransitionError(PricingDomainError):
    """A submit-for-review/publish call from a status that doesn't allow
    it (ADR-0042 Decision 3 — only DRAFT->IN_REVIEW and (DRAFT or
    IN_REVIEW)->PUBLISHED are ever valid)."""

    code = "INVALID_STATE_TRANSITION"


# --- Platform Fee Management (ADR-0045) -------------------------------


class PlatformFeeRuleNotFoundError(PricingDomainError):
    code = "RESOURCE_NOT_FOUND"


class InvalidPlatformFeeRuleInputError(PricingDomainError):
    code = "VALIDATION_FAILED"


class InvalidPlatformFeeRuleStateTransitionError(PricingDomainError):
    """Same DRAFT/IN_REVIEW/PUBLISHED lifecycle as FareRule above."""

    code = "INVALID_STATE_TRANSITION"
