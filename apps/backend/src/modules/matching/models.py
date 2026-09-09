"""SQLAlchemy ORM model for the ``matching`` schema.

Mirrors docs/04-database/database-design.md §10.1 (matching.ride_offers)
exactly.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base

_SCHEMA = "matching"


class RideOfferORM(Base):
    __tablename__ = "ride_offers"
    __table_args__ = (
        Index("idx_offers_driver_status", "driver_id", "status"),
        Index("idx_offers_ride_status", "ride_id", "status"),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Referenced by schema-qualified string, same rationale as
    # modules/ride|vehicle|driver/models.py — no Python import
    # dependency on modules/ride|driver|vehicle/ from this module.
    ride_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ride.rides.id"), nullable=False
    )
    driver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("driver.drivers.id"), nullable=False
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicle.vehicles.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    responded_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
