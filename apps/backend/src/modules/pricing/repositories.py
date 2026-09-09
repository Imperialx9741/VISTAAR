"""SQLAlchemy-backed implementations of Pricing's ports."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session as DbSession

from modules.pricing.domain.entities import (
    FareQuote,
    FareQuoteStatus,
    FareRule,
    FareRuleStatus,
    PlatformFeeRule,
)
from modules.pricing.models import FareQuoteORM, FareRuleORM, PlatformFeeRuleORM


def _fare_rule_from_orm(row: FareRuleORM) -> FareRule:
    return FareRule(
        id=row.id,
        vehicle_category=row.vehicle_category,
        base_fare=row.base_fare,
        per_km=row.per_km,
        per_minute=row.per_minute,
        waiting_per_minute=row.waiting_per_minute,
        minimum_fare=row.minimum_fare,
        status=FareRuleStatus(row.status),
        effective_from=row.effective_from,
        effective_until=row.effective_until,
        created_at=row.created_at,
    )


def _fare_quote_from_orm(row: FareQuoteORM) -> FareQuote:
    return FareQuote(
        id=row.id,
        ride_id=row.ride_id,
        version=row.version,
        base_fare=row.base_fare,
        distance_charge=row.distance_charge,
        time_charge=row.time_charge,
        waiting_charge=row.waiting_charge,
        parking_charge=row.parking_charge,
        toll_charge=row.toll_charge,
        tax_amount=row.tax_amount,
        promotion_discount=row.promotion_discount,
        additional_charge=row.additional_charge,
        total=row.total,
        reason=row.reason,
        status=FareQuoteStatus(row.status),
        created_at=row.created_at,
    )


def _live_rule_query(
    vehicle_category: str, *, now: datetime
) -> Select[tuple[FareRuleORM]]:
    # Shared by get_active_by_category()/get_active_by_category_for_
    # update() below — same WHERE clause, only the trailing
    # .with_for_update() differs.
    return (
        select(FareRuleORM)
        .where(FareRuleORM.vehicle_category == vehicle_category)
        .where(FareRuleORM.status == FareRuleStatus.PUBLISHED.value)
        .where(FareRuleORM.effective_from <= now)
        .where(
            or_(
                FareRuleORM.effective_until.is_(None),
                FareRuleORM.effective_until > now,
            )
        )
        .order_by(FareRuleORM.effective_from.desc())
    )


class SqlAlchemyFareRuleRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def get_active_by_category(
        self, vehicle_category: str, *, now: datetime
    ) -> FareRule | None:
        row = (
            self._db.execute(_live_rule_query(vehicle_category, now=now))
            .scalars()
            .first()
        )
        return _fare_rule_from_orm(row) if row else None

    def get_active_by_category_for_update(
        self, vehicle_category: str, *, now: datetime
    ) -> FareRule | None:
        row = (
            self._db.execute(
                _live_rule_query(vehicle_category, now=now).with_for_update()
            )
            .scalars()
            .first()
        )
        return _fare_rule_from_orm(row) if row else None

    def create(self, rule: FareRule) -> FareRule:
        row = FareRuleORM(
            id=rule.id,
            vehicle_category=rule.vehicle_category,
            base_fare=rule.base_fare,
            per_km=rule.per_km,
            per_minute=rule.per_minute,
            waiting_per_minute=rule.waiting_per_minute,
            minimum_fare=rule.minimum_fare,
            status=rule.status.value,
            effective_from=rule.effective_from,
            effective_until=rule.effective_until,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _fare_rule_from_orm(row)

    def get_by_id(self, rule_id: uuid.UUID) -> FareRule | None:
        row = self._db.get(FareRuleORM, rule_id)
        return _fare_rule_from_orm(row) if row else None

    def get_by_id_for_update(self, rule_id: uuid.UUID) -> FareRule | None:
        row = (
            self._db.execute(
                select(FareRuleORM).where(FareRuleORM.id == rule_id).with_for_update()
            )
            .scalars()
            .one_or_none()
        )
        return _fare_rule_from_orm(row) if row else None

    def save(self, rule: FareRule) -> None:
        row = self._db.get(FareRuleORM, rule.id)
        if row is None:
            raise LookupError(f"Fare rule {rule.id} not found")
        row.status = rule.status.value
        row.effective_from = rule.effective_from
        row.effective_until = rule.effective_until
        self._db.flush()

    def list_by_category(
        self,
        *,
        vehicle_category: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[FareRule], int]:
        filters = []
        if vehicle_category:
            filters.append(FareRuleORM.vehicle_category == vehicle_category)
        if status:
            filters.append(FareRuleORM.status == status)

        total = self._db.execute(
            select(func.count()).select_from(FareRuleORM).where(*filters)
        ).scalar_one()
        rows = (
            self._db.execute(
                select(FareRuleORM)
                .where(*filters)
                .order_by(FareRuleORM.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_fare_rule_from_orm(row) for row in rows], total


def _platform_fee_rule_from_orm(row: PlatformFeeRuleORM) -> PlatformFeeRule:
    return PlatformFeeRule(
        id=row.id,
        vehicle_category=row.vehicle_category,
        fee_amount=row.fee_amount,
        status=FareRuleStatus(row.status),
        effective_from=row.effective_from,
        effective_until=row.effective_until,
        created_by=row.created_by,
        created_at=row.created_at,
    )


def _live_platform_fee_rule_query(
    vehicle_category: str, *, now: datetime
) -> Select[tuple[PlatformFeeRuleORM]]:
    return (
        select(PlatformFeeRuleORM)
        .where(PlatformFeeRuleORM.vehicle_category == vehicle_category)
        .where(PlatformFeeRuleORM.status == FareRuleStatus.PUBLISHED.value)
        .where(PlatformFeeRuleORM.effective_from <= now)
        .where(
            or_(
                PlatformFeeRuleORM.effective_until.is_(None),
                PlatformFeeRuleORM.effective_until > now,
            )
        )
        .order_by(PlatformFeeRuleORM.effective_from.desc())
    )


class SqlAlchemyPlatformFeeRuleRepository:
    """ADR-0045 — BR-011's driver platform fee."""

    def __init__(self, db: DbSession) -> None:
        self._db = db

    def get_active_by_category(
        self, vehicle_category: str, *, now: datetime
    ) -> PlatformFeeRule | None:
        row = (
            self._db.execute(_live_platform_fee_rule_query(vehicle_category, now=now))
            .scalars()
            .first()
        )
        return _platform_fee_rule_from_orm(row) if row else None

    def get_active_by_category_for_update(
        self, vehicle_category: str, *, now: datetime
    ) -> PlatformFeeRule | None:
        row = (
            self._db.execute(
                _live_platform_fee_rule_query(
                    vehicle_category, now=now
                ).with_for_update()
            )
            .scalars()
            .first()
        )
        return _platform_fee_rule_from_orm(row) if row else None

    def create(self, rule: PlatformFeeRule) -> PlatformFeeRule:
        row = PlatformFeeRuleORM(
            id=rule.id,
            vehicle_category=rule.vehicle_category,
            fee_amount=rule.fee_amount,
            status=rule.status.value,
            effective_from=rule.effective_from,
            effective_until=rule.effective_until,
            created_by=rule.created_by,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _platform_fee_rule_from_orm(row)

    def get_by_id(self, rule_id: uuid.UUID) -> PlatformFeeRule | None:
        row = self._db.get(PlatformFeeRuleORM, rule_id)
        return _platform_fee_rule_from_orm(row) if row else None

    def get_by_id_for_update(self, rule_id: uuid.UUID) -> PlatformFeeRule | None:
        row = (
            self._db.execute(
                select(PlatformFeeRuleORM)
                .where(PlatformFeeRuleORM.id == rule_id)
                .with_for_update()
            )
            .scalars()
            .one_or_none()
        )
        return _platform_fee_rule_from_orm(row) if row else None

    def save(self, rule: PlatformFeeRule) -> None:
        row = self._db.get(PlatformFeeRuleORM, rule.id)
        if row is None:
            raise LookupError(f"Platform fee rule {rule.id} not found")
        row.status = rule.status.value
        row.effective_from = rule.effective_from
        row.effective_until = rule.effective_until
        self._db.flush()

    def list_by_category(
        self,
        *,
        vehicle_category: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[PlatformFeeRule], int]:
        filters = []
        if vehicle_category:
            filters.append(PlatformFeeRuleORM.vehicle_category == vehicle_category)
        if status:
            filters.append(PlatformFeeRuleORM.status == status)

        total = self._db.execute(
            select(func.count()).select_from(PlatformFeeRuleORM).where(*filters)
        ).scalar_one()
        rows = (
            self._db.execute(
                select(PlatformFeeRuleORM)
                .where(*filters)
                .order_by(PlatformFeeRuleORM.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_platform_fee_rule_from_orm(row) for row in rows], total


class SqlAlchemyFareQuoteRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, quote: FareQuote) -> FareQuote:
        row = FareQuoteORM(
            id=quote.id,
            ride_id=quote.ride_id,
            version=quote.version,
            base_fare=quote.base_fare,
            distance_charge=quote.distance_charge,
            time_charge=quote.time_charge,
            waiting_charge=quote.waiting_charge,
            parking_charge=quote.parking_charge,
            toll_charge=quote.toll_charge,
            tax_amount=quote.tax_amount,
            promotion_discount=quote.promotion_discount,
            additional_charge=quote.additional_charge,
            total=quote.total,
            reason=quote.reason,
            status=quote.status.value,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _fare_quote_from_orm(row)

    def get_by_id(self, fare_quote_id: uuid.UUID) -> FareQuote | None:
        row = self._db.get(FareQuoteORM, fare_quote_id)
        return _fare_quote_from_orm(row) if row else None

    def get_latest_for_ride(self, ride_id: uuid.UUID) -> FareQuote | None:
        row = (
            self._db.execute(
                select(FareQuoteORM)
                .where(FareQuoteORM.ride_id == ride_id)
                .order_by(FareQuoteORM.version.desc())
            )
            .scalars()
            .first()
        )
        return _fare_quote_from_orm(row) if row else None

    def average_total_for_ids(self, fare_quote_ids: list[uuid.UUID]) -> Decimal:
        if not fare_quote_ids:
            return Decimal("0")
        average = self._db.execute(
            select(func.avg(FareQuoteORM.total)).where(
                FareQuoteORM.id.in_(fare_quote_ids)
            )
        ).scalar_one()
        return Decimal(average) if average is not None else Decimal("0")
