"""SQLAlchemy ORM models for the ``notification`` schema.

Mirrors docs/04-database/database-design.md §32.1 (notification.
preferences) and §32.2 (notification.deliveries) exactly, plus the
uq_notification_deliveries_dedup addition migration b8e4f27a5c93
documents (a concurrency-safety backstop, not a documented-schema
column).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base

_SCHEMA = "notification"


class PreferencesORM(Base):
    __tablename__ = "preferences"
    __table_args__ = ({"schema": _SCHEMA},)

    # No foreign key — deliberately generic across customer.customers
    # and driver.drivers (database-design.md §32.1 has none either),
    # matching penalty.penalties.user_id's own established reasoning.
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    push_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sms_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    whatsapp_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class DeviceTokenORM(Base):
    """ADR-0052 — Push Notifications device registration."""

    __tablename__ = "device_tokens"
    __table_args__ = (
        UniqueConstraint("token", name="uq_notification_device_tokens_token"),
        Index("idx_notification_device_tokens_user", "user_id"),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # No foreign key — same generic-across-account-types reasoning
    # PreferencesORM.user_id above already established.
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    platform: Mapped[str] = mapped_column(String(10), nullable=False)
    token: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class DeliveryORM(Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "channel",
            "template_key",
            "event_id",
            name="uq_notification_deliveries_dedup",
        ),
        Index("idx_notification_deliveries_user", "user_id"),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    template_key: Mapped[str] = mapped_column(String(100), nullable=False)
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(180), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    template_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{_SCHEMA}.templates.id"),
        nullable=True,
    )
    # ADR-0075, migration b7353a942bf3.
    retry_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0"
    )


class TemplateORM(Base):
    """ADR-0044. An append-only version chain per (template_key,
    channel) — see uq_notification_templates_one_published (migration
    d3a978951b6f), a partial unique index the ORM's __table_args__
    below can't express directly, so it's declared only in the
    migration, matching this codebase's established treatment of every
    other partial/functional index."""

    __tablename__ = "templates"
    __table_args__ = ({"schema": _SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    template_key: Mapped[str] = mapped_column(String(50), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    event_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin.users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class BroadcastORM(Base):
    """ADR-0055 — Compose/Send Broadcast + Audience Selection.
    `template_key` references a `templates` row this same create flow
    auto-publishes (a broadcast-only template, `event_key=NULL`) — no
    FK, since a template row is never deleted and the reference is
    purely informational (the broadcast's own subject/body columns
    below are what the Admin Web actually displays, so a broadcast's
    history stays readable even if that template were ever edited or
    archived later)."""

    __tablename__ = "broadcasts"
    __table_args__ = (
        Index("idx_notification_broadcasts_status_scheduled", "status", "scheduled_at"),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    template_key: Mapped[str] = mapped_column(String(50), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    audience_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # Only populated when audience_type='SELECTED' — a JSON array of
    # UUID strings, not a join table: this list is fixed at compose
    # time and never queried/filtered on, so a normalized table would
    # buy nothing (same reasoning admin.settings.value's own bare JSONB
    # scalar/object, ADR-0048 §4, already established for this
    # codebase).
    audience_user_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="SCHEDULED")
    scheduled_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    sent_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin.users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
