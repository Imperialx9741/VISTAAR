"""Application service (use cases) for Ride.

create_ride() validates+persists `vehicle_category` via
`Ride.new()` (which reuses `modules.vehicle.domain.entities.
validate_category`/`VehicleCategory` internally — see that module's
docstring for why this is a narrow, one-directional ride -> vehicle
dependency). `payment_method` (accepted-but-unpersisted since Task 3.1,
ADR-0010 Decision 2) was removed entirely 2026-09-03 — owner decision;
see modules/ride/domain/entities.py's own docstring for the full
account.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from modules.identity.domain.otp import generate_numeric_otp, hash_otp, verify_otp
from modules.ride.domain.entities import (
    ChangeRequest,
    ChangeRequestCustomerDecision,
    ChangeRequestStatus,
    ChangeRequestType,
    Coordinates,
    EarlyDropRequest,
    GpsDispute,
    GpsDisputeDecision,
    GpsDisputeEvidence,
    GpsDisputeEvidenceType,
    GpsDisputeStatus,
    GpsVerification,
    GpsVerificationResult,
    GpsVerificationType,
    Ride,
    RideOtp,
    RideOtpStatus,
    RideStatus,
    haversine_distance_meters,
    validate_cancellation_reason,
    validate_coordinates,
)
from modules.ride.domain.errors import (
    DestinationChangeAlreadyRequestedError,
    DestinationChangeNotAwaitingConfirmationError,
    DestinationChangeNotFoundError,
    EarlyDropAlreadyRequestedError,
    EarlyDropLocationRequiredError,
    EarlyDropRequestNotFoundError,
    GpsDisputeNotFoundError,
    GpsDisputeNotOpenError,
    GpsVerificationFailedError,
    InvalidGpsDisputeActionError,
    InvalidGpsDisputeEvidenceError,
    NotWithinDestinationRadiusError,
    NotWithinPickupRadiusError,
    PickupChangeAlreadyRequestedError,
    PickupChangeTooFarError,
    RideAlreadyAssignedError,
    RideNotCancellableError,
    RideNotCompletableError,
    RideNotFoundError,
    RideNotInExpectedStateError,
    RideOtpExpiredError,
    RideOtpInvalidError,
    RideOtpMaxAttemptsError,
    ScheduledRideNotFoundError,
)
from modules.ride.ports import (
    ChangeRequestRepository,
    EarlyDropRequestRepository,
    GpsDisputeEvidenceRepository,
    GpsDisputeRepository,
    GpsVerificationRepository,
    RideOtpRepository,
    RideRepository,
)


class RideService:
    def __init__(
        self,
        *,
        rides: RideRepository,
        gps_verifications: GpsVerificationRepository | None = None,
        ride_otps: RideOtpRepository | None = None,
        early_drop_requests: EarlyDropRequestRepository | None = None,
        gps_disputes: GpsDisputeRepository | None = None,
        gps_dispute_evidence: GpsDisputeEvidenceRepository | None = None,
        change_requests: ChangeRequestRepository | None = None,
    ) -> None:
        self._rides = rides
        # Optional (default None) so every existing caller that only ever
        # needed create/cancel/accept — most of this codebase's tests and
        # modules/matching/router.py — keeps working unchanged; only the
        # Phase 06/07 methods below (ADR-0028) require the first two,
        # request_early_drop()/confirm_early_drop() (Phase 08, ADR-0030)
        # require the third, the GPS-dispute methods below (BR-124/
        # BR-125, ADR-0032) require the next two, and the Ride
        # Modifications methods below (ADR-0033) require the last one.
        self._gps_verifications = gps_verifications
        self._ride_otps = ride_otps
        self._early_drop_requests = early_drop_requests
        self._gps_disputes = gps_disputes
        self._gps_dispute_evidence = gps_dispute_evidence
        self._change_requests = change_requests

    def get_ride(self, *, ride_id: uuid.UUID) -> Ride | None:
        """Added Phase 3 / Task 3.2 for modules/matching/router.py's
        rematch composition — see ports.py::get_by_id's docstring.
        Reused unchanged (Phase 16, ADR-0023) as the Get Ride (admin)
        implementation, composed at modules/admin/router.py — this is
        NOT the same as the still-unbuilt customer/driver-facing
        `GET /api/v1/rides/{ride_id}` (api-contracts.md §13)."""
        return self._rides.get_by_id(ride_id)

    def search_rides(
        self,
        *,
        status: str | None,
        driver_id: uuid.UUID | None,
        customer_id: uuid.UUID | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Ride], int]:
        """Phase 16 (Search Rides, ADR-0023) — admin-only, composed at
        modules/admin/router.py. Pure pass-through to the repository:
        no domain logic beyond what the port itself already documents."""
        return self._rides.search(
            status=status,
            driver_id=driver_id,
            customer_id=customer_id,
            offset=offset,
            limit=limit,
        )

    # --- Reports (Admin Web §4.16, ADR-0047) -------------------------

    def count_rides_by_status_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        return self._rides.count_by_status_in_range(since=since, until=until)

    def count_rides_by_vehicle_category_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        return self._rides.count_by_vehicle_category_in_range(since=since, until=until)

    def list_active_fare_quote_ids_for_closed_in_range(
        self, *, since: datetime, until: datetime
    ) -> list[uuid.UUID]:
        return self._rides.list_active_fare_quote_ids_for_closed_in_range(
            since=since, until=until
        )

    def create_ride(
        self,
        *,
        customer_id: uuid.UUID,
        pickup_latitude: float,
        pickup_longitude: float,
        destination_latitude: float,
        destination_longitude: float,
        vehicle_category: str,
        cab_tier: str | None = None,
        scheduled_for: datetime | None = None,
        linked_contact_name: str | None = None,
        linked_contact_phone: str | None = None,
    ) -> Ride:
        ride = Ride.new(
            customer_id=customer_id,
            pickup_latitude=pickup_latitude,
            pickup_longitude=pickup_longitude,
            destination_latitude=destination_latitude,
            destination_longitude=destination_longitude,
            vehicle_category=vehicle_category,
            cab_tier=cab_tier,
            scheduled_for=scheduled_for,
            linked_contact_name=linked_contact_name,
            linked_contact_phone=linked_contact_phone,
            now=datetime.now(UTC),
        )
        return self._rides.create(ride)

    def promote_scheduled_ride_to_searching(
        self, *, ride_id: uuid.UUID, now: datetime
    ) -> Ride:
        """ADR-0057 Decision 1 — composed only by the Celery Beat task
        (modules/ride/tasks.py), never a customer- or driver-triggered
        HTTP endpoint. A no-op-raising ScheduledRideNotFoundError (not
        surfaced anywhere — the task just skips this ride) covers the
        ride having been cancelled between the poll finding it due and
        this actually running. Uses get_by_id_for_update() (not the
        unlocked get_by_id()) so this can never race a concurrent
        customer cancellation of the same ride — same reasoning
        cancel_ride()'s own lock already documents."""
        ride = self._rides.get_by_id_for_update(ride_id)
        if ride is None or ride.status is not RideStatus.SCHEDULED:
            raise ScheduledRideNotFoundError("Ride not found or no longer SCHEDULED.")

        previous_status = ride.status
        ride.status = RideStatus.SEARCHING
        self._rides.save(
            ride,
            from_status=previous_status,
            reason=None,
            actor_type="SYSTEM",
            actor_id=ride.customer_id,
        )
        return ride

    def set_active_fare_quote(
        self, *, ride_id: uuid.UUID, fare_quote_id: uuid.UUID
    ) -> None:
        """ADR-0020 Decision 6 — composed from modules/ride/router.py
        right after PricingService.calculate_fare() creates the initial
        quote."""
        self._rides.set_active_fare_quote(ride_id, fare_quote_id)

    def accept_ride(
        self,
        *,
        ride_id: uuid.UUID,
        driver_id: uuid.UUID,
        vehicle_id: uuid.UUID,
        now: datetime,
    ) -> Ride:
        """Phase 3 / Task 3.4 (ADR-0014). domain-design.md §9.6: "Only
        the Ride Domain may transition the authoritative ride state" —
        this is why the SEARCHING -> ACCEPTED write lives here rather
        than being composed inline at the router. Must be called only
        after the caller has already acquired the driver's wallet row
        lock (modules/matching/router.py's accept-offer composition) —
        that lock is what makes the fresh re-fetch of `ride` below
        race-safe against a concurrent accept of the same offer,
        matching modules.matching.service.MatchingService.accept_offer's
        identical reasoning. `vehicle_id` is the caller's freshly
        eligibility-checked vehicle (ADR-0014 Decision 2) — not
        necessarily the offer's originally-dispatched vehicle_id."""
        ride = self._rides.get_by_id(ride_id)
        if ride is None:
            raise RideNotFoundError("Ride not found.")
        if ride.status is not RideStatus.SEARCHING:
            raise RideAlreadyAssignedError("This ride is no longer SEARCHING.")

        previous_status = ride.status
        ride.driver_id = driver_id
        ride.vehicle_id = vehicle_id
        ride.status = RideStatus.ACCEPTED
        ride.accepted_at = now
        self._rides.save(
            ride,
            from_status=previous_status,
            reason=None,
            actor_type="DRIVER",
            actor_id=driver_id,
        )
        return ride

    def cancel_ride(
        self,
        *,
        ride_id: uuid.UUID,
        customer_id: uuid.UUID,
        reason: str,
        now: datetime,
    ) -> tuple[Ride, RideStatus]:
        """Phase 3 / Task 3.3 (ADR-0012), extended Phase 3 / Task 3.5
        (ADR-0015) to also allow ACCEPTED/ARRIVED -> CANCELLED
        (state-machines.md §11) now that Task 3.4 (Accept Offer) makes
        those states reachable, and Phase 3-extension ADR-0057 to also
        allow SCHEDULED -> CANCELLED (state-machines.md §3.9) — charged
        against `scheduled_for` per BR-135, not the post-acceptance
        grace/qualifying-cancellation logic below (a SCHEDULED ride
        never had a driver assigned either). Returns (ride,
        previous_status) — the caller (modules/ride/router.py) uses
        previous_status to decide whether the post-acceptance refund/
        penalty composition applies (SEARCHING never needs it —
        ADR-0012 Decision 1, unconditionally free, not counted toward
        the "first vs. second+ qualifying cancellation" counter, since
        BR-046-049's whole framework presupposes a driver was already
        assigned and a fee already
        debited).

        Uses get_by_id_for_update() (not the unlocked get_by_id()) so
        two concurrent cancel attempts on the same ride serialize on
        this lock — critical once a real refund/penalty can follow
        (ADR-0015): the caller composes wallet credit + penalty
        recording using the SAME database transaction this lock is held
        in, so a second, blocked attempt only proceeds after the first
        commits, and correctly finds the ride already CANCELLED."""
        ride = self._rides.get_by_id_for_update(ride_id)
        if ride is None or ride.customer_id != customer_id:
            # Same response for "does not exist" and "belongs to another
            # customer" — IDOR/enumeration protection, same pattern used
            # throughout this codebase.
            raise RideNotFoundError("Ride not found.")
        if ride.status not in (
            RideStatus.SCHEDULED,
            RideStatus.SEARCHING,
            RideStatus.ACCEPTED,
            RideStatus.ARRIVED,
        ):
            raise RideNotCancellableError("This ride is not in a cancellable state.")

        validated_reason = validate_cancellation_reason(reason)
        previous_status = ride.status
        ride.status = RideStatus.CANCELLED
        ride.cancelled_at = now
        self._rides.save(
            ride,
            from_status=previous_status,
            reason=validated_reason,
            actor_type="CUSTOMER",
            actor_id=customer_id,
        )
        return ride, previous_status

    def driver_cancel_ride(
        self,
        *,
        ride_id: uuid.UUID,
        driver_id: uuid.UUID,
        reason: str,
        now: datetime,
    ) -> Ride:
        """Phase 3 / Task 3.6 (ADR-0016). state-machines.md §13
        documents driver cancellation as ACCEPTED -> CANCELLED only —
        unlike customer cancellation (§11's SEARCHING/ACCEPTED/ARRIVED),
        ARRIVED is deliberately excluded here, not an oversight. The
        caller decides the financial/behavioral consequences (₹30
        penalty + strike, or the BR-071 changed-pickup-pass exemption —
        neither is decided here; this method only performs the state
        transition domain-design.md §9.6 reserves to the Ride domain)."""
        ride = self._rides.get_by_id_for_update(ride_id)
        if ride is None or ride.driver_id != driver_id:
            raise RideNotFoundError("Ride not found.")
        if ride.status is not RideStatus.ACCEPTED:
            raise RideNotCancellableError("This ride is not in a cancellable state.")

        validated_reason = validate_cancellation_reason(reason)
        previous_status = ride.status
        ride.status = RideStatus.CANCELLED
        ride.cancelled_at = now
        self._rides.save(
            ride,
            from_status=previous_status,
            reason=validated_reason,
            actor_type="DRIVER",
            actor_id=driver_id,
        )
        return ride

    def mark_arrived(
        self,
        *,
        ride_id: uuid.UUID,
        driver_id: uuid.UUID,
        latitude: float,
        longitude: float,
        radius_meters: float,
        max_attempts_before_review: int,
        dispute_evidence_window_seconds: int,
        otp_expiry_seconds: int,
        otp_hash_pepper: str,
        now: datetime,
    ) -> tuple[Ride, GpsVerification]:
        """Phase 06/07 (Driver Arrival, ADR-0028). api-contracts.md §17;
        state-machines.md §6 (`ACCEPTED -> ARRIVED`, requires
        `GPS verification = PASS`). Row-locks the ride for the whole
        composition, same pattern as cancel_ride()/driver_cancel_ride().
        Every attempt — pass or fail — is recorded in
        `ride.gps_verifications` before this method decides what to do
        about it (ADR-0028 §3's audit-trail-first design). A PASS also
        auto-issues the ride-start OTP (api-contracts.md §18 documents
        no separate "create" call — see the ADR)."""
        assert self._gps_verifications is not None
        assert self._ride_otps is not None

        ride = self._rides.get_by_id_for_update(ride_id)
        if ride is None or ride.driver_id != driver_id:
            raise RideNotFoundError("Ride not found.")
        if ride.status is not RideStatus.ACCEPTED:
            raise RideNotInExpectedStateError("This ride is not ACCEPTED.")

        already_failed = self._gps_verifications.count_failed(
            ride_id, verification_type=GpsVerificationType.ARRIVAL.value
        )
        verification = self._gps_verifications.create(
            GpsVerification.new(
                ride_id=ride_id,
                verification_type=GpsVerificationType.ARRIVAL,
                latitude=latitude,
                longitude=longitude,
                reference_latitude=ride.current_pickup.latitude,
                reference_longitude=ride.current_pickup.longitude,
                radius_meters=radius_meters,
                now=now,
            )
        )

        if verification.result is GpsVerificationResult.FAIL:
            if already_failed >= max_attempts_before_review:
                dispute = self._open_gps_dispute(
                    ride_id=ride_id,
                    gps_verification_id=verification.id,
                    verification_type=GpsVerificationType.ARRIVAL,
                    evidence_window_seconds=dispute_evidence_window_seconds,
                    now=now,
                )
                raise GpsVerificationFailedError(
                    "GPS verification has failed too many times for this "
                    "ride and now requires manual review.",
                    dispute_id=dispute.id if dispute is not None else None,
                )
            raise NotWithinPickupRadiusError(
                "Driver is not within the pickup GPS radius."
            )

        self._finalize_arrival(
            ride=ride,
            driver_id=driver_id,
            otp_expiry_seconds=otp_expiry_seconds,
            otp_hash_pepper=otp_hash_pepper,
            now=now,
        )
        return ride, verification

    def _finalize_arrival(
        self,
        *,
        ride: Ride,
        driver_id: uuid.UUID,
        otp_expiry_seconds: int,
        otp_hash_pepper: str,
        now: datetime,
    ) -> None:
        """The ACCEPTED -> ARRIVED transition + OTP issuance, factored
        out of mark_arrived() so resolve_gps_dispute()'s own APPROVE path
        (ADR-0032) can perform the exact same finalization a real PASS
        would have — `ride` is already locked and validated by the
        caller in both cases."""
        previous_status = ride.status
        ride.status = RideStatus.ARRIVED
        ride.arrived_at = now
        self._rides.save(
            ride,
            from_status=previous_status,
            reason=None,
            actor_type="DRIVER",
            actor_id=driver_id,
        )
        # The plaintext is deliberately discarded here — the driver's own
        # response to THIS call must never include it (ADR-0028 §3: the
        # driver must ask the customer to read it aloud, not see it
        # in-app). Auto-generating it now means it already exists by the
        # time the customer calls refresh_otp() below to actually see it.
        self._issue_new_otp(
            ride_id=ride.id,
            expiry_seconds=otp_expiry_seconds,
            hash_pepper=otp_hash_pepper,
            now=now,
        )

    def refresh_otp(
        self,
        *,
        ride_id: uuid.UUID,
        customer_id: uuid.UUID,
        otp_expiry_seconds: int,
        otp_hash_pepper: str,
        now: datetime,
    ) -> tuple[RideOtp, str]:
        """Phase 06/07 (Ride Start OTP — Generate/Refresh, ADR-0028).
        api-contracts.md §18. Customer-only, and the ONLY way the
        customer ever sees the plaintext OTP (ADR-0028 §3, revised): no
        notification channel exists (Phase 15, blocked) to push the code
        auto-generated by mark_arrived(), and the plaintext is never
        persisted (only its HMAC, matching modules.identity.domain.otp's
        own "never stored in plaintext where avoidable" discipline) — so
        this endpoint doubles as "reveal my current code," not merely
        "get a new one after the old one expired." Each call invalidates
        the previous ACTIVE OTP and issues a fresh one; returns
        (the persisted entity, the plaintext — for this response only)."""
        ride = self._rides.get_by_id(ride_id)
        if ride is None or ride.customer_id != customer_id:
            raise RideNotFoundError("Ride not found.")
        if ride.status is not RideStatus.ARRIVED:
            raise RideNotInExpectedStateError("This ride is not ARRIVED.")

        return self._issue_new_otp(
            ride_id=ride_id,
            expiry_seconds=otp_expiry_seconds,
            hash_pepper=otp_hash_pepper,
            now=now,
        )

    def _issue_new_otp(
        self,
        *,
        ride_id: uuid.UUID,
        expiry_seconds: int,
        hash_pepper: str,
        now: datetime,
    ) -> tuple[RideOtp, str]:
        assert self._ride_otps is not None
        existing = self._ride_otps.get_active_for_update(ride_id)
        if existing is not None:
            existing.status = RideOtpStatus.EXPIRED
            self._ride_otps.save(existing)

        plaintext = generate_numeric_otp()
        otp = RideOtp.new(
            ride_id=ride_id,
            otp_hash=hash_otp(plaintext, pepper=hash_pepper),
            expiry_seconds=expiry_seconds,
            now=now,
        )
        created = self._ride_otps.create(otp)
        return created, plaintext

    def start_ride(
        self,
        *,
        ride_id: uuid.UUID,
        driver_id: uuid.UUID,
        otp: str,
        max_attempts: int,
        otp_hash_pepper: str,
        now: datetime,
    ) -> Ride:
        """Phase 06/07 (Start Ride, ADR-0028). api-contracts.md §18;
        state-machines.md §7 (`ARRIVED -> STARTED`, requires a valid,
        unexpired, attempt-limited OTP). The plaintext `otp` the driver
        submits here is never persisted — only compared, via HMAC, to
        the hash already on record."""
        assert self._ride_otps is not None

        ride = self._rides.get_by_id_for_update(ride_id)
        if ride is None or ride.driver_id != driver_id:
            raise RideNotFoundError("Ride not found.")
        if ride.status is not RideStatus.ARRIVED:
            raise RideNotInExpectedStateError("This ride is not ARRIVED.")

        active_otp = self._ride_otps.get_active_for_update(ride_id)
        if active_otp is None:
            raise RideOtpInvalidError("No active OTP exists for this ride.")
        if now > active_otp.expires_at:
            active_otp.status = RideOtpStatus.EXPIRED
            self._ride_otps.save(active_otp)
            raise RideOtpExpiredError("The OTP has expired.")
        if active_otp.attempts >= max_attempts:
            raise RideOtpMaxAttemptsError("Maximum OTP verification attempts exceeded.")

        if not verify_otp(
            otp, pepper=otp_hash_pepper, expected_hash=active_otp.otp_hash
        ):
            active_otp.attempts += 1
            self._ride_otps.save(active_otp)
            raise RideOtpInvalidError("The OTP is incorrect.")

        active_otp.status = RideOtpStatus.USED
        self._ride_otps.save(active_otp)

        previous_status = ride.status
        ride.status = RideStatus.STARTED
        ride.started_at = now
        self._rides.save(
            ride,
            from_status=previous_status,
            reason=None,
            actor_type="DRIVER",
            actor_id=driver_id,
        )
        return ride

    def complete_ride(
        self,
        *,
        ride_id: uuid.UUID,
        driver_id: uuid.UUID,
        latitude: float,
        longitude: float,
        radius_meters: float,
        max_attempts_before_review: int,
        dispute_evidence_window_seconds: int,
        now: datetime,
    ) -> tuple[Ride, GpsVerification]:
        """Phase 06/07 (Ride Completion, ADR-0028). api-contracts.md §28;
        state-machines.md §8 (`STARTED -> COMPLETED`, requires
        `GPS verification = PASS`) and §10 (`COMPLETED -> CLOSED`,
        implemented as immediate/automatic in the same transaction — see
        the ADR for why no further precondition is documented anywhere
        to gate it on). Two separate `save()` calls below write two
        distinct `ride.state_history` rows (STARTED -> COMPLETED, then
        COMPLETED -> CLOSED), matching state-machines.md's own two-step
        definition rather than collapsing them into one transition."""
        assert self._gps_verifications is not None

        ride = self._rides.get_by_id_for_update(ride_id)
        if ride is None or ride.driver_id != driver_id:
            raise RideNotFoundError("Ride not found.")
        if ride.status is not RideStatus.STARTED:
            raise RideNotCompletableError("This ride is not STARTED.")

        already_failed = self._gps_verifications.count_failed(
            ride_id, verification_type=GpsVerificationType.COMPLETION.value
        )
        verification = self._gps_verifications.create(
            GpsVerification.new(
                ride_id=ride_id,
                verification_type=GpsVerificationType.COMPLETION,
                latitude=latitude,
                longitude=longitude,
                reference_latitude=ride.current_destination.latitude,
                reference_longitude=ride.current_destination.longitude,
                radius_meters=radius_meters,
                now=now,
            )
        )

        if verification.result is GpsVerificationResult.FAIL:
            if already_failed >= max_attempts_before_review:
                dispute = self._open_gps_dispute(
                    ride_id=ride_id,
                    gps_verification_id=verification.id,
                    verification_type=GpsVerificationType.COMPLETION,
                    evidence_window_seconds=dispute_evidence_window_seconds,
                    now=now,
                )
                raise GpsVerificationFailedError(
                    "GPS verification has failed too many times for this "
                    "ride and now requires manual review.",
                    dispute_id=dispute.id if dispute is not None else None,
                )
            raise NotWithinDestinationRadiusError(
                "Driver is not within the destination GPS radius."
            )

        self._finalize_completion(ride=ride, driver_id=driver_id, now=now)
        return ride, verification

    def _finalize_completion(
        self, *, ride: Ride, driver_id: uuid.UUID, now: datetime
    ) -> None:
        """The STARTED -> COMPLETED -> CLOSED transition, factored out of
        complete_ride() so resolve_gps_dispute()'s own APPROVE path
        (ADR-0032) can perform the exact same finalization a real PASS
        would have."""
        previous_status: RideStatus = ride.status
        ride.status = RideStatus.COMPLETED
        ride.completed_at = now
        self._rides.save(
            ride,
            from_status=previous_status,
            reason=None,
            actor_type="DRIVER",
            actor_id=driver_id,
        )

        previous_status = ride.status
        ride.status = RideStatus.CLOSED
        ride.closed_at = now
        self._rides.save(
            ride,
            from_status=previous_status,
            reason=None,
            actor_type="SYSTEM",
            actor_id=driver_id,
        )

    def request_early_drop(
        self,
        *,
        ride_id: uuid.UUID,
        customer_id: uuid.UUID,
        reason: str | None,
        now: datetime,
    ) -> EarlyDropRequest:
        """RequestEarlyDrop (domain-design.md §9.4, Phase 08, ADR-0030).
        api-contracts.md §27; state-machines.md §19 (`STARTED ->
        EARLY_DROP_REQUESTED`). Customer-only. Only one pending
        (not-yet-fully-confirmed) request may exist per ride at a time."""
        assert self._early_drop_requests is not None

        ride = self._rides.get_by_id(ride_id)
        if ride is None or ride.customer_id != customer_id:
            raise RideNotFoundError("Ride not found.")
        if ride.status is not RideStatus.STARTED:
            raise RideNotInExpectedStateError("This ride is not STARTED.")

        if self._early_drop_requests.get_pending_for_update(ride_id) is not None:
            raise EarlyDropAlreadyRequestedError(
                "An early-drop request is already pending for this ride."
            )

        return self._early_drop_requests.create(
            EarlyDropRequest.new(
                ride_id=ride_id, requested_by=customer_id, reason=reason, now=now
            )
        )

    def confirm_early_drop(
        self,
        *,
        ride_id: uuid.UUID,
        account_id: uuid.UUID,
        confirmed: bool,
        latitude: float | None,
        longitude: float | None,
        now: datetime,
    ) -> tuple[Ride | None, EarlyDropRequest]:
        """ConfirmEarlyDrop (domain-design.md §9.4, Phase 08, ADR-0030).
        api-contracts.md §27; state-machines.md §19/§21. Customer-or-
        driver, ownership-checked — the caller's own account_id (matched
        against ride.customer_id/driver_id) decides which confirmation
        flag this call sets, never a client-supplied role.
        `confirmed=False` discards the pending request entirely
        (state-machines.md §21's "Customer/Driver rejects -> STARTED") —
        no status column exists to mark it rejected with (ADR-0030
        Decision 2). GPS/location travels on the driver's own confirming
        call (ADR-0030 Decision 3) — recorded as evidence only, never
        verified against a threshold (Decision 1). Returns (the ride, if
        this call was the one that completed both confirmations and
        transitioned it to CLOSED — else None; the early-drop request as
        it stood after this call — already deleted if rejected, so only
        its pre-deletion snapshot is returned then)."""
        assert self._early_drop_requests is not None

        ride = self._rides.get_by_id_for_update(ride_id)
        if ride is None or account_id not in (ride.customer_id, ride.driver_id):
            raise RideNotFoundError("Ride not found.")

        request = self._early_drop_requests.get_pending_for_update(ride_id)
        if request is None:
            raise EarlyDropRequestNotFoundError(
                "No pending early-drop request exists for this ride."
            )

        if not confirmed:
            self._early_drop_requests.delete(request.id)
            return None, request

        is_driver = account_id == ride.driver_id
        if is_driver:
            if latitude is None or longitude is None:
                raise EarlyDropLocationRequiredError(
                    "latitude/longitude are required when the driver confirms."
                )
            request.gps_location = Coordinates(latitude=latitude, longitude=longitude)
            request.driver_confirmed = True
        else:
            request.customer_confirmed = True

        if not request.is_fully_confirmed:
            self._early_drop_requests.save(request)
            return None, request

        request.confirmed_at = now
        self._early_drop_requests.save(request)

        actor_type = "DRIVER" if is_driver else "CUSTOMER"
        previous_status: RideStatus = ride.status
        ride.status = RideStatus.COMPLETED
        ride.completed_at = now
        self._rides.save(
            ride,
            from_status=previous_status,
            reason=None,
            actor_type=actor_type,
            actor_id=account_id,
        )

        previous_status = ride.status
        ride.status = RideStatus.CLOSED
        ride.closed_at = now
        self._rides.save(
            ride,
            from_status=previous_status,
            reason=None,
            actor_type="SYSTEM",
            actor_id=account_id,
        )
        return ride, request

    def _open_gps_dispute(
        self,
        *,
        ride_id: uuid.UUID,
        gps_verification_id: uuid.UUID,
        verification_type: GpsVerificationType,
        evidence_window_seconds: int,
        now: datetime,
    ) -> GpsDispute:
        """BR-124/BR-125 (ADR-0032 Decision 2). Auto-opens a manual-review
        dispute the instant GPS verification reaches its terminal FAIL
        outcome — same transaction as that FAIL row, audit-trail-first,
        same discipline every other write in mark_arrived()/
        complete_ride() already follows."""
        assert self._gps_disputes is not None
        return self._gps_disputes.create(
            GpsDispute.new(
                ride_id=ride_id,
                gps_verification_id=gps_verification_id,
                verification_type=verification_type,
                evidence_window_seconds=evidence_window_seconds,
                now=now,
            )
        )

    def _expire_if_past_deadline(self, dispute: GpsDispute, *, now: datetime) -> None:
        """ADR-0032 Decision 5 — lazy expiry, no background worker (same
        precedent as MatchingService.expire_stale_offers(), ADR-0011
        Decision 2). Mutates `dispute` in place and persists the change
        if it just transitioned; a no-op for a dispute that is not OPEN
        or has not yet passed its deadline."""
        assert self._gps_disputes is not None
        if dispute.status is GpsDisputeStatus.OPEN and dispute.is_past_deadline(
            now=now
        ):
            dispute.status = GpsDisputeStatus.EXPIRED
            self._gps_disputes.save(dispute)

    def submit_gps_dispute_evidence(
        self,
        *,
        dispute_id: uuid.UUID,
        account_id: uuid.UUID,
        evidence_type: str,
        uri: str | None,
        text: str | None,
        now: datetime,
    ) -> GpsDisputeEvidence:
        """SubmitGpsDisputeEvidence (BR-125, ADR-0032). Customer-or-
        driver, ownership-checked against the dispute's own ride.
        Rejected once the dispute is no longer OPEN — including when
        THIS call is the one that first observes the 24h evidence
        window has elapsed (lazy expiry, ADR-0032 Decision 5)."""
        assert self._gps_disputes is not None
        assert self._gps_dispute_evidence is not None

        dispute = self._gps_disputes.get_by_id_for_update(dispute_id)
        if dispute is None:
            raise GpsDisputeNotFoundError("GPS dispute not found.")
        ride = self._rides.get_by_id(dispute.ride_id)
        if ride is None or account_id not in (ride.customer_id, ride.driver_id):
            raise GpsDisputeNotFoundError("GPS dispute not found.")

        self._expire_if_past_deadline(dispute, now=now)
        if dispute.status is not GpsDisputeStatus.OPEN:
            raise GpsDisputeNotOpenError(
                "This GPS dispute is no longer open for evidence."
            )

        try:
            parsed_type = GpsDisputeEvidenceType(evidence_type)
        except ValueError as exc:
            raise InvalidGpsDisputeEvidenceError(
                f"evidence_type must be one of "
                f"{[t.value for t in GpsDisputeEvidenceType]}."
            ) from exc
        if parsed_type is GpsDisputeEvidenceType.TEXT:
            if not text or not text.strip():
                raise InvalidGpsDisputeEvidenceError(
                    "text is required when evidence_type is TEXT."
                )
        elif not uri:
            raise InvalidGpsDisputeEvidenceError(
                "uri is required when evidence_type is PHOTO/VIDEO/DOCUMENT."
            )

        return self._gps_dispute_evidence.create(
            GpsDisputeEvidence.new(
                dispute_id=dispute_id,
                submitted_by=account_id,
                evidence_type=parsed_type,
                uri=uri if parsed_type is not GpsDisputeEvidenceType.TEXT else None,
                text_explanation=(
                    text if parsed_type is GpsDisputeEvidenceType.TEXT else None
                ),
                now=now,
            )
        )

    def get_gps_dispute(
        self,
        *,
        dispute_id: uuid.UUID,
        account_id: uuid.UUID,
        is_admin: bool,
        now: datetime,
    ) -> tuple[GpsDispute, list[GpsDisputeEvidence]]:
        """Get Dispute (api-contracts.md §77). An admin may view any
        dispute; a customer/driver only one belonging to their own ride
        (IDOR-safe — same "not found" response either way)."""
        assert self._gps_disputes is not None
        assert self._gps_dispute_evidence is not None

        dispute = self._gps_disputes.get_by_id(dispute_id)
        if dispute is None:
            raise GpsDisputeNotFoundError("GPS dispute not found.")
        if not is_admin:
            ride = self._rides.get_by_id(dispute.ride_id)
            if ride is None or account_id not in (ride.customer_id, ride.driver_id):
                raise GpsDisputeNotFoundError("GPS dispute not found.")

        # A plain read still lazily expires an overdue OPEN dispute
        # (ADR-0032 Decision 5) — but via a locked re-fetch, not the
        # unlocked `dispute` above, to avoid holding a row lock for the
        # common case (already RESOLVED/EXPIRED, or still within window)
        # where no write is needed.
        if dispute.status is GpsDisputeStatus.OPEN and dispute.is_past_deadline(
            now=now
        ):
            locked = self._gps_disputes.get_by_id_for_update(dispute_id)
            assert locked is not None
            self._expire_if_past_deadline(locked, now=now)
            dispute = locked

        evidence = self._gps_dispute_evidence.list_for_dispute(dispute_id)
        return dispute, evidence

    def list_gps_disputes_for_ride(
        self,
        *,
        ride_id: uuid.UUID,
        account_id: uuid.UUID,
        is_admin: bool,
        now: datetime,
    ) -> list[tuple[GpsDispute, list[GpsDisputeEvidence]]]:
        """List GPS Disputes for a Ride (ADR-0074, api-contracts.md §77)
        — the discovery endpoint a customer (who never receives a
        dispute_id directly, unlike the driver whose own mark_arrived()/
        complete_ride() call opens one) needs to find a dispute on their
        own ride at all. Same ownership check get_gps_dispute() already
        uses; ride-not-found and not-owned both raise the same error
        (IDOR-safe)."""
        assert self._gps_disputes is not None
        assert self._gps_dispute_evidence is not None

        ride = self._rides.get_by_id(ride_id)
        if ride is None:
            raise RideNotFoundError("Ride not found.")
        if not is_admin and account_id not in (ride.customer_id, ride.driver_id):
            raise RideNotFoundError("Ride not found.")

        disputes = self._gps_disputes.list_for_ride(ride_id)
        results: list[tuple[GpsDispute, list[GpsDisputeEvidence]]] = []
        for dispute in disputes:
            if dispute.status is GpsDisputeStatus.OPEN and dispute.is_past_deadline(
                now=now
            ):
                locked = self._gps_disputes.get_by_id_for_update(dispute.id)
                assert locked is not None
                self._expire_if_past_deadline(locked, now=now)
                dispute = locked
            evidence = self._gps_dispute_evidence.list_for_dispute(dispute.id)
            results.append((dispute, evidence))
        return results

    def search_gps_disputes(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[GpsDispute], int]:
        """Admin Search Disputes (api-contracts.md §77, ADR-0032) — admin-
        only, composed at modules/admin/router.py. Pure pass-through,
        same shape as search_rides()."""
        assert self._gps_disputes is not None
        return self._gps_disputes.search(status=status, offset=offset, limit=limit)

    def resolve_gps_dispute(
        self,
        *,
        dispute_id: uuid.UUID,
        admin_id: uuid.UUID,
        action: str,
        reason: str,
        otp_expiry_seconds: int,
        otp_hash_pepper: str,
        now: datetime,
    ) -> tuple[GpsDispute, Ride | None]:
        """ResolveGpsDispute (BR-124, ADR-0032) — admin-only, composed at
        modules/admin/router.py. APPROVE performs the exact ride
        transition the original GPS verification would have on a real
        PASS (_finalize_arrival()/_finalize_completion(), the same
        helpers mark_arrived()/complete_ride() themselves use) — REJECT
        only records the decision; the ride never transitions either way
        it wasn't already going to. Returns (dispute, ride if this call
        transitioned it via APPROVE, else None)."""
        assert self._gps_disputes is not None

        if action not in ("APPROVE", "REJECT"):
            raise InvalidGpsDisputeActionError(
                'action must be exactly "APPROVE" or "REJECT".'
            )

        dispute = self._gps_disputes.get_by_id_for_update(dispute_id)
        if dispute is None:
            raise GpsDisputeNotFoundError("GPS dispute not found.")

        self._expire_if_past_deadline(dispute, now=now)
        if dispute.status is not GpsDisputeStatus.OPEN:
            raise GpsDisputeNotOpenError("This GPS dispute is no longer open.")

        ride: Ride | None = None
        if action == "APPROVE":
            locked_ride = self._rides.get_by_id_for_update(dispute.ride_id)
            if locked_ride is None:
                raise GpsDisputeNotFoundError("GPS dispute not found.")
            if dispute.verification_type is GpsVerificationType.ARRIVAL:
                self._finalize_arrival(
                    ride=locked_ride,
                    driver_id=locked_ride.driver_id,  # type: ignore[arg-type]
                    otp_expiry_seconds=otp_expiry_seconds,
                    otp_hash_pepper=otp_hash_pepper,
                    now=now,
                )
            else:
                self._finalize_completion(
                    ride=locked_ride,
                    driver_id=locked_ride.driver_id,  # type: ignore[arg-type]
                    now=now,
                )
            ride = locked_ride

        dispute.status = GpsDisputeStatus.RESOLVED
        dispute.decision = GpsDisputeDecision(action)
        dispute.decided_by = admin_id
        dispute.decided_reason = reason
        dispute.decided_at = now
        self._gps_disputes.save(dispute)

        return dispute, ride

    def request_pickup_change(
        self,
        *,
        ride_id: uuid.UUID,
        customer_id: uuid.UUID,
        latitude: float,
        longitude: float,
        threshold_meters: float,
        now: datetime,
    ) -> tuple[Ride, float]:
        """RequestPickupChange (domain-design.md §9.4, ADR-0033;
        simplified by ADR-0056, 2026-08-31). api-contracts.md §22;
        state-machines.md §14/BR-072-074. Customer-only, ACCEPTED-only
        (pickup change only makes sense before the driver has arrived —
        ARRIVED already means mark_arrived()'s own GPS-verified
        proximity check has passed).

        A ≤threshold change is applied immediately, no request row
        created (ADR-0033 Decision 5, unchanged by ADR-0056 — only the
        threshold value itself changed, 250m -> 100m) — returns the ride
        with current_pickup already updated, and distance_meters.

        A >threshold change is now rejected outright
        (PickupChangeTooFarError) — ADR-0056 removed the old driver-
        PROCEED/PASS flow entirely; the ride is left completely
        unchanged, no request row is created, and the customer's only
        path to a farther pickup is to cancel this ride and book a new
        one."""
        assert self._change_requests is not None

        ride = self._rides.get_by_id_for_update(ride_id)
        if ride is None or ride.customer_id != customer_id:
            raise RideNotFoundError("Ride not found.")
        if ride.status is not RideStatus.ACCEPTED:
            raise RideNotInExpectedStateError("This ride is not ACCEPTED.")
        if (
            self._change_requests.get_pending_for_update(
                ride_id, request_type=ChangeRequestType.PICKUP_CHANGE
            )
            is not None
        ):
            # Defensive only (ADR-0056) — new code never creates a
            # pending PICKUP_CHANGE row anymore, so this can only ever
            # fire against a request row that predates that ADR.
            raise PickupChangeAlreadyRequestedError(
                "A pickup change request is already pending for this ride."
            )

        new_pickup = validate_coordinates(latitude, longitude, field_name="pickup")
        distance_meters = haversine_distance_meters(
            ride.current_pickup.latitude,
            ride.current_pickup.longitude,
            new_pickup.latitude,
            new_pickup.longitude,
        )

        if distance_meters > threshold_meters:
            raise PickupChangeTooFarError(
                "This pickup is too far from your current one. Cancel this "
                "ride and book a new one to change it by this much."
            )

        ride.current_pickup = new_pickup
        self._rides.update_current_pickup(ride_id, new_pickup)
        return ride, distance_meters

    def get_ride_for_destination_change(
        self, *, ride_id: uuid.UUID, customer_id: uuid.UUID
    ) -> Ride:
        """RequestDestinationChange, step 1 (domain-design.md §9.4,
        ADR-0033 Decision 9). api-contracts.md §25; state-machines.md
        §17-18/BR-079-082. Customer-only, STARTED-only (destination
        change happens mid-ride, after pickup — unlike pickup change,
        which only makes sense before arrival). Locks and returns the
        ride so the router can read original_pickup/original_
        destination/current_pickup/current_destination before composing
        PricingService.calculate_destination_change_fare() — the actual
        case/quote/request-row decision happens in
        apply_destination_change() below, once the router has that
        result (RideService does not depend on PricingService directly,
        matching this codebase's "cross-module composition only at the
        router" convention)."""
        assert self._change_requests is not None

        ride = self._rides.get_by_id_for_update(ride_id)
        if ride is None or ride.customer_id != customer_id:
            raise RideNotFoundError("Ride not found.")
        if ride.status is not RideStatus.STARTED:
            raise RideNotInExpectedStateError("This ride is not STARTED.")
        if (
            self._change_requests.get_pending_for_update(
                ride_id, request_type=ChangeRequestType.DESTINATION_CHANGE
            )
            is not None
        ):
            raise DestinationChangeAlreadyRequestedError(
                "A destination change request is already pending for this ride."
            )
        return ride

    def apply_destination_change(
        self,
        *,
        ride_id: uuid.UUID,
        customer_id: uuid.UUID,
        new_destination_latitude: float,
        new_destination_longitude: float,
        case: str,
        fare_quote_id: uuid.UUID | None,
        now: datetime,
    ) -> tuple[ChangeRequest | None, Ride]:
        """RequestDestinationChange, step 2 (ADR-0033 Decision 9). The
        router calls this after get_ride_for_destination_change() and
        PricingService.calculate_destination_change_fare() — `case` is
        whichever of WITHIN_ROUTE/BEYOND_ORIGINAL/DIFFERENT_ROUTE Pricing
        classified, `fare_quote_id` is the quote it created (None for
        WITHIN_ROUTE, BR-079 — no charge, no confirmation gate, applied
        immediately, same "nothing changed, no ceremony" treatment
        pickup change's own ≤threshold case gets, ADR-0033 Decision 5).
        BEYOND_ORIGINAL/DIFFERENT_ROUTE instead create an AWAITING_
        CUSTOMER_CONFIRMATION request with the quote already attached —
        unlike pickup change, no driver-decision step exists for
        destination change anywhere in the documented flow, so the quote
        is known up front rather than computed after a PROCEED choice."""
        assert self._change_requests is not None

        ride = self._rides.get_by_id_for_update(ride_id)
        if ride is None or ride.customer_id != customer_id:
            raise RideNotFoundError("Ride not found.")

        new_destination = validate_coordinates(
            new_destination_latitude,
            new_destination_longitude,
            field_name="destination",
        )

        if case == "WITHIN_ROUTE":
            ride.current_destination = new_destination
            self._rides.update_current_destination(ride_id, new_destination)
            return None, ride

        assert fare_quote_id is not None
        request = self._change_requests.create(
            ChangeRequest.new(
                ride_id=ride_id,
                request_type=ChangeRequestType.DESTINATION_CHANGE,
                requested_by=customer_id,
                old_location=ride.current_destination,
                new_location=new_destination,
                old_fare_quote_id=ride.active_fare_quote_id,
                status=ChangeRequestStatus.AWAITING_CUSTOMER_CONFIRMATION,
                new_fare_quote_id=fare_quote_id,
                now=now,
            )
        )
        return request, ride

    def confirm_destination_change(
        self,
        *,
        ride_id: uuid.UUID,
        customer_id: uuid.UUID,
        confirmed: bool,
        now: datetime,
    ) -> tuple[ChangeRequest, Ride, Coordinates]:
        """ConfirmDestinationChange (BR-082, ADR-0033 Decision 9).
        Customer-only. `confirmed: true` activates the fare quote
        computed at request time and applies the new destination;
        `confirmed: false` leaves the ride entirely untouched — no
        charge is silently added. `old_destination` is the ride's
        destination as it stood immediately before this call — the
        event payload needs both old and new values (event-contracts.md
        §10.6)."""
        assert self._change_requests is not None

        ride = self._rides.get_by_id(ride_id)
        if ride is None or ride.customer_id != customer_id:
            raise RideNotFoundError("Ride not found.")
        request = self._change_requests.get_pending_for_update(
            ride_id, request_type=ChangeRequestType.DESTINATION_CHANGE
        )
        if request is None:
            raise DestinationChangeNotFoundError(
                "No pending destination change request exists for this ride."
            )
        if request.status is not ChangeRequestStatus.AWAITING_CUSTOMER_CONFIRMATION:
            raise DestinationChangeNotAwaitingConfirmationError(
                "This destination change request is not awaiting customer confirmation."
            )

        old_destination = ride.current_destination
        if confirmed:
            assert request.new_fare_quote_id is not None
            self._rides.set_active_fare_quote(ride_id, request.new_fare_quote_id)
            self._rides.update_current_destination(ride_id, request.new_location)
            ride.active_fare_quote_id = request.new_fare_quote_id
            ride.current_destination = request.new_location
            request.status = ChangeRequestStatus.CONFIRMED
            request.customer_decision = ChangeRequestCustomerDecision.CONFIRMED
        else:
            request.status = ChangeRequestStatus.REJECTED
            request.customer_decision = ChangeRequestCustomerDecision.REJECTED
        request.resolved_at = now
        self._change_requests.save(request)

        return request, ride, old_destination
