"""Abstract interfaces (ports) the application layer depends on."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from modules.promotion.domain.entities import (
    Campaign,
    CampaignStatus,
    Entitlement,
    Reservation,
    Usage,
)


class EntitlementRepository(Protocol):
    def create(self, entitlement: Entitlement) -> Entitlement: ...

    def get_by_id_for_update(self, entitlement_id: uuid.UUID) -> Entitlement | None:
        """Locked for the remainder of the current transaction (SELECT
        ... FOR UPDATE, database-design.md §44's documented "Lock
        entitlement" step) — reserve/consume/restore must serialize
        concurrent access to the same entitlement's remaining_uses,
        same pattern wallet/penalty/advertisement row-locking already
        established in this codebase."""
        ...

    def save(self, entitlement: Entitlement) -> None: ...

    def list_active_for_customer(self, customer_id: uuid.UUID) -> list[Entitlement]:
        """Rows with status=ACTIVE only — may still include some whose
        expires_at has passed (lazy expiry, ADR-0011 Decision 2's same
        pattern: the service layer checks/transitions these on read,
        not a background job)."""
        ...

    def count_campaign_redemptions(
        self, campaign_id: uuid.UUID, *, customer_id: uuid.UUID | None = None
    ) -> int:
        """Count of entitlements with this campaign_id — all of them if
        customer_id is omitted (against total_usage_limit), or just one
        customer's (against per_customer_use_limit). ADR-0041 Decision
        3/§6.2."""
        ...

    def count_by_type_activated_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        """Admin Web §4.16 Promotions/Referrals report (ADR-0047) —
        "entitlements_granted_in_range", by `promotion_type`,
        `activated_at` in [since, until)."""
        ...


class UsageRepository(Protocol):
    def create(self, usage: Usage) -> Usage:
        """Insert. uq_promotion_ride_use (entitlement_id, ride_id) means
        a genuine duplicate raises IntegrityError."""
        ...

    def count_consumed_in_range(self, *, since: datetime, until: datetime) -> int:
        """Admin Web §4.16 report — COUNT(status=CONSUMED, created_at
        in [since, until))."""
        ...

    def sum_discount_in_range(self, *, since: datetime, until: datetime) -> Decimal:
        """Same report's "total_discount_given" — SUM(discount_amount)
        over the same window, any status (a restored usage still
        represents a discount that was actually applied at the time)."""
        ...


class ReservationRepository(Protocol):
    def create(self, reservation: Reservation) -> Reservation: ...

    def get_by_id(self, reservation_id: uuid.UUID) -> Reservation | None: ...

    def get_by_id_for_update(self, reservation_id: uuid.UUID) -> Reservation | None:
        """Locked for the remainder of the current transaction —
        ConsumePromotion/RestorePromotion (Phase 12, 2026-09-04 fix)
        must read-check-then-write a reservation's status atomically:
        without this lock, two concurrent/replayed calls against the
        *same* reservation_id can both observe RESERVED before either
        commits and both proceed, double-consuming or double-restoring
        it (a real race — plain get_by_id() alone does not serialize
        the status check against the write)."""
        ...

    def get_by_ride_id(self, ride_id: uuid.UUID) -> Reservation | None: ...

    def save(self, reservation: Reservation) -> None: ...


class CampaignRepository(Protocol):
    """ADR-0041. Backs both the admin-authoring endpoints and customer
    redemption."""

    def create(self, campaign: Campaign) -> Campaign: ...

    def get_by_id(self, campaign_id: uuid.UUID) -> Campaign | None: ...

    def get_by_id_for_update(self, campaign_id: uuid.UUID) -> Campaign | None:
        """Locked for the remainder of the current transaction — an
        edit or status transition must not race a concurrent one on the
        same campaign, same reasoning as EntitlementRepository's own
        get_by_id_for_update."""
        ...

    def get_by_code_for_update(self, code: str) -> Campaign | None:
        """Locked lookup for redemption — must serialize concurrent
        redemptions of the same campaign against total_usage_limit."""
        ...

    def save(self, campaign: Campaign) -> None: ...

    def list_campaigns(
        self, *, status: CampaignStatus | None, offset: int, limit: int
    ) -> tuple[list[Campaign], int]: ...

    def is_customer_eligible(
        self, *, campaign_id: uuid.UUID, customer_id: uuid.UUID
    ) -> bool:
        """True iff (campaign_id, customer_id) exists in
        campaign_eligible_customers. Only meaningful when
        eligible_scope='SELECTED' — the service layer skips this check
        entirely for 'ALL'."""
        ...

    def set_eligible_customers(
        self, *, campaign_id: uuid.UUID, customer_ids: list[uuid.UUID]
    ) -> None:
        """Replaces the full eligible-customer set for a campaign (used
        when creating/editing a SELECTED-scope campaign, DRAFT only per
        Campaign.can_edit())."""
        ...

    def add_eligible_customers(
        self, *, campaign_id: uuid.UUID, customer_ids: list[uuid.UUID]
    ) -> set[uuid.UUID]:
        """CSV Bulk Customer Targeting (Admin Web §4.10, ADR-0041 §9) —
        additive, unlike set_eligible_customers() above which replaces
        the whole set. Idempotent: a customer_id already eligible is
        left untouched, not re-inserted or errored on. Returns the
        subset of customer_ids that were newly added (not already
        eligible), so the caller can report added vs. already_eligible
        counts back to the admin."""
        ...
