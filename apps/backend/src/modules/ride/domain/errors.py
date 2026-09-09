"""Domain-level errors for Ride.

Reuse existing error codes from docs/05-api/api-contracts.md §49 rather
than inventing new ones.
"""

from __future__ import annotations

import uuid


class RideDomainError(Exception):
    code: str = "RIDE_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidCoordinateError(RideDomainError):
    """api-contracts.md §12's "Validate coordinates" step. Only standard
    geographic-range validation — no service-area/geofence restriction
    is documented anywhere, so none is enforced (ADR-0010 discussion)."""

    code = "VALIDATION_FAILED"


class InvalidCancellationReasonError(RideDomainError):
    """cancel's `reason` must be a non-empty string within
    ride.state_history.reason's VARCHAR(100) — no canonical reason enum
    is documented anywhere (Task 3.3)."""

    code = "VALIDATION_FAILED"


class RideNotFoundError(RideDomainError):
    """Also used when the ride exists but belongs to another customer —
    same "don't reveal existence to an unauthorized caller" reasoning
    used throughout this codebase (e.g.
    modules.vehicle.domain.errors.VehicleNotFoundError). Reuses the
    ride-specific RIDE_NOT_FOUND code (api-contracts.md §49) rather than
    the generic RESOURCE_NOT_FOUND, since api-contracts.md documents this
    endpoint with that specific code."""

    code = "RIDE_NOT_FOUND"


class RideNotCancellableError(RideDomainError):
    """api-contracts.md §49. Task 3.3 only ever reaches this for a ride
    that isn't SEARCHING — ACCEPTED/ARRIVED cancellation isn't
    implemented yet (ADR-0012 Item 3, blocked on Task 3.4)."""

    code = "RIDE_NOT_CANCELLABLE"


class RideAlreadyAssignedError(RideDomainError):
    """Phase 3 / Task 3.4 (ADR-0014). api-contracts.md §16: Accept Offer
    requires the ride still be SEARCHING; raised when it no longer is
    (already ACCEPTED by a resolved race, or moved on/cancelled by some
    other path). Reuses the existing RIDE_ALREADY_ASSIGNED code
    (api-contracts.md §49)."""

    code = "RIDE_ALREADY_ASSIGNED"


class RideNotInExpectedStateError(RideDomainError):
    """Phase 06/07 (ADR-0028). Raised by mark_arrived() when the ride
    isn't ACCEPTED, and by start_ride() when it isn't ARRIVED — the same
    "not in the expected starting state" treatment Approve/Reject
    Driver/Vehicle already use their own INVALID_STATE_TRANSITION code
    for (api-contracts.md §49). No ride-lifecycle-specific code is
    documented for these two cases (unlike completion, which has its
    own RIDE_NOT_COMPLETABLE — see below), so the generic code is
    reused rather than one invented."""

    code = "INVALID_STATE_TRANSITION"


class RideNotCompletableError(RideDomainError):
    """Phase 06/07 (ADR-0028). Raised by complete_ride() when the ride
    isn't STARTED. Reuses the existing, previously-unused
    RIDE_NOT_COMPLETABLE code (api-contracts.md §49) — documented since
    at least this session's earlier work, never had a raiser until now."""

    code = "RIDE_NOT_COMPLETABLE"


class NotWithinPickupRadiusError(RideDomainError):
    """api-contracts.md §17 — Driver Arrival, a retriable GPS-verification
    failure (attempts 1 through RIDE_GPS_MAX_ATTEMPTS_BEFORE_REVIEW - 1
    for a given ride; see GpsVerificationFailedError for what happens
    after that)."""

    code = "NOT_WITHIN_PICKUP_RADIUS"


class NotWithinDestinationRadiusError(RideDomainError):
    """api-contracts.md §28 — Ride Completion, the COMPLETION-verification
    equivalent of NotWithinPickupRadiusError above."""

    code = "NOT_WITHIN_DESTINATION_RADIUS"


class GpsVerificationFailedError(RideDomainError):
    """ADR-0028 Decision 1/§3: raised instead of NotWithinPickupRadius/
    DestinationRadiusError once RIDE_GPS_MAX_ATTEMPTS_BEFORE_REVIEW
    failed attempts already exist for this (ride_id, verification_type)
    — "past normal retry, needs human judgment." Reuses the existing,
    previously-unused GPS_VERIFICATION_FAILED code (api-contracts.md
    §49). `dispute_id` (BR-124/BR-125, ADR-0032) is set by mark_arrived()/
    complete_ride() to the GPS dispute this same failure just opened —
    the router surfaces it via the error envelope's `details` field
    (shared/api_envelope.py) so the caller can discover and act on it;
    optional only so this error class stays constructible without one in
    contexts that don't have a dispute yet (there are none in practice,
    but this avoids a required positional-after-message footgun)."""

    code = "GPS_VERIFICATION_FAILED"

    def __init__(self, message: str, *, dispute_id: uuid.UUID | None = None) -> None:
        super().__init__(message)
        self.dispute_id = dispute_id


class RideOtpInvalidError(RideDomainError):
    """api-contracts.md §18/§49 — reuses the same OTP_INVALID code the
    login-OTP flow already uses (modules.identity), a different
    resource but the same documented error-code vocabulary."""

    code = "OTP_INVALID"


class RideOtpExpiredError(RideDomainError):
    code = "OTP_EXPIRED"


class RideOtpMaxAttemptsError(RideDomainError):
    code = "OTP_MAX_ATTEMPTS"


class EarlyDropAlreadyRequestedError(RideDomainError):
    """Phase 08 (ADR-0030). Raised by request_early_drop() when a
    not-yet-fully-confirmed early-drop request already exists for this
    ride — only one may be pending at a time. Reuses the same
    INVALID_STATE_TRANSITION code request_early_drop()'s ride-not-STARTED
    check also uses (api-contracts.md §49) — no early-drop-specific code
    is documented."""

    code = "INVALID_STATE_TRANSITION"


class EarlyDropRequestNotFoundError(RideDomainError):
    """Phase 08 (ADR-0030). Raised by confirm_early_drop() when no
    pending early-drop request exists for this ride to confirm/reject."""

    code = "RIDE_NOT_FOUND"


class EarlyDropLocationRequiredError(RideDomainError):
    """Phase 08 (ADR-0030 Decision 3). Raised by confirm_early_drop()
    when the caller is the driver confirming (`confirmed: true`) without
    supplying latitude/longitude — the driver's own confirm call is the
    one place this codebase records `gps_location` for early drop."""

    code = "VALIDATION_FAILED"


class GpsDisputeNotFoundError(RideDomainError):
    """BR-124/BR-125 (ADR-0032). Also used when the dispute exists but
    belongs to a ride the caller does not own — same IDOR-safe treatment
    as RideNotFoundError."""

    code = "RIDE_NOT_FOUND"


class GpsDisputeNotOpenError(RideDomainError):
    """BR-124/BR-125 (ADR-0032). Raised by submit_gps_dispute_evidence()
    once the dispute is no longer OPEN (already RESOLVED, or lazily
    transitioned to EXPIRED by this same call observing evidence_deadline
    has passed — ADR-0032 Decision 5), and by resolve_gps_dispute() for
    the same two cases. No dispute-specific code is documented, so the
    same generic code every other "not in the expected state" case in
    this module already reuses (RideNotInExpectedStateError) applies
    here too."""

    code = "INVALID_STATE_TRANSITION"


class InvalidGpsDisputeEvidenceError(RideDomainError):
    """BR-125 (ADR-0032). Raised when evidence_type is not one of
    PHOTO/VIDEO/DOCUMENT/TEXT, or the wrong field (uri vs. text) is
    supplied/missing for the given evidence_type."""

    code = "VALIDATION_FAILED"


class InvalidGpsDisputeActionError(RideDomainError):
    """BR-124 (ADR-0032). Raised by resolve_gps_dispute() when `action`
    is not exactly "APPROVE" or "REJECT" — the same "client cannot
    invent an action value" treatment PenaltyService.resolve_penalty()
    already gives its own action field (ADR-0023)."""

    code = "VALIDATION_FAILED"


class PickupChangeAlreadyRequestedError(RideDomainError):
    """ADR-0033; kept by ADR-0056 (2026-08-31) purely as a defensive
    backward-compatibility guard. Raised by request_pickup_change() when
    a not-yet-resolved pickup-change request already exists for this
    ride — only one may be pending at a time, same "only one pending"
    constraint EarlyDropAlreadyRequestedError already enforces for early
    drop. New code never creates a pending PICKUP_CHANGE request anymore
    (ADR-0056 rejects a >threshold change outright instead), so this can
    now only ever fire against a request row that predates that ADR."""

    code = "INVALID_STATE_TRANSITION"


class PickupChangeTooFarError(RideDomainError):
    """ADR-0056 (2026-08-31, owner decision). Raised by
    request_pickup_change() when the new pickup is beyond
    RIDE_PICKUP_CHANGE_THRESHOLD_METERS (100m) — replaces the old
    driver-PROCEED/PASS flow entirely. The ride is left completely
    unchanged; the customer must cancel this ride and book a new one if
    they need a pickup this far away."""

    code = "PICKUP_CHANGE_TOO_FAR"


class DestinationChangeAlreadyRequestedError(RideDomainError):
    """ADR-0033 Decision 9. Raised by request_destination_change() when
    a not-yet-resolved DESTINATION_CHANGE request already exists for
    this ride — same "only one pending" constraint
    PickupChangeAlreadyRequestedError already enforces for pickup
    change."""

    code = "INVALID_STATE_TRANSITION"


class DestinationChangeNotFoundError(RideDomainError):
    """ADR-0033 Decision 9. Raised by confirm_destination_change() when
    no pending DESTINATION_CHANGE request exists for this ride."""

    code = "RIDE_NOT_FOUND"


class DestinationChangeNotAwaitingConfirmationError(RideDomainError):
    """ADR-0033 Decision 9. Raised by confirm_destination_change() when
    the request isn't AWAITING_CUSTOMER_CONFIRMATION (already confirmed/
    rejected)."""

    code = "INVALID_STATE_TRANSITION"


class InvalidScheduledForError(RideDomainError):
    """ADR-0057, BR-137. `scheduled_for` must be between 1 and 24 hours
    from now — engineering defaults the owner approved as a starting
    point, not independently re-derived business values."""

    code = "VALIDATION_FAILED"


class InvalidLinkedContactError(RideDomainError):
    """ADR-0057, BR-138-140 (Book for Someone Else). `linked_contact`'s
    `name`/`phone` must both be present or both absent — never just one
    — and `phone` must be a valid phone number (reuses
    modules.identity.domain.phone_number.PhoneNumber's own E.164
    validation/normalization, translated to this module's own error
    type so callers only ever need to catch RideDomainError)."""

    code = "VALIDATION_FAILED"


class ScheduledRideNotFoundError(RideDomainError):
    """ADR-0057 — raised by promote_scheduled_ride_to_searching() (the
    Celery Beat task's own composition point) when the ride no longer
    exists or is no longer SCHEDULED (e.g. the customer cancelled it
    between the poll finding it due and the task actually running).
    Not customer-facing — this method has no HTTP endpoint, only the
    Beat task calls it, and treats this as a no-op skip, not an error
    to surface anywhere."""

    code = "RIDE_NOT_FOUND"
