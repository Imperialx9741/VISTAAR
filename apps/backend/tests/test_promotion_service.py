"""Unit tests for PromotionService against in-memory fake repositories."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from modules.promotion.domain.entities import (
    Campaign,
    CampaignStatus,
    DiscountType,
    Entitlement,
    EntitlementStatus,
    Reservation,
    Usage,
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
from modules.promotion.service import PromotionService
from modules.vehicle.domain.entities import VehicleCategory

CUSTOMER_ID = uuid.uuid4()
RIDE_ID = uuid.uuid4()
ADMIN_ID = uuid.uuid4()
NOW = datetime.now(UTC)


class FakeEntitlementRepository:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, Entitlement] = {}

    def create(self, entitlement: Entitlement) -> Entitlement:
        self.by_id[entitlement.id] = entitlement
        return entitlement

    def get_by_id_for_update(self, entitlement_id: uuid.UUID) -> Entitlement | None:
        return self.by_id.get(entitlement_id)

    def save(self, entitlement: Entitlement) -> None:
        self.by_id[entitlement.id] = entitlement

    def list_active_for_customer(self, customer_id: uuid.UUID) -> list[Entitlement]:
        return [
            e
            for e in self.by_id.values()
            if e.customer_id == customer_id and e.status is EntitlementStatus.ACTIVE
        ]

    def count_campaign_redemptions(
        self, campaign_id: uuid.UUID, *, customer_id: uuid.UUID | None = None
    ) -> int:
        return len(
            [
                e
                for e in self.by_id.values()
                if e.campaign_id == campaign_id
                and (customer_id is None or e.customer_id == customer_id)
            ]
        )

    def count_by_type_activated_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self.by_id.values():
            if since <= e.activated_at < until:
                key = e.promotion_type.value
                counts[key] = counts.get(key, 0) + 1
        return counts


class FakeCampaignRepository:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, Campaign] = {}
        self.eligible_customers: dict[uuid.UUID, set[uuid.UUID]] = {}

    def create(self, campaign: Campaign) -> Campaign:
        self.by_id[campaign.id] = campaign
        return campaign

    def get_by_id(self, campaign_id: uuid.UUID) -> Campaign | None:
        return self.by_id.get(campaign_id)

    def get_by_id_for_update(self, campaign_id: uuid.UUID) -> Campaign | None:
        return self.by_id.get(campaign_id)

    def get_by_code_for_update(self, code: str) -> Campaign | None:
        for campaign in self.by_id.values():
            if campaign.code == code:
                return campaign
        return None

    def save(self, campaign: Campaign) -> None:
        self.by_id[campaign.id] = campaign

    def list_campaigns(
        self, *, status: CampaignStatus | None, offset: int, limit: int
    ) -> tuple[list[Campaign], int]:
        rows = [c for c in self.by_id.values() if status is None or c.status is status]
        return rows[offset : offset + limit], len(rows)

    def is_customer_eligible(
        self, *, campaign_id: uuid.UUID, customer_id: uuid.UUID
    ) -> bool:
        return customer_id in self.eligible_customers.get(campaign_id, set())

    def set_eligible_customers(
        self, *, campaign_id: uuid.UUID, customer_ids: list[uuid.UUID]
    ) -> None:
        self.eligible_customers[campaign_id] = set(customer_ids)

    def add_eligible_customers(
        self, *, campaign_id: uuid.UUID, customer_ids: list[uuid.UUID]
    ) -> set[uuid.UUID]:
        existing = self.eligible_customers.setdefault(campaign_id, set())
        newly_added = {cid for cid in customer_ids if cid not in existing}
        existing.update(newly_added)
        return newly_added


class FakeUsageRepository:
    def __init__(self) -> None:
        self.created: list[Usage] = []

    def create(self, usage: Usage) -> Usage:
        self.created.append(usage)
        return usage

    def count_consumed_in_range(self, *, since: datetime, until: datetime) -> int:
        return sum(
            1
            for u in self.created
            if u.status.value == "CONSUMED" and since <= u.created_at < until
        )

    def sum_discount_in_range(self, *, since: datetime, until: datetime) -> Decimal:
        return sum(
            (u.discount_amount for u in self.created if since <= u.created_at < until),
            Decimal("0"),
        )


class FakeReservationRepository:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, Reservation] = {}

    def create(self, reservation: Reservation) -> Reservation:
        self.by_id[reservation.id] = reservation
        return reservation

    def get_by_id(self, reservation_id: uuid.UUID) -> Reservation | None:
        return self.by_id.get(reservation_id)

    def get_by_id_for_update(self, reservation_id: uuid.UUID) -> Reservation | None:
        return self.by_id.get(reservation_id)

    def get_by_ride_id(self, ride_id: uuid.UUID) -> Reservation | None:
        for reservation in self.by_id.values():
            if reservation.ride_id == ride_id:
                return reservation
        return None

    def save(self, reservation: Reservation) -> None:
        self.by_id[reservation.id] = reservation


@pytest.fixture
def entitlements() -> FakeEntitlementRepository:
    return FakeEntitlementRepository()


@pytest.fixture
def usages() -> FakeUsageRepository:
    return FakeUsageRepository()


@pytest.fixture
def reservations() -> FakeReservationRepository:
    return FakeReservationRepository()


@pytest.fixture
def campaigns() -> FakeCampaignRepository:
    return FakeCampaignRepository()


@pytest.fixture
def service(
    entitlements: FakeEntitlementRepository,
    usages: FakeUsageRepository,
    reservations: FakeReservationRepository,
    campaigns: FakeCampaignRepository,
) -> PromotionService:
    return PromotionService(
        entitlements=entitlements,
        usages=usages,
        reservations=reservations,
        campaigns=campaigns,
    )


def test_grant_welcome_promotion_is_three_uses_at_fifty_percent(
    service: PromotionService,
) -> None:
    entitlement = service.grant_welcome_promotion(customer_id=CUSTOMER_ID, now=NOW)

    assert entitlement.promotion_type.value == "WELCOME"
    assert entitlement.total_uses == 3
    assert entitlement.remaining_uses == 3
    assert entitlement.discount_percent == Decimal("50")
    assert entitlement.max_discount_amount == Decimal("100")  # BR-063, ADR-0049
    assert entitlement.expires_at == NOW + timedelta(days=30)


def test_grant_referral_promotion_referred_is_three_uses(
    service: PromotionService,
) -> None:
    entitlement = service.grant_referral_promotion(
        customer_id=CUSTOMER_ID, is_referring_customer=False, now=NOW
    )

    assert entitlement.promotion_type.value == "REFERRAL_REFERRED"
    assert entitlement.total_uses == 3
    assert entitlement.max_discount_amount == Decimal("100")  # BR-063, ADR-0049


def test_grant_referral_promotion_referring_is_two_uses(
    service: PromotionService,
) -> None:
    entitlement = service.grant_referral_promotion(
        customer_id=CUSTOMER_ID, is_referring_customer=True, now=NOW
    )

    assert entitlement.promotion_type.value == "REFERRAL_REFERRING"
    assert entitlement.total_uses == 2
    assert entitlement.max_discount_amount == Decimal("100")  # BR-063, ADR-0049


def test_list_entitlements_lazily_expires_past_expiry(
    service: PromotionService, entitlements: FakeEntitlementRepository
) -> None:
    entitlement = service.grant_welcome_promotion(customer_id=CUSTOMER_ID, now=NOW)
    later = NOW + timedelta(days=31)

    active = service.list_entitlements(customer_id=CUSTOMER_ID, now=later)

    assert active == []
    assert entitlements.by_id[entitlement.id].status is EntitlementStatus.EXPIRED


def test_list_entitlements_excludes_other_customers(
    service: PromotionService,
) -> None:
    service.grant_welcome_promotion(customer_id=CUSTOMER_ID, now=NOW)

    active = service.list_entitlements(customer_id=uuid.uuid4(), now=NOW)

    assert active == []


def test_reserve_entitlement_decrements_remaining_uses(
    service: PromotionService,
) -> None:
    entitlement = service.grant_welcome_promotion(customer_id=CUSTOMER_ID, now=NOW)

    reservation = service.reserve_entitlement(
        customer_id=CUSTOMER_ID,
        entitlement_id=entitlement.id,
        ride_id=RIDE_ID,
        now=NOW,
    )

    assert reservation.status.value == "RESERVED"
    assert entitlement.remaining_uses == 2


def test_reserve_entitlement_marks_exhausted_at_zero(
    service: PromotionService,
) -> None:
    entitlement = service.grant_referral_promotion(
        customer_id=CUSTOMER_ID, is_referring_customer=True, now=NOW
    )  # 2 uses

    service.reserve_entitlement(
        customer_id=CUSTOMER_ID,
        entitlement_id=entitlement.id,
        ride_id=uuid.uuid4(),
        now=NOW,
    )
    service.reserve_entitlement(
        customer_id=CUSTOMER_ID,
        entitlement_id=entitlement.id,
        ride_id=uuid.uuid4(),
        now=NOW,
    )

    assert entitlement.remaining_uses == 0
    assert entitlement.status is EntitlementStatus.EXHAUSTED
    with pytest.raises(PromotionAlreadyUsedError):
        service.reserve_entitlement(
            customer_id=CUSTOMER_ID,
            entitlement_id=entitlement.id,
            ride_id=uuid.uuid4(),
            now=NOW,
        )


def test_reserve_entitlement_rejects_wrong_owner(
    service: PromotionService,
) -> None:
    entitlement = service.grant_welcome_promotion(customer_id=CUSTOMER_ID, now=NOW)

    with pytest.raises(EntitlementNotFoundError):
        service.reserve_entitlement(
            customer_id=uuid.uuid4(),  # IDOR-safe: not-found either way
            entitlement_id=entitlement.id,
            ride_id=RIDE_ID,
            now=NOW,
        )


def test_reserve_entitlement_rejects_expired(service: PromotionService) -> None:
    entitlement = service.grant_welcome_promotion(customer_id=CUSTOMER_ID, now=NOW)
    later = NOW + timedelta(days=31)

    with pytest.raises(PromotionExpiredError):
        service.reserve_entitlement(
            customer_id=CUSTOMER_ID,
            entitlement_id=entitlement.id,
            ride_id=RIDE_ID,
            now=later,
        )
    assert entitlement.status is EntitlementStatus.EXPIRED


def test_consume_reservation_marks_consumed(service: PromotionService) -> None:
    entitlement = service.grant_welcome_promotion(customer_id=CUSTOMER_ID, now=NOW)
    reservation = service.reserve_entitlement(
        customer_id=CUSTOMER_ID,
        entitlement_id=entitlement.id,
        ride_id=RIDE_ID,
        now=NOW,
    )

    usage = service.consume_reservation(
        reservation_id=reservation.id, discount_amount=Decimal("50"), now=NOW
    )

    assert usage.status.value == "CONSUMED"
    assert reservation.status.value == "CONSUMED"


def test_consume_reservation_rejects_already_resolved(
    service: PromotionService,
) -> None:
    entitlement = service.grant_welcome_promotion(customer_id=CUSTOMER_ID, now=NOW)
    reservation = service.reserve_entitlement(
        customer_id=CUSTOMER_ID,
        entitlement_id=entitlement.id,
        ride_id=RIDE_ID,
        now=NOW,
    )
    service.consume_reservation(
        reservation_id=reservation.id, discount_amount=Decimal("50"), now=NOW
    )

    with pytest.raises(PromotionAlreadyUsedError):
        service.consume_reservation(
            reservation_id=reservation.id, discount_amount=Decimal("50"), now=NOW
        )


def test_consume_reservation_not_found(service: PromotionService) -> None:
    with pytest.raises(ReservationNotFoundError):
        service.consume_reservation(
            reservation_id=uuid.uuid4(), discount_amount=Decimal("50"), now=NOW
        )


def test_restore_reservation_gives_back_the_use(service: PromotionService) -> None:
    entitlement = service.grant_referral_promotion(
        customer_id=CUSTOMER_ID, is_referring_customer=True, now=NOW
    )  # 2 uses
    service.reserve_entitlement(
        customer_id=CUSTOMER_ID,
        entitlement_id=entitlement.id,
        ride_id=uuid.uuid4(),
        now=NOW,
    )
    reservation = service.reserve_entitlement(
        customer_id=CUSTOMER_ID,
        entitlement_id=entitlement.id,
        ride_id=uuid.uuid4(),
        now=NOW,
    )
    assert entitlement.status is EntitlementStatus.EXHAUSTED

    restored = service.restore_reservation(reservation_id=reservation.id, now=NOW)

    assert restored.status.value == "RESTORED"
    assert entitlement.remaining_uses == 1
    assert entitlement.status is EntitlementStatus.ACTIVE  # reverted from EXHAUSTED


def test_restore_reservation_rejects_already_resolved(
    service: PromotionService,
) -> None:
    entitlement = service.grant_welcome_promotion(customer_id=CUSTOMER_ID, now=NOW)
    reservation = service.reserve_entitlement(
        customer_id=CUSTOMER_ID,
        entitlement_id=entitlement.id,
        ride_id=RIDE_ID,
        now=NOW,
    )
    service.restore_reservation(reservation_id=reservation.id, now=NOW)

    with pytest.raises(PromotionAlreadyUsedError):
        service.restore_reservation(reservation_id=reservation.id, now=NOW)


# --- Campaign (ADR-0041) ----------------------------------------------------


def _make_campaign(
    service: PromotionService,
    *,
    code: str | None = "SAVE50",
    discount_type: str = "PERCENT",
    discount_value: Decimal = Decimal("50"),
    max_discount_amount: Decimal | None = Decimal("100"),
    minimum_fare: Decimal | None = None,
    eligible_scope: str = "ALL",
    per_customer_use_limit: int = 1,
    total_usage_limit: int | None = None,
    ride_count_limit: int | None = None,
    vehicle_category: VehicleCategory | None = None,
    starts_at: datetime = NOW - timedelta(days=1),
    ends_at: datetime | None = NOW + timedelta(days=30),
    eligible_customer_ids: list[uuid.UUID] | None = None,
) -> Campaign:
    return service.create_campaign(
        code=code,
        name="50% off",
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
        eligible_customer_ids=eligible_customer_ids,
        created_by=ADMIN_ID,
        now=NOW,
    )


def test_create_campaign_starts_as_draft(service: PromotionService) -> None:
    campaign = _make_campaign(service)

    assert campaign.status is CampaignStatus.DRAFT
    assert campaign.discount_type is DiscountType.PERCENT


def test_create_campaign_rejects_selected_scope_without_code(
    service: PromotionService,
) -> None:
    with pytest.raises(InvalidCampaignInputError):
        _make_campaign(service, code=None, eligible_scope="SELECTED")


def test_activate_pause_end_lifecycle(service: PromotionService) -> None:
    campaign = _make_campaign(service)

    activated = service.activate_campaign(campaign_id=campaign.id)
    assert activated.status is CampaignStatus.ACTIVE

    paused = service.pause_campaign(campaign_id=campaign.id)
    assert paused.status is CampaignStatus.PAUSED

    reactivated = service.activate_campaign(campaign_id=campaign.id)
    assert reactivated.status is CampaignStatus.ACTIVE

    ended = service.end_campaign(campaign_id=campaign.id)
    assert ended.status is CampaignStatus.ENDED

    with pytest.raises(InvalidCampaignStateTransitionError):
        service.activate_campaign(campaign_id=campaign.id)


def test_update_campaign_rejected_once_active(service: PromotionService) -> None:
    campaign = _make_campaign(service)
    service.activate_campaign(campaign_id=campaign.id)

    with pytest.raises(InvalidCampaignStateTransitionError):
        service.update_campaign(
            campaign_id=campaign.id,
            code=campaign.code,
            name="Changed name",
            vehicle_category=None,
            discount_type="PERCENT",
            discount_value=Decimal("60"),
            max_discount_amount=campaign.max_discount_amount,
            minimum_fare=None,
            eligible_scope="ALL",
            per_customer_use_limit=1,
            total_usage_limit=None,
            ride_count_limit=None,
            starts_at=campaign.starts_at,
            ends_at=campaign.ends_at,
            eligible_customer_ids=None,
        )


def test_update_campaign_allowed_while_draft(service: PromotionService) -> None:
    campaign = _make_campaign(service)

    updated = service.update_campaign(
        campaign_id=campaign.id,
        code=campaign.code,
        name="Renamed",
        vehicle_category=None,
        discount_type="PERCENT",
        discount_value=Decimal("60"),
        max_discount_amount=campaign.max_discount_amount,
        minimum_fare=None,
        eligible_scope="ALL",
        per_customer_use_limit=1,
        total_usage_limit=None,
        ride_count_limit=None,
        starts_at=campaign.starts_at,
        ends_at=campaign.ends_at,
        eligible_customer_ids=None,
    )

    assert updated.name == "Renamed"
    assert updated.discount_value == Decimal("60")


# --- bulk_add_eligible_customers() (Admin Web §4.10, ADR-0041 §9) -----------


def test_bulk_add_eligible_customers_is_additive(service: PromotionService) -> None:
    campaign = _make_campaign(service, eligible_scope="SELECTED")
    first, second, third = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    service.bulk_add_eligible_customers(campaign_id=campaign.id, customer_ids=[first])

    newly_added = service.bulk_add_eligible_customers(
        campaign_id=campaign.id, customer_ids=[first, second, third]
    )

    # `first` was already eligible from the prior call — additive
    # semantics mean it's untouched, not an error, and not double-added.
    assert newly_added == {second, third}


def test_bulk_add_eligible_customers_rejects_non_selected_scope(
    service: PromotionService,
) -> None:
    campaign = _make_campaign(service, eligible_scope="ALL")

    with pytest.raises(InvalidCampaignInputError):
        service.bulk_add_eligible_customers(
            campaign_id=campaign.id, customer_ids=[uuid.uuid4()]
        )


def test_bulk_add_eligible_customers_rejected_once_active(
    service: PromotionService,
) -> None:
    campaign = _make_campaign(service, eligible_scope="SELECTED")
    service.activate_campaign(campaign_id=campaign.id)

    with pytest.raises(InvalidCampaignStateTransitionError):
        service.bulk_add_eligible_customers(
            campaign_id=campaign.id, customer_ids=[uuid.uuid4()]
        )


def test_bulk_add_eligible_customers_raises_for_unknown_campaign(
    service: PromotionService,
) -> None:
    with pytest.raises(CampaignNotFoundError):
        service.bulk_add_eligible_customers(
            campaign_id=uuid.uuid4(), customer_ids=[uuid.uuid4()]
        )


def test_redeem_campaign_code_creates_percent_entitlement(
    service: PromotionService,
) -> None:
    campaign = _make_campaign(service, discount_value=Decimal("50"))
    service.activate_campaign(campaign_id=campaign.id)

    entitlement = service.redeem_campaign_code(
        customer_id=CUSTOMER_ID,
        code="SAVE50",
        vehicle_category=VehicleCategory.CAB,
        fare=Decimal("500"),
        now=NOW,
    )

    assert entitlement.campaign_id == campaign.id
    assert entitlement.discount_percent == Decimal("50")
    assert entitlement.max_discount_amount == Decimal("100")
    assert entitlement.total_uses == 1  # no ride_count_limit set


def test_redeem_flat_campaign_represented_as_capped_percent(
    service: PromotionService,
) -> None:
    # ADR-0041 §6.1: a FLAT ₹50-off campaign is stored as
    # discount_percent=100 + max_discount_amount=50 — min(fare, 50).
    campaign = _make_campaign(
        service,
        code="FLAT50",
        discount_type="FLAT",
        discount_value=Decimal("50"),
        max_discount_amount=None,
    )
    service.activate_campaign(campaign_id=campaign.id)

    entitlement = service.redeem_campaign_code(
        customer_id=CUSTOMER_ID,
        code="FLAT50",
        vehicle_category=VehicleCategory.CAB,
        fare=Decimal("500"),
        now=NOW,
    )

    assert entitlement.discount_percent == Decimal("100")
    assert entitlement.max_discount_amount == Decimal("50")


def test_redeem_campaign_code_not_found(service: PromotionService) -> None:
    with pytest.raises(CampaignNotFoundError):
        service.redeem_campaign_code(
            customer_id=CUSTOMER_ID,
            code="NOPE",
            vehicle_category=VehicleCategory.CAB,
            fare=Decimal("500"),
            now=NOW,
        )


def test_redeem_campaign_code_rejects_while_draft(service: PromotionService) -> None:
    _make_campaign(service)  # never activated

    with pytest.raises(CampaignNotActiveError):
        service.redeem_campaign_code(
            customer_id=CUSTOMER_ID,
            code="SAVE50",
            vehicle_category=VehicleCategory.CAB,
            fare=Decimal("500"),
            now=NOW,
        )


def test_redeem_campaign_code_rejects_outside_window(service: PromotionService) -> None:
    campaign = _make_campaign(
        service,
        starts_at=NOW + timedelta(days=1),
        ends_at=NOW + timedelta(days=10),
    )
    service.activate_campaign(campaign_id=campaign.id)

    with pytest.raises(CampaignNotActiveError):
        service.redeem_campaign_code(
            customer_id=CUSTOMER_ID,
            code="SAVE50",
            vehicle_category=VehicleCategory.CAB,
            fare=Decimal("500"),
            now=NOW,  # before starts_at
        )


def test_redeem_campaign_code_rejects_vehicle_category_mismatch(
    service: PromotionService,
) -> None:
    campaign = _make_campaign(service, vehicle_category=VehicleCategory.BIKE)
    service.activate_campaign(campaign_id=campaign.id)

    with pytest.raises(CampaignNotEligibleError):
        service.redeem_campaign_code(
            customer_id=CUSTOMER_ID,
            code="SAVE50",
            vehicle_category=VehicleCategory.CAB,
            fare=Decimal("500"),
            now=NOW,
        )


def test_redeem_campaign_code_rejects_non_selected_customer(
    service: PromotionService,
) -> None:
    campaign = _make_campaign(
        service,
        eligible_scope="SELECTED",
        eligible_customer_ids=[uuid.uuid4()],  # not CUSTOMER_ID
    )
    service.activate_campaign(campaign_id=campaign.id)

    with pytest.raises(CampaignNotEligibleError):
        service.redeem_campaign_code(
            customer_id=CUSTOMER_ID,
            code="SAVE50",
            vehicle_category=VehicleCategory.CAB,
            fare=Decimal("500"),
            now=NOW,
        )


def test_redeem_campaign_code_allows_selected_customer(
    service: PromotionService,
) -> None:
    campaign = _make_campaign(
        service,
        eligible_scope="SELECTED",
        eligible_customer_ids=[CUSTOMER_ID],
    )
    service.activate_campaign(campaign_id=campaign.id)

    entitlement = service.redeem_campaign_code(
        customer_id=CUSTOMER_ID,
        code="SAVE50",
        vehicle_category=VehicleCategory.CAB,
        fare=Decimal("500"),
        now=NOW,
    )

    assert entitlement.campaign_id == campaign.id


def test_redeem_campaign_code_rejects_below_minimum_fare(
    service: PromotionService,
) -> None:
    campaign = _make_campaign(service, minimum_fare=Decimal("200"))
    service.activate_campaign(campaign_id=campaign.id)

    with pytest.raises(CampaignMinimumFareNotMetError):
        service.redeem_campaign_code(
            customer_id=CUSTOMER_ID,
            code="SAVE50",
            vehicle_category=VehicleCategory.CAB,
            fare=Decimal("100"),
            now=NOW,
        )


def test_redeem_campaign_code_rejects_over_per_customer_limit(
    service: PromotionService,
) -> None:
    campaign = _make_campaign(service, per_customer_use_limit=1)
    service.activate_campaign(campaign_id=campaign.id)
    service.redeem_campaign_code(
        customer_id=CUSTOMER_ID,
        code="SAVE50",
        vehicle_category=VehicleCategory.CAB,
        fare=Decimal("500"),
        now=NOW,
    )

    with pytest.raises(CampaignUsageLimitExceededError):
        service.redeem_campaign_code(
            customer_id=CUSTOMER_ID,
            code="SAVE50",
            vehicle_category=VehicleCategory.CAB,
            fare=Decimal("500"),
            now=NOW,
        )


def test_redeem_campaign_code_rejects_over_total_usage_limit(
    service: PromotionService,
) -> None:
    campaign = _make_campaign(service, total_usage_limit=1, per_customer_use_limit=5)
    service.activate_campaign(campaign_id=campaign.id)
    service.redeem_campaign_code(
        customer_id=CUSTOMER_ID,
        code="SAVE50",
        vehicle_category=VehicleCategory.CAB,
        fare=Decimal("500"),
        now=NOW,
    )

    with pytest.raises(CampaignUsageLimitExceededError):
        service.redeem_campaign_code(
            customer_id=uuid.uuid4(),  # a different customer
            code="SAVE50",
            vehicle_category=VehicleCategory.CAB,
            fare=Decimal("500"),
            now=NOW,
        )


def test_redeem_campaign_code_entitlement_expiry_capped_at_campaign_end(
    service: PromotionService,
) -> None:
    campaign = _make_campaign(service, ends_at=NOW + timedelta(days=5))
    service.activate_campaign(campaign_id=campaign.id)

    entitlement = service.redeem_campaign_code(
        customer_id=CUSTOMER_ID,
        code="SAVE50",
        vehicle_category=VehicleCategory.CAB,
        fare=Decimal("500"),
        now=NOW,
    )

    assert entitlement.expires_at == campaign.ends_at  # capped, not the 30-day default


def test_redeem_campaign_code_uses_ride_count_limit_as_total_uses(
    service: PromotionService,
) -> None:
    campaign = _make_campaign(service, ride_count_limit=3)
    service.activate_campaign(campaign_id=campaign.id)

    entitlement = service.redeem_campaign_code(
        customer_id=CUSTOMER_ID,
        code="SAVE50",
        vehicle_category=VehicleCategory.CAB,
        fare=Decimal("500"),
        now=NOW,
    )

    assert entitlement.total_uses == 3
    assert entitlement.remaining_uses == 3
