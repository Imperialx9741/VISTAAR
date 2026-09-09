"""SQLAlchemy ORM models for the ``ride`` schema.

Mirrors docs/04-database/database-design.md §9.1 (ride.rides) and §9.2
(ride.state_history) exactly — see ADR-0010 Decision 7 for why
database-design.md, not technical-architecture.md §11, is authoritative.

The four geometry columns use shared.geometry.GeometryPoint4326: the
Python-side value is a WKT string (e.g. "POINT(85.1376 25.5941)",
longitude first per the WKT/PostGIS convention), automatically wrapped
in ST_GeomFromText(...) on write and unwrapped via ST_AsText(...) on
read — see that module's docstring. modules/ride/repositories.py
converts to/from plain latitude/longitude floats at this boundary.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base
from shared.geometry import GeometryPoint4326

_SCHEMA = "ride"


class RideORM(Base):
    __tablename__ = "rides"
    __table_args__ = (
        Index("idx_rides_pickup_geo", "original_pickup", postgresql_using="gist"),
        Index(
            "idx_rides_destination_geo",
            "original_destination",
            postgresql_using="gist",
        ),
        # ADR-0057 — the scheduled-ride Beat task's own "find due rides"
        # poll (modules/ride/tasks.py); partial so this index stays
        # tiny (only ever a handful of SCHEDULED rides at once).
        Index(
            "idx_rides_lock_in_at",
            "lock_in_at",
            postgresql_where=text("status = 'SCHEDULED'"),
        ),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Referenced by schema-qualified string, same rationale as
    # modules/customer|driver|vehicle/models.py — no Python import
    # dependency on modules/customer|driver|vehicle/ from this module.
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer.customers.id"), nullable=False
    )
    driver_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("driver.drivers.id"), nullable=True
    )
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicle.vehicles.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    # Added Phase 3 / Task 3.2 (ADR-0011 Decision 1) — absent when this
    # table was first created in Task 3.1 (ADR-0010 §8 Addendum).
    requested_vehicle_category: Mapped[str] = mapped_column(String(20), nullable=False)
    # ADR-0020 Decision 1 — CAB-only sub-tier, additive.
    requested_cab_tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    original_pickup: Mapped[str] = mapped_column(GeometryPoint4326(), nullable=False)
    current_pickup: Mapped[str] = mapped_column(GeometryPoint4326(), nullable=False)
    original_destination: Mapped[str] = mapped_column(
        GeometryPoint4326(), nullable=False
    )
    current_destination: Mapped[str] = mapped_column(
        GeometryPoint4326(), nullable=False
    )
    # Bare nullable UUID, no foreign key — database-design.md §9.1 exactly.
    # Task 3.1 never sets this (ADR-0010 Decision 1: no fare quote is
    # calculated or created).
    active_fare_quote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    # ADR-0057 (2026-08-31) — Schedule a Ride / Book for Someone Else,
    # all four additive/nullable. NULL for every ride created before
    # this ADR and for every ordinary immediate/self-booked ride since.
    scheduled_for: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    lock_in_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    linked_contact_name: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    linked_contact_phone: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    requested_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    arrived_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
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


class RideOtpORM(Base):
    """Mirrors database-design.md §13.1 exactly (ride.ride_otps)."""

    __tablename__ = "ride_otps"
    __table_args__ = (
        Index("idx_ride_otps_ride_created", "ride_id", "created_at"),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ride_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ride.rides.id"), nullable=False
    )
    otp_hash: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class GpsVerificationORM(Base):
    """Mirrors database-design.md §14.1 exactly (ride.gps_verifications)."""

    __tablename__ = "gps_verifications"
    __table_args__ = (
        Index("idx_gps_verifications_ride_type", "ride_id", "verification_type"),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ride_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ride.rides.id"), nullable=False
    )
    verification_type: Mapped[str] = mapped_column(String(30), nullable=False)
    latitude: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=7), nullable=False
    )
    longitude: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=7), nullable=False
    )
    reference_latitude: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=7), nullable=True
    )
    reference_longitude: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=7), nullable=True
    )
    distance_meters: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=12, scale=3), nullable=True
    )
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class EarlyDropRequestORM(Base):
    """Mirrors database-design.md §12.1 exactly (ride.early_drop_requests),
    plus the additive `reason` column (ADR-0030 Decision 4). No
    `result`/status column exists — ADR-0030 Decision 1: GPS/location is
    recorded as evidence only, never verified against a threshold."""

    __tablename__ = "early_drop_requests"
    __table_args__ = (
        Index("idx_early_drop_requests_ride", "ride_id"),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ride_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ride.rides.id"), nullable=False
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    customer_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    driver_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    gps_location: Mapped[str | None] = mapped_column(GeometryPoint4326(), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )


class ChangeRequestORM(Base):
    """Mirrors database-design.md §11.1 exactly (ride.change_requests,
    ADR-0033) — one table shared by both Pickup Change and (a future)
    Destination Change, discriminated by `request_type`."""

    __tablename__ = "change_requests"
    __table_args__ = (
        Index("idx_change_requests_ride", "ride_id"),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ride_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ride.rides.id"), nullable=False
    )
    request_type: Mapped[str] = mapped_column(String(30), nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    old_location: Mapped[str | None] = mapped_column(GeometryPoint4326(), nullable=True)
    new_location: Mapped[str | None] = mapped_column(GeometryPoint4326(), nullable=True)
    old_fare_quote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pricing.fare_quotes.id"), nullable=True
    )
    new_fare_quote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pricing.fare_quotes.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="PENDING"
    )
    driver_decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    customer_decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )


class GpsDisputeORM(Base):
    """Mirrors database-design.md §14.2 exactly (ride.gps_disputes)."""

    __tablename__ = "gps_disputes"
    __table_args__ = (
        Index("idx_gps_disputes_ride", "ride_id"),
        Index("idx_gps_disputes_status", "status"),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ride_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ride.rides.id"), nullable=False
    )
    gps_verification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ride.gps_verifications.id"), nullable=False
    )
    verification_type: Mapped[str] = mapped_column(String(30), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    evidence_deadline: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    decided_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )


class GpsDisputeEvidenceORM(Base):
    """Mirrors database-design.md §14.3 exactly (ride.gps_dispute_evidence)."""

    __tablename__ = "gps_dispute_evidence"
    __table_args__ = (
        Index("idx_gps_dispute_evidence_dispute", "dispute_id"),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dispute_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ride.gps_disputes.id"), nullable=False
    )
    submitted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(20), nullable=False)
    uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class RideStateHistoryORM(Base):
    __tablename__ = "state_history"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ride_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ride.rides.id"), nullable=False
    )
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    actor_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
