"""SQLAlchemy ORM models for the ``penalty`` schema.

Mirrors docs/04-database/database-design.md §26.1 (penalty.penalties)
and §26.2 (penalty.strikes) exactly, plus the
uq_penalties_ride_penalty_type addition migration 383b55c70732 and this
module's ports.py document (a concurrency-safety backstop, not a
documented-schema column).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base

_SCHEMA = "penalty"


class PenaltyORM(Base):
    __tablename__ = "penalties"
    __table_args__ = (
        UniqueConstraint(
            "ride_id", "penalty_type", name="uq_penalties_ride_penalty_type"
        ),
        # Narrowed 2026-09-04 (BR-049 correction, ADR-0069): was
        # (user_id, expires_at) — expires_at no longer exists (customer
        # penalties never expire). Still supports the real query pattern
        # this index exists for: "does this user have any OUTSTANDING
        # penalty" (PenaltyRepository.sum_amount_outstanding_for_user(),
        # list_outstanding_unattached_for_user_for_update()).
        Index(
            "idx_open_penalties",
            "user_id",
            postgresql_where=text("status = 'OUTSTANDING'"),
        ),
        Index(
            "ix_penalties_settlement_ride_id",
            "settlement_ride_id",
            postgresql_where=text("settlement_ride_id IS NOT NULL"),
        ),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # No foreign key — deliberately generic across customer.customers
    # and driver.drivers (database-design.md §26.1 has none either).
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ride_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ride.rides.id"), nullable=True
    )
    penalty_type: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="OUTSTANDING"
    )
    issued_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    settled_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    # Customer Outstanding Penalty Settlement (owner decision,
    # 2026-09-03) — the ride whose completion settles this penalty,
    # distinct from ride_id above (the ride the penalty was originally
    # incurred on). See migrations/versions/
    # a7c3f9e51d4b_customer_penalty_settlement_via_driver_.py and
    # modules/penalty/domain/entities.py's attach/release/settle state
    # machine.
    settlement_ride_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ride.rides.id"), nullable=True
    )


class StrikeORM(Base):
    __tablename__ = "strikes"
    __table_args__ = ({"schema": _SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    driver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("driver.drivers.id"), nullable=False
    )
    ride_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ride.rides.id"), nullable=True
    )
    reason: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
