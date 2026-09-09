"""SQLAlchemy ORM models for the ``referral`` schema.

Mirrors docs/04-database/database-design.md §25.1-§25.3 exactly, plus
the uq_referrals_referred_id addition migration ddc5e2ce287d,
§25.4/§25.5 (Referral Reward Configuration, ADR-0043), and ports.py
document.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base

_SCHEMA = "referral"


class ReferralCodeORM(Base):
    __tablename__ = "codes"
    __table_args__ = (
        UniqueConstraint("code", name="uq_referral_codes_code"),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_type: Mapped[str] = mapped_column(String(20), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class ReferralORM(Base):
    __tablename__ = "referrals"
    __table_args__ = (
        UniqueConstraint("referred_id", name="uq_referrals_referred_id"),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    referral_code_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{_SCHEMA}.codes.id"), nullable=False
    )
    referrer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    referred_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    referred_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ATTACHED")
    activated_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class RewardORM(Base):
    __tablename__ = "rewards"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_referral_rewards_idempotency_key"),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    referral_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{_SCHEMA}.referrals.id"), nullable=False
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reward_type: Mapped[str] = mapped_column(String(40), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=12, scale=2), nullable=True
    )
    promotion_uses: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class DriverBonusRuleORM(Base):
    __tablename__ = "driver_bonus_rules"
    __table_args__ = ({"schema": _SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    referred_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2), nullable=False
    )
    referrer_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2), nullable=False
    )
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


class CustomerRewardRuleORM(Base):
    __tablename__ = "customer_reward_rules"
    __table_args__ = ({"schema": _SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    reward_type: Mapped[str] = mapped_column(String(30), nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2), nullable=False
    )
    total_uses: Mapped[int] = mapped_column(Integer, nullable=False)
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
