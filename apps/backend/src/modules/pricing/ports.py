"""Abstract interfaces (ports) the application layer depends on."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from modules.pricing.domain.entities import FareQuote, FareRule, PlatformFeeRule


class FareRuleRepository(Protocol):
    def get_active_by_category(
        self, vehicle_category: str, *, now: datetime
    ) -> FareRule | None:
        """The one currently-live rule (status=PUBLISHED, effective_from
        <= now < effective_until or effective_until IS NULL) for a given
        pricing.fare_rules.vehicle_category key (see domain/entities.py::
        fare_rule_key()). ADR-0042: "active" is now derived from status +
        the effective window, not a stored column."""
        ...

    def get_active_by_category_for_update(
        self, vehicle_category: str, *, now: datetime
    ) -> FareRule | None:
        """Same as get_active_by_category(), but locked (SELECT ... FOR
        UPDATE) for the remainder of the current transaction — used by
        PublishFareRule (ADR-0042 Decision 2) to close out the prior
        live rule for this category without a race against a concurrent
        publish."""
        ...

    def create(self, rule: FareRule) -> FareRule: ...

    def get_by_id(self, rule_id: uuid.UUID) -> FareRule | None: ...

    def get_by_id_for_update(self, rule_id: uuid.UUID) -> FareRule | None: ...

    def save(self, rule: FareRule) -> None: ...

    def list_by_category(
        self,
        *,
        vehicle_category: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[FareRule], int]:
        """Admin Web §4.8's "List fare rules ... with version history" —
        every status, not just PUBLISHED (ADR-0042 Decision 4)."""
        ...


class PlatformFeeRuleRepository(Protocol):
    """ADR-0045 — BR-011's driver platform fee."""

    def get_active_by_category(
        self, vehicle_category: str, *, now: datetime
    ) -> PlatformFeeRule | None:
        """The one currently-live rule for a given vehicle_category
        (BIKE/AUTO/CAB) — read at Accept Offer time."""
        ...

    def get_active_by_category_for_update(
        self, vehicle_category: str, *, now: datetime
    ) -> PlatformFeeRule | None:
        """Locked variant, used by Publish to close out the prior live
        rule for this category (ADR-0042 Decision 2 pattern)."""
        ...

    def create(self, rule: PlatformFeeRule) -> PlatformFeeRule: ...

    def get_by_id(self, rule_id: uuid.UUID) -> PlatformFeeRule | None: ...

    def get_by_id_for_update(self, rule_id: uuid.UUID) -> PlatformFeeRule | None: ...

    def save(self, rule: PlatformFeeRule) -> None: ...

    def list_by_category(
        self,
        *,
        vehicle_category: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[PlatformFeeRule], int]:
        """Version history — every status, not just PUBLISHED."""
        ...


class FareQuoteRepository(Protocol):
    def create(self, quote: FareQuote) -> FareQuote: ...

    def get_by_id(self, fare_quote_id: uuid.UUID) -> FareQuote | None:
        """Added Phase 16 (ADR-0023) for the admin Get Ride / Search
        Rides response — the caller looks this up via the ride's own
        `active_fare_quote_id`, never by ride_id: `pricing.fare_quotes`
        can hold more than one version per ride (a future fare-revision
        feature), so this is the only unambiguous single-quote read."""
        ...

    def get_latest_for_ride(self, ride_id: uuid.UUID) -> FareQuote | None:
        """ADR-0033 Decision 6 — the highest-`version` quote for a ride,
        needed to compute the next version number for a pickup-change/
        destination-change revision. Every ride created so far only ever
        has version 1 (CreateFareRevision was never called before this
        ADR); this is the first caller that can produce a version 2+."""
        ...

    def average_total_for_ids(self, fare_quote_ids: list[uuid.UUID]) -> Decimal:
        """Admin Web §4.16 Rides report (ADR-0047) — AVG(total) over
        exactly these ids (RideRepository.list_active_fare_quote_ids_
        for_closed_in_range()'s result), not a date-ranged query itself
        — keeps this repository within its own `pricing` schema rather
        than joining across `ride`/`pricing` in one query. 0 for an
        empty list."""
        ...
