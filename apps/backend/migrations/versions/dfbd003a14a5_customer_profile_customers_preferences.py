"""customer profile: customers, preferences

Phase 2 / Task 2.2 (Customer Profile). Creates customer.customers and
customer.preferences exactly as specified in
docs/04-database/database-design.md §6 — no additive columns this time
(unlike the identity migration).

Revision ID: dfbd003a14a5
Revises: 7c8c77e5c16c
Create Date: 2026-08-21 12:30:15.091959

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dfbd003a14a5"
down_revision: str | None = "7c8c77e5c16c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS customer")

    op.create_table(
        "customers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.accounts.id"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("full_name", sa.String(length=150), nullable=True),
        sa.Column("profile_photo_uri", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="customer",
    )

    op.create_table(
        "preferences",
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customer.customers.id"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "language",
            sa.String(length=10),
            nullable=False,
            server_default="en",
        ),
        sa.Column(
            "notification_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="customer",
    )


def downgrade() -> None:
    op.drop_table("preferences", schema="customer")
    op.drop_table("customers", schema="customer")
    op.execute("DROP SCHEMA IF EXISTS customer CASCADE")
