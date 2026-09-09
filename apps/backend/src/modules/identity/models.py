"""SQLAlchemy ORM models for the ``identity`` schema.

Mirrors docs/04-database/database-design.md §5 (identity.accounts,
identity.otp_challenges) exactly for those two tables, plus one addition —
identity.sessions — needed for refresh-token/session tracking that
database-design.md did not yet define. See database-design.md's own update
in this change for the corresponding documentation addition; this file
does not invent a schema database-design.md contradicts.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base

_SCHEMA = "identity"


class AccountORM(Base):
    __tablename__ = "accounts"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_type: Mapped[str] = mapped_column(String(20), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
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


class OtpChallengeORM(Base):
    __tablename__ = "otp_challenges"
    __table_args__ = (
        Index("idx_otp_phone_status", "phone", "status"),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{_SCHEMA}.accounts.id"), nullable=True
    )
    account_type: Mapped[str] = mapped_column(String(20), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    otp_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class MfaCredentialORM(Base):
    """ADR-0051 (2026-08-28) — not present in database-design.md's
    original identity schema, same "additive, own migration" treatment
    SessionORM already got. account_id is the primary key, not a
    separate id column — at most one credential per account."""

    __tablename__ = "mfa_credentials"
    __table_args__ = {"schema": _SCHEMA}

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{_SCHEMA}.accounts.id"), primary_key=True
    )
    secret: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )


class SessionORM(Base):
    """Not present in database-design.md's original identity schema —
    added by this change. See the task report for the corresponding
    database-design.md update."""

    __tablename__ = "sessions"
    __table_args__ = (
        Index("idx_sessions_account", "account_id"),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{_SCHEMA}.accounts.id"), nullable=False
    )
    refresh_token_hash: Mapped[str] = mapped_column(
        String(180), unique=True, nullable=False
    )
    device_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
