"""Pricing domain entities and fare calculation.

Field shapes match docs/04-database/database-design.md §15.1
(pricing.fare_rules) and §15.2 (pricing.fare_quotes) exactly, plus one
additive column (fare_rules.minimum_fare — ADR-0020 Decision 4).
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from modules.pricing.domain.errors import (
    InvalidFareRuleInputError,
    InvalidFareRuleStateTransitionError,
    InvalidPlatformFeeRuleInputError,
    InvalidPlatformFeeRuleStateTransitionError,
)

_MONEY_QUANTUM = Decimal("0.01")

# BR-005/006 (business-rules.md), resolved by ADR-0020: no Time Charge
# component in v1 — nothing in pricing.fare_rules' per_minute column is
# ever read here, and per_minute is always seeded as 0 (see the
# migration). Kept as a real, documented-but-currently-inert column
# rather than removed — the same "0 for now, not deleted" treatment
# every other unimplemented fare_quotes line item already gets.

# Earth radius in km — standard mean-radius constant, used only by the
# interim haversine distance calculation below (ADR-0020 Decision 5).
_EARTH_RADIUS_KM = 6371.0


class FareQuoteStatus(StrEnum):
    """DRAFT is database-design.md §15.2's documented default. No other
    value is produced yet — CreateFareRevision (customer-confirmation-
    gated revisions, BR-032/033) is not implemented (ADR-0020 §7:
    nothing calls it yet), so nothing here ever needs a second state."""

    DRAFT = "DRAFT"


class FareRuleStatus(StrEnum):
    """ADR-0042: replaces the old `active` boolean. DRAFT -> IN_REVIEW ->
    PUBLISHED — see PublishFareRule (service.py) for why Submit for
    Review is not a mandatory gate before Publish."""

    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    PUBLISHED = "PUBLISHED"


@dataclass(slots=True)
class FareRule:
    id: uuid.UUID
    vehicle_category: str
    base_fare: Decimal
    per_km: Decimal
    per_minute: Decimal
    waiting_per_minute: Decimal
    minimum_fare: Decimal
    status: FareRuleStatus
    effective_from: datetime | None
    effective_until: datetime | None
    created_at: datetime

    @staticmethod
    def new(
        *,
        vehicle_category: str,
        base_fare: Decimal,
        per_km: Decimal,
        per_minute: Decimal,
        waiting_per_minute: Decimal,
        minimum_fare: Decimal,
        now: datetime,
    ) -> FareRule:
        """ADR-0042 Decision 4 (Create Draft). effective_from/until stay
        NULL until Publish — a draft's live-from moment is not decided
        yet."""
        if not vehicle_category.strip():
            raise InvalidFareRuleInputError("vehicle_category is required.")
        for name, value in (
            ("base_fare", base_fare),
            ("per_km", per_km),
            ("per_minute", per_minute),
            ("waiting_per_minute", waiting_per_minute),
            ("minimum_fare", minimum_fare),
        ):
            if value < 0:
                raise InvalidFareRuleInputError(f"{name} cannot be negative.")
        return FareRule(
            id=uuid.uuid4(),
            vehicle_category=vehicle_category,
            base_fare=base_fare,
            per_km=per_km,
            per_minute=per_minute,
            waiting_per_minute=waiting_per_minute,
            minimum_fare=minimum_fare,
            status=FareRuleStatus.DRAFT,
            effective_from=None,
            effective_until=None,
            created_at=now,
        )

    def submit_for_review(self) -> None:
        if self.status is not FareRuleStatus.DRAFT:
            raise InvalidFareRuleStateTransitionError(
                f"Cannot submit a fare rule in status {self.status} for review."
            )
        self.status = FareRuleStatus.IN_REVIEW

    def publish(self, *, effective_from: datetime) -> None:
        """Only sets this rule's own fields — closing out any
        previously-published rule for the same category is the service
        layer's job (ADR-0042 Decision 2), since it spans two rows."""
        if self.status not in (FareRuleStatus.DRAFT, FareRuleStatus.IN_REVIEW):
            raise InvalidFareRuleStateTransitionError(
                f"Cannot publish a fare rule already in status {self.status}."
            )
        self.status = FareRuleStatus.PUBLISHED
        self.effective_from = effective_from


_PLATFORM_FEE_VEHICLE_CATEGORIES = frozenset({"BIKE", "AUTO", "CAB"})


@dataclass(slots=True)
class PlatformFeeRule:
    """ADR-0045 — BR-011's driver platform fee. A separate table from
    FareRule above, not an additional column on it: a platform fee
    (driver economics) and a customer fare are two different concepts
    that happen to share a versioning shape. Keyed by the plain 3-value
    `vehicle_category` set (BIKE/AUTO/CAB) — deliberately NOT
    fare_rules' 5-key set, since no per-CAB-tier fee is documented
    anywhere (BR-011: "CAB's fee applies uniformly regardless of
    tier"). Reuses FareRuleStatus — the identical DRAFT/IN_REVIEW/
    PUBLISHED vocabulary, same module."""

    id: uuid.UUID
    vehicle_category: str
    fee_amount: Decimal
    status: FareRuleStatus
    effective_from: datetime | None
    effective_until: datetime | None
    created_by: uuid.UUID
    created_at: datetime

    @staticmethod
    def new(
        *,
        vehicle_category: str,
        fee_amount: Decimal,
        created_by: uuid.UUID,
        now: datetime,
    ) -> PlatformFeeRule:
        if vehicle_category not in _PLATFORM_FEE_VEHICLE_CATEGORIES:
            raise InvalidPlatformFeeRuleInputError(
                "vehicle_category must be one of BIKE, AUTO, CAB."
            )
        if fee_amount < 0:
            raise InvalidPlatformFeeRuleInputError("fee_amount cannot be negative.")
        return PlatformFeeRule(
            id=uuid.uuid4(),
            vehicle_category=vehicle_category,
            fee_amount=fee_amount,
            status=FareRuleStatus.DRAFT,
            effective_from=None,
            effective_until=None,
            created_by=created_by,
            created_at=now,
        )

    def submit_for_review(self) -> None:
        if self.status is not FareRuleStatus.DRAFT:
            raise InvalidPlatformFeeRuleStateTransitionError(
                f"Cannot submit a platform fee rule in status {self.status} for review."
            )
        self.status = FareRuleStatus.IN_REVIEW

    def publish(self, *, effective_from: datetime) -> None:
        if self.status not in (FareRuleStatus.DRAFT, FareRuleStatus.IN_REVIEW):
            raise InvalidPlatformFeeRuleStateTransitionError(
                f"Cannot publish a platform fee rule already in status {self.status}."
            )
        self.status = FareRuleStatus.PUBLISHED
        self.effective_from = effective_from


@dataclass(slots=True)
class FareQuote:
    id: uuid.UUID
    ride_id: uuid.UUID
    version: int
    base_fare: Decimal
    distance_charge: Decimal
    time_charge: Decimal
    waiting_charge: Decimal
    parking_charge: Decimal
    toll_charge: Decimal
    tax_amount: Decimal
    promotion_discount: Decimal
    additional_charge: Decimal
    total: Decimal
    reason: str | None
    status: FareQuoteStatus
    created_at: datetime


def fare_rule_key(vehicle_category: str, cab_tier: str | None) -> str:
    """The string pricing.fare_rules.vehicle_category is actually keyed
    by (ADR-0020 Decision 1/5) — "CAB_ECO"/"CAB_PREMIUM"/
    "CAB_PREMIUM_PLUS" for CAB's three sub-tiers, the bare category
    otherwise. Mirrors modules.vehicle.domain.entities.
    matching_category_key()'s same composite-key idea, but with an
    underscore (fare_rules.vehicle_category is a plain VARCHAR(20) key,
    not also used as a Redis key, so no ":" delimiter convention to
    match)."""
    if vehicle_category == "CAB":
        assert cab_tier is not None  # enforced upstream (validate_cab_tier)
        return f"CAB_{cab_tier}"
    return vehicle_category


def haversine_distance_km(
    pickup_latitude: float,
    pickup_longitude: float,
    destination_latitude: float,
    destination_longitude: float,
) -> Decimal:
    """Interim straight-line distance (ADR-0020 Decision 5) — NOT the
    real road distance technical-architecture.md's Mapbox+OSM choice
    would eventually provide; no Mapbox credential exists in this
    environment (§0.4), the same "flag the specific external-provider
    gap, build everything else" treatment ADR-0018 gave Admoto.
    Standard haversine great-circle formula."""
    lat1, lon1, lat2, lon2 = map(
        math.radians,
        [
            pickup_latitude,
            pickup_longitude,
            destination_latitude,
            destination_longitude,
        ],
    )
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    return Decimal(str(_EARTH_RADIUS_KM * c))


def calculate_fare(
    *,
    ride_id: uuid.UUID,
    rule: FareRule,
    pickup_latitude: float,
    pickup_longitude: float,
    destination_latitude: float,
    destination_longitude: float,
    promotion_discount_percent: Decimal | None,
    promotion_max_discount_amount: Decimal | None,
    now: datetime,
) -> FareQuote:
    """CalculateFare (domain-design.md §11.4), folding in
    ApplyPromotionDiscount when a reserved entitlement is passed in —
    ADR-0020 Decision 6: the one real caller (ride creation) always
    needs both together, the same pragmatic single-command-does-both
    shape ADR-0019 used for GrantReferralPromotion's referred/referring
    sides. Always version 1 / reason INITIAL_QUOTE — CreateFareRevision
    is not implemented (see this module's docstring).

    total = max(minimum_fare, base_fare + per_km * distance)
            - promotion_discount
    (+ time_charge(0) + waiting_charge(0) + parking_charge(0) +
    toll_charge(0) + tax_amount(0) + additional_charge(0) — domain-
    design.md §11.3's formula exactly, with every not-yet-composed line
    item genuinely 0, not omitted)."""
    distance_km = haversine_distance_km(
        pickup_latitude, pickup_longitude, destination_latitude, destination_longitude
    )
    raw_distance_charge = (rule.per_km * distance_km).quantize(_MONEY_QUANTUM)

    subtotal = rule.base_fare + raw_distance_charge
    if subtotal < rule.minimum_fare:
        # Floor applied by bumping distance_charge, not by adding a new
        # column — see this module's docstring / ADR-0020 Decision 4.
        distance_charge = (rule.minimum_fare - rule.base_fare).quantize(_MONEY_QUANTUM)
    else:
        distance_charge = raw_distance_charge

    ride_charge = rule.base_fare + distance_charge

    promotion_discount = Decimal("0.00")
    if promotion_discount_percent is not None:
        promotion_discount = (
            ride_charge * promotion_discount_percent / Decimal("100")
        ).quantize(_MONEY_QUANTUM)
        if promotion_max_discount_amount is not None:
            promotion_discount = min(promotion_discount, promotion_max_discount_amount)

    total = ride_charge - promotion_discount

    return FareQuote(
        id=uuid.uuid4(),
        ride_id=ride_id,
        version=1,
        base_fare=rule.base_fare,
        distance_charge=distance_charge,
        time_charge=Decimal("0.00"),
        waiting_charge=Decimal("0.00"),
        parking_charge=Decimal("0.00"),
        toll_charge=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        promotion_discount=promotion_discount,
        additional_charge=Decimal("0.00"),
        total=total,
        reason="INITIAL_QUOTE",
        status=FareQuoteStatus.DRAFT,
        created_at=now,
    )


class DestinationChangeCase(StrEnum):
    """BR-079/080/081 (ADR-0033 Decision 9)."""

    WITHIN_ROUTE = "WITHIN_ROUTE"
    BEYOND_ORIGINAL = "BEYOND_ORIGINAL"
    DIFFERENT_ROUTE = "DIFFERENT_ROUTE"


# Approximate meters-per-degree at the equator — used only to convert
# lat/lon degree differences into a local planar (x, y) meters
# approximation for the point-to-line projection below. Accurate enough
# at city scale (the same "interim, not real geodesy" treatment
# haversine_distance_km already gets, ADR-0020 Decision 5) — longitude
# is scaled by cos(latitude) to account for meridians converging toward
# the poles.
_METERS_PER_DEGREE_LATITUDE = 111_320.0


def _classify_destination_change(
    *,
    original_pickup_latitude: float,
    original_pickup_longitude: float,
    original_destination_latitude: float,
    original_destination_longitude: float,
    new_destination_latitude: float,
    new_destination_longitude: float,
    route_deviation_threshold_meters: float,
) -> DestinationChangeCase:
    """ADR-0033 Decision 9. Projects the new destination onto the
    (infinite) line through the original pickup and original
    destination, in a local planar-meters approximation. Within
    `route_deviation_threshold_meters` of that line: a projection at or
    before the original destination is WITHIN_ROUTE (BR-079), beyond it
    is BEYOND_ORIGINAL (BR-080). Off the line entirely (including
    "behind" the original pickup) is DIFFERENT_ROUTE (BR-081) — no
    document addresses that specific sub-case, and treating it as
    "simply beyond" would misapply BR-080's flat-rate billing to a
    change that isn't actually a simple extension."""
    mean_lat_radians = math.radians(
        (original_pickup_latitude + original_destination_latitude) / 2
    )
    meters_per_degree_longitude = _METERS_PER_DEGREE_LATITUDE * math.cos(
        mean_lat_radians
    )

    def to_local_meters(latitude: float, longitude: float) -> tuple[float, float]:
        return (
            (longitude - original_pickup_longitude) * meters_per_degree_longitude,
            (latitude - original_pickup_latitude) * _METERS_PER_DEGREE_LATITUDE,
        )

    ax, ay = 0.0, 0.0  # original pickup, the local origin
    bx, by = to_local_meters(
        original_destination_latitude, original_destination_longitude
    )
    px, py = to_local_meters(new_destination_latitude, new_destination_longitude)

    ab_x, ab_y = bx - ax, by - ay
    ap_x, ap_y = px - ax, py - ay
    ab_length_squared = ab_x * ab_x + ab_y * ab_y

    if ab_length_squared == 0.0:
        # Degenerate case (original pickup == original destination) —
        # no line to project onto; nothing here is genuinely "along the
        # route", so recalculate fully.
        return DestinationChangeCase.DIFFERENT_ROUTE

    t = (ap_x * ab_x + ap_y * ab_y) / ab_length_squared
    closest_x, closest_y = ax + t * ab_x, ay + t * ab_y
    perpendicular_distance_meters = math.hypot(px - closest_x, py - closest_y)

    if perpendicular_distance_meters > route_deviation_threshold_meters or t < 0:
        return DestinationChangeCase.DIFFERENT_ROUTE
    if t <= 1:
        return DestinationChangeCase.WITHIN_ROUTE
    return DestinationChangeCase.BEYOND_ORIGINAL


def calculate_destination_change_fare(
    *,
    rule: FareRule,
    previous_quote: FareQuote,
    original_pickup_latitude: float,
    original_pickup_longitude: float,
    original_destination_latitude: float,
    original_destination_longitude: float,
    new_destination_latitude: float,
    new_destination_longitude: float,
    current_latitude: float,
    current_longitude: float,
    route_deviation_threshold_meters: float,
    destination_extension_rate_per_km: Decimal,
    next_version: int,
    now: datetime,
) -> tuple[FareQuote | None, DestinationChangeCase]:
    """CalculateDestinationChangeFare (domain-design.md §11.4, ADR-0033
    Decision 9 — BR-079/080/081). Returns (None, WITHIN_ROUTE) for
    BR-079 — no charge, no quote, the same "nothing changed, no
    ceremony" treatment a ≤threshold pickup change gets (ADR-0033
    Decision 5; the >threshold pickup-change *charge* path this once
    also referenced was removed by ADR-0056, 2026-08-31). BEYOND_
    ORIGINAL (BR-080) bills `additional_charge = ₹8/km × the straight-
    line distance from the original destination to the new one` — not
    the deviation-projection distance, matching BR-080's own worked
    example's literal "additional distance" framing. DIFFERENT_ROUTE
    (BR-081) recalculates the full base_fare/distance_charge from
    `current_latitude/longitude` (ADR-0033's documented interpretation
    of "current location") to the new destination, carrying forward the
    previous quote's promotion_discount unchanged (BR-063's discount cap
    is a flat reservation, not a formula reapplied on every revision)."""
    case = _classify_destination_change(
        original_pickup_latitude=original_pickup_latitude,
        original_pickup_longitude=original_pickup_longitude,
        original_destination_latitude=original_destination_latitude,
        original_destination_longitude=original_destination_longitude,
        new_destination_latitude=new_destination_latitude,
        new_destination_longitude=new_destination_longitude,
        route_deviation_threshold_meters=route_deviation_threshold_meters,
    )

    if case is DestinationChangeCase.WITHIN_ROUTE:
        return None, case

    if case is DestinationChangeCase.BEYOND_ORIGINAL:
        additional_distance_km = haversine_distance_km(
            original_destination_latitude,
            original_destination_longitude,
            new_destination_latitude,
            new_destination_longitude,
        )
        additional_charge = (
            destination_extension_rate_per_km * additional_distance_km
        ).quantize(_MONEY_QUANTUM)
        total = previous_quote.total + additional_charge
        return (
            FareQuote(
                id=uuid.uuid4(),
                ride_id=previous_quote.ride_id,
                version=next_version,
                base_fare=previous_quote.base_fare,
                distance_charge=previous_quote.distance_charge,
                time_charge=previous_quote.time_charge,
                waiting_charge=previous_quote.waiting_charge,
                parking_charge=previous_quote.parking_charge,
                toll_charge=previous_quote.toll_charge,
                tax_amount=previous_quote.tax_amount,
                promotion_discount=previous_quote.promotion_discount,
                additional_charge=additional_charge,
                total=total,
                reason="DESTINATION_CHANGE",
                status=FareQuoteStatus.DRAFT,
                created_at=now,
            ),
            case,
        )

    # DIFFERENT_ROUTE — full recalculation from current_latitude/
    # longitude to the new destination, same base_fare + distance_charge
    # (floored at minimum_fare) formula calculate_fare() itself uses.
    distance_km = haversine_distance_km(
        current_latitude,
        current_longitude,
        new_destination_latitude,
        new_destination_longitude,
    )
    raw_distance_charge = (rule.per_km * distance_km).quantize(_MONEY_QUANTUM)
    subtotal = rule.base_fare + raw_distance_charge
    if subtotal < rule.minimum_fare:
        distance_charge = (rule.minimum_fare - rule.base_fare).quantize(_MONEY_QUANTUM)
    else:
        distance_charge = raw_distance_charge
    new_ride_charge = rule.base_fare + distance_charge
    total = new_ride_charge - previous_quote.promotion_discount

    return (
        FareQuote(
            id=uuid.uuid4(),
            ride_id=previous_quote.ride_id,
            version=next_version,
            base_fare=rule.base_fare,
            distance_charge=distance_charge,
            time_charge=previous_quote.time_charge,
            waiting_charge=previous_quote.waiting_charge,
            parking_charge=previous_quote.parking_charge,
            toll_charge=previous_quote.toll_charge,
            tax_amount=previous_quote.tax_amount,
            promotion_discount=previous_quote.promotion_discount,
            additional_charge=Decimal("0.00"),
            total=total,
            reason="DESTINATION_CHANGE",
            status=FareQuoteStatus.DRAFT,
            created_at=now,
        ),
        case,
    )
