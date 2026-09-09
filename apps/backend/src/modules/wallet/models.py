"""SQLAlchemy ORM models for the ``wallet`` schema.

Mirrors docs/04-database/database-design.md §17.1 (wallet.wallets) and
§17.2 (wallet.transactions) exactly.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base

_SCHEMA = "wallet"


class WalletORM(Base):
    __tablename__ = "wallets"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="wallet_balance_nonnegative"),
        CheckConstraint(
            "outstanding_debt >= 0", name="wallet_outstanding_debt_nonnegative"
        ),
        {"schema": _SCHEMA},
    )

    # Referenced by schema-qualified string, same rationale as
    # modules/vehicle|ride|matching/models.py — no Python import
    # dependency on modules/driver/ from this module.
    driver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("driver.drivers.id"), primary_key=True
    )
    balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2), nullable=False, default=Decimal("0")
    )
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    # Sarthi Wallet Low-Balance Rule (ADR-0058, 2026-09-02, owner
    # decision) — see modules.wallet.domain.entities.LOW_BALANCE_THRESHOLD
    # and WalletService.enforce_low_balance_policy() for the rule itself.
    low_balance_grace_ride_used: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False
    )
    # Sarthi Unpaid Cancellation-Penalty Recovery (ADR-0062, 2026-09-03,
    # owner decision) — see modules.wallet.domain.entities.Wallet.
    # outstanding_debt's own doc comment.
    outstanding_debt: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2), nullable=False, default=Decimal("0")
    )


class WalletTransactionORM(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("idx_wallet_transactions_driver", "driver_id"),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    driver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("driver.drivers.id"), nullable=False
    )
    ride_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ride.rides.id"), nullable=True
    )
    transaction_type: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2), nullable=False
    )
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    balance_before: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2), nullable=False
    )
    balance_after: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(180), unique=True, nullable=False
    )
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    transaction_metadata: Mapped[dict[str, object] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
