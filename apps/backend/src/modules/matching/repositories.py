"""Infrastructure implementations of Matching's ports.

SqlAlchemyOfferRepository (Postgres) and RedisNearbyDriverIndex (Redis,
via shared/geo.py) both live here — one module, two backing stores, same
grouping shared/idempotency.py and shared/geo.py's own callers already
use elsewhere.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

import shared.geo as geo
from modules.matching.domain.entities import Offer, OfferStatus
from modules.matching.models import RideOfferORM


def _offer_from_orm(row: RideOfferORM) -> Offer:
    return Offer(
        id=row.id,
        ride_id=row.ride_id,
        driver_id=row.driver_id,
        vehicle_id=row.vehicle_id,
        status=OfferStatus(row.status),
        expires_at=row.expires_at,
        responded_at=row.responded_at,
        created_at=row.created_at,
    )


class SqlAlchemyOfferRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, offer: Offer) -> Offer:
        row = RideOfferORM(
            id=offer.id,
            ride_id=offer.ride_id,
            driver_id=offer.driver_id,
            vehicle_id=offer.vehicle_id,
            status=offer.status.value,
            expires_at=offer.expires_at,
            responded_at=offer.responded_at,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _offer_from_orm(row)

    def get_by_id(self, offer_id: uuid.UUID) -> Offer | None:
        row = self._db.get(RideOfferORM, offer_id)
        return _offer_from_orm(row) if row else None

    def list_pending_for_driver(self, driver_id: uuid.UUID) -> list[Offer]:
        rows = (
            self._db.execute(
                select(RideOfferORM)
                .where(RideOfferORM.driver_id == driver_id)
                .where(RideOfferORM.status == OfferStatus.PENDING.value)
                .order_by(RideOfferORM.created_at)
            )
            .scalars()
            .all()
        )
        return [_offer_from_orm(row) for row in rows]

    def driver_ids_already_offered_for_ride(self, ride_id: uuid.UUID) -> set[uuid.UUID]:
        rows = (
            self._db.execute(
                select(RideOfferORM.driver_id).where(RideOfferORM.ride_id == ride_id)
            )
            .scalars()
            .all()
        )
        return set(rows)

    def list_pending_for_ride(self, ride_id: uuid.UUID) -> list[Offer]:
        rows = (
            self._db.execute(
                select(RideOfferORM)
                .where(RideOfferORM.ride_id == ride_id)
                .where(RideOfferORM.status == OfferStatus.PENDING.value)
                .order_by(RideOfferORM.created_at)
            )
            .scalars()
            .all()
        )
        return [_offer_from_orm(row) for row in rows]

    def save(self, offer: Offer) -> None:
        row = self._db.get(RideOfferORM, offer.id)
        if row is None:
            raise LookupError(f"Offer {offer.id} not found")

        row.status = offer.status.value
        row.responded_at = offer.responded_at
        self._db.flush()

    def count_by_status_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        rows = self._db.execute(
            select(RideOfferORM.status, func.count())
            .where(RideOfferORM.created_at >= since)
            .where(RideOfferORM.created_at < until)
            .group_by(RideOfferORM.status)
        ).all()
        return {key: value for key, value in rows}  # noqa: C416

    def average_time_to_accept_seconds_in_range(
        self, *, since: datetime, until: datetime
    ) -> Decimal:
        seconds = func.extract(
            "epoch", RideOfferORM.responded_at - RideOfferORM.created_at
        )
        average = self._db.execute(
            select(func.coalesce(func.avg(seconds), 0))
            .where(RideOfferORM.status == OfferStatus.ACCEPTED.value)
            .where(RideOfferORM.created_at >= since)
            .where(RideOfferORM.created_at < until)
        ).scalar_one()
        return Decimal(average)

    def search(
        self,
        *,
        status: str | None,
        ride_id: uuid.UUID | None,
        driver_id: uuid.UUID | None,
        since: datetime | None,
        until: datetime | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Offer], int]:
        # Admin Web §4.6 (ADR-0054) — allow-listed filters only, same
        # "no client-supplied field name" discipline
        # modules/ride/repositories.py's own search() already documents.
        stmt = select(RideOfferORM)
        count_stmt = select(func.count()).select_from(RideOfferORM)
        if status is not None:
            stmt = stmt.where(RideOfferORM.status == status)
            count_stmt = count_stmt.where(RideOfferORM.status == status)
        if ride_id is not None:
            stmt = stmt.where(RideOfferORM.ride_id == ride_id)
            count_stmt = count_stmt.where(RideOfferORM.ride_id == ride_id)
        if driver_id is not None:
            stmt = stmt.where(RideOfferORM.driver_id == driver_id)
            count_stmt = count_stmt.where(RideOfferORM.driver_id == driver_id)
        if since is not None:
            stmt = stmt.where(RideOfferORM.created_at >= since)
            count_stmt = count_stmt.where(RideOfferORM.created_at >= since)
        if until is not None:
            stmt = stmt.where(RideOfferORM.created_at < until)
            count_stmt = count_stmt.where(RideOfferORM.created_at < until)

        total = self._db.execute(count_stmt).scalar_one()
        rows = (
            self._db.execute(
                stmt.order_by(RideOfferORM.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_offer_from_orm(row) for row in rows], total


class RedisNearbyDriverIndex:
    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client

    async def nearest_driver_ids(
        self,
        *,
        category: str,
        latitude: float,
        longitude: float,
        radius_km: float,
        limit: int,
    ) -> list[uuid.UUID]:
        return await geo.nearest_driver_ids(
            self._redis,
            category=category,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            limit=limit,
        )
