"""identity foundation: accounts, otp_challenges, sessions

This is VISTAAR's first migration. It creates only the tables genuinely
required for Phase 2 / Task 2.1 (Identity & Authentication Foundation):

- identity.accounts        (docs/04-database/database-design.md §5.1)
- identity.otp_challenges  (docs/04-database/database-design.md §5.2)
- identity.sessions        (new — refresh-token/session tracking; not in
                             database-design.md's original identity
                             schema, added by this change alongside the
                             corresponding documentation update)

No driver/vehicle/ride/wallet/payment/notification tables are created
here — those belong to later tasks, per this task's explicit scope.

Revision ID: 7c8c77e5c16c
Revises: None
Create Date: 2026-08-21 11:42:56.999267

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c8c77e5c16c"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # database-design.md §4 ("Shared Types"): pgcrypto for gen_random_uuid()
    # default values used at the SQL level; server_default here is applied
    # via SQLAlchemy defaults instead (see models.py), but the extension is
    # still declared for parity with database-design.md and for any future
    # migration that does rely on gen_random_uuid() server-side.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # database-design.md §3: "Use logical schemas to separate domains."
    op.execute("CREATE SCHEMA IF NOT EXISTS identity")

    op.create_table(
        "accounts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("account_type", sa.String(length=20), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
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
        sa.UniqueConstraint("phone", name="uq_accounts_phone"),
        schema="identity",
    )

    op.create_table(
        "otp_challenges",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.accounts.id"),
            nullable=True,
        ),
        # Not in database-design.md's original identity.otp_challenges —
        # see modules/identity/domain/entities.py's OtpChallenge docstring
        # for why this column exists.
        sa.Column("account_type", sa.String(length=20), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("otp_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="identity",
    )
    op.create_index(
        "idx_otp_phone_status",
        "otp_challenges",
        ["phone", "status"],
        schema="identity",
    )

    op.create_table(
        "sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.accounts.id"),
            nullable=False,
        ),
        sa.Column("refresh_token_hash", sa.String(length=180), nullable=False),
        sa.Column("device_metadata", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "refresh_token_hash", name="uq_sessions_refresh_token_hash"
        ),
        schema="identity",
    )
    op.create_index(
        "idx_sessions_account", "sessions", ["account_id"], schema="identity"
    )


def downgrade() -> None:
    op.drop_index("idx_sessions_account", table_name="sessions", schema="identity")
    op.drop_table("sessions", schema="identity")
    op.drop_index(
        "idx_otp_phone_status", table_name="otp_challenges", schema="identity"
    )
    op.drop_table("otp_challenges", schema="identity")
    op.drop_table("accounts", schema="identity")
    op.execute("DROP SCHEMA IF EXISTS identity CASCADE")
