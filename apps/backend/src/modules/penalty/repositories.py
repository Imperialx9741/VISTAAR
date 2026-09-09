"""SQLAlchemy-backed implementations of Penalty's ports."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from modules.penalty.domain.entities import Penalty, PenaltyStatus, PenaltyType, Strike
from modules.penalty.models import PenaltyORM, StrikeORM


def _penalty_from_orm(row: PenaltyORM) -> Penalty:
    return Penalty(
        id=row.id,
        user_id=row.user_id,
        ride_id=row.ride_id,
        penalty_type=PenaltyType(row.penalty_type),
        amount=row.amount,
        status=PenaltyStatus(row.status),
        issued_at=row.issued_at,
        settled_at=row.settled_at,
        settlement_ride_id=row.settlement_ride_id,
    )


def _strike_from_orm(row: StrikeORM) -> Strike:
    return Strike(
        id=row.id,
        driver_id=row.driver_id,
        ride_id=row.ride_id,
        reason=row.reason,
        created_at=row.created_at,
    )


class SqlAlchemyPenaltyRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def count_by_user_and_type(
        self, user_id: uuid.UUID, *, penalty_type: PenaltyType
    ) -> int:
        return self._db.execute(
            select(func.count())
            .select_from(PenaltyORM)
            .where(PenaltyORM.user_id == user_id)
            .where(PenaltyORM.penalty_type == penalty_type.value)
        ).scalar_one()

    def create(self, penalty: Penalty) -> Penalty:
        row = PenaltyORM(
            id=penalty.id,
            user_id=penalty.user_id,
            ride_id=penalty.ride_id,
            penalty_type=penalty.penalty_type.value,
            amount=penalty.amount,
            status=penalty.status.value,
            issued_at=penalty.issued_at,
            settled_at=penalty.settled_at,
            settlement_ride_id=penalty.settlement_ride_id,
        )
        self._db.add(row)
        try:
            self._db.flush()
        except IntegrityError:
            # uq_penalties_ride_penalty_type — a concurrent cancel
            # attempt on the same ride already recorded this exact
            # penalty. Not an error: return the existing row (same
            # idempotent-on-conflict shape
            # modules.wallet.repositories.SqlAlchemyWalletRepository.
            # get_or_create_for_update uses).
            self._db.rollback()
            existing = self._db.execute(
                select(PenaltyORM)
                .where(PenaltyORM.ride_id == penalty.ride_id)
                .where(PenaltyORM.penalty_type == penalty.penalty_type.value)
            ).scalar_one_or_none()
            if existing is None:
                raise
            return _penalty_from_orm(existing)

        self._db.refresh(row)
        return _penalty_from_orm(row)

    def get_by_id_for_update(self, penalty_id: uuid.UUID) -> Penalty | None:
        row = self._db.execute(
            select(PenaltyORM).where(PenaltyORM.id == penalty_id).with_for_update()
        ).scalar_one_or_none()
        return _penalty_from_orm(row) if row else None

    def list_outstanding_unattached_for_user_for_update(
        self, user_id: uuid.UUID
    ) -> list[Penalty]:
        """Customer Outstanding Penalty Settlement (owner decision,
        2026-09-03) — every OUTSTANDING penalty this user has that
        isn't already carried forward to some other ride, row-locked so
        two concurrent Create Ride requests for the same customer (a
        real, if rare, possibility — ADR-0010 Decision 5 places no limit
        on simultaneous SEARCHING rides) can't both attach the same
        penalty to two different rides."""
        rows = (
            self._db.execute(
                select(PenaltyORM)
                .where(PenaltyORM.user_id == user_id)
                .where(PenaltyORM.status == PenaltyStatus.OUTSTANDING.value)
                .where(PenaltyORM.settlement_ride_id.is_(None))
                .with_for_update()
            )
            .scalars()
            .all()
        )
        return [_penalty_from_orm(row) for row in rows]

    def list_by_settlement_ride_id_for_update(
        self, ride_id: uuid.UUID
    ) -> list[Penalty]:
        """Every OUTSTANDING penalty currently attached to this specific
        ride (attach_outstanding_penalties_to_ride() at that ride's own
        booking) — used both to release the attachment if the ride is
        cancelled before completion, and to settle it if the ride
        completes. Row-locked for the same reason as the unattached
        query above."""
        rows = (
            self._db.execute(
                select(PenaltyORM)
                .where(PenaltyORM.settlement_ride_id == ride_id)
                .where(PenaltyORM.status == PenaltyStatus.OUTSTANDING.value)
                .with_for_update()
            )
            .scalars()
            .all()
        )
        return [_penalty_from_orm(row) for row in rows]

    def save(self, penalty: Penalty) -> None:
        row = self._db.get(PenaltyORM, penalty.id)
        if row is None:
            raise LookupError(f"Penalty {penalty.id} not found")
        row.status = penalty.status.value
        row.settled_at = penalty.settled_at
        row.settlement_ride_id = penalty.settlement_ride_id
        self._db.flush()

    def search(
        self,
        *,
        status: str | None,
        user_id: uuid.UUID | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Penalty], int]:
        stmt = select(PenaltyORM)
        count_stmt = select(func.count()).select_from(PenaltyORM)
        if status is not None:
            stmt = stmt.where(PenaltyORM.status == status)
            count_stmt = count_stmt.where(PenaltyORM.status == status)
        if user_id is not None:
            stmt = stmt.where(PenaltyORM.user_id == user_id)
            count_stmt = count_stmt.where(PenaltyORM.user_id == user_id)

        total = self._db.execute(count_stmt).scalar_one()
        rows = (
            self._db.execute(
                stmt.order_by(PenaltyORM.issued_at.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )
        return [_penalty_from_orm(row) for row in rows], total

    def count_by_status(self) -> dict[str, int]:
        rows = self._db.execute(
            select(PenaltyORM.status, func.count()).group_by(PenaltyORM.status)
        ).all()
        return {key: value for key, value in rows}  # noqa: C416

    def count_by_type(self) -> dict[str, int]:
        rows = self._db.execute(
            select(PenaltyORM.penalty_type, func.count()).group_by(
                PenaltyORM.penalty_type
            )
        ).all()
        return {key: value for key, value in rows}  # noqa: C416

    def sum_amount_outstanding(self) -> Decimal:
        total = self._db.execute(
            select(func.coalesce(func.sum(PenaltyORM.amount), 0)).where(
                PenaltyORM.status == PenaltyStatus.OUTSTANDING.value
            )
        ).scalar_one()
        return Decimal(total)

    def sum_amount_outstanding_for_user(self, user_id: uuid.UUID) -> Decimal:
        total = self._db.execute(
            select(func.coalesce(func.sum(PenaltyORM.amount), 0))
            .where(PenaltyORM.status == PenaltyStatus.OUTSTANDING.value)
            .where(PenaltyORM.user_id == user_id)
        ).scalar_one()
        return Decimal(total)

    def sum_amount_settled_in_range(
        self, *, since: datetime, until: datetime
    ) -> Decimal:
        total = self._db.execute(
            select(func.coalesce(func.sum(PenaltyORM.amount), 0))
            .where(PenaltyORM.settled_at.is_not(None))
            .where(PenaltyORM.settled_at >= since)
            .where(PenaltyORM.settled_at < until)
        ).scalar_one()
        return Decimal(total)


class SqlAlchemyStrikeRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, strike: Strike) -> Strike:
        row = StrikeORM(
            id=strike.id,
            driver_id=strike.driver_id,
            ride_id=strike.ride_id,
            reason=strike.reason,
            created_at=strike.created_at,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _strike_from_orm(row)

    def list_for_driver(
        self, driver_id: uuid.UUID, *, offset: int, limit: int
    ) -> tuple[list[Strike], int]:
        total = self._db.execute(
            select(func.count())
            .select_from(StrikeORM)
            .where(StrikeORM.driver_id == driver_id)
        ).scalar_one()
        rows = (
            self._db.execute(
                select(StrikeORM)
                .where(StrikeORM.driver_id == driver_id)
                .order_by(StrikeORM.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_strike_from_orm(row) for row in rows], total
