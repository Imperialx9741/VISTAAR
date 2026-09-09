"""Domain-level errors for Advertisement."""

from __future__ import annotations


class AdvertisementDomainError(Exception):
    code: str = "ADVERTISEMENT_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidCampaignInputError(AdvertisementDomainError):
    code = "VALIDATION_FAILED"


class CampaignNotFoundError(AdvertisementDomainError):
    code = "RESOURCE_NOT_FOUND"


class DriverCampaignNotFoundError(AdvertisementDomainError):
    """Also used when the assignment exists but belongs to another
    driver — same IDOR-safe "not found either way" pattern used
    throughout this codebase."""

    code = "RESOURCE_NOT_FOUND"


class InvalidDriverCampaignStateError(AdvertisementDomainError):
    """Raised when a command is attempted against a driver_campaign not
    in the state that command requires (e.g. submitting proof twice,
    verifying before proof is submitted, calculating a payout before
    verification)."""

    code = "INVALID_STATE_TRANSITION"


class PayoutAlreadyCalculatedError(AdvertisementDomainError):
    """uq_payouts_driver_campaign — at most one payout per driver
    campaign (migration 83c95d7eaf67)."""

    code = "INVALID_STATE_TRANSITION"


class PayoutNotFoundError(AdvertisementDomainError):
    code = "RESOURCE_NOT_FOUND"


class PayoutAlreadySettledError(AdvertisementDomainError):
    code = "INVALID_STATE_TRANSITION"


# --- Advertisement Admin API (ADR-0046) --------------------------------


class InvalidCampaignStateTransitionError(AdvertisementDomainError):
    """A pause/resume/end call from a status that doesn't allow it
    (ADR-0046 Decision 1 — ACTIVE <-> PAUSED, (ACTIVE or PAUSED) ->
    ENDED are the only valid transitions)."""

    code = "INVALID_STATE_TRANSITION"


class CampaignNotActiveError(AdvertisementDomainError):
    """Raised by AssignDriver against a PAUSED/ENDED campaign — pausing
    stops new assignments without disturbing ones already in flight."""

    code = "INVALID_STATE_TRANSITION"
