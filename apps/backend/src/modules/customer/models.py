"""SQLAlchemy ORM models for the ``customer`` schema.

Mirrors docs/04-database/database-design.md §6 exactly — no additive
columns this time (unlike modules/identity/models.py's otp_challenges).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base

_SCHEMA = "customer"


class CustomerORM(Base):
    __tablename__ = "customers"
    __table_args__ = {"schema": _SCHEMA}

    # A customer's id IS its account id, per database-design.md §6.1's
    # documented "id UUID PRIMARY KEY REFERENCES identity.accounts(id)".
    # Referenced by schema-qualified string rather than importing
    # modules.identity.models.AccountORM directly, so this module still
    # has no Python import dependency on modules/identity/ (see this
    # module's __init__.py) — SQLAlchemy resolves the FK at
    # mapper-configuration time via the shared core.database.Base
    # metadata, once both modules' models have been imported by main.py.
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.accounts.id"), primary_key=True
    )
    full_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    profile_photo_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CustomerPreferencesORM(Base):
    __tablename__ = "preferences"
    __table_args__ = {"schema": _SCHEMA}

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{_SCHEMA}.customers.id"),
        primary_key=True,
    )
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    notification_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
