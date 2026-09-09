"""Abstract interfaces (ports) the application layer depends on."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol

from modules.ride.domain.entities import (
    ChangeRequest,
    ChangeRequestType,
    Coordinates,
    EarlyDropRequest,
    GpsDispute,
    GpsDisputeEvidence,
    GpsVerification,
    Ride,
    RideOtp,
    RideStatus,
)


class RideRepository(Protocol):
    def create(self, ride: Ride) -> Ride:
        """Persists the ride.rides row and its ride.state_history
        (NULL -> ride.status) row in the same transaction — see
        docs/04-database/database-design.md §9.2 ("Every authoritative
        ride-state transition must create a history record") and
        ADR-0010 Decision 3."""
        ...

    def get_by_id(self, ride_id: uuid.UUID) -> Ride | None:
        """Added Phase 3 / Task 3.2 — modules/matching/router.py needs a
        ride's requested_vehicle_category and pickup point to dispatch a
        rematch offer after an offer is rejected or expires, and to
        include pickup in Get Current Offers' response. Not exposed via
        HTTP (GET /api/v1/rides/{ride_id} is still out of scope — see
        modules/ride/__init__.py)."""
        ...

    def get_by_id_for_update(self, ride_id: uuid.UUID) -> Ride | None:
        """Added Phase 3 / Task 3.5 (ADR-0015). Returns the ride locked
        for the remainder of the current transaction (SELECT ... FOR
        UPDATE, database-design.md §42's row-locking pattern, applied
        here to the ride row rather than a wallet row). Used by
        cancel_ride()/driver_cancel_ride() so two concurrent cancel
        attempts on the SAME ride serialize on this lock: the second one
        re-reads post-commit state and correctly sees the ride is no
        longer in a cancellable state, rather than both racing through
        a refund/penalty composition for the same event."""
        ...

    def save(
        self,
        ride: Ride,
        *,
        from_status: RideStatus,
        reason: str | None,
        actor_type: str,
        actor_id: uuid.UUID,
    ) -> None:
        """Added Phase 3 / Task 3.3 (cancel_ride()); extended Phase 3 /
        Task 3.4 (accept_ride()) to also sync driver_id/vehicle_id/
        accepted_at, and Phase 06/07 (ADR-0028) to also sync
        arrived_at/started_at/completed_at/closed_at — persists ALL of
        `ride`'s current field values (not just the ones the calling use
        case happens to change) and writes one ride.state_history row
        (`from_status` -> ride.status) in the same transaction — same
        "every authoritative transition creates a history record"
        requirement create() already satisfies. `from_status` is passed
        explicitly rather than re-derived, since by the time this is
        called `ride.status` already holds the *new* value."""
        ...

    def set_active_fare_quote(
        self, ride_id: uuid.UUID, fare_quote_id: uuid.UUID
    ) -> None:
        """ADR-0020 Decision 6. A plain UPDATE of
        ride.rides.active_fare_quote_id only — deliberately NOT save():
        setting the first (or a revised) fare quote is not itself an
        authoritative ride-state transition (`ride.status` never
        changes), so it must not write a ride.state_history row the way
        save() unconditionally does."""
        ...

    def update_current_pickup(self, ride_id: uuid.UUID, pickup: Coordinates) -> None:
        """ADR-0033 — same "plain UPDATE, not save()" shape as
        set_active_fare_quote() above, for the ≤250m auto-apply and the
        >250m PROCEED-then-confirmed cases, neither of which changes
        `ride.status`. The PASS case (which does change `ride.status`,
        ACCEPTED -> SEARCHING) instead sets `ride.current_pickup` on the
        entity and goes through the ordinary save() path below, which
        also syncs this column."""
        ...

    def update_current_destination(
        self, ride_id: uuid.UUID, destination: Coordinates
    ) -> None:
        """ADR-0033 — the destination-change equivalent of
        update_current_pickup() above. Destination change never involves
        a status transition (no driver PROCEED/PASS choice exists for
        it), so every case goes through this plain-UPDATE path, never
        save()."""
        ...

    def search(
        self,
        *,
        status: str | None,
        driver_id: uuid.UUID | None,
        customer_id: uuid.UUID | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Ride], int]:
        """Phase 16 (Search Rides, ADR-0023). Allow-listed filters only
        (api-contracts.md §51) — `status`/`driver_id`/`customer_id` are
        exactly the three query params §46 documents for this route.
        Ordered newest-first (`requested_at DESC`) so a fresh page 1 is
        always the most operationally relevant one for a monitoring
        admin. Returns (page of rides, total matching count) so the
        caller can build §50's pagination envelope without a second
        round trip through this port."""
        ...

    def list_due_scheduled(self, *, before: datetime, limit: int) -> list[Ride]:
        """ADR-0057 — SCHEDULED rides whose lock_in_at <= `before`,
        oldest lock_in_at first (so a backlog drains in the order it
        accrued). Composed only by the Beat task
        (modules/ride/tasks.py) — no HTTP endpoint calls this. `limit`
        bounds one poll's worth of work; a backlog larger than that
        simply gets picked up on the next 5-minute tick, same "correct
        first, not fastest possible" tradeoff ADR-0055's own scheduled-
        broadcast poll already accepted."""
        ...

    def count_by_status_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        """Admin Web §4.16 Rides report (ADR-0047) — every RideStatus
        value, keyed by name, for rides with `created_at` in
        [since, until). A status with zero matching rides is omitted,
        not zeroed — the caller fills gaps if it wants a dense shape."""
        ...

    def count_by_vehicle_category_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        """Same report, grouped by `requested_vehicle_category`."""
        ...

    def list_active_fare_quote_ids_for_closed_in_range(
        self, *, since: datetime, until: datetime
    ) -> list[uuid.UUID]:
        """CLOSED rides' `active_fare_quote_id`, for `created_at` in
        [since, until) — the caller (PricingRepository, a different
        schema) averages `pricing.fare_quotes.total` over these ids.
        Kept as two single-schema queries rather than one cross-schema
        join, matching this codebase's established boundary (e.g.
        modules/admin/router.py already composes RideService +
        PricingService separately for Get Ride, never joining across
        `ride`/`pricing` in one query). Excludes rides with no active
        quote (should not happen for a CLOSED ride, but not asserted
        away here)."""
        ...


class RideOtpRepository(Protocol):
    """Phase 06/07 (Ride Start OTP, ADR-0028). database-design.md §13.1."""

    def create(self, otp: RideOtp) -> RideOtp: ...

    def get_active_for_update(self, ride_id: uuid.UUID) -> RideOtp | None:
        """The current ACTIVE ride_otps row for this ride, locked for the
        remainder of the current transaction — "Only the latest valid OTP
        can start the ride" (database-design.md §13.1), so a concurrent
        start_ride()/refresh_otp() call for the same ride must serialize
        on it, same row-locking pattern as every other exclusive
        transition in this codebase."""
        ...

    def save(self, otp: RideOtp) -> None:
        """Persists `otp`'s current attempts/status back onto the
        already-locked row a prior get_active_for_update() call returned
        in this same transaction."""
        ...


class GpsVerificationRepository(Protocol):
    """Phase 06/07 (GPS Verification Foundation, ADR-0028).
    database-design.md §14.1."""

    def create(self, verification: GpsVerification) -> GpsVerification: ...

    def count_failed(self, ride_id: uuid.UUID, *, verification_type: str) -> int:
        """How many FAIL rows already exist for this (ride_id,
        verification_type) — the retry-limit check ADR-0028 Decision 1
        needs before deciding whether the next failure is retriable
        (NOT_WITHIN_PICKUP_RADIUS/NOT_WITHIN_DESTINATION_RADIUS) or
        terminal (GPS_VERIFICATION_FAILED)."""
        ...


class EarlyDropRequestRepository(Protocol):
    """Phase 08 (Early Drop, ADR-0030). database-design.md §12.1."""

    def create(self, request: EarlyDropRequest) -> EarlyDropRequest: ...

    def get_pending_for_update(self, ride_id: uuid.UUID) -> EarlyDropRequest | None:
        """The current not-yet-fully-confirmed early_drop_requests row
        for this ride (if any), locked for the remainder of the current
        transaction — same row-locking pattern as
        RideOtpRepository.get_active_for_update(). "Pending" means
        confirmed_at IS NULL (ADR-0030 Decision 1/2: confirmed_at is only
        ever set once BOTH parties have confirmed)."""
        ...

    def save(self, request: EarlyDropRequest) -> None:
        """Persists `request`'s current customer_confirmed/
        driver_confirmed/gps_location/confirmed_at back onto the
        already-locked row a prior get_pending_for_update() call returned
        in this same transaction."""
        ...

    def delete(self, request_id: uuid.UUID) -> None:
        """ADR-0030 Decision 2 — `confirmed: false` discards the pending
        request outright (no status column exists to mark it REJECTED
        with) so a fresh POST .../early-drop can be filed afterward."""
        ...


class GpsDisputeRepository(Protocol):
    """BR-124/BR-125 (GPS Dispute Manual Review, ADR-0032).
    database-design.md §14.2."""

    def create(self, dispute: GpsDispute) -> GpsDispute: ...

    def get_by_id_for_update(self, dispute_id: uuid.UUID) -> GpsDispute | None:
        """Locked for the remainder of the current transaction — same
        row-locking pattern as every other exclusive transition in this
        codebase. Used by both submit_gps_dispute_evidence() (to lazily
        expire it, ADR-0032 Decision 5) and resolve_gps_dispute()."""
        ...

    def get_by_id(self, dispute_id: uuid.UUID) -> GpsDispute | None:
        """Unlocked read — used by get_gps_dispute() (a read-only view),
        matching RideRepository's own get_by_id()/get_by_id_for_update()
        split."""
        ...

    def list_for_ride(self, ride_id: uuid.UUID) -> list[GpsDispute]:
        """List GPS Disputes for a Ride (ADR-0074, 2026-09-04) — newest
        first. A ride has at most two GPS verifications (pickup,
        destination) and therefore at most two disputes ever, so this is
        always a tiny, unpaginated result."""
        ...

    def save(self, dispute: GpsDispute) -> None:
        """Persists `dispute`'s current status/decision/decided_*
        fields back onto the already-fetched row."""
        ...

    def search(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[GpsDispute], int]:
        """Admin Search Disputes (api-contracts.md §77) — same
        allow-listed-filter/pagination shape as RideRepository.search()."""
        ...


class GpsDisputeEvidenceRepository(Protocol):
    """BR-125 (ADR-0032). database-design.md §14.3."""

    def create(self, evidence: GpsDisputeEvidence) -> GpsDisputeEvidence: ...

    def list_for_dispute(self, dispute_id: uuid.UUID) -> list[GpsDisputeEvidence]:
        """Oldest-first — matching RideOtpRepository/EarlyDropRequest
        Repository's own "most relevant last" ordering conventions
        inverted for a chronological evidence trail, which is what an
        admin reviewing a dispute actually wants to read."""
        ...


class ChangeRequestRepository(Protocol):
    """Ride Modifications — Pickup Change/Destination Change (ADR-0033).
    database-design.md §11.1, one table shared by both request types.
    `ride_id`-scoped, not `request_id`-scoped — api-contracts.md §22-24
    documents none of the three pickup-change endpoints as taking a
    request id in the path (unlike GPS disputes), matching
    EarlyDropRequestRepository's identical "one pending request per
    ride" shape."""

    def create(self, request: ChangeRequest) -> ChangeRequest: ...

    def get_pending_for_update(
        self, ride_id: uuid.UUID, *, request_type: ChangeRequestType
    ) -> ChangeRequest | None:
        """The current not-yet-resolved change_requests row for this
        ride and request_type (if any), locked for the remainder of the
        current transaction — same row-locking pattern as
        EarlyDropRequestRepository.get_pending_for_update(). "Pending"
        means status is AWAITING_DRIVER_DECISION or
        AWAITING_CUSTOMER_CONFIRMATION. Filtered by request_type so a
        pending PICKUP_CHANGE request and a pending DESTINATION_CHANGE
        request on the same ride (once the latter is implemented) never
        collide."""
        ...

    def save(self, request: ChangeRequest) -> None:
        """Persists `request`'s current status/driver_decision/
        customer_decision/new_fare_quote_id/resolved_at fields back onto
        the already-locked row a prior get_pending_for_update() call
        returned in this same transaction."""
        ...
