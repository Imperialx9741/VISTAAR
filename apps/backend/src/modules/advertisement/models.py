"""SQLAlchemy ORM models for the ``advertisement`` schema.

Mirrors docs/04-database/database-design.md §31.1-§31.3 exactly, plus
the uq_payouts_driver_campaign addition migration 83c95d7eaf67 and
ports.py document.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base

_SCHEMA = "advertisement"


class CampaignORM(Base):
    __tablename__ = "campaigns"
    __table_args__ = ({"schema": _SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    partner_name: Mapped[str] = mapped_column(String(150), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    payout_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2), nullable=False
    )
    driver_share_percent: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2), nullable=False, default=Decimal("80")
    )
    vistaar_share_percent: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2), nullable=False, default=Decimal("20")
    )
    starts_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    ends_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class DriverCampaignORM(Base):
    __tablename__ = "driver_campaigns"
    __table_args__ = ({"schema": _SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{_SCHEMA}.campaigns.id"),
        nullable=False,
    )
    # Referenced by schema-qualified string, same rationale as
    # modules/vehicle|ride|matching|wallet/models.py — no Python import
    # dependency on modules/driver/ from this module.
    driver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("driver.drivers.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ASSIGNED")
    proof_uri: Mapped[str | None] = mapped_column(Text(), nullable=True)
    verification_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class PayoutORM(Base):
    __tablename__ = "payouts"
    __table_args__ = (
        UniqueConstraint("driver_campaign_id", name="uq_payouts_driver_campaign"),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    driver_campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{_SCHEMA}.driver_campaigns.id"),
        nullable=False,
    )
    gross_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2), nullable=False
    )
    driver_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2), nullable=False
    )
    vistaar_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
