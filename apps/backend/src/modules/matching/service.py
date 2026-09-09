"""Application service (use cases) for Matching.

MatchingService is deliberately decoupled from modules.ride and
modules.driver/modules.vehicle: it depends only on the Protocols in
ports.py (OfferRepository, NearbyDriverIndex, DriverEligibilityChecker).
Composition with those other modules happens at
modules/matching/dependencies.py (DriverEligibilityChecker) and at the
routers that call into this service (modules/matching/router.py for
rematch-on-expire/reject, modules/ride/router.py for the initial
dispatch after ride creation) — both need ride details (requested
category, pickup point) this service has no access to by design.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from modules.matching.domain.entities import Offer, OfferStatus
from modules.matching.domain.errors import (
    DriverNotEligibleError,
    OfferAlreadyRespondedError,
    OfferExpiredError,
    OfferNotFoundError,
    VehicleNotEligibleError,
)
from modules.matching.ports import (
    DriverEligibilityChecker,
    NearbyDriverIndex,
    OfferRepository,
)


class MatchingService:
    def __init__(
        self,
        *,
        offers: OfferRepository,
        driver_index: NearbyDriverIndex,
        eligibility: DriverEligibilityChecker,
    ) -> None:
        self._offers = offers
        self._driver_index = driver_index
        self._eligibility = eligibility

    async def dispatch_offer(
        self,
        *,
        ride_id: uuid.UUID,
        requested_category: str,
        pickup_latitude: float,
        pickup_longitude: float,
        search_radius_km: float,
        offer_ttl_seconds: int,
        candidate_limit: int,
        now: datetime,
    ) -> Offer | None:
        """BR-026/BR-029/BR-030: finds the nearest eligible driver who
        hasn't already been offered this ride and creates a PENDING
        offer for them. Returns None if none is found — the ride stays
        SEARCHING with no active offer (ADR-0011 Item 5); that's a
        legitimate, quiet outcome here, not an error."""
        already_offered = self._offers.driver_ids_already_offered_for_ride(ride_id)
        candidates = await self._driver_index.nearest_driver_ids(
            category=requested_category,
            latitude=pickup_latitude,
            longitude=pickup_longitude,
            radius_km=search_radius_km,
            limit=candidate_limit,
        )
        for driver_id in candidates:
            if driver_id in already_offered:
                continue
            vehicle_id = self._eligibility.check(
                driver_id, requested_category=requested_category
            )
            if vehicle_id is None:
                continue
            offer = Offer.new(
                ride_id=ride_id,
                driver_id=driver_id,
                vehicle_id=vehicle_id,
                ttl_seconds=offer_ttl_seconds,
                now=now,
            )
            return self._offers.create(offer)
        return None

    def cancel_pending_offers_for_ride(
        self, *, ride_id: uuid.UUID, now: datetime
    ) -> list[Offer]:
        """Phase 3 / Task 3.3 (ADR-0012 Decision 2). Cancels any
        outstanding PENDING offer for a ride that's being cancelled
        (customer cancellation, modules/ride/router.py) — the one
        documented offer status (database-design.md §10.1) this module
        hadn't used until now. No rematch follows (the ride itself is
        CANCELLED, not SEARCHING anymore)."""
        pending = self._offers.list_pending_for_ride(ride_id)
        cancelled: list[Offer] = []
        for offer in pending:
            offer.status = OfferStatus.CANCELLED
            offer.responded_at = now
            self._offers.save(offer)
            cancelled.append(offer)
        return cancelled

    def expire_stale_offers(
        self, *, driver_id: uuid.UUID, now: datetime
    ) -> tuple[list[Offer], list[Offer]]:
        """ADR-0011 Decision 2 (lazy expiry, no background worker).
        Returns (still_pending, newly_expired). The caller is
        responsible for dispatching a rematch offer for each
        newly_expired offer's ride — this method never touches ride
        details (see this module's docstring)."""
        pending = self._offers.list_pending_for_driver(driver_id)
        still_pending: list[Offer] = []
        newly_expired: list[Offer] = []
        for offer in pending:
            if offer.is_expired(now=now):
                offer.status = OfferStatus.EXPIRED
                offer.responded_at = now
                self._offers.save(offer)
                newly_expired.append(offer)
            else:
                still_pending.append(offer)
        return still_pending, newly_expired

    def get_offer_for_driver(
        self, *, driver_id: uuid.UUID, offer_id: uuid.UUID
    ) -> Offer | None:
        """Phase 3 / Task 3.4. Read-only lookup, no status validation —
        used by modules/matching/router.py's accept-offer composition to
        discover the offer's ride_id (needed to fetch the ride's
        requested_vehicle_category for accept_offer() below) *before*
        the wallet row lock is acquired. Safe to call unlocked: the
        real validation happens in accept_offer(), called after the
        lock. Returns None for "does not exist" and "belongs to another
        driver" alike — same IDOR-safe treatment as reject_offer()."""
        offer = self._offers.get_by_id(offer_id)
        if offer is None or offer.driver_id != driver_id:
            return None
        return offer

    def accept_offer(
        self,
        *,
        driver_id: uuid.UUID,
        offer_id: uuid.UUID,
        requested_category: str,
        now: datetime,
    ) -> tuple[Offer, uuid.UUID]:
        """Phase 3 / Task 3.4 (ADR-0014). Must be called only after the
        caller has already acquired the driver's wallet row lock
        (modules/matching/router.py's accept_offer_endpoint()) — that
        lock is what serializes two concurrent accept attempts on the
        SAME offer (both necessarily belong to the same driver_id, so
        both contend for the same wallet row), making the fresh re-fetch
        of `offer` below race-safe: a second, blocked caller only
        proceeds past the lock after the first has committed, and will
        then correctly see the already-ACCEPTED status here.

        Returns (offer, assigned_vehicle_id). Re-validates driver/
        vehicle eligibility fresh (ADR-0014 Decision 2) and returns the
        eligibility check's own vehicle_id, NOT offer.vehicle_id (which
        stays unchanged on the Offer itself — an accurate historical
        record of what was originally offered, even if the driver has
        since switched their ACTIVE vehicle) — the caller must assign
        this returned vehicle_id to the ride, not the offer's."""
        offer = self._offers.get_by_id(offer_id)
        if offer is None or offer.driver_id != driver_id:
            raise OfferNotFoundError("Offer not found.")
        if offer.status is not OfferStatus.PENDING:
            raise OfferAlreadyRespondedError(
                "This offer has already been responded to."
            )
        if offer.is_expired(now=now):
            offer.status = OfferStatus.EXPIRED
            offer.responded_at = now
            self._offers.save(offer)
            raise OfferExpiredError("This offer has expired.")

        eligibility = self._eligibility.check_with_reason(
            driver_id, requested_category=requested_category
        )
        if eligibility.ineligible_reason == "DRIVER_NOT_ELIGIBLE":
            raise DriverNotEligibleError("Driver is not currently eligible.")
        if eligibility.ineligible_reason == "VEHICLE_NOT_ELIGIBLE":
            raise VehicleNotEligibleError("No currently eligible vehicle.")
        assert eligibility.vehicle_id is not None  # eligible => vehicle_id is set

        offer.status = OfferStatus.ACCEPTED
        offer.responded_at = now
        self._offers.save(offer)
        return offer, eligibility.vehicle_id

    def reject_offer(
        self, *, driver_id: uuid.UUID, offer_id: uuid.UUID, now: datetime
    ) -> Offer:
        """BR-029. If the offer turns out to already be past its expiry
        by the time this runs, it's recorded as EXPIRED rather than
        REJECTED (accurate history) but still succeeds — from the
        driver's perspective they're done with it either way. The
        caller is responsible for dispatching a rematch offer
        afterward, same as expire_stale_offers()."""
        offer = self._offers.get_by_id(offer_id)
        if offer is None or offer.driver_id != driver_id:
            # Same response for "does not exist" and "belongs to
            # another driver" — IDOR/enumeration protection, same
            # pattern used throughout this codebase.
            raise OfferNotFoundError("Offer not found.")
        if offer.status is not OfferStatus.PENDING:
            raise OfferAlreadyRespondedError(
                "This offer has already been responded to."
            )

        offer.status = (
            OfferStatus.EXPIRED if offer.is_expired(now=now) else OfferStatus.REJECTED
        )
        offer.responded_at = now
        self._offers.save(offer)
        return offer

    # --- Reports (Admin Web §4.16, ADR-0047) -------------------------

    def count_offers_by_status_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        return self._offers.count_by_status_in_range(since=since, until=until)

    def average_time_to_accept_seconds_in_range(
        self, *, since: datetime, until: datetime
    ) -> Decimal:
        return self._offers.average_time_to_accept_seconds_in_range(
            since=since, until=until
        )

    # --- Admin visibility (Admin Web §4.6, ADR-0054) ------------------

    def get_offer(self, offer_id: uuid.UUID) -> Offer | None:
        """Admin-only lookup, no driver-ownership restriction — distinct
        from get_offer_for_driver() above, same "no ownership
        restriction, admin-only" split modules/ride/service.py's
        get_ride() already establishes relative to the driver/customer-
        facing ride lookup."""
        return self._offers.get_by_id(offer_id)

    def search_offers(
        self,
        *,
        status: str | None,
        ride_id: uuid.UUID | None,
        driver_id: uuid.UUID | None,
        since: datetime | None,
        until: datetime | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Offer], int]:
        """Admin Web §4.6 Matching/Offers screen (ADR-0054). Pure
        pass-through to the repository: no domain logic beyond what the
        port itself already documents, same shape RideService.
        search_rides() already uses for its own admin search."""
        return self._offers.search(
            status=status,
            ride_id=ride_id,
            driver_id=driver_id,
            since=since,
            until=until,
            offset=offset,
            limit=limit,
        )
