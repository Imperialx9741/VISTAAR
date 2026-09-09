"""Promotion domain entities.

Field shapes match docs/04-database/database-design.md §24.1
(promotion.entitlements), §24.2 (promotion.usage), §24.3
(promotion.reservations), and §24.4/§24.5 (promotion.campaigns/
campaign_eligible_customers, added ADR-0041) exactly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from modules.promotion.domain.errors import (
    InvalidCampaignInputError,
    InvalidCampaignStateTransitionError,
    InvalidPromotionInputError,
)
from modules.vehicle.domain.entities import VehicleCategory

# BR-062 / domain-design.md §15.5: 30 days after activation.
_ENTITLEMENT_VALIDITY_DAYS = 30

# BR-058/059/060 / domain-design.md §15.5's "Current Rules" — approved,
# fixed values.
_WELCOME_TOTAL_USES = 3
_WELCOME_DISCOUNT_PERCENT = Decimal("50")
_REFERRAL_CUSTOMER_TOTAL_USES = 3
_REFERRAL_CUSTOMER_DISCOUNT_PERCENT = Decimal("50")
_REFERRING_CUSTOMER_TOTAL_USES = 2
_REFERRING_CUSTOMER_DISCOUNT_PERCENT = Decimal("50")

# BR-063 (ADR-0049, 2026-08-28): ₹100 per ride, the same figure across
# all three 50%-off welcome/referral entitlement types — no source
# document or owner instruction distinguishes them. Campaign-redeemed
# entitlements (PromotionType.CAMPAIGN) are unaffected; their cap comes
# from the campaign an admin authored (BR-128), not this constant.
_WELCOME_REFERRAL_MAX_DISCOUNT_AMOUNT = Decimal("100")


class PromotionType(StrEnum):
    """Exactly database-design.md §24.1's VARCHAR(50) promotion_type
    column values this codebase currently produces (BR-058/059/060) —
    matches api-contracts.md §37's own "WELCOME" example exactly."""

    WELCOME = "WELCOME"
    REFERRAL_REFERRED = "REFERRAL_REFERRED"
    REFERRAL_REFERRING = "REFERRAL_REFERRING"
    # ADR-0041: an entitlement created by RedeemCampaignCode rather than
    # the welcome/referral grant flows. campaign_id is always set
    # alongside this value.
    CAMPAIGN = "CAMPAIGN"


class EntitlementStatus(StrEnum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    EXHAUSTED = "EXHAUSTED"


class UsageStatus(StrEnum):
    """No canonical enum documented for promotion.usage.status beyond
    what "consumed" vs. "restored" implies (BR-065/066) — the two
    values this codebase's ConsumePromotion/RestorePromotion commands
    actually produce."""

    CONSUMED = "CONSUMED"
    RESTORED = "RESTORED"


class ReservationStatus(StrEnum):
    """Matches database-design.md §24.3's documented default
    ('RESERVED') plus the two outcomes ConsumePromotion/
    RestorePromotion transition a reservation into."""

    RESERVED = "RESERVED"
    CONSUMED = "CONSUMED"
    RESTORED = "RESTORED"


@dataclass(slots=True)
class Entitlement:
    id: uuid.UUID
    customer_id: uuid.UUID
    promotion_type: PromotionType
    total_uses: int
    remaining_uses: int
    discount_percent: Decimal
    max_discount_amount: Decimal | None
    activated_at: datetime
    expires_at: datetime
    status: EntitlementStatus
    # NULL for welcome/referral grants (unchanged since before ADR-0041);
    # set only on an entitlement created by RedeemCampaignCode.
    campaign_id: uuid.UUID | None = None

    @staticmethod
    def _new(
        *,
        customer_id: uuid.UUID,
        promotion_type: PromotionType,
        total_uses: int,
        discount_percent: Decimal,
        now: datetime,
        max_discount_amount: Decimal | None = None,
        campaign_id: uuid.UUID | None = None,
    ) -> Entitlement:
        return Entitlement(
            id=uuid.uuid4(),
            customer_id=customer_id,
            promotion_type=promotion_type,
            total_uses=total_uses,
            remaining_uses=total_uses,
            discount_percent=discount_percent,
            # BR-063 (ADR-0049): ₹100 for welcome/referral grants, or
            # whatever a campaign-redeemed entitlement passes explicitly
            # instead (ADR-0041 §6.1) — see
            # Entitlement.new_campaign_redemption below. Before ADR-0049
            # this was always None for welcome/referral grants — the
            # cap was explicitly TBD (business-rules.md §18), and NULL
            # was genuinely accurate then, not a placeholder standing in
            # for an unknown value (ADR-0019 Decision 2, same treatment
            # ADR-0013 gave outstanding_settlement).
            max_discount_amount=max_discount_amount,
            activated_at=now,
            expires_at=now + timedelta(days=_ENTITLEMENT_VALIDITY_DAYS),
            status=EntitlementStatus.ACTIVE,
            campaign_id=campaign_id,
        )

    @staticmethod
    def new_welcome(*, customer_id: uuid.UUID, now: datetime) -> Entitlement:
        """BR-058: 50% off the first 3 rides, unconditional on referral,
        capped at ₹100/ride (BR-063, ADR-0049)."""
        return Entitlement._new(
            customer_id=customer_id,
            promotion_type=PromotionType.WELCOME,
            total_uses=_WELCOME_TOTAL_USES,
            discount_percent=_WELCOME_DISCOUNT_PERCENT,
            now=now,
            max_discount_amount=_WELCOME_REFERRAL_MAX_DISCOUNT_AMOUNT,
        )

    @staticmethod
    def new_referral_referred(
        *,
        customer_id: uuid.UUID,
        now: datetime,
        total_uses: int | None = None,
        discount_percent: Decimal | None = None,
    ) -> Entitlement:
        """BR-059: the referred customer's 3 additional 50%-off rides,
        capped at ₹100/ride (BR-063, ADR-0049).
        `total_uses`/`discount_percent` default to the module-level
        constants below — the referral module's own live-configured
        values (ADR-0043, ReferralService.get_active_customer_reward_
        rule()) are threaded through from the router layer when a
        PUBLISHED rule exists; these constants remain the last-resort
        fallback (ADR-0043 §4, resolved during implementation), not
        deleted. The ₹100 cap itself is NOT part of that live-configured
        rule (ADR-0043 never touched BR-063) — it always applies."""
        return Entitlement._new(
            customer_id=customer_id,
            promotion_type=PromotionType.REFERRAL_REFERRED,
            total_uses=total_uses or _REFERRAL_CUSTOMER_TOTAL_USES,
            discount_percent=discount_percent or _REFERRAL_CUSTOMER_DISCOUNT_PERCENT,
            now=now,
            max_discount_amount=_WELCOME_REFERRAL_MAX_DISCOUNT_AMOUNT,
        )

    @staticmethod
    def new_referral_referring(
        *,
        customer_id: uuid.UUID,
        now: datetime,
        total_uses: int | None = None,
        discount_percent: Decimal | None = None,
    ) -> Entitlement:
        """BR-060: the referring customer's 2 rides at 50% off, capped
        at ₹100/ride (BR-063, ADR-0049). Same override/fallback contract
        as new_referral_referred() above."""
        return Entitlement._new(
            customer_id=customer_id,
            promotion_type=PromotionType.REFERRAL_REFERRING,
            total_uses=total_uses or _REFERRING_CUSTOMER_TOTAL_USES,
            discount_percent=discount_percent or _REFERRING_CUSTOMER_DISCOUNT_PERCENT,
            now=now,
            max_discount_amount=_WELCOME_REFERRAL_MAX_DISCOUNT_AMOUNT,
        )

    @staticmethod
    def new_campaign_redemption(
        *,
        customer_id: uuid.UUID,
        campaign: Campaign,
        now: datetime,
    ) -> Entitlement:
        """ADR-0041 §6.2 (resolved during implementation): a redeemed
        campaign's `ride_count_limit` — "only a customer's first N
        rides ever" per the spec's own example — is the most natural
        source for this entitlement's `total_uses`, reusing the exact
        field welcome/referral grants already use for "how many rides
        can this be applied to." Absent a limit, a coupon is single-use
        per redemption (`total_uses=1`), matching the migration's own
        `per_customer_use_limit` default of 1. The entitlement's expiry
        is capped at the campaign's own `ends_at` when one is set — an
        entitlement must never outlive the campaign that produced it —
        else it falls back to the same 30-day window every other
        entitlement uses (BR-062).
        """
        discount_percent, max_discount_amount = campaign.redemption_discount_fields()
        expires_at = now + timedelta(days=_ENTITLEMENT_VALIDITY_DAYS)
        if campaign.ends_at is not None and campaign.ends_at < expires_at:
            expires_at = campaign.ends_at
        return Entitlement(
            id=uuid.uuid4(),
            customer_id=customer_id,
            promotion_type=PromotionType.CAMPAIGN,
            total_uses=campaign.ride_count_limit or 1,
            remaining_uses=campaign.ride_count_limit or 1,
            discount_percent=discount_percent,
            max_discount_amount=max_discount_amount,
            activated_at=now,
            expires_at=expires_at,
            status=EntitlementStatus.ACTIVE,
            campaign_id=campaign.id,
        )

    def is_expired(self, *, now: datetime) -> bool:
        return self.expires_at <= now


@dataclass(slots=True)
class Usage:
    id: uuid.UUID
    entitlement_id: uuid.UUID
    ride_id: uuid.UUID
    discount_amount: Decimal
    status: UsageStatus
    created_at: datetime

    @staticmethod
    def new(
        *,
        entitlement_id: uuid.UUID,
        ride_id: uuid.UUID,
        discount_amount: Decimal,
        status: UsageStatus,
        now: datetime,
    ) -> Usage:
        if discount_amount < 0:
            raise InvalidPromotionInputError("discount_amount cannot be negative.")
        return Usage(
            id=uuid.uuid4(),
            entitlement_id=entitlement_id,
            ride_id=ride_id,
            discount_amount=discount_amount,
            status=status,
            created_at=now,
        )


@dataclass(slots=True)
class Reservation:
    id: uuid.UUID
    entitlement_id: uuid.UUID
    ride_id: uuid.UUID
    status: ReservationStatus
    created_at: datetime

    @staticmethod
    def new(
        *, entitlement_id: uuid.UUID, ride_id: uuid.UUID, now: datetime
    ) -> Reservation:
        return Reservation(
            id=uuid.uuid4(),
            entitlement_id=entitlement_id,
            ride_id=ride_id,
            status=ReservationStatus.RESERVED,
            created_at=now,
        )


# --- Campaign (ADR-0041) ---------------------------------------------------
#
# A campaign is an authored, many-times-redeemable coupon definition —
# a materially different lifecycle from Entitlement above (one
# customer's already-granted promotion). See ADR-0041 §1/§7 for why
# these are two tables, not one.


class DiscountType(StrEnum):
    PERCENT = "PERCENT"
    FLAT = "FLAT"


class EligibleScope(StrEnum):
    ALL = "ALL"
    SELECTED = "SELECTED"


class CampaignStatus(StrEnum):
    """DRAFT -> ACTIVE <-> PAUSED, and DRAFT/ACTIVE/PAUSED -> ENDED
    (terminal). Editing (PATCH) is allowed only in DRAFT (ADR-0041
    Decision 4)."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ENDED = "ENDED"


# Status -> the set of statuses a single activate/pause/end call may
# move a campaign from. Matches ADR-0041 Decision 3's endpoint list
# exactly: activate accepts DRAFT or PAUSED, pause accepts only ACTIVE,
# end accepts any non-terminal status.
_ALLOWED_TRANSITIONS_TO_ACTIVE = {CampaignStatus.DRAFT, CampaignStatus.PAUSED}
_ALLOWED_TRANSITIONS_TO_PAUSED = {CampaignStatus.ACTIVE}
_ALLOWED_TRANSITIONS_TO_ENDED = {
    CampaignStatus.DRAFT,
    CampaignStatus.ACTIVE,
    CampaignStatus.PAUSED,
}


def _validate_campaign_fields(
    *,
    code: str | None,
    name: str,
    discount_type: DiscountType,
    discount_value: Decimal,
    max_discount_amount: Decimal | None,
    minimum_fare: Decimal | None,
    eligible_scope: EligibleScope,
    per_customer_use_limit: int,
    total_usage_limit: int | None,
    ride_count_limit: int | None,
    starts_at: datetime,
    ends_at: datetime | None,
) -> None:
    """Shared by Campaign.new (creation) and Campaign.apply_edit
    (DRAFT-only PATCH, ADR-0041 Decision 4) so both paths enforce
    identical field rules. Raises the campaign-specific
    InvalidCampaignInputError, not the entitlement-facing
    InvalidPromotionInputError used elsewhere in this module — same
    VALIDATION_FAILED code, but a distinct type, matching this
    codebase's existing precedent of a module owning its own
    "InvalidCampaignInputError" for its own campaign-shaped entity
    (modules.advertisement.domain.errors has one for its own,
    unrelated, advertisement campaigns)."""
    if not name.strip():
        raise InvalidCampaignInputError("name is required.")
    if discount_value <= 0:
        raise InvalidCampaignInputError("discount_value must be positive.")
    if discount_type == DiscountType.PERCENT and discount_value > 100:
        raise InvalidCampaignInputError(
            "discount_value cannot exceed 100 for a PERCENT campaign."
        )
    if max_discount_amount is not None and max_discount_amount <= 0:
        raise InvalidCampaignInputError(
            "max_discount_amount must be positive when provided."
        )
    if minimum_fare is not None and minimum_fare < 0:
        raise InvalidCampaignInputError("minimum_fare cannot be negative.")
    if per_customer_use_limit <= 0:
        raise InvalidCampaignInputError("per_customer_use_limit must be at least 1.")
    if total_usage_limit is not None and total_usage_limit <= 0:
        raise InvalidCampaignInputError(
            "total_usage_limit must be positive when provided."
        )
    if ride_count_limit is not None and ride_count_limit <= 0:
        raise InvalidCampaignInputError(
            "ride_count_limit must be positive when provided."
        )
    if ends_at is not None and ends_at <= starts_at:
        raise InvalidCampaignInputError("ends_at must be after starts_at.")
    if eligible_scope == EligibleScope.SELECTED and code is None:
        # A SELECTED-scope campaign is targeted at specific customers by
        # definition — an auto-applied (codeless) campaign only makes
        # sense scoped ALL, since there is no code to gate redemption to
        # the selected list otherwise.
        raise InvalidCampaignInputError("eligible_scope='SELECTED' requires a code.")


@dataclass(slots=True)
class Campaign:
    id: uuid.UUID
    code: str | None
    name: str
    vehicle_category: VehicleCategory | None
    discount_type: DiscountType
    discount_value: Decimal
    max_discount_amount: Decimal | None
    minimum_fare: Decimal | None
    eligible_scope: EligibleScope
    per_customer_use_limit: int
    total_usage_limit: int | None
    ride_count_limit: int | None
    starts_at: datetime
    ends_at: datetime | None
    status: CampaignStatus
    created_by: uuid.UUID
    created_at: datetime

    @staticmethod
    def new(
        *,
        code: str | None,
        name: str,
        vehicle_category: VehicleCategory | None,
        discount_type: DiscountType,
        discount_value: Decimal,
        max_discount_amount: Decimal | None,
        minimum_fare: Decimal | None,
        eligible_scope: EligibleScope,
        per_customer_use_limit: int,
        total_usage_limit: int | None,
        ride_count_limit: int | None,
        starts_at: datetime,
        ends_at: datetime | None,
        created_by: uuid.UUID,
        now: datetime,
    ) -> Campaign:
        _validate_campaign_fields(
            code=code,
            name=name,
            discount_type=discount_type,
            discount_value=discount_value,
            max_discount_amount=max_discount_amount,
            minimum_fare=minimum_fare,
            eligible_scope=eligible_scope,
            per_customer_use_limit=per_customer_use_limit,
            total_usage_limit=total_usage_limit,
            ride_count_limit=ride_count_limit,
            starts_at=starts_at,
            ends_at=ends_at,
        )

        return Campaign(
            id=uuid.uuid4(),
            code=code,
            name=name,
            vehicle_category=vehicle_category,
            discount_type=discount_type,
            discount_value=discount_value,
            max_discount_amount=max_discount_amount,
            minimum_fare=minimum_fare,
            eligible_scope=eligible_scope,
            per_customer_use_limit=per_customer_use_limit,
            total_usage_limit=total_usage_limit,
            ride_count_limit=ride_count_limit,
            starts_at=starts_at,
            ends_at=ends_at,
            status=CampaignStatus.DRAFT,
            created_by=created_by,
            created_at=now,
        )

    def is_within_window(self, *, now: datetime) -> bool:
        if now < self.starts_at:
            return False
        if self.ends_at is not None and now >= self.ends_at:
            return False
        return True

    def can_edit(self) -> bool:
        """ADR-0041 Decision 4: PATCH succeeds only in DRAFT — once a
        campaign is ACTIVE/PAUSED it may already have real redemptions,
        so only status transitions (activate/pause/end) remain
        available, never its discount terms."""
        return self.status == CampaignStatus.DRAFT

    def apply_edit(
        self,
        *,
        code: str | None,
        name: str,
        vehicle_category: VehicleCategory | None,
        discount_type: DiscountType,
        discount_value: Decimal,
        max_discount_amount: Decimal | None,
        minimum_fare: Decimal | None,
        eligible_scope: EligibleScope,
        per_customer_use_limit: int,
        total_usage_limit: int | None,
        ride_count_limit: int | None,
        starts_at: datetime,
        ends_at: datetime | None,
    ) -> None:
        """PATCH — caller (the service layer) must check can_edit()
        first; this only validates and mutates the editable fields, id/
        status/created_by/created_at are never touched here."""
        _validate_campaign_fields(
            code=code,
            name=name,
            discount_type=discount_type,
            discount_value=discount_value,
            max_discount_amount=max_discount_amount,
            minimum_fare=minimum_fare,
            eligible_scope=eligible_scope,
            per_customer_use_limit=per_customer_use_limit,
            total_usage_limit=total_usage_limit,
            ride_count_limit=ride_count_limit,
            starts_at=starts_at,
            ends_at=ends_at,
        )
        self.code = code
        self.name = name
        self.vehicle_category = vehicle_category
        self.discount_type = discount_type
        self.discount_value = discount_value
        self.max_discount_amount = max_discount_amount
        self.minimum_fare = minimum_fare
        self.eligible_scope = eligible_scope
        self.per_customer_use_limit = per_customer_use_limit
        self.total_usage_limit = total_usage_limit
        self.ride_count_limit = ride_count_limit
        self.starts_at = starts_at
        self.ends_at = ends_at

    def activate(self) -> None:
        if self.status not in _ALLOWED_TRANSITIONS_TO_ACTIVE:
            raise InvalidCampaignStateTransitionError(
                f"Cannot activate a campaign in status {self.status}."
            )
        self.status = CampaignStatus.ACTIVE

    def pause(self) -> None:
        if self.status not in _ALLOWED_TRANSITIONS_TO_PAUSED:
            raise InvalidCampaignStateTransitionError(
                f"Cannot pause a campaign in status {self.status}."
            )
        self.status = CampaignStatus.PAUSED

    def end(self) -> None:
        if self.status not in _ALLOWED_TRANSITIONS_TO_ENDED:
            raise InvalidCampaignStateTransitionError(
                f"Cannot end a campaign in status {self.status}."
            )
        self.status = CampaignStatus.ENDED

    def redemption_discount_fields(self) -> tuple[Decimal, Decimal | None]:
        """Returns the (discount_percent, max_discount_amount) pair a
        redeeming entitlement should be created with — ADR-0041 §6.1.

        PERCENT campaigns pass their own discount_value/
        max_discount_amount straight through. FLAT campaigns have no
        percent of their own; representing "X off" as
        discount_percent=100 + max_discount_amount=X is mathematically
        identical (min(fare, X) either way), so no separate stored
        representation is needed on Entitlement.
        """
        if self.discount_type == DiscountType.PERCENT:
            return self.discount_value, self.max_discount_amount
        return Decimal("100"), self.discount_value
