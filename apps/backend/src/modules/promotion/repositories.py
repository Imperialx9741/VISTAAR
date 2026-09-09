"""SQLAlchemy-backed implementations of Promotion's ports."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from modules.promotion.domain.entities import (
    Campaign,
    CampaignStatus,
    DiscountType,
    EligibleScope,
    Entitlement,
    EntitlementStatus,
    PromotionType,
    Reservation,
    ReservationStatus,
    Usage,
    UsageStatus,
)
from modules.promotion.models import (
    CampaignEligibleCustomerORM,
    CampaignORM,
    EntitlementORM,
    ReservationORM,
    UsageORM,
)
from modules.vehicle.domain.entities import VehicleCategory


def _entitlement_from_orm(row: EntitlementORM) -> Entitlement:
    return Entitlement(
        id=row.id,
        customer_id=row.customer_id,
        promotion_type=PromotionType(row.promotion_type),
        total_uses=row.total_uses,
        remaining_uses=row.remaining_uses,
        discount_percent=row.discount_percent,
        max_discount_amount=row.max_discount_amount,
        activated_at=row.activated_at,
        expires_at=row.expires_at,
        status=EntitlementStatus(row.status),
        campaign_id=row.campaign_id,
    )


def _campaign_from_orm(row: CampaignORM) -> Campaign:
    return Campaign(
        id=row.id,
        code=row.code,
        name=row.name,
        vehicle_category=(
            VehicleCategory(row.vehicle_category) if row.vehicle_category else None
        ),
        discount_type=DiscountType(row.discount_type),
        discount_value=row.discount_value,
        max_discount_amount=row.max_discount_amount,
        minimum_fare=row.minimum_fare,
        eligible_scope=EligibleScope(row.eligible_scope),
        per_customer_use_limit=row.per_customer_use_limit,
        total_usage_limit=row.total_usage_limit,
        ride_count_limit=row.ride_count_limit,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        status=CampaignStatus(row.status),
        created_by=row.created_by,
        created_at=row.created_at,
    )


def _usage_from_orm(row: UsageORM) -> Usage:
    return Usage(
        id=row.id,
        entitlement_id=row.entitlement_id,
        ride_id=row.ride_id,
        discount_amount=row.discount_amount,
        status=UsageStatus(row.status),
        created_at=row.created_at,
    )


def _reservation_from_orm(row: ReservationORM) -> Reservation:
    return Reservation(
        id=row.id,
        entitlement_id=row.entitlement_id,
        ride_id=row.ride_id,
        status=ReservationStatus(row.status),
        created_at=row.created_at,
    )


class SqlAlchemyEntitlementRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, entitlement: Entitlement) -> Entitlement:
        row = EntitlementORM(
            id=entitlement.id,
            customer_id=entitlement.customer_id,
            promotion_type=entitlement.promotion_type.value,
            total_uses=entitlement.total_uses,
            remaining_uses=entitlement.remaining_uses,
            discount_percent=entitlement.discount_percent,
            max_discount_amount=entitlement.max_discount_amount,
            activated_at=entitlement.activated_at,
            expires_at=entitlement.expires_at,
            status=entitlement.status.value,
            campaign_id=entitlement.campaign_id,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _entitlement_from_orm(row)

    def get_by_id_for_update(self, entitlement_id: uuid.UUID) -> Entitlement | None:
        row = self._db.execute(
            select(EntitlementORM)
            .where(EntitlementORM.id == entitlement_id)
            .with_for_update()
        ).scalar_one_or_none()
        return _entitlement_from_orm(row) if row else None

    def save(self, entitlement: Entitlement) -> None:
        row = self._db.get(EntitlementORM, entitlement.id)
        if row is None:
            raise LookupError(f"Entitlement {entitlement.id} not found")
        row.remaining_uses = entitlement.remaining_uses
        row.status = entitlement.status.value
        self._db.flush()

    def list_active_for_customer(self, customer_id: uuid.UUID) -> list[Entitlement]:
        rows = (
            self._db.execute(
                select(EntitlementORM)
                .where(EntitlementORM.customer_id == customer_id)
                .where(EntitlementORM.status == EntitlementStatus.ACTIVE.value)
                .order_by(EntitlementORM.activated_at)
            )
            .scalars()
            .all()
        )
        return [_entitlement_from_orm(row) for row in rows]

    def count_campaign_redemptions(
        self, campaign_id: uuid.UUID, *, customer_id: uuid.UUID | None = None
    ) -> int:
        query = (
            select(func.count())
            .select_from(EntitlementORM)
            .where(EntitlementORM.campaign_id == campaign_id)
        )
        if customer_id is not None:
            query = query.where(EntitlementORM.customer_id == customer_id)
        return self._db.execute(query).scalar_one()

    def count_by_type_activated_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        rows = self._db.execute(
            select(EntitlementORM.promotion_type, func.count())
            .where(EntitlementORM.activated_at >= since)
            .where(EntitlementORM.activated_at < until)
            .group_by(EntitlementORM.promotion_type)
        ).all()
        return {key: value for key, value in rows}  # noqa: C416


class SqlAlchemyUsageRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, usage: Usage) -> Usage:
        row = UsageORM(
            id=usage.id,
            entitlement_id=usage.entitlement_id,
            ride_id=usage.ride_id,
            discount_amount=usage.discount_amount,
            status=usage.status.value,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _usage_from_orm(row)

    def count_consumed_in_range(self, *, since: datetime, until: datetime) -> int:
        return self._db.execute(
            select(func.count())
            .select_from(UsageORM)
            .where(UsageORM.status == UsageStatus.CONSUMED.value)
            .where(UsageORM.created_at >= since)
            .where(UsageORM.created_at < until)
        ).scalar_one()

    def sum_discount_in_range(self, *, since: datetime, until: datetime) -> Decimal:
        total = self._db.execute(
            select(func.coalesce(func.sum(UsageORM.discount_amount), 0))
            .where(UsageORM.created_at >= since)
            .where(UsageORM.created_at < until)
        ).scalar_one()
        return Decimal(total)


class SqlAlchemyReservationRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, reservation: Reservation) -> Reservation:
        row = ReservationORM(
            id=reservation.id,
            entitlement_id=reservation.entitlement_id,
            ride_id=reservation.ride_id,
            status=reservation.status.value,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _reservation_from_orm(row)

    def get_by_id(self, reservation_id: uuid.UUID) -> Reservation | None:
        row = self._db.get(ReservationORM, reservation_id)
        return _reservation_from_orm(row) if row else None

    def get_by_id_for_update(self, reservation_id: uuid.UUID) -> Reservation | None:
        row = self._db.execute(
            select(ReservationORM)
            .where(ReservationORM.id == reservation_id)
            .with_for_update()
        ).scalar_one_or_none()
        return _reservation_from_orm(row) if row else None

    def get_by_ride_id(self, ride_id: uuid.UUID) -> Reservation | None:
        row = self._db.execute(
            select(ReservationORM).where(ReservationORM.ride_id == ride_id)
        ).scalar_one_or_none()
        return _reservation_from_orm(row) if row else None

    def save(self, reservation: Reservation) -> None:
        row = self._db.get(ReservationORM, reservation.id)
        if row is None:
            raise LookupError(f"Reservation {reservation.id} not found")
        row.status = reservation.status.value
        self._db.flush()


class SqlAlchemyCampaignRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, campaign: Campaign) -> Campaign:
        row = CampaignORM(
            id=campaign.id,
            code=campaign.code,
            name=campaign.name,
            vehicle_category=(
                campaign.vehicle_category.value if campaign.vehicle_category else None
            ),
            discount_type=campaign.discount_type.value,
            discount_value=campaign.discount_value,
            max_discount_amount=campaign.max_discount_amount,
            minimum_fare=campaign.minimum_fare,
            eligible_scope=campaign.eligible_scope.value,
            per_customer_use_limit=campaign.per_customer_use_limit,
            total_usage_limit=campaign.total_usage_limit,
            ride_count_limit=campaign.ride_count_limit,
            starts_at=campaign.starts_at,
            ends_at=campaign.ends_at,
            status=campaign.status.value,
            created_by=campaign.created_by,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _campaign_from_orm(row)

    def get_by_id(self, campaign_id: uuid.UUID) -> Campaign | None:
        row = self._db.get(CampaignORM, campaign_id)
        return _campaign_from_orm(row) if row else None

    def get_by_id_for_update(self, campaign_id: uuid.UUID) -> Campaign | None:
        row = self._db.execute(
            select(CampaignORM).where(CampaignORM.id == campaign_id).with_for_update()
        ).scalar_one_or_none()
        return _campaign_from_orm(row) if row else None

    def get_by_code_for_update(self, code: str) -> Campaign | None:
        row = self._db.execute(
            select(CampaignORM).where(CampaignORM.code == code).with_for_update()
        ).scalar_one_or_none()
        return _campaign_from_orm(row) if row else None

    def save(self, campaign: Campaign) -> None:
        row = self._db.get(CampaignORM, campaign.id)
        if row is None:
            raise LookupError(f"Campaign {campaign.id} not found")
        row.name = campaign.name
        row.vehicle_category = (
            campaign.vehicle_category.value if campaign.vehicle_category else None
        )
        row.discount_type = campaign.discount_type.value
        row.discount_value = campaign.discount_value
        row.max_discount_amount = campaign.max_discount_amount
        row.minimum_fare = campaign.minimum_fare
        row.eligible_scope = campaign.eligible_scope.value
        row.per_customer_use_limit = campaign.per_customer_use_limit
        row.total_usage_limit = campaign.total_usage_limit
        row.ride_count_limit = campaign.ride_count_limit
        row.starts_at = campaign.starts_at
        row.ends_at = campaign.ends_at
        row.status = campaign.status.value
        self._db.flush()

    def list_campaigns(
        self, *, status: CampaignStatus | None, offset: int, limit: int
    ) -> tuple[list[Campaign], int]:
        base = select(CampaignORM)
        count_query = select(func.count()).select_from(CampaignORM)
        if status is not None:
            base = base.where(CampaignORM.status == status.value)
            count_query = count_query.where(CampaignORM.status == status.value)
        total = self._db.execute(count_query).scalar_one()
        rows = (
            self._db.execute(
                base.order_by(CampaignORM.created_at.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )
        return [_campaign_from_orm(row) for row in rows], total

    def is_customer_eligible(
        self, *, campaign_id: uuid.UUID, customer_id: uuid.UUID
    ) -> bool:
        row = self._db.execute(
            select(CampaignEligibleCustomerORM).where(
                CampaignEligibleCustomerORM.campaign_id == campaign_id,
                CampaignEligibleCustomerORM.customer_id == customer_id,
            )
        ).scalar_one_or_none()
        return row is not None

    def set_eligible_customers(
        self, *, campaign_id: uuid.UUID, customer_ids: list[uuid.UUID]
    ) -> None:
        self._db.execute(
            CampaignEligibleCustomerORM.__table__.delete().where(
                CampaignEligibleCustomerORM.campaign_id == campaign_id
            )
        )
        for customer_id in customer_ids:
            self._db.add(
                CampaignEligibleCustomerORM(
                    campaign_id=campaign_id, customer_id=customer_id
                )
            )
        self._db.flush()

    def add_eligible_customers(
        self, *, campaign_id: uuid.UUID, customer_ids: list[uuid.UUID]
    ) -> set[uuid.UUID]:
        if not customer_ids:
            return set()
        already_eligible = set(
            self._db.execute(
                select(CampaignEligibleCustomerORM.customer_id).where(
                    CampaignEligibleCustomerORM.campaign_id == campaign_id,
                    CampaignEligibleCustomerORM.customer_id.in_(customer_ids),
                )
            )
            .scalars()
            .all()
        )
        newly_added = {cid for cid in customer_ids if cid not in already_eligible}
        for customer_id in newly_added:
            self._db.add(
                CampaignEligibleCustomerORM(
                    campaign_id=campaign_id, customer_id=customer_id
                )
            )
        self._db.flush()
        return newly_added
