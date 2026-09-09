"""SQLAlchemy ORM models for the ``admin`` schema.

Mirrors docs/04-database/database-design.md §33 (Admin Tables) —
`admin.permissions` (§33.3) added by ADR-0040 (BR-126/BR-127). No
additive columns beyond that (see domain/entities.py's docstring for
why security.md §46's actor_role/ip_address are deliberately not
added to admin.audit_logs).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base

_SCHEMA = "admin"


class AdminUserORM(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": _SCHEMA}

    # An admin's id IS its account id, per database-design.md §33.1's
    # documented "id UUID PRIMARY KEY REFERENCES identity.accounts(id)" —
    # same shared-primary-key pattern as driver.drivers/customer.customers.
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.accounts.id"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class PermissionORM(Base):
    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint(
            "admin_id", "module", name="uq_admin_permissions_admin_module"
        ),
        Index("idx_admin_permissions_admin", "admin_id"),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    admin_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin.users.id"), nullable=False
    )
    module: Mapped[str] = mapped_column(String(40), nullable=False)
    access_level: Mapped[str] = mapped_column(String(10), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AuditLogORM(Base):
    __tablename__ = "audit_logs"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    admin_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin.users.id"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    before_state: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    after_state: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(180), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class SettingORM(Base):
    """ADR-0048. A flat key-value store for promotion defaults/
    operational thresholds/feature flags/general settings only —
    fare/platform-fee/referral/notification settings have their own
    dedicated, versioned tables and are never duplicated here."""

    __tablename__ = "settings"
    __table_args__ = {"schema": _SCHEMA}

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[object] = mapped_column(JSONB, nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin.users.id"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
