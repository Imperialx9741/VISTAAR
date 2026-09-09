"""Unit tests for PricingService and the pure fare-calculation domain
logic, against in-memory fake repositories."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from modules.pricing.domain.entities import (
    DestinationChangeCase,
    FareQuote,
    FareQuoteStatus,
    FareRule,
    FareRuleStatus,
    PlatformFeeRule,
    calculate_destination_change_fare,
    calculate_fare,
    fare_rule_key,
    haversine_distance_km,
)
from modules.pricing.domain.errors import (
    FareRuleNotFoundError,
    InvalidFareRuleInputError,
    InvalidFareRuleStateTransitionError,
    InvalidPlatformFeeRuleInputError,
    InvalidPlatformFeeRuleStateTransitionError,
    PlatformFeeRuleNotFoundError,
    PreviousFareQuoteNotFoundError,
)
from modules.pricing.service import PricingService

NOW = datetime.now(UTC)
RIDE_ID = uuid.uuid4()

# Same pickup/destination pair used throughout tests/test_ride_api.py —
# haversine distance ≈ 2.854 km (verified independently).
PICKUP = (25.5941, 85.1376)
DESTINATION = (25.6120, 85.1580)


class FakeFareRuleRepository:
    def __init__(self, rules: dict[str, FareRule] | None = None) -> None:
        # by_id is the real store — multiple rows per vehicle_category
        # are expected (version history), same as the real table; the
        # constructor's dict-keyed `rules` param (pre-existing
        # calculate_fare() tests below, one rule per category) is just a
        # convenience seeding shape, indexed into by_id like anything
        # else.
        self.by_id: dict[uuid.UUID, FareRule] = {
            r.id: r for r in (rules or {}).values()
        }

    def get_active_by_category(
        self, vehicle_category: str, *, now: datetime
    ) -> FareRule | None:
        candidates = [
            r
            for r in self.by_id.values()
            if r.vehicle_category == vehicle_category
            and r.status is FareRuleStatus.PUBLISHED
            and r.effective_from is not None
            and r.effective_from <= now
            and (r.effective_until is None or r.effective_until > now)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda r: r.effective_from or datetime.min)

    def get_active_by_category_for_update(
        self, vehicle_category: str, *, now: datetime
    ) -> FareRule | None:
        return self.get_active_by_category(vehicle_category, now=now)

    def create(self, rule: FareRule) -> FareRule:
        self.by_id[rule.id] = rule
        return rule

    def get_by_id(self, rule_id: uuid.UUID) -> FareRule | None:
        return self.by_id.get(rule_id)

    def get_by_id_for_update(self, rule_id: uuid.UUID) -> FareRule | None:
        return self.by_id.get(rule_id)

    def save(self, rule: FareRule) -> None:
        self.by_id[rule.id] = rule

    def list_by_category(
        self,
        *,
        vehicle_category: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[FareRule], int]:
        rows = [
            r
            for r in self.by_id.values()
            if (vehicle_category is None or r.vehicle_category == vehicle_category)
            and (status is None or r.status.value == status)
        ]
        return rows[offset : offset + limit], len(rows)


class FakePlatformFeeRuleRepository:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, PlatformFeeRule] = {}

    def get_active_by_category(
        self, vehicle_category: str, *, now: datetime
    ) -> PlatformFeeRule | None:
        candidates = [
            r
            for r in self.by_id.values()
            if r.vehicle_category == vehicle_category
            and r.status is FareRuleStatus.PUBLISHED
            and r.effective_from is not None
            and r.effective_from <= now
            and (r.effective_until is None or r.effective_until > now)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda r: r.effective_from or datetime.min)

    def get_active_by_category_for_update(
        self, vehicle_category: str, *, now: datetime
    ) -> PlatformFeeRule | None:
        return self.get_active_by_category(vehicle_category, now=now)

    def create(self, rule: PlatformFeeRule) -> PlatformFeeRule:
        self.by_id[rule.id] = rule
        return rule

    def get_by_id(self, rule_id: uuid.UUID) -> PlatformFeeRule | None:
        return self.by_id.get(rule_id)

    def get_by_id_for_update(self, rule_id: uuid.UUID) -> PlatformFeeRule | None:
        return self.by_id.get(rule_id)

    def save(self, rule: PlatformFeeRule) -> None:
        self.by_id[rule.id] = rule

    def list_by_category(
        self,
        *,
        vehicle_category: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[PlatformFeeRule], int]:
        rows = [
            r
            for r in self.by_id.values()
            if (vehicle_category is None or r.vehicle_category == vehicle_category)
            and (status is None or r.status.value == status)
        ]
        return rows[offset : offset + limit], len(rows)


class FakeFareQuoteRepository:
    def __init__(self) -> None:
        self.created: list[FareQuote] = []

    def create(self, quote: FareQuote) -> FareQuote:
        self.created.append(quote)
        return quote

    def get_by_id(self, fare_quote_id: uuid.UUID) -> FareQuote | None:
        return next((q for q in self.created if q.id == fare_quote_id), None)

    def get_latest_for_ride(self, ride_id: uuid.UUID) -> FareQuote | None:
        matches = [q for q in self.created if q.ride_id == ride_id]
        if not matches:
            return None
        return max(matches, key=lambda q: q.version)

    def average_total_for_ids(self, fare_quote_ids: list[uuid.UUID]) -> Decimal:
        totals = [q.total for q in self.created if q.id in fare_quote_ids]
        if not totals:
            return Decimal("0")
        return sum(totals, Decimal("0")) / len(totals)


def _rule(
    vehicle_category: str,
    *,
    base_fare: str,
    per_km: str,
    minimum_fare: str,
) -> FareRule:
    return FareRule(
        id=uuid.uuid4(),
        vehicle_category=vehicle_category,
        base_fare=Decimal(base_fare),
        per_km=Decimal(per_km),
        per_minute=Decimal("0"),
        waiting_per_minute=Decimal("0"),
        minimum_fare=Decimal(minimum_fare),
        status=FareRuleStatus.PUBLISHED,
        effective_from=NOW - timedelta(days=1),
        effective_until=None,
        created_at=NOW,
    )


# --- fare_rule_key ----------------------------------------------------------


def test_fare_rule_key_for_cab_composes_the_tier() -> None:
    assert fare_rule_key("CAB", "ECO") == "CAB_ECO"
    assert fare_rule_key("CAB", "PREMIUM") == "CAB_PREMIUM"
    assert fare_rule_key("CAB", "PREMIUM_PLUS") == "CAB_PREMIUM_PLUS"


def test_fare_rule_key_for_bike_and_auto_is_unchanged() -> None:
    assert fare_rule_key("BIKE", None) == "BIKE"
    assert fare_rule_key("AUTO", None) == "AUTO"


# --- haversine_distance_km ---------------------------------------------------


def test_haversine_distance_between_identical_points_is_zero() -> None:
    assert haversine_distance_km(12.34, 56.78, 12.34, 56.78) == Decimal("0")


def test_haversine_distance_matches_known_value() -> None:
    distance = haversine_distance_km(*PICKUP, *DESTINATION)
    assert float(distance) == pytest.approx(2.854, abs=0.01)


# --- calculate_fare (pure domain logic) --------------------------------------


def test_calculate_fare_above_minimum_uses_base_plus_distance() -> None:
    rule = _rule("CAB_ECO", base_fare="55.00", per_km="12.00", minimum_fare="79.00")

    quote = calculate_fare(
        ride_id=RIDE_ID,
        rule=rule,
        pickup_latitude=PICKUP[0],
        pickup_longitude=PICKUP[1],
        destination_latitude=DESTINATION[0],
        destination_longitude=DESTINATION[1],
        promotion_discount_percent=None,
        promotion_max_discount_amount=None,
        now=NOW,
    )

    assert quote.base_fare == Decimal("55.00")
    assert quote.distance_charge == Decimal("34.25")  # 12.00 * 2.854, rounded
    assert quote.total == Decimal("89.25")
    assert quote.promotion_discount == Decimal("0.00")
    assert quote.time_charge == Decimal("0.00")
    assert quote.waiting_charge == Decimal("0.00")
    assert quote.version == 1
    assert quote.reason == "INITIAL_QUOTE"
    assert quote.status.value == "DRAFT"


def test_calculate_fare_below_minimum_is_floored() -> None:
    """A short trip whose base+distance falls under minimum_fare is
    floored to it, by bumping distance_charge (ADR-0020 Decision 4) —
    base_fare + distance_charge always sums to the floor exactly."""
    rule = _rule("BIKE", base_fare="29.00", per_km="7.00", minimum_fare="39.00")

    quote = calculate_fare(
        ride_id=RIDE_ID,
        rule=rule,
        pickup_latitude=25.5941,
        pickup_longitude=85.1376,
        destination_latitude=25.5945,  # ~50m away — a trivial distance
        destination_longitude=85.1376,
        promotion_discount_percent=None,
        promotion_max_discount_amount=None,
        now=NOW,
    )

    assert quote.base_fare + quote.distance_charge == Decimal("39.00")
    assert quote.total == Decimal("39.00")


def test_calculate_fare_applies_promotion_discount() -> None:
    """BR-058: 50% off."""
    rule = _rule("CAB_ECO", base_fare="55.00", per_km="12.00", minimum_fare="79.00")

    quote = calculate_fare(
        ride_id=RIDE_ID,
        rule=rule,
        pickup_latitude=PICKUP[0],
        pickup_longitude=PICKUP[1],
        destination_latitude=DESTINATION[0],
        destination_longitude=DESTINATION[1],
        promotion_discount_percent=Decimal("50"),
        promotion_max_discount_amount=None,
        now=NOW,
    )

    # 89.25 * 50% = 44.625, quantized ROUND_HALF_EVEN -> 44.62.
    assert quote.promotion_discount == Decimal("44.62")
    assert quote.total == Decimal("44.63")  # 89.25 - 44.62


def test_calculate_fare_promotion_discount_is_capped() -> None:
    rule = _rule("CAB_ECO", base_fare="55.00", per_km="12.00", minimum_fare="79.00")

    quote = calculate_fare(
        ride_id=RIDE_ID,
        rule=rule,
        pickup_latitude=PICKUP[0],
        pickup_longitude=PICKUP[1],
        destination_latitude=DESTINATION[0],
        destination_longitude=DESTINATION[1],
        promotion_discount_percent=Decimal("50"),
        promotion_max_discount_amount=Decimal("10.00"),
        now=NOW,
    )

    assert quote.promotion_discount == Decimal("10.00")  # capped, not 44.63
    assert quote.total == Decimal("79.25")


@pytest.mark.parametrize(
    ("ride_charge", "expected_discount"),
    [
        # BR-063/ADR-0049, owner-confirmed exactly 2026-09-04: 50% off,
        # capped at ₹100/ride — these are the owner's own worked
        # examples, not invented. per_km=0 makes ride_charge == base_fare
        # exactly, independent of the fixed PICKUP/DESTINATION distance
        # every other test in this file uses.
        ("100.00", "50.00"),  # 50% of 100 = 50, under the cap
        ("180.00", "90.00"),  # 50% of 180 = 90, under the cap
        ("200.00", "100.00"),  # 50% of 200 = 100, exactly at the cap
        ("500.00", "100.00"),  # 50% of 500 = 250, capped down to 100
    ],
)
def test_calculate_fare_promotion_discount_matches_owner_worked_examples(
    ride_charge: str, expected_discount: str
) -> None:
    rule = _rule("CAB_ECO", base_fare=ride_charge, per_km="0.00", minimum_fare="0.00")

    quote = calculate_fare(
        ride_id=RIDE_ID,
        rule=rule,
        pickup_latitude=PICKUP[0],
        pickup_longitude=PICKUP[1],
        destination_latitude=DESTINATION[0],
        destination_longitude=DESTINATION[1],
        promotion_discount_percent=Decimal("50"),
        promotion_max_discount_amount=Decimal("100"),
        now=NOW,
    )

    assert quote.promotion_discount == Decimal(expected_discount)
    assert quote.total == Decimal(ride_charge) - Decimal(expected_discount)


# --- PricingService.calculate_fare (repository composition) -----------------


def test_service_looks_up_the_rule_by_composite_key() -> None:
    rule = _rule("CAB_PREMIUM", base_fare="65.00", per_km="14.00", minimum_fare="99.00")
    service = PricingService(
        fare_rules=FakeFareRuleRepository({"CAB_PREMIUM": rule}),
        fare_quotes=FakeFareQuoteRepository(),
    )

    quote = service.calculate_fare(
        ride_id=RIDE_ID,
        vehicle_category="CAB",
        cab_tier="PREMIUM",
        pickup_latitude=PICKUP[0],
        pickup_longitude=PICKUP[1],
        destination_latitude=DESTINATION[0],
        destination_longitude=DESTINATION[1],
        now=NOW,
    )

    assert quote.base_fare == Decimal("65.00")


def test_service_persists_the_quote() -> None:
    rule = _rule("AUTO", base_fare="39.00", per_km="10.00", minimum_fare="59.00")
    fake_quotes = FakeFareQuoteRepository()
    service = PricingService(
        fare_rules=FakeFareRuleRepository({"AUTO": rule}),
        fare_quotes=fake_quotes,
    )

    quote = service.calculate_fare(
        ride_id=RIDE_ID,
        vehicle_category="AUTO",
        cab_tier=None,
        pickup_latitude=PICKUP[0],
        pickup_longitude=PICKUP[1],
        destination_latitude=DESTINATION[0],
        destination_longitude=DESTINATION[1],
        now=NOW,
    )

    assert fake_quotes.created == [quote]


def test_service_raises_when_no_active_rule_exists() -> None:
    service = PricingService(
        fare_rules=FakeFareRuleRepository({}),
        fare_quotes=FakeFareQuoteRepository(),
    )

    with pytest.raises(FareRuleNotFoundError):
        service.calculate_fare(
            ride_id=RIDE_ID,
            vehicle_category="BIKE",
            cab_tier=None,
            pickup_latitude=PICKUP[0],
            pickup_longitude=PICKUP[1],
            destination_latitude=DESTINATION[0],
            destination_longitude=DESTINATION[1],
            now=NOW,
        )


# --- get_fare_quote() (Phase 16, ADR-0023) ---------------------------------


def test_get_fare_quote_returns_a_previously_created_quote() -> None:
    rule = _rule("BIKE", base_fare="20.00", per_km="8.00", minimum_fare="30.00")
    fake_quotes = FakeFareQuoteRepository()
    service = PricingService(
        fare_rules=FakeFareRuleRepository({"BIKE": rule}), fare_quotes=fake_quotes
    )
    quote = service.calculate_fare(
        ride_id=RIDE_ID,
        vehicle_category="BIKE",
        cab_tier=None,
        pickup_latitude=PICKUP[0],
        pickup_longitude=PICKUP[1],
        destination_latitude=DESTINATION[0],
        destination_longitude=DESTINATION[1],
        now=NOW,
    )

    fetched = service.get_fare_quote(fare_quote_id=quote.id)

    assert fetched == quote


def test_get_fare_quote_returns_none_for_unknown_id() -> None:
    service = PricingService(
        fare_rules=FakeFareRuleRepository({}), fare_quotes=FakeFareQuoteRepository()
    )

    assert service.get_fare_quote(fare_quote_id=uuid.uuid4()) is None


# --- calculate_pickup_change_charge (ADR-0033) — REMOVED by ADR-0056
# (2026-08-31): pickup change has no chargeable path anymore, so these
# tests (both the pure domain function and PricingService's own
# composition) were deleted along with the code they tested. See
# ADR-0056 and the pricing/domain/entities.py history for what this
# section used to cover.


def _initial_quote(*, total: str = "70.00") -> FareQuote:
    return FareQuote(
        id=uuid.uuid4(),
        ride_id=RIDE_ID,
        version=1,
        base_fare=Decimal("20.00"),
        distance_charge=Decimal("50.00"),
        time_charge=Decimal("0.00"),
        waiting_charge=Decimal("0.00"),
        parking_charge=Decimal("0.00"),
        toll_charge=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        promotion_discount=Decimal("0.00"),
        additional_charge=Decimal("0.00"),
        total=Decimal(total),
        reason="INITIAL_QUOTE",
        status=FareQuoteStatus.DRAFT,
        created_at=NOW,
    )


# --- calculate_destination_change_fare (pure domain logic, ADR-0033 --------
# Decision 9). A due-east straight line at a fixed latitude, so the
# route-deviation projection is easy to reason about: pickup and
# destination differ only in longitude.

_ROUTE_PICKUP = (25.0000, 85.0000)
_ROUTE_DESTINATION = (25.0000, 85.0200)
_ROUTE_DEVIATION_THRESHOLD_METERS = 200.0
_DESTINATION_EXTENSION_RATE_PER_KM = Decimal("8.00")


def test_destination_change_within_route_needs_no_confirmation() -> None:
    rule = _rule("CAB_ECO", base_fare="20.00", per_km="10.00", minimum_fare="30.00")
    previous = _initial_quote(total="70.00")
    # Midpoint between pickup and destination.
    midpoint = (25.0000, 85.0100)

    quote, case = calculate_destination_change_fare(
        rule=rule,
        previous_quote=previous,
        original_pickup_latitude=_ROUTE_PICKUP[0],
        original_pickup_longitude=_ROUTE_PICKUP[1],
        original_destination_latitude=_ROUTE_DESTINATION[0],
        original_destination_longitude=_ROUTE_DESTINATION[1],
        new_destination_latitude=midpoint[0],
        new_destination_longitude=midpoint[1],
        current_latitude=_ROUTE_PICKUP[0],
        current_longitude=_ROUTE_PICKUP[1],
        route_deviation_threshold_meters=_ROUTE_DEVIATION_THRESHOLD_METERS,
        destination_extension_rate_per_km=_DESTINATION_EXTENSION_RATE_PER_KM,
        next_version=2,
        now=NOW,
    )

    assert case is DestinationChangeCase.WITHIN_ROUTE
    assert quote is None


def test_destination_change_beyond_original_bills_the_extra_distance() -> None:
    rule = _rule("CAB_ECO", base_fare="20.00", per_km="10.00", minimum_fare="30.00")
    previous = _initial_quote(total="70.00")
    # Same bearing, extended past the original destination.
    beyond = (25.0000, 85.0400)
    expected_additional_km = haversine_distance_km(
        _ROUTE_DESTINATION[0], _ROUTE_DESTINATION[1], beyond[0], beyond[1]
    )
    expected_additional_charge = (
        _DESTINATION_EXTENSION_RATE_PER_KM * expected_additional_km
    ).quantize(Decimal("0.01"))

    quote, case = calculate_destination_change_fare(
        rule=rule,
        previous_quote=previous,
        original_pickup_latitude=_ROUTE_PICKUP[0],
        original_pickup_longitude=_ROUTE_PICKUP[1],
        original_destination_latitude=_ROUTE_DESTINATION[0],
        original_destination_longitude=_ROUTE_DESTINATION[1],
        new_destination_latitude=beyond[0],
        new_destination_longitude=beyond[1],
        current_latitude=_ROUTE_PICKUP[0],
        current_longitude=_ROUTE_PICKUP[1],
        route_deviation_threshold_meters=_ROUTE_DEVIATION_THRESHOLD_METERS,
        destination_extension_rate_per_km=_DESTINATION_EXTENSION_RATE_PER_KM,
        next_version=2,
        now=NOW,
    )

    assert case is DestinationChangeCase.BEYOND_ORIGINAL
    assert quote is not None
    assert quote.version == 2
    assert quote.reason == "DESTINATION_CHANGE"
    assert quote.additional_charge == expected_additional_charge
    assert quote.total == previous.total + expected_additional_charge


def test_destination_change_different_route_recalculates_from_current_location() -> (
    None
):
    rule = _rule("CAB_ECO", base_fare="20.00", per_km="10.00", minimum_fare="30.00")
    previous = _initial_quote(total="70.00")
    # Far off the pickup->destination line — well beyond the tolerance.
    far_away = (25.1000, 85.0100)
    current_location = _ROUTE_PICKUP

    quote, case = calculate_destination_change_fare(
        rule=rule,
        previous_quote=previous,
        original_pickup_latitude=_ROUTE_PICKUP[0],
        original_pickup_longitude=_ROUTE_PICKUP[1],
        original_destination_latitude=_ROUTE_DESTINATION[0],
        original_destination_longitude=_ROUTE_DESTINATION[1],
        new_destination_latitude=far_away[0],
        new_destination_longitude=far_away[1],
        current_latitude=current_location[0],
        current_longitude=current_location[1],
        route_deviation_threshold_meters=_ROUTE_DEVIATION_THRESHOLD_METERS,
        destination_extension_rate_per_km=_DESTINATION_EXTENSION_RATE_PER_KM,
        next_version=2,
        now=NOW,
    )

    assert case is DestinationChangeCase.DIFFERENT_ROUTE
    assert quote is not None
    assert quote.reason == "DESTINATION_CHANGE"
    # additional_charge is always 0 for a full recalculation — the new
    # total comes entirely from base_fare + distance_charge instead.
    assert quote.additional_charge == Decimal("0.00")
    expected_distance_km = haversine_distance_km(
        current_location[0], current_location[1], far_away[0], far_away[1]
    )
    expected_distance_charge = (rule.per_km * expected_distance_km).quantize(
        Decimal("0.01")
    )
    assert quote.distance_charge == expected_distance_charge
    assert (
        quote.total
        == rule.base_fare + expected_distance_charge - previous.promotion_discount
    )


def test_destination_change_exactly_at_the_original_destination_is_within_route() -> (
    None
):
    """t == 1 (the projection lands exactly on the original destination)
    must be WITHIN_ROUTE, not BEYOND_ORIGINAL — BR-079 says "between"
    inclusively, and BR-080 requires actually going *beyond* it."""
    rule = _rule("CAB_ECO", base_fare="20.00", per_km="10.00", minimum_fare="30.00")
    previous = _initial_quote(total="70.00")

    quote, case = calculate_destination_change_fare(
        rule=rule,
        previous_quote=previous,
        original_pickup_latitude=_ROUTE_PICKUP[0],
        original_pickup_longitude=_ROUTE_PICKUP[1],
        original_destination_latitude=_ROUTE_DESTINATION[0],
        original_destination_longitude=_ROUTE_DESTINATION[1],
        new_destination_latitude=_ROUTE_DESTINATION[0],
        new_destination_longitude=_ROUTE_DESTINATION[1],
        current_latitude=_ROUTE_PICKUP[0],
        current_longitude=_ROUTE_PICKUP[1],
        route_deviation_threshold_meters=_ROUTE_DEVIATION_THRESHOLD_METERS,
        destination_extension_rate_per_km=_DESTINATION_EXTENSION_RATE_PER_KM,
        next_version=2,
        now=NOW,
    )

    assert case is DestinationChangeCase.WITHIN_ROUTE
    assert quote is None


def test_destination_change_behind_the_pickup_is_different_route() -> None:
    """A collinear point behind the original pickup (t < 0) is neither
    "between" (BR-079) nor "beyond the destination" (BR-080) — it must
    fall to the full-recalculation case (BR-081)."""
    rule = _rule("CAB_ECO", base_fare="20.00", per_km="10.00", minimum_fare="30.00")
    previous = _initial_quote(total="70.00")
    behind_pickup = (25.0000, 84.9900)

    _quote, case = calculate_destination_change_fare(
        rule=rule,
        previous_quote=previous,
        original_pickup_latitude=_ROUTE_PICKUP[0],
        original_pickup_longitude=_ROUTE_PICKUP[1],
        original_destination_latitude=_ROUTE_DESTINATION[0],
        original_destination_longitude=_ROUTE_DESTINATION[1],
        new_destination_latitude=behind_pickup[0],
        new_destination_longitude=behind_pickup[1],
        current_latitude=_ROUTE_PICKUP[0],
        current_longitude=_ROUTE_PICKUP[1],
        route_deviation_threshold_meters=_ROUTE_DEVIATION_THRESHOLD_METERS,
        destination_extension_rate_per_km=_DESTINATION_EXTENSION_RATE_PER_KM,
        next_version=2,
        now=NOW,
    )

    assert case is DestinationChangeCase.DIFFERENT_ROUTE


# --- PricingService.calculate_destination_change_fare -----------------------


def test_service_calculate_destination_change_fare_persists_a_quote() -> None:
    rule = _rule("BIKE", base_fare="20.00", per_km="8.00", minimum_fare="30.00")
    fake_quotes = FakeFareQuoteRepository()
    service = PricingService(
        fare_rules=FakeFareRuleRepository({"BIKE": rule}), fare_quotes=fake_quotes
    )
    initial = service.calculate_fare(
        ride_id=RIDE_ID,
        vehicle_category="BIKE",
        cab_tier=None,
        pickup_latitude=_ROUTE_PICKUP[0],
        pickup_longitude=_ROUTE_PICKUP[1],
        destination_latitude=_ROUTE_DESTINATION[0],
        destination_longitude=_ROUTE_DESTINATION[1],
        now=NOW,
    )

    quote, case = service.calculate_destination_change_fare(
        ride_id=RIDE_ID,
        vehicle_category="BIKE",
        cab_tier=None,
        original_pickup_latitude=_ROUTE_PICKUP[0],
        original_pickup_longitude=_ROUTE_PICKUP[1],
        original_destination_latitude=_ROUTE_DESTINATION[0],
        original_destination_longitude=_ROUTE_DESTINATION[1],
        new_destination_latitude=25.0000,
        new_destination_longitude=85.0400,
        current_latitude=_ROUTE_PICKUP[0],
        current_longitude=_ROUTE_PICKUP[1],
        route_deviation_threshold_meters=_ROUTE_DEVIATION_THRESHOLD_METERS,
        destination_extension_rate_per_km=_DESTINATION_EXTENSION_RATE_PER_KM,
        now=NOW,
    )

    assert case is DestinationChangeCase.BEYOND_ORIGINAL
    assert quote is not None
    assert quote.version == 2
    assert fake_quotes.get_latest_for_ride(RIDE_ID) == quote
    assert initial.id != quote.id


def test_service_calculate_destination_change_fare_within_route_creates_no_quote() -> (
    None
):
    rule = _rule("BIKE", base_fare="20.00", per_km="8.00", minimum_fare="30.00")
    fake_quotes = FakeFareQuoteRepository()
    service = PricingService(
        fare_rules=FakeFareRuleRepository({"BIKE": rule}), fare_quotes=fake_quotes
    )
    service.calculate_fare(
        ride_id=RIDE_ID,
        vehicle_category="BIKE",
        cab_tier=None,
        pickup_latitude=_ROUTE_PICKUP[0],
        pickup_longitude=_ROUTE_PICKUP[1],
        destination_latitude=_ROUTE_DESTINATION[0],
        destination_longitude=_ROUTE_DESTINATION[1],
        now=NOW,
    )

    quote, case = service.calculate_destination_change_fare(
        ride_id=RIDE_ID,
        vehicle_category="BIKE",
        cab_tier=None,
        original_pickup_latitude=_ROUTE_PICKUP[0],
        original_pickup_longitude=_ROUTE_PICKUP[1],
        original_destination_latitude=_ROUTE_DESTINATION[0],
        original_destination_longitude=_ROUTE_DESTINATION[1],
        new_destination_latitude=25.0000,
        new_destination_longitude=85.0100,
        current_latitude=_ROUTE_PICKUP[0],
        current_longitude=_ROUTE_PICKUP[1],
        route_deviation_threshold_meters=_ROUTE_DEVIATION_THRESHOLD_METERS,
        destination_extension_rate_per_km=_DESTINATION_EXTENSION_RATE_PER_KM,
        now=NOW,
    )

    assert case is DestinationChangeCase.WITHIN_ROUTE
    assert quote is None
    assert len(fake_quotes.created) == 1  # only the initial quote


def test_service_calculate_destination_change_fare_raises_without_a_prior_quote() -> (
    None
):
    rule = _rule("BIKE", base_fare="20.00", per_km="8.00", minimum_fare="30.00")
    service = PricingService(
        fare_rules=FakeFareRuleRepository({"BIKE": rule}),
        fare_quotes=FakeFareQuoteRepository(),
    )

    with pytest.raises(PreviousFareQuoteNotFoundError):
        service.calculate_destination_change_fare(
            ride_id=RIDE_ID,
            vehicle_category="BIKE",
            cab_tier=None,
            original_pickup_latitude=_ROUTE_PICKUP[0],
            original_pickup_longitude=_ROUTE_PICKUP[1],
            original_destination_latitude=_ROUTE_DESTINATION[0],
            original_destination_longitude=_ROUTE_DESTINATION[1],
            new_destination_latitude=25.0000,
            new_destination_longitude=85.0400,
            current_latitude=_ROUTE_PICKUP[0],
            current_longitude=_ROUTE_PICKUP[1],
            route_deviation_threshold_meters=_ROUTE_DEVIATION_THRESHOLD_METERS,
            destination_extension_rate_per_km=_DESTINATION_EXTENSION_RATE_PER_KM,
            now=NOW,
        )


# --- Fare Management (Admin Web §4.8, ADR-0042) -----------------------------


def _draft_service() -> tuple[PricingService, FakeFareRuleRepository]:
    fake_rules = FakeFareRuleRepository()
    service = PricingService(
        fare_rules=fake_rules, fare_quotes=FakeFareQuoteRepository()
    )
    return service, fake_rules


def test_create_fare_rule_starts_as_draft() -> None:
    service, _fake_rules = _draft_service()

    rule = service.create_fare_rule(
        vehicle_category="CAB_ECO",
        base_fare=Decimal("55.00"),
        per_km=Decimal("12.00"),
        per_minute=Decimal("0"),
        waiting_per_minute=Decimal("0"),
        minimum_fare=Decimal("79.00"),
        now=NOW,
    )

    assert rule.status is FareRuleStatus.DRAFT
    assert rule.effective_from is None


def test_create_fare_rule_rejects_negative_rate() -> None:
    service, _fake_rules = _draft_service()

    with pytest.raises(InvalidFareRuleInputError):
        service.create_fare_rule(
            vehicle_category="CAB_ECO",
            base_fare=Decimal("-1"),
            per_km=Decimal("12.00"),
            per_minute=Decimal("0"),
            waiting_per_minute=Decimal("0"),
            minimum_fare=Decimal("79.00"),
            now=NOW,
        )


def test_submit_for_review_then_publish() -> None:
    service, _fake_rules = _draft_service()
    rule = service.create_fare_rule(
        vehicle_category="CAB_ECO",
        base_fare=Decimal("55.00"),
        per_km=Decimal("12.00"),
        per_minute=Decimal("0"),
        waiting_per_minute=Decimal("0"),
        minimum_fare=Decimal("79.00"),
        now=NOW,
    )

    reviewed = service.submit_fare_rule_for_review(rule.id)
    assert reviewed.status is FareRuleStatus.IN_REVIEW

    published = service.publish_fare_rule(rule_id=rule.id, effective_from=None, now=NOW)
    assert published.status is FareRuleStatus.PUBLISHED
    assert published.effective_from == NOW


def test_publish_directly_from_draft_is_allowed() -> None:
    """ADR-0042 Decision 3: Submit for Review is not a mandatory gate."""
    service, _fake_rules = _draft_service()
    rule = service.create_fare_rule(
        vehicle_category="CAB_ECO",
        base_fare=Decimal("55.00"),
        per_km=Decimal("12.00"),
        per_minute=Decimal("0"),
        waiting_per_minute=Decimal("0"),
        minimum_fare=Decimal("79.00"),
        now=NOW,
    )

    published = service.publish_fare_rule(rule_id=rule.id, effective_from=None, now=NOW)
    assert published.status is FareRuleStatus.PUBLISHED


def test_publish_twice_is_rejected() -> None:
    service, _fake_rules = _draft_service()
    rule = service.create_fare_rule(
        vehicle_category="CAB_ECO",
        base_fare=Decimal("55.00"),
        per_km=Decimal("12.00"),
        per_minute=Decimal("0"),
        waiting_per_minute=Decimal("0"),
        minimum_fare=Decimal("79.00"),
        now=NOW,
    )
    service.publish_fare_rule(rule_id=rule.id, effective_from=None, now=NOW)

    with pytest.raises(InvalidFareRuleStateTransitionError):
        service.publish_fare_rule(rule_id=rule.id, effective_from=None, now=NOW)


def test_publish_closes_out_the_previously_published_rule() -> None:
    """ADR-0042 Decision 2: at most one rule is ever live per category."""
    service, fake_rules = _draft_service()
    old_rule = service.create_fare_rule(
        vehicle_category="CAB_ECO",
        base_fare=Decimal("50.00"),
        per_km=Decimal("10.00"),
        per_minute=Decimal("0"),
        waiting_per_minute=Decimal("0"),
        minimum_fare=Decimal("70.00"),
        now=NOW - timedelta(days=10),
    )
    service.publish_fare_rule(
        rule_id=old_rule.id, effective_from=NOW - timedelta(days=10), now=NOW
    )
    assert fake_rules.by_id[old_rule.id].effective_until is None

    new_rule = service.create_fare_rule(
        vehicle_category="CAB_ECO",
        base_fare=Decimal("55.00"),
        per_km=Decimal("12.00"),
        per_minute=Decimal("0"),
        waiting_per_minute=Decimal("0"),
        minimum_fare=Decimal("79.00"),
        now=NOW,
    )
    service.publish_fare_rule(rule_id=new_rule.id, effective_from=NOW, now=NOW)

    assert fake_rules.by_id[old_rule.id].effective_until == NOW
    assert fake_rules.by_id[new_rule.id].effective_from == NOW
    assert fake_rules.by_id[new_rule.id].effective_until is None
    # calculate_fare now resolves to the new rule, not the old one.
    live = service._fare_rules.get_active_by_category("CAB_ECO", now=NOW)
    assert live is not None and live.id == new_rule.id


def test_list_fare_rules_returns_every_status() -> None:
    service, _fake_rules = _draft_service()
    draft = service.create_fare_rule(
        vehicle_category="BIKE",
        base_fare=Decimal("20.00"),
        per_km=Decimal("8.00"),
        per_minute=Decimal("0"),
        waiting_per_minute=Decimal("0"),
        minimum_fare=Decimal("30.00"),
        now=NOW,
    )
    published = service.create_fare_rule(
        vehicle_category="BIKE",
        base_fare=Decimal("22.00"),
        per_km=Decimal("9.00"),
        per_minute=Decimal("0"),
        waiting_per_minute=Decimal("0"),
        minimum_fare=Decimal("32.00"),
        now=NOW,
    )
    service.publish_fare_rule(rule_id=published.id, effective_from=NOW, now=NOW)

    rules, total = service.list_fare_rules(
        vehicle_category="BIKE", status=None, offset=0, limit=20
    )

    assert total == 2
    assert {r.id for r in rules} == {draft.id, published.id}


def test_get_fare_rule_unknown_id_raises() -> None:
    service, _fake_rules = _draft_service()

    with pytest.raises(FareRuleNotFoundError):
        service.get_fare_rule(uuid.uuid4())


# --- Platform Fee Management (Admin Web §4.8, ADR-0045) ---------------------

ADMIN_ID = uuid.uuid4()


def _platform_fee_service() -> tuple[PricingService, FakePlatformFeeRuleRepository]:
    fake_rules = FakePlatformFeeRuleRepository()
    service = PricingService(
        fare_rules=FakeFareRuleRepository(),
        fare_quotes=FakeFareQuoteRepository(),
        platform_fee_rules=fake_rules,
    )
    return service, fake_rules


def test_create_platform_fee_rule_starts_as_draft() -> None:
    service, _fake_rules = _platform_fee_service()

    rule = service.create_platform_fee_rule(
        vehicle_category="BIKE",
        fee_amount=Decimal("3.00"),
        created_by=ADMIN_ID,
        now=NOW,
    )

    assert rule.status is FareRuleStatus.DRAFT
    assert rule.effective_from is None


def test_create_platform_fee_rule_rejects_negative_amount() -> None:
    service, _fake_rules = _platform_fee_service()

    with pytest.raises(InvalidPlatformFeeRuleInputError):
        service.create_platform_fee_rule(
            vehicle_category="BIKE",
            fee_amount=Decimal("-1"),
            created_by=ADMIN_ID,
            now=NOW,
        )


def test_create_platform_fee_rule_rejects_unknown_category() -> None:
    service, _fake_rules = _platform_fee_service()

    with pytest.raises(InvalidPlatformFeeRuleInputError):
        service.create_platform_fee_rule(
            vehicle_category="CAB_ECO",  # fare_rules' 5-key set, not this one
            fee_amount=Decimal("5.00"),
            created_by=ADMIN_ID,
            now=NOW,
        )


def test_platform_fee_rule_submit_for_review_then_publish() -> None:
    service, _fake_rules = _platform_fee_service()
    rule = service.create_platform_fee_rule(
        vehicle_category="AUTO",
        fee_amount=Decimal("5.00"),
        created_by=ADMIN_ID,
        now=NOW,
    )

    reviewed = service.submit_platform_fee_rule_for_review(rule.id)
    assert reviewed.status is FareRuleStatus.IN_REVIEW

    published = service.publish_platform_fee_rule(
        rule_id=rule.id, effective_from=None, now=NOW
    )
    assert published.status is FareRuleStatus.PUBLISHED
    assert published.effective_from == NOW


def test_publish_platform_fee_rule_twice_is_rejected() -> None:
    service, _fake_rules = _platform_fee_service()
    rule = service.create_platform_fee_rule(
        vehicle_category="AUTO",
        fee_amount=Decimal("5.00"),
        created_by=ADMIN_ID,
        now=NOW,
    )
    service.publish_platform_fee_rule(rule_id=rule.id, effective_from=None, now=NOW)

    with pytest.raises(InvalidPlatformFeeRuleStateTransitionError):
        service.publish_platform_fee_rule(rule_id=rule.id, effective_from=None, now=NOW)


def test_publish_platform_fee_rule_closes_out_the_previously_published_rule() -> None:
    """ADR-0045 Decision 1: at most one rule is ever live per category,
    same "close out the previous one" mechanism as Fare Management."""
    service, fake_rules = _platform_fee_service()
    old_rule = service.create_platform_fee_rule(
        vehicle_category="CAB",
        fee_amount=Decimal("8.00"),
        created_by=ADMIN_ID,
        now=NOW - timedelta(days=10),
    )
    service.publish_platform_fee_rule(
        rule_id=old_rule.id, effective_from=NOW - timedelta(days=10), now=NOW
    )
    assert fake_rules.by_id[old_rule.id].effective_until is None

    new_rule = service.create_platform_fee_rule(
        vehicle_category="CAB",
        fee_amount=Decimal("10.00"),
        created_by=ADMIN_ID,
        now=NOW,
    )
    service.publish_platform_fee_rule(rule_id=new_rule.id, effective_from=NOW, now=NOW)

    assert fake_rules.by_id[old_rule.id].effective_until == NOW
    assert fake_rules.by_id[new_rule.id].effective_from == NOW
    assert fake_rules.by_id[new_rule.id].effective_until is None
    live = service.get_active_platform_fee_rule("CAB", now=NOW)
    assert live is not None and live.id == new_rule.id


def test_list_platform_fee_rules_returns_every_status() -> None:
    service, _fake_rules = _platform_fee_service()
    draft = service.create_platform_fee_rule(
        vehicle_category="BIKE",
        fee_amount=Decimal("2.00"),
        created_by=ADMIN_ID,
        now=NOW,
    )
    published = service.create_platform_fee_rule(
        vehicle_category="BIKE",
        fee_amount=Decimal("3.00"),
        created_by=ADMIN_ID,
        now=NOW,
    )
    service.publish_platform_fee_rule(rule_id=published.id, effective_from=NOW, now=NOW)

    rules, total = service.list_platform_fee_rules(
        vehicle_category="BIKE", status=None, offset=0, limit=20
    )

    assert total == 2
    assert {r.id for r in rules} == {draft.id, published.id}


def test_get_platform_fee_rule_unknown_id_raises() -> None:
    service, _fake_rules = _platform_fee_service()

    with pytest.raises(PlatformFeeRuleNotFoundError):
        service.get_platform_fee_rule(uuid.uuid4())


def test_get_active_platform_fee_rule_returns_none_when_nothing_published() -> None:
    service, _fake_rules = _platform_fee_service()

    assert service.get_active_platform_fee_rule("BIKE", now=NOW) is None
