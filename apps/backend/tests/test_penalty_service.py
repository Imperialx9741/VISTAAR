"""Unit tests for PenaltyService against in-memory fake repositories."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from modules.penalty.domain.entities import Penalty, PenaltyStatus, PenaltyType, Strike
from modules.penalty.domain.errors import (
    InvalidPenaltyResolutionActionError,
    PenaltyNotFoundError,
    PenaltyNotOutstandingError,
)
from modules.penalty.service import PenaltyService

CUSTOMER_ID = uuid.uuid4()
DRIVER_ID = uuid.uuid4()
NOW = datetime.now(UTC)


class FakePenaltyRepository:
    def __init__(self) -> None:
        self.by_ride_and_type: dict[tuple[uuid.UUID | None, str], Penalty] = {}
        self.all: list[Penalty] = []

    def count_by_user_and_type(
        self, user_id: uuid.UUID, *, penalty_type: PenaltyType
    ) -> int:
        return sum(
            1
            for p in self.all
            if p.user_id == user_id and p.penalty_type is penalty_type
        )

    def create(self, penalty: Penalty) -> Penalty:
        key = (penalty.ride_id, penalty.penalty_type.value)
        if key in self.by_ride_and_type:
            # uq_penalties_ride_penalty_type equivalent — idempotent.
            return self.by_ride_and_type[key]
        self.by_ride_and_type[key] = penalty
        self.all.append(penalty)
        return penalty

    def get_by_id_for_update(self, penalty_id: uuid.UUID) -> Penalty | None:
        return next((p for p in self.all if p.id == penalty_id), None)

    def list_outstanding_unattached_for_user_for_update(
        self, user_id: uuid.UUID
    ) -> list[Penalty]:
        return [
            p
            for p in self.all
            if p.user_id == user_id
            and p.status is PenaltyStatus.OUTSTANDING
            and p.settlement_ride_id is None
        ]

    def list_by_settlement_ride_id_for_update(
        self, ride_id: uuid.UUID
    ) -> list[Penalty]:
        return [
            p
            for p in self.all
            if p.settlement_ride_id == ride_id and p.status is PenaltyStatus.OUTSTANDING
        ]

    def save(self, penalty: Penalty) -> None:
        for index, existing in enumerate(self.all):
            if existing.id == penalty.id:
                self.all[index] = penalty
                return
        raise LookupError(f"Penalty {penalty.id} not found")

    def search(
        self,
        *,
        status: str | None,
        user_id: uuid.UUID | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Penalty], int]:
        matches = [
            p
            for p in self.all
            if (status is None or p.status.value == status)
            and (user_id is None or p.user_id == user_id)
        ]
        return matches[offset : offset + limit], len(matches)

    def count_by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for p in self.all:
            counts[p.status.value] = counts.get(p.status.value, 0) + 1
        return counts

    def count_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for p in self.all:
            counts[p.penalty_type.value] = counts.get(p.penalty_type.value, 0) + 1
        return counts

    def sum_amount_outstanding(self) -> Decimal:
        return sum(
            (p.amount for p in self.all if p.status.value == "OUTSTANDING"),
            Decimal("0"),
        )

    def sum_amount_outstanding_for_user(self, user_id: uuid.UUID) -> Decimal:
        return sum(
            (
                p.amount
                for p in self.all
                if p.status.value == "OUTSTANDING" and p.user_id == user_id
            ),
            Decimal("0"),
        )

    def sum_amount_settled_in_range(
        self, *, since: datetime, until: datetime
    ) -> Decimal:
        return sum(
            (
                p.amount
                for p in self.all
                if p.settled_at is not None and since <= p.settled_at < until
            ),
            Decimal("0"),
        )


class FakeStrikeRepository:
    def __init__(self) -> None:
        self.created: list[Strike] = []

    def create(self, strike: Strike) -> Strike:
        self.created.append(strike)
        return strike

    def list_for_driver(
        self, driver_id: uuid.UUID, *, offset: int, limit: int
    ) -> tuple[list[Strike], int]:
        matches = [s for s in self.created if s.driver_id == driver_id]
        matches.sort(key=lambda s: s.created_at, reverse=True)
        return matches[offset : offset + limit], len(matches)


@pytest.fixture
def penalties() -> FakePenaltyRepository:
    return FakePenaltyRepository()


@pytest.fixture
def strikes() -> FakeStrikeRepository:
    return FakeStrikeRepository()


@pytest.fixture
def service(
    penalties: FakePenaltyRepository, strikes: FakeStrikeRepository
) -> PenaltyService:
    return PenaltyService(penalties=penalties, strikes=strikes)


def test_first_qualifying_cancellation_is_free_and_settled(
    service: PenaltyService,
) -> None:
    penalty = service.record_customer_cancellation(
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )

    assert penalty.amount == Decimal("0")
    assert penalty.status.value == "SETTLED"
    assert penalty.settled_at == NOW


def test_second_qualifying_cancellation_charges_fifteen_and_is_outstanding(
    service: PenaltyService,
) -> None:
    service.record_customer_cancellation(
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )

    second = service.record_customer_cancellation(
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )

    assert second.amount == Decimal("15")
    assert second.status.value == "OUTSTANDING"
    assert second.settled_at is None


def test_customer_penalties_never_expire(
    service: PenaltyService, penalties: FakePenaltyRepository
) -> None:
    """BR-049, corrected 2026-09-04 (owner decision, ADR-0069):
    "Customer penalties in VISTAAR NEVER EXPIRE." Was previously
    test_charge_expires_in_thirty_days, asserting the opposite (a
    30-day expires_at) — the field itself is now removed entirely, not
    just left unset, so there is nothing to assert an expiry value
    against. This test instead confirms the positive invariant: a real
    OUTSTANDING charge stays exactly OUTSTANDING — no code anywhere in
    this service ever transitions it away on its own, since nothing
    here even reads a clock to decide that; the only transitions are
    settle_via_ride() (payment) and waive() (an admin's explicit
    action), neither called here."""
    service.record_customer_cancellation(
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )
    second = service.record_customer_cancellation(
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )
    assert second.status is PenaltyStatus.OUTSTANDING

    # No field to expire on the entity at all anymore.
    assert not hasattr(second, "expires_at")

    # Still outstanding per the same aggregate the customer-facing
    # display/attach flow (ADR-0059/ADR-0066) actually reads — nothing
    # about the passage of time is even representable here to test
    # against, which is itself the point.
    assert penalties.sum_amount_outstanding_for_user(CUSTOMER_ID) == Decimal("15")


def test_different_customers_each_get_their_own_first_free_cancellation(
    service: PenaltyService,
) -> None:
    other_customer = uuid.uuid4()

    service.record_customer_cancellation(
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )
    other_first = service.record_customer_cancellation(
        customer_id=other_customer, ride_id=uuid.uuid4(), now=NOW
    )

    assert other_first.amount == Decimal("0")


def test_record_customer_cancellation_is_idempotent_per_ride(
    service: PenaltyService,
) -> None:
    ride_id = uuid.uuid4()

    first = service.record_customer_cancellation(
        customer_id=CUSTOMER_ID, ride_id=ride_id, now=NOW
    )
    second = service.record_customer_cancellation(
        customer_id=CUSTOMER_ID, ride_id=ride_id, now=NOW
    )

    assert first.id == second.id


def test_record_driver_strike(
    service: PenaltyService, strikes: FakeStrikeRepository
) -> None:
    ride_id = uuid.uuid4()

    strike = service.record_driver_strike(
        driver_id=DRIVER_ID, ride_id=ride_id, reason="UNWILLING_TO_PROCEED", now=NOW
    )

    assert strike.driver_id == DRIVER_ID
    assert strike.ride_id == ride_id
    assert strike.reason == "UNWILLING_TO_PROCEED"
    assert strikes.created == [strike]


# --- list_strikes_for_driver() (Admin Web §4.9, api-contracts.md §46.18) --


def test_list_strikes_for_driver_returns_only_that_drivers_strikes(
    service: PenaltyService,
) -> None:
    other_driver = uuid.uuid4()
    mine = service.record_driver_strike(
        driver_id=DRIVER_ID, ride_id=uuid.uuid4(), reason="DRIVER_CANCELLATION", now=NOW
    )
    service.record_driver_strike(
        driver_id=other_driver,
        ride_id=uuid.uuid4(),
        reason="DRIVER_CANCELLATION",
        now=NOW,
    )

    results, total = service.list_strikes_for_driver(DRIVER_ID, offset=0, limit=20)

    assert total == 1
    assert [s.id for s in results] == [mine.id]


def test_list_strikes_for_driver_orders_newest_first_and_paginates(
    service: PenaltyService,
) -> None:
    older = service.record_driver_strike(
        driver_id=DRIVER_ID,
        ride_id=uuid.uuid4(),
        reason="DRIVER_CANCELLATION",
        now=NOW - timedelta(days=1),
    )
    newer = service.record_driver_strike(
        driver_id=DRIVER_ID, ride_id=uuid.uuid4(), reason="DRIVER_CANCELLATION", now=NOW
    )

    page_one, total = service.list_strikes_for_driver(DRIVER_ID, offset=0, limit=1)
    page_two, _ = service.list_strikes_for_driver(DRIVER_ID, offset=1, limit=1)

    assert total == 2
    assert [s.id for s in page_one] == [newer.id]
    assert [s.id for s in page_two] == [older.id]


def test_list_strikes_for_driver_is_empty_for_a_driver_with_none(
    service: PenaltyService,
) -> None:
    results, total = service.list_strikes_for_driver(DRIVER_ID, offset=0, limit=20)

    assert results == []
    assert total == 0


# --- resolve_penalty() / search_penalties() (Phase 16, ADR-0023) ----------


def test_resolve_penalty_waives_an_outstanding_penalty(
    service: PenaltyService,
) -> None:
    first = service.record_customer_cancellation(  # free, already SETTLED
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )
    second = service.record_customer_cancellation(  # ₹15, OUTSTANDING
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )
    third = service.record_customer_cancellation(  # ₹15, OUTSTANDING
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )
    assert second.status is PenaltyStatus.OUTSTANDING

    resolved = service.resolve_penalty(
        penalty_id=second.id, action="WAIVE", reason="Verified system error"
    )

    assert resolved.status is PenaltyStatus.WAIVED
    assert resolved.amount == second.amount  # immutable (api-contracts.md §48)
    assert resolved.settled_at is None  # WAIVED != SETTLED (ADR-0023 Decision 4)
    assert first.status is PenaltyStatus.SETTLED  # untouched
    assert third.status is PenaltyStatus.OUTSTANDING  # untouched


def test_resolve_penalty_rejects_unsupported_action(
    service: PenaltyService,
) -> None:
    service.record_customer_cancellation(  # ₹0, SETTLED
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )
    outstanding = service.record_customer_cancellation(  # ₹15, OUTSTANDING
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )

    with pytest.raises(InvalidPenaltyResolutionActionError):
        service.resolve_penalty(penalty_id=outstanding.id, action="REFUND", reason=None)


def test_resolve_nonexistent_penalty_raises_not_found(
    service: PenaltyService,
) -> None:
    with pytest.raises(PenaltyNotFoundError):
        service.resolve_penalty(penalty_id=uuid.uuid4(), action="WAIVE", reason=None)


def test_resolve_already_waived_penalty_raises_not_outstanding(
    service: PenaltyService,
) -> None:
    service.record_customer_cancellation(
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )
    outstanding = service.record_customer_cancellation(
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )
    service.resolve_penalty(penalty_id=outstanding.id, action="WAIVE", reason=None)

    with pytest.raises(PenaltyNotOutstandingError):
        service.resolve_penalty(penalty_id=outstanding.id, action="WAIVE", reason=None)


def test_resolve_settled_penalty_raises_not_outstanding(
    service: PenaltyService,
) -> None:
    settled = service.record_customer_cancellation(
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )
    assert settled.status is PenaltyStatus.SETTLED

    with pytest.raises(PenaltyNotOutstandingError):
        service.resolve_penalty(penalty_id=settled.id, action="WAIVE", reason=None)


def test_search_penalties_filters_by_status_and_user_id(
    service: PenaltyService,
) -> None:
    other_customer = uuid.uuid4()
    service.record_customer_cancellation(
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )
    outstanding = service.record_customer_cancellation(
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )
    service.record_customer_cancellation(
        customer_id=other_customer, ride_id=uuid.uuid4(), now=NOW
    )

    results, total = service.search_penalties(
        status="OUTSTANDING", user_id=CUSTOMER_ID, offset=0, limit=20
    )

    assert total == 1
    assert results == [outstanding]


# --- Customer Outstanding Penalty Settlement (ADR-0066, owner decision
# 2026-09-03) -----------------------------------------------------------


def test_attach_outstanding_penalties_to_ride_attaches_and_returns_total(
    service: PenaltyService,
) -> None:
    service.record_customer_cancellation(  # ₹0, SETTLED — never attached
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )
    outstanding = service.record_customer_cancellation(  # ₹15, OUTSTANDING
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )
    new_ride_id = uuid.uuid4()

    total = service.attach_outstanding_penalties_to_ride(
        customer_id=CUSTOMER_ID, ride_id=new_ride_id
    )

    assert total == Decimal("15")
    assert outstanding.settlement_ride_id == new_ride_id
    assert outstanding.status is PenaltyStatus.OUTSTANDING  # not settled yet


def test_attach_outstanding_penalties_to_ride_is_zero_with_none_outstanding(
    service: PenaltyService,
) -> None:
    total = service.attach_outstanding_penalties_to_ride(
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4()
    )
    assert total == Decimal("0")


def test_attach_outstanding_penalties_to_ride_never_reattaches_an_already_attached_one(
    service: PenaltyService,
) -> None:
    service.record_customer_cancellation(  # first — ₹0, SETTLED, irrelevant here
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )
    outstanding = service.record_customer_cancellation(  # second — ₹15, OUTSTANDING
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )
    first_ride = uuid.uuid4()
    service.attach_outstanding_penalties_to_ride(
        customer_id=CUSTOMER_ID, ride_id=first_ride
    )

    second_ride = uuid.uuid4()
    total = service.attach_outstanding_penalties_to_ride(
        customer_id=CUSTOMER_ID, ride_id=second_ride
    )

    assert total == Decimal("0")  # already attached to first_ride
    assert outstanding.settlement_ride_id == first_ride


def test_release_penalties_from_cancelled_ride_frees_the_attachment(
    service: PenaltyService,
) -> None:
    service.record_customer_cancellation(  # first — ₹0, SETTLED, irrelevant here
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )
    outstanding = service.record_customer_cancellation(  # second — ₹15, OUTSTANDING
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )
    ride_id = uuid.uuid4()
    service.attach_outstanding_penalties_to_ride(
        customer_id=CUSTOMER_ID, ride_id=ride_id
    )
    assert outstanding.settlement_ride_id == ride_id

    service.release_penalties_from_cancelled_ride(ride_id=ride_id)

    assert outstanding.settlement_ride_id is None
    assert outstanding.status is PenaltyStatus.OUTSTANDING


def test_release_penalties_from_cancelled_ride_is_a_no_op_for_a_ride_with_none_attached(
    service: PenaltyService,
) -> None:
    # Must not raise for the overwhelming common case: a cancelled ride
    # that never carried a penalty forward.
    service.release_penalties_from_cancelled_ride(ride_id=uuid.uuid4())


def test_released_penalty_can_be_attached_to_a_later_ride(
    service: PenaltyService,
) -> None:
    service.record_customer_cancellation(  # first — ₹0, SETTLED, irrelevant here
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )
    outstanding = service.record_customer_cancellation(  # second — ₹15, OUTSTANDING
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )
    cancelled_ride = uuid.uuid4()
    service.attach_outstanding_penalties_to_ride(
        customer_id=CUSTOMER_ID, ride_id=cancelled_ride
    )
    service.release_penalties_from_cancelled_ride(ride_id=cancelled_ride)

    later_ride = uuid.uuid4()
    total = service.attach_outstanding_penalties_to_ride(
        customer_id=CUSTOMER_ID, ride_id=later_ride
    )

    assert total == Decimal("15")
    assert outstanding.settlement_ride_id == later_ride


def test_settle_penalties_for_completed_ride_settles_and_returns_total(
    service: PenaltyService,
) -> None:
    service.record_customer_cancellation(  # first — ₹0, SETTLED, irrelevant here
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )
    outstanding = service.record_customer_cancellation(  # second — ₹15, OUTSTANDING
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )
    ride_id = uuid.uuid4()
    service.attach_outstanding_penalties_to_ride(
        customer_id=CUSTOMER_ID, ride_id=ride_id
    )
    settle_time = NOW + timedelta(hours=1)

    total = service.settle_penalties_for_completed_ride(
        ride_id=ride_id, now=settle_time
    )

    assert total == Decimal("15")
    assert outstanding.status is PenaltyStatus.SETTLED
    assert outstanding.settled_at == settle_time
    assert outstanding.settlement_ride_id == ride_id  # left in place, an audit trail


def test_settle_penalties_for_completed_ride_is_zero_for_a_ride_with_none_attached(
    service: PenaltyService,
) -> None:
    total = service.settle_penalties_for_completed_ride(
        ride_id=uuid.uuid4(), now=NOW
    )
    assert total == Decimal("0")


def test_a_settled_penalty_never_double_settles_on_a_second_call(
    service: PenaltyService,
) -> None:
    service.record_customer_cancellation(  # first — ₹0, SETTLED, irrelevant here
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )
    service.record_customer_cancellation(  # second — ₹15, OUTSTANDING
        customer_id=CUSTOMER_ID, ride_id=uuid.uuid4(), now=NOW
    )
    ride_id = uuid.uuid4()
    service.attach_outstanding_penalties_to_ride(
        customer_id=CUSTOMER_ID, ride_id=ride_id
    )
    first_total = service.settle_penalties_for_completed_ride(ride_id=ride_id, now=NOW)
    assert first_total == Decimal("15")  # sanity check: a real settlement happened

    second_total = service.settle_penalties_for_completed_ride(
        ride_id=ride_id, now=NOW
    )

    assert second_total == Decimal("0")
