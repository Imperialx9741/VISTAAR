"""Pydantic request DTOs for the Ride API.

Mirrors docs/05-api/api-contracts.md §12's "Customer Requests Ride" and
§19's "Customer Cancellation" requests, extended with `cab_tier`
(ADR-0020 Decision 1) — required when `vehicle_category` is `CAB`, must
be omitted/null otherwise; RideService.create_ride() -> Ride.new() ->
validate_cab_tier() enforces this, not Pydantic. Also extended
(api-contracts.md §12.1, ADR-0057) with `scheduled_for`/`linked_contact`
— both optional and independent of each other; window/pairing
validation happens the same way (RideService.create_ride() ->
Ride.new() -> validate_scheduled_for()/validate_linked_contact()), not
here.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class GeoPointBody(BaseModel):
    latitude: float
    longitude: float


class LinkedContactBody(BaseModel):
    """ADR-0057 (Book for Someone Else) — both fields required together
    at the Pydantic level (there is no way to make Pydantic itself
    enforce "both or neither" across CreateRideBody's own optional
    `linked_contact` field, so that half of the pairing rule is
    RideService's own job, matching `cab_tier`'s precedent above)."""

    name: str
    phone: str


class CreateRideBody(BaseModel):
    pickup: GeoPointBody
    destination: GeoPointBody
    vehicle_category: str
    cab_tier: str | None = None
    # payment_method removed 2026-09-03 — owner decision: no user-facing
    # UPI/CASH selection in the app, the User settles directly with the
    # Sarthi by whatever means they agree (P2P model, ADR-0025). This
    # field was always accepted-but-unpersisted (ADR-0010 Decision 2)
    # and never influenced ride creation — see
    # modules/ride/domain/entities.py's own docstring for the full
    # account. Deliberately not kept as an ignored/optional field: a
    # client sending it now gets FastAPI/Pydantic's default "extra
    # field ignored" behavior, matching every other schema in this
    # codebase's mass-assignment posture (security-review-pass-2
    # §2.2) — nothing needs to notice or reject it.
    scheduled_for: datetime | None = None
    linked_contact: LinkedContactBody | None = None


class CancelRideBody(BaseModel):
    reason: str


class GpsVerificationBody(BaseModel):
    """Phase 06/07 (ADR-0028). api-contracts.md §17 (Driver Arrival) and
    §28 (Ride Completion) document "server verifies driver location
    against [pickup/destination] radius" but, unlike §12's `pickup`/
    `destination`, never show a request body example — the driver's
    current GPS reading has to travel to the server somehow, so this
    mirrors GeoPointBody's own two-field shape rather than inventing a
    new one."""

    latitude: float
    longitude: float


class StartRideBody(BaseModel):
    otp: str


class RequestEarlyDropBody(BaseModel):
    """Phase 08 (ADR-0030). api-contracts.md §27's documented Request
    body."""

    reason: str | None = None


class ConfirmEarlyDropBody(BaseModel):
    """Phase 08 (ADR-0030). api-contracts.md §27's documented Confirm
    body, extended with `latitude`/`longitude` (ADR-0030 Decision 3) —
    required only when the caller is the driver, enforced at the service
    layer (RideService.confirm_early_drop()), not here, matching
    `cab_tier`'s own precedent (CreateRideBody's own docstring)."""

    confirmed: bool
    latitude: float | None = None
    longitude: float | None = None


class GpsDisputeEvidenceUploadUrlBody(BaseModel):
    """BR-125 (ADR-0032). Same shape as RequestUploadUrlBody
    (modules.driver.schemas) — content_type validated at the storage
    layer (shared.storage), not here."""

    content_type: str


class SubmitGpsDisputeEvidenceBody(BaseModel):
    """BR-125 (ADR-0032). `evidence_type` must be one of PHOTO/VIDEO/
    DOCUMENT/TEXT; `uri` is required for the first three, `text` for
    TEXT — enforced at the service layer
    (RideService.submit_gps_dispute_evidence()), matching every other
    conditional-requirement field in this module."""

    evidence_type: str
    uri: str | None = None
    text: str | None = None


class RequestPickupChangeBody(BaseModel):
    """Ride Modifications (ADR-0033). api-contracts.md §22's documented
    Pickup Change request — same two-field shape as GeoPointBody, kept
    as its own class rather than reused since this one has its own
    docstring/call-site meaning (the new pickup, not the ride's
    original)."""

    latitude: float
    longitude: float


class RequestDestinationChangeBody(BaseModel):
    """ADR-0033 Decision 9. api-contracts.md §25's documented Destination
    Change request — same two-field shape as GeoPointBody, kept as its
    own class for the same reason RequestPickupChangeBody is (the new
    destination, not the ride's original)."""

    latitude: float
    longitude: float


class ConfirmDestinationChangeBody(BaseModel):
    """ADR-0033 Decision 9. api-contracts.md §26's documented Destination
    Change Confirmation request — this one documents a
    `change_request_id` field (pickup change's own confirmation
    endpoint, which had no such field, was removed by ADR-0056); the
    router uses it as a consistency check against the ride's own
    currently-pending request (RideService.confirm_destination_change()
    is still ride_id-scoped internally, matching every other "one
    pending request" lookup in this module) rather than as the primary
    lookup key."""

    change_request_id: str
    confirmed: bool
