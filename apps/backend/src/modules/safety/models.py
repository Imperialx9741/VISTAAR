"""SQLAlchemy ORM models for the ``safety`` schema.

Mirrors docs/04-database/database-design.md §28.1 (safety.incidents) and
§28.2 (safety.events) exactly.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base
from shared.geometry import GeometryPoint4326

_SCHEMA = "safety"


class SafetyIncidentORM(Base):
    __tablename__ = "incidents"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ride_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ride.rides.id"), nullable=True
    )
    reporter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    incident_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="OPEN")
    location: Mapped[str | None] = mapped_column(GeometryPoint4326(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )


class SafetyEventORM(Base):
    __tablename__ = "events"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("safety.incidents.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    event_metadata: Mapped[dict[str, object] | None] = mapped_column(
        "metadata", JSONB(), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
