"""SQLAlchemy ORM models for the ``support`` schema.

Mirrors docs/04-database/database-design.md §30.1 (support.cases, plus
the additive ride_id column — ADR-0022 Decision 1) and §30.2
(support.messages) exactly.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base

_SCHEMA = "support"


class SupportCaseORM(Base):
    __tablename__ = "cases"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # No FK — polymorphic across customer.customers/driver.drivers, same
    # precedent as penalty.penalties.user_id (ADR-0015).
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Additive beyond database-design.md §30.1 — see ADR-0022 Decision 1.
    ride_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ride.rides.id"), nullable=True
    )
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="NORMAL")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="OPEN")
    assigned_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SupportMessageORM(Base):
    __tablename__ = "messages"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("support.cases.id"), nullable=False
    )
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False)
    sender_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
