"""SQLAlchemy-backed implementation of WalletRepository."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from modules.wallet.domain.entities import (
    TransactionDirection,
    TransactionType,
    Wallet,
    WalletTransaction,
)
from modules.wallet.domain.errors import WalletTransactionFailedError
from modules.wallet.models import WalletORM, WalletTransactionORM


def _wallet_from_orm(row: WalletORM) -> Wallet:
    return Wallet(
        driver_id=row.driver_id,
        balance=row.balance,
        version=row.version,
        updated_at=row.updated_at,
        low_balance_grace_ride_used=row.low_balance_grace_ride_used,
        outstanding_debt=row.outstanding_debt,
    )


def _transaction_from_orm(row: WalletTransactionORM) -> WalletTransaction:
    return WalletTransaction(
        id=row.id,
        driver_id=row.driver_id,
        ride_id=row.ride_id,
        transaction_type=TransactionType(row.transaction_type),
        amount=row.amount,
        direction=TransactionDirection(row.direction),
        balance_before=row.balance_before,
        balance_after=row.balance_after,
        idempotency_key=row.idempotency_key,
        reference_type=row.reference_type,
        reference_id=row.reference_id,
        metadata=row.transaction_metadata,
        created_at=row.created_at,
    )


class SqlAlchemyWalletRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def get_or_create_for_update(
        self, driver_id: uuid.UUID, *, now: datetime
    ) -> Wallet:
        row = self._locked_row(driver_id)
        if row is not None:
            return _wallet_from_orm(row)

        new_row = WalletORM(driver_id=driver_id, balance=Decimal("0"), version=1)
        self._db.add(new_row)
        try:
            self._db.flush()
        except IntegrityError:
            # Lost a race to create this driver's wallet row — a
            # concurrent transaction's insert won. Re-fetch under lock;
            # it now exists (or the FK genuinely doesn't — re-raise).
            self._db.rollback()
            row = self._locked_row(driver_id)
            if row is None:
                raise
            return _wallet_from_orm(row)

        self._db.refresh(new_row)
        return _wallet_from_orm(new_row)

    def _locked_row(self, driver_id: uuid.UUID) -> WalletORM | None:
        return self._db.execute(
            select(WalletORM).where(WalletORM.driver_id == driver_id).with_for_update()
        ).scalar_one_or_none()

    def get_transaction_by_idempotency_key(
        self, idempotency_key: str
    ) -> WalletTransaction | None:
        row = self._db.execute(
            select(WalletTransactionORM).where(
                WalletTransactionORM.idempotency_key == idempotency_key
            )
        ).scalar_one_or_none()
        return _transaction_from_orm(row) if row else None

    def get_debit_for_ride(
        self, ride_id: uuid.UUID, *, transaction_type: str
    ) -> WalletTransaction | None:
        row = (
            self._db.execute(
                select(WalletTransactionORM)
                .where(WalletTransactionORM.ride_id == ride_id)
                .where(WalletTransactionORM.transaction_type == transaction_type)
                .where(
                    WalletTransactionORM.direction == TransactionDirection.DEBIT.value
                )
                .order_by(WalletTransactionORM.created_at)
            )
            .scalars()
            .first()
        )
        return _transaction_from_orm(row) if row else None

    def apply_debit(self, *, wallet: Wallet, transaction: WalletTransaction) -> None:
        row = self._db.get(WalletORM, wallet.driver_id)
        if row is None:
            raise LookupError(f"Wallet {wallet.driver_id} not found")

        row.balance = wallet.balance
        row.version = wallet.version
        row.low_balance_grace_ride_used = wallet.low_balance_grace_ride_used
        row.outstanding_debt = wallet.outstanding_debt

        tx_row = WalletTransactionORM(
            id=transaction.id,
            driver_id=transaction.driver_id,
            ride_id=transaction.ride_id,
            transaction_type=transaction.transaction_type.value,
            amount=transaction.amount,
            direction=transaction.direction.value,
            balance_before=transaction.balance_before,
            balance_after=transaction.balance_after,
            idempotency_key=transaction.idempotency_key,
            reference_type=transaction.reference_type,
            reference_id=transaction.reference_id,
            transaction_metadata=transaction.metadata,
        )
        self._db.add(tx_row)

        try:
            self._db.flush()
        except IntegrityError as exc:
            # Defensive backstop only — WalletService.debit() already
            # checks get_transaction_by_idempotency_key() both before
            # and after acquiring the wallet row lock, so a genuine
            # duplicate should never reach here. The wallet_balance_
            # nonnegative CHECK constraint (database-design.md §17.1) is
            # the same kind of unconditional backstop the balance
            # validation above it already enforces. Either way, a clean
            # domain error is preferable to a raw IntegrityError
            # reaching the client.
            self._db.rollback()
            raise WalletTransactionFailedError(
                "Could not complete this wallet transaction due to a "
                "concurrent update or constraint violation. Please retry."
            ) from exc

        self._db.refresh(row)
        wallet.updated_at = row.updated_at

    def update_low_balance_grace(self, wallet: Wallet) -> None:
        """Sarthi Wallet Low-Balance Rule (ADR-0058) — persists
        `wallet.low_balance_grace_ride_used`/`.version` after
        WalletService.enforce_low_balance_policy() marks the grace ride
        as used. Not a financial transaction (no ledger row, no
        idempotency key needed): the caller already holds this row's
        lock via get_or_create_for_update(), and the HTTP-level
        Idempotency-Key on accept-offer itself is what prevents a
        retried request from consuming the grace twice."""
        row = self._db.get(WalletORM, wallet.driver_id)
        if row is None:
            raise LookupError(f"Wallet {wallet.driver_id} not found")
        row.low_balance_grace_ride_used = wallet.low_balance_grace_ride_used
        row.version = wallet.version
        self._db.flush()
        self._db.refresh(row)
        wallet.updated_at = row.updated_at

    def list_transactions(
        self,
        driver_id: uuid.UUID,
        *,
        transaction_type: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[WalletTransaction], int]:
        stmt = select(WalletTransactionORM).where(
            WalletTransactionORM.driver_id == driver_id
        )
        count_stmt = (
            select(func.count())
            .select_from(WalletTransactionORM)
            .where(WalletTransactionORM.driver_id == driver_id)
        )
        if transaction_type is not None:
            stmt = stmt.where(WalletTransactionORM.transaction_type == transaction_type)
            count_stmt = count_stmt.where(
                WalletTransactionORM.transaction_type == transaction_type
            )

        total = self._db.execute(count_stmt).scalar_one()
        rows = (
            self._db.execute(
                stmt.order_by(WalletTransactionORM.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_transaction_from_orm(row) for row in rows], total

    def sum_debits_since(self, *, transaction_type: str, since: datetime) -> Decimal:
        total = self._db.execute(
            select(func.coalesce(func.sum(WalletTransactionORM.amount), 0))
            .where(WalletTransactionORM.transaction_type == transaction_type)
            .where(WalletTransactionORM.direction == "DEBIT")
            .where(WalletTransactionORM.created_at >= since)
        ).scalar_one()
        return Decimal(total)

    def sum_by_type_and_direction_in_range(
        self,
        *,
        transaction_type: str,
        direction: str,
        since: datetime,
        until: datetime,
    ) -> Decimal:
        total = self._db.execute(
            select(func.coalesce(func.sum(WalletTransactionORM.amount), 0))
            .where(WalletTransactionORM.transaction_type == transaction_type)
            .where(WalletTransactionORM.direction == direction)
            .where(WalletTransactionORM.created_at >= since)
            .where(WalletTransactionORM.created_at < until)
        ).scalar_one()
        return Decimal(total)

    def count_by_transaction_type_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        rows = self._db.execute(
            select(WalletTransactionORM.transaction_type, func.count())
            .where(WalletTransactionORM.created_at >= since)
            .where(WalletTransactionORM.created_at < until)
            .group_by(WalletTransactionORM.transaction_type)
        ).all()
        return {key: value for key, value in rows}  # noqa: C416

    def apply_credit(self, *, wallet: Wallet, transaction: WalletTransaction) -> None:
        row = self._db.get(WalletORM, wallet.driver_id)
        if row is None:
            raise LookupError(f"Wallet {wallet.driver_id} not found")

        row.balance = wallet.balance
        row.version = wallet.version
        row.low_balance_grace_ride_used = wallet.low_balance_grace_ride_used
        row.outstanding_debt = wallet.outstanding_debt

        tx_row = WalletTransactionORM(
            id=transaction.id,
            driver_id=transaction.driver_id,
            ride_id=transaction.ride_id,
            transaction_type=transaction.transaction_type.value,
            amount=transaction.amount,
            direction=transaction.direction.value,
            balance_before=transaction.balance_before,
            balance_after=transaction.balance_after,
            idempotency_key=transaction.idempotency_key,
            reference_type=transaction.reference_type,
            reference_id=transaction.reference_id,
            transaction_metadata=transaction.metadata,
        )
        self._db.add(tx_row)

        try:
            self._db.flush()
        except IntegrityError as exc:
            # Same defensive backstop as apply_debit() — WalletService.
            # credit() already checks get_transaction_by_idempotency_key()
            # both before and after acquiring the wallet row lock.
            self._db.rollback()
            raise WalletTransactionFailedError(
                "Could not complete this wallet transaction due to a "
                "concurrent update or constraint violation. Please retry."
            ) from exc

        self._db.refresh(row)
        wallet.updated_at = row.updated_at
