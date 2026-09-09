"""SQLAlchemy ORM models for the ``vehicle`` schema.

Mirrors docs/04-database/database-design.md §8.1 (vehicle.vehicles) and
§8.2 (vehicle.documents, added Phase 2 / Task 2.5) exactly — including
vehicle.documents having no updated_at column and no documented indexes,
an asymmetry vs. driver.documents that is preserved deliberately (see
modules/vehicle/domain/entities.py::VehicleDocument).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base

_SCHEMA = "vehicle"


class VehicleORM(Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        Index("idx_vehicles_driver", "driver_id"),
        Index(
            "idx_vehicles_category_status",
            "category",
            "verification_status",
            "operational_status",
        ),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Referenced by schema-qualified string, same rationale as
    # modules/customer|driver/models.py — no Python import dependency on
    # modules/driver/ from this module.
    driver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("driver.drivers.id"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    # ADR-0020 Decision 1 — CAB-only sub-tier, additive beyond
    # database-design.md §8.1's original column list.
    cab_tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    registration_number: Mapped[str] = mapped_column(
        String(30), unique=True, nullable=False
    )
    make: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PENDING"
    )
    operational_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="INACTIVE"
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


class VehicleDocumentORM(Base):
    __tablename__ = "documents"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicle.vehicles.id"), nullable=False
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
    # No updated_at — database-design.md §8.2 does not document one for
    # vehicle.documents (unlike driver.documents). Not added here.
