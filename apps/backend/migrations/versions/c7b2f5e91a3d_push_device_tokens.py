"""push device tokens

Push Notifications device registration (ADR-0052). Adds
notification.device_tokens — one row per registered FCM token,
account-type-agnostic (user_id is a bare UUID, no foreign key, same
reasoning notification.preferences/deliveries.user_id already use). No
seed data.

Revision ID: c7b2f5e91a3d
Revises: a1c3e9f7d208
Create Date: 2026-08-28 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c7b2f5e91a3d"
down_revision: str | None = "a1c3e9f7d208"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "device_tokens",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", sa.String(length=10), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("token", name="uq_notification_device_tokens_token"),
        schema="notification",
    )
    op.create_index(
        "idx_notification_device_tokens_user",
        "device_tokens",
        ["user_id"],
        schema="notification",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_notification_device_tokens_user",
        table_name="device_tokens",
        schema="notification",
    )
    op.drop_table("device_tokens", schema="notification")
