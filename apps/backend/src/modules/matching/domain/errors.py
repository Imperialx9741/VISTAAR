"""Domain-level errors for Matching.

Reuse existing error codes from docs/05-api/api-contracts.md §49 rather
than inventing new ones.
"""

from __future__ import annotations


class MatchingDomainError(Exception):
    code: str = "MATCHING_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class OfferNotFoundError(MatchingDomainError):
    """Also used when the offer exists but belongs to another driver —
    same "don't reveal existence to an unauthorized caller" reasoning
    used throughout this codebase (e.g.
    modules.vehicle.domain.errors.VehicleNotFoundError)."""

    code = "RESOURCE_NOT_FOUND"


class OfferAlreadyRespondedError(MatchingDomainError):
    """api-contracts.md §16: raised when Reject Offer targets an offer
    that is not PENDING (already ACCEPTED, REJECTED, EXPIRED, or
    CANCELLED)."""

    code = "OFFER_ALREADY_RESPONDED"


class OfferExpiredError(MatchingDomainError):
    """Phase 3 / Task 3.4 (ADR-0014). api-contracts.md §16: Accept Offer
    against an offer whose expires_at has passed. Distinct from
    OfferAlreadyRespondedError even though MatchingService.accept_offer()
    also transitions the offer to EXPIRED here (same accurate-history
    treatment reject_offer() already gives an expired offer) — accepting
    an expired offer must fail, unlike rejecting one, so this gets its
    own documented code (api-contracts.md §49) rather than being folded
    into OFFER_ALREADY_RESPONDED."""

    code = "OFFER_EXPIRED"


class DriverNotEligibleError(MatchingDomainError):
    """Phase 3 / Task 3.4 (ADR-0014). api-contracts.md §16: Accept Offer
    re-validates driver eligibility (state-machines.md §5's "Driver
    eligible" requirement) using the same ComposedEligibilityChecker
    used at dispatch — this driver no longer passes it. Reuses the
    existing DRIVER_NOT_ELIGIBLE code, already used by Go Online/Approve
    Driver for the same underlying condition."""

    code = "DRIVER_NOT_ELIGIBLE"


class VehicleNotEligibleError(MatchingDomainError):
    """Phase 3 / Task 3.4 (ADR-0014). api-contracts.md §16: Accept Offer
    re-validates vehicle eligibility (state-machines.md §5's "Vehicle
    eligible" requirement) — this driver has no currently-eligible
    ACTIVE vehicle for the ride's requested category. Reuses the
    existing VEHICLE_NOT_ELIGIBLE code, same as NoActiveVehicleError's
    use for the related-but-distinct "no vehicle for location update"
    condition."""

    code = "VEHICLE_NOT_ELIGIBLE"


class InvalidCoordinateError(MatchingDomainError):
    """api-contracts.md §15's "Valid coordinates" check. Standard
    geographic-range validation only — duplicated in spirit from
    modules.ride.domain.entities.validate_coordinates rather than
    imported from it, to keep this module's dependency on modules.ride
    at zero (matching -> ride would be the wrong direction; see
    modules/matching/__init__.py)."""

    code = "VALIDATION_FAILED"


class DriverNotOnlineError(MatchingDomainError):
    """api-contracts.md §15: a location update requires the driver to
    be ONLINE. Reuses the existing DRIVER_NOT_ONLINE code (api-
    contracts.md §49) rather than inventing a new one."""

    code = "DRIVER_NOT_ONLINE"


class NoActiveVehicleError(MatchingDomainError):
    """No ACTIVE vehicle exists for this driver, so there is no vehicle
    category to write into the geo index. Reuses the existing
    VEHICLE_NOT_ELIGIBLE code — modules.vehicle uses the same code for
    the same underlying condition (no approved+active vehicle)."""

    code = "VEHICLE_NOT_ELIGIBLE"
