"""SQLAlchemy ORM models for the ``pricing`` schema.

Mirrors docs/04-database/database-design.md §15.1 (pricing.fare_rules,
plus the additive minimum_fare column — ADR-0020 Decision 4 — and the
`status` column replacing `active` — ADR-0042) and §15.2
(pricing.fare_quotes) exactly.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base

_SCHEMA = "pricing"


class FareRuleORM(Base):
    __tablename__ = "fare_rules"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    vehicle_category: Mapped[str] = mapped_column(String(20), nullable=False)
    base_fare: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    per_km: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    per_minute: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    waiting_per_minute: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    minimum_fare: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    effective_from: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    effective_until: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class PlatformFeeRuleORM(Base):
    """ADR-0045 — BR-011's driver platform fee, versioned/effective-
    dated. Unlike FareRuleORM above, has a `created_by` FK — this table
    didn't exist before ADR-0042's audit-trail convention was already
    established, so it follows the newer pattern (matching
    referral.driver_bonus_rules/customer_reward_rules, ADR-0043) rather
    than fare_rules' own precedent."""

    __tablename__ = "platform_fee_rules"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    vehicle_category: Mapped[str] = mapped_column(String(20), nullable=False)
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    effective_from: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    effective_until: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin.users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class FareQuoteORM(Base):
    __tablename__ = "fare_quotes"
    __table_args__ = (
        Index("uq_fare_quote_version", "ride_id", "version", unique=True),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ride_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ride.rides.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False)
    base_fare: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    distance_charge: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    time_charge: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    waiting_charge: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    parking_charge: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    toll_charge: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    promotion_discount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    additional_charge: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
