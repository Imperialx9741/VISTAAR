"""notification foundation: preferences and deliveries

Notification Domain Foundation (ADR-0034). Creates notification.
preferences and notification.deliveries exactly as specified in docs/
04-database/database-design.md §32.1/§32.2 — no more.

notification.preferences.user_id has no foreign key (matches database-
design.md §32.1 exactly) — deliberately generic across both
customer.customers and driver.drivers, the same "no single users table"
reasoning penalty.penalties.user_id already established (migration
383b55c70732).

uq_notification_deliveries_dedup (user_id, channel, template_key,
event_id) is an addition beyond database-design.md's literal column
list — a concurrency-safety backstop for "Unique delivery key should
prevent duplicate notification processing" (§32.2's own prose
requirement), the same UNIQUE-constraint-as-idempotency-guard pattern
wallet.transactions.idempotency_key and penalty.penalties' own unique
constraint already established. event_id is nullable (not every
delivery is triggered by a documented domain event), so the constraint
only actually dedupes rows where all four columns are non-NULL —
Postgres treats NULL as distinct in unique constraints, matching the
column's own nullable-by-design shape.

Revision ID: b8e4f27a5c93
Revises: a3f6c9e12b47
Create Date: 2026-08-25 17:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8e4f27a5c93"
down_revision: str | None = "a3f6c9e12b47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS notification")

    op.create_table(
        "preferences",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "push_enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "sms_enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "whatsapp_enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="notification",
    )

    op.create_table(
        "deliveries",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("template_key", sa.String(length=100), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("provider_reference", sa.String(length=180), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("delivered_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "user_id",
            "channel",
            "template_key",
            "event_id",
            name="uq_notification_deliveries_dedup",
        ),
        schema="notification",
    )
    op.create_index(
        "idx_notification_deliveries_user",
        "deliveries",
        ["user_id"],
        schema="notification",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_notification_deliveries_user",
        table_name="deliveries",
        schema="notification",
    )
    op.drop_table("deliveries", schema="notification")
    op.drop_table("preferences", schema="notification")
    op.execute("DROP SCHEMA IF EXISTS notification CASCADE")
