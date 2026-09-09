"""Unit tests for MatchingService against in-memory fakes (no DB, no
Redis) — same style as tests/test_vehicle_service.py."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from modules.matching.domain.entities import Offer, OfferStatus
from modules.matching.domain.errors import (
    DriverNotEligibleError,
    OfferAlreadyRespondedError,
    OfferExpiredError,
    OfferNotFoundError,
    VehicleNotEligibleError,
)
from modules.matching.ports import EligibilityResult
from modules.matching.service import MatchingService

RIDE_ID = uuid.uuid4()
NOW = datetime.now(UTC)


class FakeOfferRepository:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, Offer] = {}

    def create(self, offer: Offer) -> Offer:
        self.by_id[offer.id] = offer
        return offer

    def get_by_id(self, offer_id: uuid.UUID) -> Offer | None:
        return self.by_id.get(offer_id)

    def list_pending_for_driver(self, driver_id: uuid.UUID) -> list[Offer]:
        return [
            o
            for o in self.by_id.values()
            if o.driver_id == driver_id and o.status is OfferStatus.PENDING
        ]

    def driver_ids_already_offered_for_ride(self, ride_id: uuid.UUID) -> set[uuid.UUID]:
        return {o.driver_id for o in self.by_id.values() if o.ride_id == ride_id}

    def list_pending_for_ride(self, ride_id: uuid.UUID) -> list[Offer]:
        return [
            o
            for o in self.by_id.values()
            if o.ride_id == ride_id and o.status is OfferStatus.PENDING
        ]

    def save(self, offer: Offer) -> None:
        self.by_id[offer.id] = offer

    def count_by_status_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for o in self.by_id.values():
            if since <= o.created_at < until:
                key = o.status.value
                counts[key] = counts.get(key, 0) + 1
        return counts

    def average_time_to_accept_seconds_in_range(
        self, *, since: datetime, until: datetime
    ) -> Decimal:
        durations = [
            (o.responded_at - o.created_at).total_seconds()
            for o in self.by_id.values()
            if o.status is OfferStatus.ACCEPTED
            and o.responded_at is not None
            and since <= o.created_at < until
        ]
        if not durations:
            return Decimal("0")
        return Decimal(str(sum(durations) / len(durations)))

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
        matches = [
            o
            for o in self.by_id.values()
            if (status is None or o.status.value == status)
            and (ride_id is None or o.ride_id == ride_id)
            and (driver_id is None or o.driver_id == driver_id)
            and (since is None or o.created_at >= since)
            and (until is None or o.created_at < until)
        ]
        matches.sort(key=lambda o: o.created_at, reverse=True)
        return matches[offset : offset + limit], len(matches)


class FakeNearbyDriverIndex:
    def __init__(self, driver_ids: list[uuid.UUID]) -> None:
        self.driver_ids = driver_ids

    async def nearest_driver_ids(
        self,
        *,
        category: str,
        latitude: float,
        longitude: float,
        radius_km: float,
        limit: int,
    ) -> list[uuid.UUID]:
        return self.driver_ids[:limit]


class FakeEligibilityChecker:
    def __init__(
        self,
        eligible: dict[uuid.UUID, uuid.UUID],
        *,
        ineligible_reason: str = "DRIVER_NOT_ELIGIBLE",
    ) -> None:
        """eligible maps driver_id -> vehicle_id for eligible drivers;
        any driver_id not present is treated as ineligible.
        ineligible_reason (Task 3.4) lets accept_offer() tests choose
        which of the two documented reasons a missing driver_id should
        report; dispatch_offer()'s tests never look at it."""
        self.eligible = eligible
        self.ineligible_reason = ineligible_reason

    def check(
        self, driver_id: uuid.UUID, *, requested_category: str
    ) -> uuid.UUID | None:
        return self.eligible.get(driver_id)

    def check_with_reason(
        self, driver_id: uuid.UUID, *, requested_category: str
    ) -> EligibilityResult:
        vehicle_id = self.eligible.get(driver_id)
        return EligibilityResult(
            vehicle_id=vehicle_id,
            ineligible_reason=None if vehicle_id else self.ineligible_reason,
        )


def _service(
    *, driver_ids: list[uuid.UUID], eligible: dict[uuid.UUID, uuid.UUID]
) -> tuple[MatchingService, FakeOfferRepository]:
    offers = FakeOfferRepository()
    service = MatchingService(
        offers=offers,
        driver_index=FakeNearbyDriverIndex(driver_ids),
        eligibility=FakeEligibilityChecker(eligible),
    )
    return service, offers


async def _dispatch(
    service: MatchingService, ride_id: uuid.UUID = RIDE_ID
) -> Offer | None:
    return await service.dispatch_offer(
        ride_id=ride_id,
        requested_category="CAB",
        pickup_latitude=25.5941,
        pickup_longitude=85.1376,
        search_radius_km=5,
        offer_ttl_seconds=20,
        candidate_limit=20,
        now=NOW,
    )


@pytest.mark.anyio
async def test_dispatch_offer_creates_a_pending_offer_for_nearest_eligible() -> None:
    driver_id = uuid.uuid4()
    vehicle_id = uuid.uuid4()
    service, offers = _service(driver_ids=[driver_id], eligible={driver_id: vehicle_id})

    offer = await _dispatch(service)

    assert offer is not None
    assert offer.driver_id == driver_id
    assert offer.vehicle_id == vehicle_id
    assert offer.status is OfferStatus.PENDING
    assert offers.by_id[offer.id] == offer


@pytest.mark.anyio
async def test_dispatch_offer_skips_ineligible_candidates() -> None:
    ineligible = uuid.uuid4()
    eligible_driver = uuid.uuid4()
    eligible_vehicle = uuid.uuid4()
    service, _ = _service(
        driver_ids=[ineligible, eligible_driver],
        eligible={eligible_driver: eligible_vehicle},
    )

    offer = await _dispatch(service)

    assert offer is not None
    assert offer.driver_id == eligible_driver


@pytest.mark.anyio
async def test_dispatch_offer_returns_none_when_no_eligible_driver_found() -> None:
    """ADR-0011 Item 5: the ride stays SEARCHING with no active offer —
    a legitimate, quiet outcome, not an error."""
    service, _ = _service(driver_ids=[uuid.uuid4()], eligible={})

    offer = await _dispatch(service)

    assert offer is None


@pytest.mark.anyio
async def test_dispatch_offer_skips_drivers_already_offered_this_ride() -> None:
    first_driver, first_vehicle = uuid.uuid4(), uuid.uuid4()
    second_driver, second_vehicle = uuid.uuid4(), uuid.uuid4()
    service, offers = _service(
        driver_ids=[first_driver, second_driver],
        eligible={first_driver: first_vehicle, second_driver: second_vehicle},
    )
    first_offer = await _dispatch(service)
    assert first_offer is not None
    offers.by_id[first_offer.id].status = OfferStatus.REJECTED  # already tried

    second_offer = await _dispatch(service)

    assert second_offer is not None
    assert second_offer.driver_id == second_driver


def test_cancel_pending_offers_for_ride_cancels_only_pending_offers_for_that_ride() -> (
    None
):
    """Phase 3 / Task 3.3, ADR-0012 Decision 2."""
    offers = FakeOfferRepository()
    service = MatchingService(
        offers=offers,
        driver_index=FakeNearbyDriverIndex([]),
        eligibility=FakeEligibilityChecker({}),
    )
    pending_for_ride = offers.create(
        Offer.new(
            ride_id=RIDE_ID,
            driver_id=uuid.uuid4(),
            vehicle_id=uuid.uuid4(),
            ttl_seconds=20,
            now=NOW,
        )
    )
    already_rejected_for_ride = offers.create(
        Offer.new(
            ride_id=RIDE_ID,
            driver_id=uuid.uuid4(),
            vehicle_id=uuid.uuid4(),
            ttl_seconds=20,
            now=NOW,
        )
    )
    already_rejected_for_ride.status = OfferStatus.REJECTED
    other_ride_pending = offers.create(
        Offer.new(
            ride_id=uuid.uuid4(),
            driver_id=uuid.uuid4(),
            vehicle_id=uuid.uuid4(),
            ttl_seconds=20,
            now=NOW,
        )
    )

    cancelled = service.cancel_pending_offers_for_ride(ride_id=RIDE_ID, now=NOW)

    assert [o.id for o in cancelled] == [pending_for_ride.id]
    assert offers.by_id[pending_for_ride.id].status is OfferStatus.CANCELLED
    assert offers.by_id[pending_for_ride.id].responded_at == NOW
    assert offers.by_id[already_rejected_for_ride.id].status is OfferStatus.REJECTED
    assert offers.by_id[other_ride_pending.id].status is OfferStatus.PENDING


def test_cancel_pending_offers_for_ride_is_a_noop_when_none_pending() -> None:
    offers = FakeOfferRepository()
    service = MatchingService(
        offers=offers,
        driver_index=FakeNearbyDriverIndex([]),
        eligibility=FakeEligibilityChecker({}),
    )
    assert service.cancel_pending_offers_for_ride(ride_id=RIDE_ID, now=NOW) == []


def test_expire_stale_offers_transitions_expired_offers_and_keeps_pending_ones() -> (
    None
):
    driver_id = uuid.uuid4()
    offers = FakeOfferRepository()
    service = MatchingService(
        offers=offers,
        driver_index=FakeNearbyDriverIndex([]),
        eligibility=FakeEligibilityChecker({}),
    )
    expired = Offer.new(
        ride_id=RIDE_ID,
        driver_id=driver_id,
        vehicle_id=uuid.uuid4(),
        ttl_seconds=-1,
        now=NOW,
    )
    still_valid = Offer.new(
        ride_id=uuid.uuid4(),
        driver_id=driver_id,
        vehicle_id=uuid.uuid4(),
        ttl_seconds=20,
        now=NOW,
    )
    offers.create(expired)
    offers.create(still_valid)

    pending, newly_expired = service.expire_stale_offers(driver_id=driver_id, now=NOW)

    assert [o.id for o in pending] == [still_valid.id]
    assert [o.id for o in newly_expired] == [expired.id]
    assert offers.by_id[expired.id].status is OfferStatus.EXPIRED
    assert offers.by_id[expired.id].responded_at == NOW


def test_reject_offer_transitions_pending_to_rejected() -> None:
    driver_id = uuid.uuid4()
    offers = FakeOfferRepository()
    service = MatchingService(
        offers=offers,
        driver_index=FakeNearbyDriverIndex([]),
        eligibility=FakeEligibilityChecker({}),
    )
    offer = offers.create(
        Offer.new(
            ride_id=RIDE_ID,
            driver_id=driver_id,
            vehicle_id=uuid.uuid4(),
            ttl_seconds=20,
            now=NOW,
        )
    )

    rejected = service.reject_offer(driver_id=driver_id, offer_id=offer.id, now=NOW)

    assert rejected.status is OfferStatus.REJECTED
    assert rejected.responded_at == NOW


def test_reject_offer_records_expired_instead_when_already_past_expiry() -> None:
    driver_id = uuid.uuid4()
    offers = FakeOfferRepository()
    service = MatchingService(
        offers=offers,
        driver_index=FakeNearbyDriverIndex([]),
        eligibility=FakeEligibilityChecker({}),
    )
    offer = offers.create(
        Offer.new(
            ride_id=RIDE_ID,
            driver_id=driver_id,
            vehicle_id=uuid.uuid4(),
            ttl_seconds=-1,
            now=NOW,
        )
    )

    result = service.reject_offer(driver_id=driver_id, offer_id=offer.id, now=NOW)

    assert result.status is OfferStatus.EXPIRED


def test_reject_offer_raises_for_unknown_offer() -> None:
    offers = FakeOfferRepository()
    service = MatchingService(
        offers=offers,
        driver_index=FakeNearbyDriverIndex([]),
        eligibility=FakeEligibilityChecker({}),
    )
    with pytest.raises(OfferNotFoundError):
        service.reject_offer(driver_id=uuid.uuid4(), offer_id=uuid.uuid4(), now=NOW)


def test_reject_offer_raises_when_offer_belongs_to_another_driver() -> None:
    driver_id = uuid.uuid4()
    other_driver = uuid.uuid4()
    offers = FakeOfferRepository()
    service = MatchingService(
        offers=offers,
        driver_index=FakeNearbyDriverIndex([]),
        eligibility=FakeEligibilityChecker({}),
    )
    offer = offers.create(
        Offer.new(
            ride_id=RIDE_ID,
            driver_id=driver_id,
            vehicle_id=uuid.uuid4(),
            ttl_seconds=20,
            now=NOW,
        )
    )
    with pytest.raises(OfferNotFoundError):
        service.reject_offer(driver_id=other_driver, offer_id=offer.id, now=NOW)


def test_reject_offer_raises_when_already_responded() -> None:
    driver_id = uuid.uuid4()
    offers = FakeOfferRepository()
    service = MatchingService(
        offers=offers,
        driver_index=FakeNearbyDriverIndex([]),
        eligibility=FakeEligibilityChecker({}),
    )
    offer = offers.create(
        Offer.new(
            ride_id=RIDE_ID,
            driver_id=driver_id,
            vehicle_id=uuid.uuid4(),
            ttl_seconds=20,
            now=NOW,
        )
    )
    service.reject_offer(driver_id=driver_id, offer_id=offer.id, now=NOW)

    with pytest.raises(OfferAlreadyRespondedError):
        service.reject_offer(driver_id=driver_id, offer_id=offer.id, now=NOW)


# --- get_offer_for_driver() / accept_offer() (Phase 3 / Task 3.4) ------


def _pending_offer(
    offers: FakeOfferRepository, *, driver_id: uuid.UUID, vehicle_id: uuid.UUID
) -> Offer:
    return offers.create(
        Offer.new(
            ride_id=RIDE_ID,
            driver_id=driver_id,
            vehicle_id=vehicle_id,
            ttl_seconds=20,
            now=NOW,
        )
    )


def test_get_offer_for_driver_returns_none_for_unknown_offer() -> None:
    service, _ = _service(driver_ids=[], eligible={})
    result = service.get_offer_for_driver(driver_id=uuid.uuid4(), offer_id=uuid.uuid4())
    assert result is None


def test_get_offer_for_driver_returns_none_for_another_drivers_offer() -> None:
    driver_id = uuid.uuid4()
    other_driver = uuid.uuid4()
    offers = FakeOfferRepository()
    service = MatchingService(
        offers=offers,
        driver_index=FakeNearbyDriverIndex([]),
        eligibility=FakeEligibilityChecker({}),
    )
    offer = _pending_offer(offers, driver_id=driver_id, vehicle_id=uuid.uuid4())

    result = service.get_offer_for_driver(driver_id=other_driver, offer_id=offer.id)

    assert result is None


def test_get_offer_for_driver_returns_the_offer_when_owned() -> None:
    driver_id = uuid.uuid4()
    offers = FakeOfferRepository()
    service = MatchingService(
        offers=offers,
        driver_index=FakeNearbyDriverIndex([]),
        eligibility=FakeEligibilityChecker({}),
    )
    offer = _pending_offer(offers, driver_id=driver_id, vehicle_id=uuid.uuid4())

    result = service.get_offer_for_driver(driver_id=driver_id, offer_id=offer.id)

    assert result is not None
    assert result.id == offer.id


def test_accept_offer_transitions_to_accepted_and_returns_fresh_vehicle_id() -> None:
    driver_id = uuid.uuid4()
    dispatch_time_vehicle = uuid.uuid4()
    current_active_vehicle = uuid.uuid4()
    offers = FakeOfferRepository()
    service = MatchingService(
        offers=offers,
        driver_index=FakeNearbyDriverIndex([]),
        eligibility=FakeEligibilityChecker({driver_id: current_active_vehicle}),
    )
    offer = _pending_offer(
        offers, driver_id=driver_id, vehicle_id=dispatch_time_vehicle
    )

    accepted_offer, vehicle_id = service.accept_offer(
        driver_id=driver_id, offer_id=offer.id, requested_category="CAB", now=NOW
    )

    assert accepted_offer.status is OfferStatus.ACCEPTED
    assert accepted_offer.responded_at == NOW
    # ADR-0014 Decision 2: the freshly-checked vehicle is returned, not
    # necessarily the offer's original dispatch-time snapshot — the
    # offer's own vehicle_id stays unchanged as historical record.
    assert vehicle_id == current_active_vehicle
    assert accepted_offer.vehicle_id == dispatch_time_vehicle


def test_accept_offer_raises_for_unknown_offer() -> None:
    service, _ = _service(driver_ids=[], eligible={})
    with pytest.raises(OfferNotFoundError):
        service.accept_offer(
            driver_id=uuid.uuid4(),
            offer_id=uuid.uuid4(),
            requested_category="CAB",
            now=NOW,
        )


def test_accept_offer_raises_when_offer_belongs_to_another_driver() -> None:
    driver_id = uuid.uuid4()
    other_driver = uuid.uuid4()
    offers = FakeOfferRepository()
    service = MatchingService(
        offers=offers,
        driver_index=FakeNearbyDriverIndex([]),
        eligibility=FakeEligibilityChecker({other_driver: uuid.uuid4()}),
    )
    offer = _pending_offer(offers, driver_id=driver_id, vehicle_id=uuid.uuid4())

    with pytest.raises(OfferNotFoundError):
        service.accept_offer(
            driver_id=other_driver,
            offer_id=offer.id,
            requested_category="CAB",
            now=NOW,
        )


def test_accept_offer_raises_when_already_responded() -> None:
    driver_id = uuid.uuid4()
    vehicle_id = uuid.uuid4()
    offers = FakeOfferRepository()
    service = MatchingService(
        offers=offers,
        driver_index=FakeNearbyDriverIndex([]),
        eligibility=FakeEligibilityChecker({driver_id: vehicle_id}),
    )
    offer = _pending_offer(offers, driver_id=driver_id, vehicle_id=vehicle_id)
    service.accept_offer(
        driver_id=driver_id, offer_id=offer.id, requested_category="CAB", now=NOW
    )

    with pytest.raises(OfferAlreadyRespondedError):
        service.accept_offer(
            driver_id=driver_id, offer_id=offer.id, requested_category="CAB", now=NOW
        )


def test_accept_offer_raises_offer_expired_and_marks_it_expired() -> None:
    driver_id = uuid.uuid4()
    vehicle_id = uuid.uuid4()
    offers = FakeOfferRepository()
    service = MatchingService(
        offers=offers,
        driver_index=FakeNearbyDriverIndex([]),
        eligibility=FakeEligibilityChecker({driver_id: vehicle_id}),
    )
    offer = _pending_offer(offers, driver_id=driver_id, vehicle_id=vehicle_id)
    past_expiry = offer.expires_at + timedelta(seconds=1)

    with pytest.raises(OfferExpiredError):
        service.accept_offer(
            driver_id=driver_id,
            offer_id=offer.id,
            requested_category="CAB",
            now=past_expiry,
        )

    assert offers.by_id[offer.id].status is OfferStatus.EXPIRED


def test_accept_offer_raises_driver_not_eligible() -> None:
    driver_id = uuid.uuid4()
    vehicle_id = uuid.uuid4()
    offers = FakeOfferRepository()
    service = MatchingService(
        offers=offers,
        driver_index=FakeNearbyDriverIndex([]),
        eligibility=FakeEligibilityChecker({}, ineligible_reason="DRIVER_NOT_ELIGIBLE"),
    )
    offer = _pending_offer(offers, driver_id=driver_id, vehicle_id=vehicle_id)

    with pytest.raises(DriverNotEligibleError):
        service.accept_offer(
            driver_id=driver_id,
            offer_id=offer.id,
            requested_category="CAB",
            now=NOW,
        )
    # A failed eligibility re-check must not consume the offer.
    assert offers.by_id[offer.id].status is OfferStatus.PENDING


def test_accept_offer_raises_vehicle_not_eligible() -> None:
    driver_id = uuid.uuid4()
    vehicle_id = uuid.uuid4()
    offers = FakeOfferRepository()
    service = MatchingService(
        offers=offers,
        driver_index=FakeNearbyDriverIndex([]),
        eligibility=FakeEligibilityChecker(
            {}, ineligible_reason="VEHICLE_NOT_ELIGIBLE"
        ),
    )
    offer = _pending_offer(offers, driver_id=driver_id, vehicle_id=vehicle_id)

    with pytest.raises(VehicleNotEligibleError):
        service.accept_offer(
            driver_id=driver_id,
            offer_id=offer.id,
            requested_category="CAB",
            now=NOW,
        )
    assert offers.by_id[offer.id].status is OfferStatus.PENDING


# --- get_offer() / search_offers() (Admin Web §4.6, ADR-0054) ----------


def test_get_offer_returns_none_for_unknown_offer() -> None:
    service, _ = _service(driver_ids=[], eligible={})
    assert service.get_offer(uuid.uuid4()) is None


def test_get_offer_returns_any_drivers_offer_unrestricted() -> None:
    """Admin lookup — unlike get_offer_for_driver(), no ownership
    check; any offer_id resolves regardless of which driver holds it."""
    driver_id = uuid.uuid4()
    offers = FakeOfferRepository()
    service = MatchingService(
        offers=offers,
        driver_index=FakeNearbyDriverIndex([]),
        eligibility=FakeEligibilityChecker({}),
    )
    offer = _pending_offer(offers, driver_id=driver_id, vehicle_id=uuid.uuid4())

    result = service.get_offer(offer.id)

    assert result is not None
    assert result.id == offer.id


def test_search_offers_filters_by_status() -> None:
    offers = FakeOfferRepository()
    service = MatchingService(
        offers=offers,
        driver_index=FakeNearbyDriverIndex([]),
        eligibility=FakeEligibilityChecker({}),
    )
    pending = _pending_offer(offers, driver_id=uuid.uuid4(), vehicle_id=uuid.uuid4())
    accepted = _pending_offer(offers, driver_id=uuid.uuid4(), vehicle_id=uuid.uuid4())
    offers.by_id[accepted.id].status = OfferStatus.ACCEPTED

    results, total = service.search_offers(
        status="PENDING",
        ride_id=None,
        driver_id=None,
        since=None,
        until=None,
        offset=0,
        limit=20,
    )

    assert total == 1
    assert [o.id for o in results] == [pending.id]


def test_search_offers_filters_by_ride_id_and_driver_id() -> None:
    offers = FakeOfferRepository()
    service = MatchingService(
        offers=offers,
        driver_index=FakeNearbyDriverIndex([]),
        eligibility=FakeEligibilityChecker({}),
    )
    target_driver = uuid.uuid4()
    target_ride = uuid.uuid4()
    matching_offer = offers.create(
        Offer.new(
            ride_id=target_ride,
            driver_id=target_driver,
            vehicle_id=uuid.uuid4(),
            ttl_seconds=20,
            now=NOW,
        )
    )
    offers.create(
        Offer.new(
            ride_id=uuid.uuid4(),
            driver_id=uuid.uuid4(),
            vehicle_id=uuid.uuid4(),
            ttl_seconds=20,
            now=NOW,
        )
    )

    by_ride, ride_total = service.search_offers(
        status=None,
        ride_id=target_ride,
        driver_id=None,
        since=None,
        until=None,
        offset=0,
        limit=20,
    )
    by_driver, driver_total = service.search_offers(
        status=None,
        ride_id=None,
        driver_id=target_driver,
        since=None,
        until=None,
        offset=0,
        limit=20,
    )

    assert ride_total == 1
    assert [o.id for o in by_ride] == [matching_offer.id]
    assert driver_total == 1
    assert [o.id for o in by_driver] == [matching_offer.id]


def test_search_offers_filters_by_date_range() -> None:
    offers = FakeOfferRepository()
    service = MatchingService(
        offers=offers,
        driver_index=FakeNearbyDriverIndex([]),
        eligibility=FakeEligibilityChecker({}),
    )
    in_range = offers.create(
        Offer.new(
            ride_id=uuid.uuid4(),
            driver_id=uuid.uuid4(),
            vehicle_id=uuid.uuid4(),
            ttl_seconds=20,
            now=NOW,
        )
    )
    out_of_range = offers.create(
        Offer.new(
            ride_id=uuid.uuid4(),
            driver_id=uuid.uuid4(),
            vehicle_id=uuid.uuid4(),
            ttl_seconds=20,
            now=NOW - timedelta(days=10),
        )
    )

    results, total = service.search_offers(
        status=None,
        ride_id=None,
        driver_id=None,
        since=NOW - timedelta(days=1),
        until=NOW + timedelta(days=1),
        offset=0,
        limit=20,
    )

    assert total == 1
    assert [o.id for o in results] == [in_range.id]
    assert out_of_range.id not in [o.id for o in results]


def test_search_offers_paginates_newest_first() -> None:
    offers = FakeOfferRepository()
    service = MatchingService(
        offers=offers,
        driver_index=FakeNearbyDriverIndex([]),
        eligibility=FakeEligibilityChecker({}),
    )
    older = offers.create(
        Offer.new(
            ride_id=uuid.uuid4(),
            driver_id=uuid.uuid4(),
            vehicle_id=uuid.uuid4(),
            ttl_seconds=20,
            now=NOW - timedelta(minutes=5),
        )
    )
    newer = offers.create(
        Offer.new(
            ride_id=uuid.uuid4(),
            driver_id=uuid.uuid4(),
            vehicle_id=uuid.uuid4(),
            ttl_seconds=20,
            now=NOW,
        )
    )

    page_one, total = service.search_offers(
        status=None,
        ride_id=None,
        driver_id=None,
        since=None,
        until=None,
        offset=0,
        limit=1,
    )
    page_two, _ = service.search_offers(
        status=None,
        ride_id=None,
        driver_id=None,
        since=None,
        until=None,
        offset=1,
        limit=1,
    )

    assert total == 2
    assert [o.id for o in page_one] == [newer.id]
    assert [o.id for o in page_two] == [older.id]
