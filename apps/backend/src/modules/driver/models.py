"""SQLAlchemy ORM models for the ``driver`` schema.

Mirrors docs/04-database/database-design.md §7.1 (driver.drivers) and
§7.2 (driver.documents, added Phase 2 / Task 2.5) exactly.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base

_SCHEMA = "driver"


class DriverORM(Base):
    __tablename__ = "drivers"
    __table_args__ = {"schema": _SCHEMA}

    # A driver's id IS its account id, per database-design.md §7.1's
    # documented "id UUID PRIMARY KEY REFERENCES identity.accounts(id)".
    # Referenced by schema-qualified string, same rationale as
    # modules/customer/models.py::CustomerORM.id — no Python import
    # dependency on modules/identity/ from this module.
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.accounts.id"), primary_key=True
    )
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    profile_photo_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PENDING"
    )
    operational_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="OFFLINE"
    )
    strikes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class DriverDocumentORM(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("idx_driver_documents_expiry", "expires_at"),
        Index("idx_driver_documents_driver", "driver_id"),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    driver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("driver.drivers.id"), nullable=False
    )
    document_type: Mapped[str] = mapped_column(String(40), nullable=False)
    document_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    evidence_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PENDING"
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
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
