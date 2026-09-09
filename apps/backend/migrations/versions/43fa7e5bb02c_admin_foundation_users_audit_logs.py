"""admin foundation users audit logs

Phase 2 / Task 2.7A (Admin Foundation & Driver/Vehicle Approval). Creates
the `admin` schema and its two tables exactly as specified in
docs/04-database/database-design.md §33 (Admin Tables) — admin.users,
admin.audit_logs. No additive columns (see
docs/14-decisions/ADR-0009-admin-approval-scope-and-open-items.md
conflict 2 for why security.md §46's actor_role/ip_address are
deliberately not added).

Revision ID: 43fa7e5bb02c
Revises: c4b8f13e7226
Create Date: 2026-08-21 16:29:38.092619

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "43fa7e5bb02c"
down_revision: str | None = "c4b8f13e7226"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS admin")

    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.accounts.id"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="ACTIVE"
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="admin",
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "admin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin.users.id"),
            nullable=False,
        ),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=True),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("before_state", postgresql.JSONB(), nullable=True),
        sa.Column("after_state", postgresql.JSONB(), nullable=True),
        sa.Column("request_id", sa.String(length=180), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="admin",
    )


def downgrade() -> None:
    op.drop_table("audit_logs", schema="admin")
    op.drop_table("users", schema="admin")
    op.execute("DROP SCHEMA IF EXISTS admin CASCADE")
