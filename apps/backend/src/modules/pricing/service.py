"""Application service (use cases) for Pricing.

Implements domain-design.md §11.4's CalculateFare (with
ApplyPromotionDiscount folded in — ADR-0020 Decision 6) and
CalculateDestinationChangeFare (ADR-0033). Not implemented:
CreateFareRevision — no live caller exists yet. CalculatePickupChange
Charge (ADR-0033) was removed by ADR-0056 (2026-08-31) — pickup change
no longer has a paid path at all.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from modules.pricing.domain.entities import (
    DestinationChangeCase,
    FareQuote,
    FareRule,
    PlatformFeeRule,
    calculate_destination_change_fare,
    calculate_fare,
    fare_rule_key,
)
from modules.pricing.domain.errors import (
    FareRuleNotFoundError,
    PlatformFeeRuleNotFoundError,
    PreviousFareQuoteNotFoundError,
)
from modules.pricing.ports import (
    FareQuoteRepository,
    FareRuleRepository,
    PlatformFeeRuleRepository,
)


class PricingService:
    def __init__(
        self,
        *,
        fare_rules: FareRuleRepository,
        fare_quotes: FareQuoteRepository,
        platform_fee_rules: PlatformFeeRuleRepository | None = None,
    ) -> None:
        self._fare_rules = fare_rules
        self._fare_quotes = fare_quotes
        # Optional (default None) for callers that never touch platform
        # fee configuration (unit tests, mostly) — the real
        # get_pricing_service() DI wiring always provides one, matching
        # ReferralService's own optional-dependency pattern (ADR-0043).
        self._platform_fee_rules = platform_fee_rules

    def calculate_fare(
        self,
        *,
        ride_id: uuid.UUID,
        vehicle_category: str,
        cab_tier: str | None,
        pickup_latitude: float,
        pickup_longitude: float,
        destination_latitude: float,
        destination_longitude: float,
        promotion_discount_percent: Decimal | None = None,
        promotion_max_discount_amount: Decimal | None = None,
        now: datetime,
    ) -> FareQuote:
        key = fare_rule_key(vehicle_category, cab_tier)
        rule = self._fare_rules.get_active_by_category(key, now=now)
        if rule is None:
            raise FareRuleNotFoundError(f"No active fare rule for '{key}'.")

        quote = calculate_fare(
            ride_id=ride_id,
            rule=rule,
            pickup_latitude=pickup_latitude,
            pickup_longitude=pickup_longitude,
            destination_latitude=destination_latitude,
            destination_longitude=destination_longitude,
            promotion_discount_percent=promotion_discount_percent,
            promotion_max_discount_amount=promotion_max_discount_amount,
            now=now,
        )
        return self._fare_quotes.create(quote)

    def get_fare_quote(self, *, fare_quote_id: uuid.UUID) -> FareQuote | None:
        """Phase 16 (ADR-0023) — admin Get Ride / Search Rides response,
        composed at modules/admin/router.py via the ride's own
        `active_fare_quote_id`. Pure pass-through, no domain logic."""
        return self._fare_quotes.get_by_id(fare_quote_id)

    def average_fare_total_for_ids(self, fare_quote_ids: list[uuid.UUID]) -> Decimal:
        """Admin Web §4.16 Rides report (ADR-0047) — pure pass-through."""
        return self._fare_quotes.average_total_for_ids(fare_quote_ids)

    def calculate_destination_change_fare(
        self,
        *,
        ride_id: uuid.UUID,
        vehicle_category: str,
        cab_tier: str | None,
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
        now: datetime,
    ) -> tuple[FareQuote | None, DestinationChangeCase]:
        """CalculateDestinationChangeFare (domain-design.md §11.4,
        ADR-0033 Decision 9 — BR-079/080/081). Returns (None,
        WITHIN_ROUTE) for BR-079 — no quote is created or persisted."""
        key = fare_rule_key(vehicle_category, cab_tier)
        rule = self._fare_rules.get_active_by_category(key, now=now)
        if rule is None:
            raise FareRuleNotFoundError(f"No active fare rule for '{key}'.")

        previous_quote = self._fare_quotes.get_latest_for_ride(ride_id)
        if previous_quote is None:
            raise PreviousFareQuoteNotFoundError(
                f"No existing fare quote found for ride {ride_id}."
            )

        quote, case = calculate_destination_change_fare(
            rule=rule,
            previous_quote=previous_quote,
            original_pickup_latitude=original_pickup_latitude,
            original_pickup_longitude=original_pickup_longitude,
            original_destination_latitude=original_destination_latitude,
            original_destination_longitude=original_destination_longitude,
            new_destination_latitude=new_destination_latitude,
            new_destination_longitude=new_destination_longitude,
            current_latitude=current_latitude,
            current_longitude=current_longitude,
            route_deviation_threshold_meters=route_deviation_threshold_meters,
            destination_extension_rate_per_km=destination_extension_rate_per_km,
            next_version=previous_quote.version + 1,
            now=now,
        )
        if quote is None:
            return None, case
        return self._fare_quotes.create(quote), case

    # --- Fare Management (Admin Web §4.8, ADR-0042) ----------------------

    def create_fare_rule(
        self,
        *,
        vehicle_category: str,
        base_fare: Decimal,
        per_km: Decimal,
        per_minute: Decimal,
        waiting_per_minute: Decimal,
        minimum_fare: Decimal,
        now: datetime,
    ) -> FareRule:
        rule = FareRule.new(
            vehicle_category=vehicle_category,
            base_fare=base_fare,
            per_km=per_km,
            per_minute=per_minute,
            waiting_per_minute=waiting_per_minute,
            minimum_fare=minimum_fare,
            now=now,
        )
        return self._fare_rules.create(rule)

    def get_fare_rule(self, rule_id: uuid.UUID) -> FareRule:
        rule = self._fare_rules.get_by_id(rule_id)
        if rule is None:
            raise FareRuleNotFoundError("Fare rule not found.")
        return rule

    def list_fare_rules(
        self,
        *,
        vehicle_category: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[FareRule], int]:
        return self._fare_rules.list_by_category(
            vehicle_category=vehicle_category,
            status=status,
            offset=offset,
            limit=limit,
        )

    def submit_fare_rule_for_review(self, rule_id: uuid.UUID) -> FareRule:
        rule = self._fare_rules.get_by_id_for_update(rule_id)
        if rule is None:
            raise FareRuleNotFoundError("Fare rule not found.")
        rule.submit_for_review()
        self._fare_rules.save(rule)
        return rule

    def publish_fare_rule(
        self, *, rule_id: uuid.UUID, effective_from: datetime | None, now: datetime
    ) -> FareRule:
        """ADR-0042 Decision 2: locks and closes out the previously-live
        rule for this category (if any) before publishing the new one,
        so at most one rule is ever live per category at a time."""
        rule = self._fare_rules.get_by_id_for_update(rule_id)
        if rule is None:
            raise FareRuleNotFoundError("Fare rule not found.")

        publish_at = effective_from if effective_from is not None else now
        previous = self._fare_rules.get_active_by_category_for_update(
            rule.vehicle_category, now=publish_at
        )
        if previous is not None and previous.id != rule.id:
            previous.effective_until = publish_at
            self._fare_rules.save(previous)

        rule.publish(effective_from=publish_at)
        self._fare_rules.save(rule)
        return rule

    # --- Platform Fee Management (Admin Web §4.8, ADR-0045) ---------------

    def get_active_platform_fee_rule(
        self, vehicle_category: str, *, now: datetime
    ) -> PlatformFeeRule | None:
        """Read at Accept Offer time (modules/matching/router.py).
        Returns None if no PUBLISHED row is live for this category —
        the caller falls back to its own last-resort constant (ADR-0045
        §5, resolved during implementation — see the ADR), not this
        service's job to know what that fallback value is."""
        assert self._platform_fee_rules is not None
        return self._platform_fee_rules.get_active_by_category(
            vehicle_category, now=now
        )

    def create_platform_fee_rule(
        self,
        *,
        vehicle_category: str,
        fee_amount: Decimal,
        created_by: uuid.UUID,
        now: datetime,
    ) -> PlatformFeeRule:
        assert self._platform_fee_rules is not None
        rule = PlatformFeeRule.new(
            vehicle_category=vehicle_category,
            fee_amount=fee_amount,
            created_by=created_by,
            now=now,
        )
        return self._platform_fee_rules.create(rule)

    def get_platform_fee_rule(self, rule_id: uuid.UUID) -> PlatformFeeRule:
        assert self._platform_fee_rules is not None
        rule = self._platform_fee_rules.get_by_id(rule_id)
        if rule is None:
            raise PlatformFeeRuleNotFoundError("Platform fee rule not found.")
        return rule

    def list_platform_fee_rules(
        self,
        *,
        vehicle_category: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[PlatformFeeRule], int]:
        assert self._platform_fee_rules is not None
        return self._platform_fee_rules.list_by_category(
            vehicle_category=vehicle_category,
            status=status,
            offset=offset,
            limit=limit,
        )

    def submit_platform_fee_rule_for_review(
        self, rule_id: uuid.UUID
    ) -> PlatformFeeRule:
        assert self._platform_fee_rules is not None
        rule = self._platform_fee_rules.get_by_id_for_update(rule_id)
        if rule is None:
            raise PlatformFeeRuleNotFoundError("Platform fee rule not found.")
        rule.submit_for_review()
        self._platform_fee_rules.save(rule)
        return rule

    def publish_platform_fee_rule(
        self, *, rule_id: uuid.UUID, effective_from: datetime | None, now: datetime
    ) -> PlatformFeeRule:
        """Identical "close out the prior live rule for this category"
        mechanism as publish_fare_rule() above (ADR-0042 Decision 2)."""
        assert self._platform_fee_rules is not None
        rule = self._platform_fee_rules.get_by_id_for_update(rule_id)
        if rule is None:
            raise PlatformFeeRuleNotFoundError("Platform fee rule not found.")

        publish_at = effective_from if effective_from is not None else now
        previous = self._platform_fee_rules.get_active_by_category_for_update(
            rule.vehicle_category, now=publish_at
        )
        if previous is not None and previous.id != rule.id:
            previous.effective_until = publish_at
            self._platform_fee_rules.save(previous)

        rule.publish(effective_from=publish_at)
        self._platform_fee_rules.save(rule)
        return rule
