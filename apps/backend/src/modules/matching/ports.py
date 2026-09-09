"""Abstract interfaces (ports) the application layer depends on."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from modules.matching.domain.entities import Offer


class OfferRepository(Protocol):
    def create(self, offer: Offer) -> Offer: ...

    def get_by_id(self, offer_id: uuid.UUID) -> Offer | None: ...

    def list_pending_for_driver(self, driver_id: uuid.UUID) -> list[Offer]:
        """PENDING offers only — a driver may only ever have one at a
        time in practice (this module always dispatches to the next
        driver only after the previous offer leaves PENDING), but this
        returns a list rather than assuming that invariant."""
        ...

    def driver_ids_already_offered_for_ride(self, ride_id: uuid.UUID) -> set[uuid.UUID]:
        """Every driver_id with ANY offer (any status) already recorded
        for this ride — used to exclude drivers already tried (BR-029/
        BR-030's "next" eligible driver must be a different driver)."""
        ...

    def list_pending_for_ride(self, ride_id: uuid.UUID) -> list[Offer]:
        """Added Phase 3 / Task 3.3 (ADR-0012 Decision 2). PENDING offers
        for a ride — at most one in practice (this module never
        dispatches a second offer while one is already PENDING for the
        same ride), but returns a list rather than assuming that
        invariant, same as list_pending_for_driver."""
        ...

    def save(self, offer: Offer) -> None: ...

    def count_by_status_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        """Admin Web §4.16 Matching report (ADR-0047) — `created_at` in
        [since, until)."""
        ...

    def average_time_to_accept_seconds_in_range(
        self, *, since: datetime, until: datetime
    ) -> Decimal:
        """AVG(responded_at - created_at) in seconds, for ACCEPTED
        offers with `created_at` in [since, until). 0 if none accepted
        in range."""
        ...

    def search(
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
        """Admin Web §4.6 Matching/Offers screen (ADR-0054) — every
        filter is optional and independent (unlike list_pending_for_
        driver/list_pending_for_ride above, this is not restricted to
        PENDING and needs no known driver_id/ride_id to call). `since`/
        `until` filter on `created_at`, same half-open [since, until)
        convention Reports' own range queries use. Ordered newest
        first, same convention every other admin search endpoint in
        this codebase uses."""
        ...


class NearbyDriverIndex(Protocol):
    async def nearest_driver_ids(
        self,
        *,
        category: str,
        latitude: float,
        longitude: float,
        radius_km: float,
        limit: int,
    ) -> list[uuid.UUID]:
        """Nearest-first driver_ids currently present in the geo index
        for this category — presence only means "was ONLINE with this
        vehicle category as of their last location write", not current
        eligibility. See shared/geo.py."""
        ...


@dataclass(frozen=True, slots=True)
class EligibilityResult:
    """Phase 3 / Task 3.4 (ADR-0014). Fine-grained outcome of an
    eligibility check — `check_with_reason()`'s return shape.
    `ineligible_reason` is `None` when `vehicle_id` is set (eligible),
    else one of the two documented error codes (api-contracts.md §16,
    §49) explaining *why* — "DRIVER_NOT_ELIGIBLE" or
    "VEHICLE_NOT_ELIGIBLE" — distinct from `check()`'s coarser
    UUID | None, which dispatch_offer() uses and which only needs
    "eligible or not", never why."""

    vehicle_id: uuid.UUID | None
    ineligible_reason: str | None


class DriverEligibilityChecker(Protocol):
    def check(
        self, driver_id: uuid.UUID, *, requested_category: str
    ) -> uuid.UUID | None:
        """Returns the driver's currently ACTIVE, eligible vehicle's id
        if this driver is eligible for a ride of `requested_category`
        right now (re-verified against Postgres — never trusts Redis
        presence alone), else None. Composed from modules.driver/
        modules.vehicle at the dependency-wiring layer — see
        modules/matching/dependencies.py::ComposedEligibilityChecker."""
        ...

    def check_with_reason(
        self, driver_id: uuid.UUID, *, requested_category: str
    ) -> EligibilityResult:
        """Same check as check(), but distinguishes *why* an ineligible
        driver failed — added Phase 3 / Task 3.4 for accept_offer()
        (api-contracts.md §16 documents DRIVER_NOT_ELIGIBLE and
        VEHICLE_NOT_ELIGIBLE as two distinct possible errors).
        dispatch_offer() has no use for the reason (it only skips
        ineligible candidates) and keeps calling check()."""
        ...
