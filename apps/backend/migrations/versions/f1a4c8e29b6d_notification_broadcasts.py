"""notification broadcasts

Compose/Send Broadcast + Audience Selection (ADR-0055, Tier C). Adds
notification.broadcasts — one row per admin-composed broadcast, each
one backed by a broadcast-only notification.templates row (event_key
NULL, ADR-0044's own schema comment anticipated this) created and
published by the same request that inserts this row, so a broadcast's
actual per-recipient sends go through NotificationService.send()'s
existing template-driven path unchanged. `audience_user_ids` (JSONB,
nullable) only holds a value when audience_type='SELECTED' — every
other audience type is resolved fresh, server-side, at the moment of
actual dispatch (never snapshotted here). `status` starts SCHEDULED
even for an immediate (scheduled_at IS NULL) broadcast — the same
request that inserts it dispatches and flips it to SENT before
returning, so a truly SCHEDULED row appearing to a later request only
ever means a future-dated broadcast still awaiting its scheduled_at.

Revision ID: f1a4c8e29b6d
Revises: c7b2f5e91a3d
Create Date: 2026-08-29 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f1a4c8e29b6d"
down_revision: str | None = "c7b2f5e91a3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "broadcasts",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("template_key", sa.String(length=50), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("audience_type", sa.String(length=30), nullable=False),
        sa.Column("audience_user_ids", postgresql.JSONB(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="SCHEDULED"
        ),
        sa.Column("scheduled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("sent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("sent_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["admin.users.id"]),
        schema="notification",
    )
    op.create_index(
        "idx_notification_broadcasts_status_scheduled",
        "broadcasts",
        ["status", "scheduled_at"],
        schema="notification",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_notification_broadcasts_status_scheduled",
        table_name="broadcasts",
        schema="notification",
    )
    op.drop_table("broadcasts", schema="notification")
