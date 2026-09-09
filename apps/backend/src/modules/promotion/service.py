"""Application service (use cases) for Promotion.

Implements domain-design.md §15.3's six commands (GrantWelcomePromotion,
GrantReferralPromotion, ReservePromotion, ConsumePromotion,
RestorePromotion, ExpirePromotion — the last is lazy, evaluated on read,
same "no background worker" pattern ADR-0011 Decision 2 established for
offer expiry, not a separate command here).

reserve/consume/restore ARE composed into modules/ride/router.py:
reserve_entitlement() at Create Ride, and — since ADR-0070 (2026-09-04)
closed ADR-0019's Item 6 — consume_reservation_for_ride()/
restore_reservation_for_ride() at ride completion/cancellation. Proven
end-to-end by tests/test_ride_lifecycle_api.py's real HTTP + real
Postgres tests, and at the unit/race level by
tests/test_promotion_service.py and tests/test_promotion_api.py's
real-concurrency tests.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from modules.promotion.domain.entities import (
    Campaign,
    CampaignStatus,
    DiscountType,
    EligibleScope,
    Entitlement,
    EntitlementStatus,
    Reservation,
    ReservationStatus,
    Usage,
    UsageStatus,
)
from modules.promotion.domain.errors import (
    CampaignMinimumFareNotMetError,
    CampaignNotActiveError,
    CampaignNotEligibleError,
    CampaignNotFoundError,
    CampaignUsageLimitExceededError,
    EntitlementNotFoundError,
    InvalidCampaignInputError,
    InvalidCampaignStateTransitionError,
    PromotionAlreadyUsedError,
    PromotionExpiredError,
    ReservationNotFoundError,
)
from modules.promotion.ports import (
    CampaignRepository,
    EntitlementRepository,
    ReservationRepository,
    UsageRepository,
)
from modules.vehicle.domain.entities import VehicleCategory


class PromotionService:
    def __init__(
        self,
        *,
        entitlements: EntitlementRepository,
        usages: UsageRepository,
        reservations: ReservationRepository,
        campaigns: CampaignRepository,
    ) -> None:
        self._entitlements = entitlements
        self._usages = usages
        self._reservations = reservations
        self._campaigns = campaigns

    # --- Grant --------------------------------------------------------

    def grant_welcome_promotion(
        self, *, customer_id: uuid.UUID, now: datetime
    ) -> Entitlement:
        entitlement = Entitlement.new_welcome(customer_id=customer_id, now=now)
        return self._entitlements.create(entitlement)

    def grant_referral_promotion(
        self,
        *,
        customer_id: uuid.UUID,
        is_referring_customer: bool,
        now: datetime,
        total_uses: int | None = None,
        discount_percent: Decimal | None = None,
    ) -> Entitlement:
        """BR-059 (the referred customer) / BR-060 (the referring
        customer) — same command, two outcomes, matching
        domain-design.md §15.3's single GrantReferralPromotion.
        `total_uses`/`discount_percent`, if supplied, come from the
        referral module's own live-configured reward rule (ADR-0043,
        threaded through by the router composing both modules) — see
        Entitlement.new_referral_referred()/new_referral_referring()
        for the fallback contract when omitted."""
        entitlement = (
            Entitlement.new_referral_referring(
                customer_id=customer_id,
                now=now,
                total_uses=total_uses,
                discount_percent=discount_percent,
            )
            if is_referring_customer
            else Entitlement.new_referral_referred(
                customer_id=customer_id,
                now=now,
                total_uses=total_uses,
                discount_percent=discount_percent,
            )
        )
        return self._entitlements.create(entitlement)

    # --- Query ----------------------------------------------------------

    def list_entitlements(
        self, *, customer_id: uuid.UUID, now: datetime
    ) -> list[Entitlement]:
        """Lazily expires (ExpirePromotion) any ACTIVE entitlement past
        its expires_at before returning — same lazy-evaluation pattern
        ADR-0011 Decision 2 established, not a background job."""
        active = self._entitlements.list_active_for_customer(customer_id)
        still_active: list[Entitlement] = []
        for entitlement in active:
            if entitlement.is_expired(now=now):
                entitlement.status = EntitlementStatus.EXPIRED
                self._entitlements.save(entitlement)
            else:
                still_active.append(entitlement)
        return still_active

    # --- Reserve / Consume / Restore ------------------------------------

    def reserve_entitlement(
        self,
        *,
        customer_id: uuid.UUID,
        entitlement_id: uuid.UUID,
        ride_id: uuid.UUID,
        now: datetime,
    ) -> Reservation:
        """database-design.md §44: Lock entitlement -> Check
        remaining_uses -> Reserve/decrement -> ... The decrement happens
        HERE (at reserve time, not consume time) — BR-065's "early
        cancellation restores" only makes sense if a use was already
        provisionally taken; ConsumePromotion below does not touch
        remaining_uses again."""
        entitlement = self._entitlements.get_by_id_for_update(entitlement_id)
        if entitlement is None or entitlement.customer_id != customer_id:
            # IDOR-safe "not found either way" — same pattern used
            # throughout this codebase.
            raise EntitlementNotFoundError("Entitlement not found.")
        if (
            entitlement.is_expired(now=now)
            or entitlement.status is EntitlementStatus.EXPIRED
        ):
            entitlement.status = EntitlementStatus.EXPIRED
            self._entitlements.save(entitlement)
            raise PromotionExpiredError("This promotion has expired.")
        if entitlement.remaining_uses <= 0:
            raise PromotionAlreadyUsedError("This promotion has no remaining uses.")

        entitlement.remaining_uses -= 1
        if entitlement.remaining_uses == 0:
            entitlement.status = EntitlementStatus.EXHAUSTED
        self._entitlements.save(entitlement)

        reservation = Reservation.new(
            entitlement_id=entitlement.id, ride_id=ride_id, now=now
        )
        return self._reservations.create(reservation)

    def consume_reservation(
        self,
        *,
        reservation_id: uuid.UUID,
        discount_amount: Decimal,
        now: datetime,
    ) -> Usage:
        """BR-066: a late-cancelled or completed promotional ride
        consumes the reservation — the use taken at reserve time is
        final. Doubly idempotent: `uq_promotion_ride_use` (entitlement_
        id, ride_id) makes a duplicate INSERT fail at the database level
        regardless, but the reservation itself is now also locked
        (`get_by_id_for_update`, fixed 2026-09-04) so a concurrent or
        replayed call against the *same* reservation_id is rejected with
        the ordinary `PromotionAlreadyUsedError` domain error rather than
        racing to double-consume it — matching Advertisement's payout-
        recalculation treatment: a second consume attempt is a caller
        error worth surfacing, not a legitimate retry to replay
        quietly."""
        reservation = self._reservations.get_by_id_for_update(reservation_id)
        if reservation is None:
            raise ReservationNotFoundError("Reservation not found.")
        if reservation.status is not ReservationStatus.RESERVED:
            raise PromotionAlreadyUsedError(
                "This reservation has already been resolved."
            )

        usage = Usage.new(
            entitlement_id=reservation.entitlement_id,
            ride_id=reservation.ride_id,
            discount_amount=discount_amount,
            status=UsageStatus.CONSUMED,
            now=now,
        )
        created = self._usages.create(usage)

        reservation.status = ReservationStatus.CONSUMED
        self._reservations.save(reservation)
        return created

    def restore_reservation(
        self, *, reservation_id: uuid.UUID, now: datetime
    ) -> Reservation:
        """BR-065: a qualifying early cancellation gives the use back.
        The reservation is locked first (`get_by_id_for_update`, fixed
        2026-09-04) and its status re-checked under that lock — unlike
        consume, there is no unique-constraint backstop here
        (`remaining_uses` is a plain mutable counter, not an INSERT), so
        without this lock a concurrent or replayed restore of the *same*
        reservation_id could pass the status check twice before either
        commits and double-increment remaining_uses. Locking the
        entitlement alone (still done below, for two *different*
        reservations racing on the same entitlement) does not close that
        gap by itself, since the entitlement lock is acquired after the
        status check, not before it."""
        reservation = self._reservations.get_by_id_for_update(reservation_id)
        if reservation is None:
            raise ReservationNotFoundError("Reservation not found.")
        if reservation.status is not ReservationStatus.RESERVED:
            raise PromotionAlreadyUsedError(
                "This reservation has already been resolved."
            )

        entitlement = self._entitlements.get_by_id_for_update(
            reservation.entitlement_id
        )
        if entitlement is None:
            raise EntitlementNotFoundError("Entitlement not found.")
        entitlement.remaining_uses += 1
        if entitlement.status is EntitlementStatus.EXHAUSTED:
            entitlement.status = EntitlementStatus.ACTIVE
        self._entitlements.save(entitlement)

        reservation.status = ReservationStatus.RESTORED
        self._reservations.save(reservation)
        return reservation

    # --- Ride-lifecycle composition (ADR-0070) ---------------------------

    def consume_reservation_for_ride(
        self, *, ride_id: uuid.UUID, discount_amount: Decimal, now: datetime
    ) -> Usage | None:
        """Called from modules/ride/router.py's complete_ride(), once the
        ride actually reaches COMPLETED. Returns None — a no-op — for the
        common case of a ride with no RESERVED reservation at all (most
        rides never had a promotion applied, and a ride that already had
        its reservation resolved, e.g. by an early-drop/cancel path that
        never actually happens for a completed ride, is left alone
        rather than raising). `get_by_ride_id` here is an unlocked,
        cheap existence check only — the actual status re-check and
        state transition happen inside consume_reservation() under its
        own row lock, so a stale read here can never cause a double-
        consume; it can only cause an unnecessary
        `PromotionAlreadyUsedError`, which the caller treats as best-
        effort (same pattern as PenaltyService.
        settle_penalties_for_completed_ride())."""
        reservation = self._reservations.get_by_ride_id(ride_id)
        if reservation is None or reservation.status is not ReservationStatus.RESERVED:
            return None
        return self.consume_reservation(
            reservation_id=reservation.id, discount_amount=discount_amount, now=now
        )

    def restore_reservation_for_ride(
        self, *, ride_id: uuid.UUID, now: datetime
    ) -> Reservation | None:
        """Called from modules/ride/router.py's cancel_ride()/
        driver_cancel_ride(), after a ride that might have reserved a
        promotion is cancelled. BR-065's early/late-cancellation
        boundary is genuinely TBD (business-rules.md §18/§19) — no
        threshold is invented here, so every cancellation of a ride
        carrying a RESERVED reservation restores it unconditionally,
        matching BR-065's letter (never wrongly forfeits a customer's
        use) while leaving BR-066's "late cancellation consumes it
        instead" case unenforced until that boundary is actually
        decided (flagged, not guessed at — same discipline this
        codebase applies to every other genuinely-TBD business value).
        Returns None for the common no-reservation case; see
        consume_reservation_for_ride() above for why an unlocked
        get_by_ride_id() here is still race-safe."""
        reservation = self._reservations.get_by_ride_id(ride_id)
        if reservation is None or reservation.status is not ReservationStatus.RESERVED:
            return None
        return self.restore_reservation(reservation_id=reservation.id, now=now)

    # --- Campaign authoring (ADR-0041, admin — Offers/Coupons module) ---

    def create_campaign(
        self,
        *,
        code: str | None,
        name: str,
        vehicle_category: VehicleCategory | None,
        discount_type: str,
        discount_value: Decimal,
        max_discount_amount: Decimal | None,
        minimum_fare: Decimal | None,
        eligible_scope: str,
        per_customer_use_limit: int,
        total_usage_limit: int | None,
        ride_count_limit: int | None,
        starts_at: datetime,
        ends_at: datetime | None,
        eligible_customer_ids: list[uuid.UUID] | None,
        created_by: uuid.UUID,
        now: datetime,
    ) -> Campaign:
        campaign = Campaign.new(
            code=code,
            name=name,
            vehicle_category=vehicle_category,
            discount_type=DiscountType(discount_type),
            discount_value=discount_value,
            max_discount_amount=max_discount_amount,
            minimum_fare=minimum_fare,
            eligible_scope=EligibleScope(eligible_scope),
            per_customer_use_limit=per_customer_use_limit,
            total_usage_limit=total_usage_limit,
            ride_count_limit=ride_count_limit,
            starts_at=starts_at,
            ends_at=ends_at,
            created_by=created_by,
            now=now,
        )
        created = self._campaigns.create(campaign)
        if campaign.eligible_scope is EligibleScope.SELECTED and eligible_customer_ids:
            self._campaigns.set_eligible_customers(
                campaign_id=created.id, customer_ids=eligible_customer_ids
            )
        return created

    def get_campaign(self, campaign_id: uuid.UUID) -> Campaign:
        campaign = self._campaigns.get_by_id(campaign_id)
        if campaign is None:
            raise CampaignNotFoundError("Campaign not found.")
        return campaign

    def list_campaigns(
        self, *, status: CampaignStatus | None, offset: int, limit: int
    ) -> tuple[list[Campaign], int]:
        return self._campaigns.list_campaigns(status=status, offset=offset, limit=limit)

    def update_campaign(
        self,
        *,
        campaign_id: uuid.UUID,
        code: str | None,
        name: str,
        vehicle_category: VehicleCategory | None,
        discount_type: str,
        discount_value: Decimal,
        max_discount_amount: Decimal | None,
        minimum_fare: Decimal | None,
        eligible_scope: str,
        per_customer_use_limit: int,
        total_usage_limit: int | None,
        ride_count_limit: int | None,
        starts_at: datetime,
        ends_at: datetime | None,
        eligible_customer_ids: list[uuid.UUID] | None,
    ) -> Campaign:
        campaign = self._campaigns.get_by_id_for_update(campaign_id)
        if campaign is None:
            raise CampaignNotFoundError("Campaign not found.")
        if not campaign.can_edit():
            raise InvalidCampaignStateTransitionError(
                "Only a DRAFT campaign can be edited — pause/end it and "
                "create a new one instead."
            )
        campaign.apply_edit(
            code=code,
            name=name,
            vehicle_category=vehicle_category,
            discount_type=DiscountType(discount_type),
            discount_value=discount_value,
            max_discount_amount=max_discount_amount,
            minimum_fare=minimum_fare,
            eligible_scope=EligibleScope(eligible_scope),
            per_customer_use_limit=per_customer_use_limit,
            total_usage_limit=total_usage_limit,
            ride_count_limit=ride_count_limit,
            starts_at=starts_at,
            ends_at=ends_at,
        )
        self._campaigns.save(campaign)
        if campaign.eligible_scope is EligibleScope.SELECTED:
            self._campaigns.set_eligible_customers(
                campaign_id=campaign.id, customer_ids=eligible_customer_ids or []
            )
        return campaign

    def bulk_add_eligible_customers(
        self, *, campaign_id: uuid.UUID, customer_ids: list[uuid.UUID]
    ) -> set[uuid.UUID]:
        """CSV Bulk Customer Targeting (Admin Web §4.10, ADR-0041 §9) —
        additive, unlike update_campaign()'s set_eligible_customers()
        which replaces the whole set (ADR-0041 §9 explains why bulk
        upload needs the opposite semantics: a re-uploaded refreshed
        list should never silently drop individually-added customers).
        Only valid while the campaign is DRAFT (same can_edit() gate
        Edit Campaign already enforces) and only meaningful for
        eligible_scope='SELECTED' (same "this field only means
        something for SELECTED" rule Create/Edit already enforce for
        eligible_customer_ids). The caller (router) resolves phone
        numbers to customer_ids and reports unmatched rows back to the
        admin before this is ever called — this method only handles the
        already-resolved, already-existing customer id set. Returns the
        subset newly added (not already eligible)."""
        campaign = self._campaigns.get_by_id_for_update(campaign_id)
        if campaign is None:
            raise CampaignNotFoundError("Campaign not found.")
        if not campaign.can_edit():
            raise InvalidCampaignStateTransitionError(
                "Only a DRAFT campaign accepts bulk customer targeting — "
                "pause/end it and create a new one instead."
            )
        if campaign.eligible_scope is not EligibleScope.SELECTED:
            raise InvalidCampaignInputError(
                "Bulk customer targeting only applies to a campaign with "
                "eligible_scope='SELECTED'."
            )
        return self._campaigns.add_eligible_customers(
            campaign_id=campaign_id, customer_ids=customer_ids
        )

    def activate_campaign(self, *, campaign_id: uuid.UUID) -> Campaign:
        campaign = self._campaigns.get_by_id_for_update(campaign_id)
        if campaign is None:
            raise CampaignNotFoundError("Campaign not found.")
        campaign.activate()
        self._campaigns.save(campaign)
        return campaign

    def pause_campaign(self, *, campaign_id: uuid.UUID) -> Campaign:
        campaign = self._campaigns.get_by_id_for_update(campaign_id)
        if campaign is None:
            raise CampaignNotFoundError("Campaign not found.")
        campaign.pause()
        self._campaigns.save(campaign)
        return campaign

    def end_campaign(self, *, campaign_id: uuid.UUID) -> Campaign:
        campaign = self._campaigns.get_by_id_for_update(campaign_id)
        if campaign is None:
            raise CampaignNotFoundError("Campaign not found.")
        campaign.end()
        self._campaigns.save(campaign)
        return campaign

    # --- Campaign redemption (customer-facing, ADR-0041 Decision 2) -----

    def redeem_campaign_code(
        self,
        *,
        customer_id: uuid.UUID,
        code: str,
        vehicle_category: VehicleCategory,
        fare: Decimal,
        now: datetime,
    ) -> Entitlement:
        """database-design.md-style validation order: lock the campaign
        (serializes concurrent redemptions against total_usage_limit),
        then status/window, eligibility, minimum fare, then the two
        usage-limit checks, then create the entitlement."""
        campaign = self._campaigns.get_by_code_for_update(code)
        if campaign is None:
            raise CampaignNotFoundError("Invalid campaign code.")
        campaign_active = campaign.status is CampaignStatus.ACTIVE
        if not campaign_active or not campaign.is_within_window(now=now):
            raise CampaignNotActiveError("This campaign is not currently active.")
        if (
            campaign.vehicle_category is not None
            and campaign.vehicle_category != vehicle_category
        ):
            raise CampaignNotEligibleError(
                "This campaign does not apply to the selected vehicle category."
            )
        if campaign.eligible_scope is EligibleScope.SELECTED and not (
            self._campaigns.is_customer_eligible(
                campaign_id=campaign.id, customer_id=customer_id
            )
        ):
            raise CampaignNotEligibleError("You are not eligible for this campaign.")
        if campaign.minimum_fare is not None and fare < campaign.minimum_fare:
            raise CampaignMinimumFareNotMetError(
                f"A minimum fare of {campaign.minimum_fare} is required for this "
                "campaign."
            )
        if campaign.total_usage_limit is not None:
            total_redemptions = self._entitlements.count_campaign_redemptions(
                campaign.id
            )
            if total_redemptions >= campaign.total_usage_limit:
                raise CampaignUsageLimitExceededError(
                    "This campaign's usage limit has been reached."
                )
        customer_redemptions = self._entitlements.count_campaign_redemptions(
            campaign.id, customer_id=customer_id
        )
        if customer_redemptions >= campaign.per_customer_use_limit:
            raise CampaignUsageLimitExceededError(
                "You have already redeemed this campaign the maximum number of times."
            )

        entitlement = Entitlement.new_campaign_redemption(
            customer_id=customer_id, campaign=campaign, now=now
        )
        return self._entitlements.create(entitlement)

    # --- Reports (Admin Web §4.16, ADR-0047) -------------------------

    def count_entitlements_by_type_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        return self._entitlements.count_by_type_activated_in_range(
            since=since, until=until
        )

    def count_usage_consumed_in_range(self, *, since: datetime, until: datetime) -> int:
        return self._usages.count_consumed_in_range(since=since, until=until)

    def sum_discount_given_in_range(
        self, *, since: datetime, until: datetime
    ) -> Decimal:
        return self._usages.sum_discount_in_range(since=since, until=until)
