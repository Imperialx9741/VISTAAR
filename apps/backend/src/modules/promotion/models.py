"""SQLAlchemy ORM models for the ``promotion`` schema.

Mirrors docs/04-database/database-design.md §24.1-§24.3 (entitlements/
usage/reservations) and §24.4/§24.5 (campaigns/campaign_eligible_
customers, added ADR-0041) exactly.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base

_SCHEMA = "promotion"


class EntitlementORM(Base):
    __tablename__ = "entitlements"
    __table_args__ = ({"schema": _SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer.customers.id"), nullable=False
    )
    promotion_type: Mapped[str] = mapped_column(String(50), nullable=False)
    total_uses: Mapped[int] = mapped_column(nullable=False)
    remaining_uses: Mapped[int] = mapped_column(nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2), nullable=False
    )
    max_discount_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=12, scale=2), nullable=True
    )
    activated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    # ADR-0041: additive, nullable — NULL for welcome/referral grants,
    # set only on an entitlement created by RedeemCampaignCode.
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{_SCHEMA}.campaigns.id"), nullable=True
    )


class UsageORM(Base):
    __tablename__ = "usage"
    __table_args__ = (
        Index("uq_promotion_ride_use", "entitlement_id", "ride_id", unique=True),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entitlement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{_SCHEMA}.entitlements.id"),
        nullable=False,
    )
    ride_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ride.rides.id"), nullable=False
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class ReservationORM(Base):
    __tablename__ = "reservations"
    __table_args__ = ({"schema": _SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entitlement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{_SCHEMA}.entitlements.id"),
        nullable=False,
    )
    ride_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ride.rides.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="RESERVED")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class CampaignORM(Base):
    __tablename__ = "campaigns"
    __table_args__ = ({"schema": _SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str | None] = mapped_column(String(30), nullable=True, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    vehicle_category: Mapped[str | None] = mapped_column(String(20), nullable=True)
    discount_type: Mapped[str] = mapped_column(String(10), nullable=False)
    discount_value: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2), nullable=False
    )
    max_discount_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=12, scale=2), nullable=True
    )
    minimum_fare: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=12, scale=2), nullable=True
    )
    eligible_scope: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ALL"
    )
    per_customer_use_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    total_usage_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ride_count_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    starts_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    ends_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin.users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class CampaignEligibleCustomerORM(Base):
    __tablename__ = "campaign_eligible_customers"
    __table_args__ = ({"schema": _SCHEMA},)

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{_SCHEMA}.campaigns.id"),
        primary_key=True,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customer.customers.id"),
        primary_key=True,
    )
