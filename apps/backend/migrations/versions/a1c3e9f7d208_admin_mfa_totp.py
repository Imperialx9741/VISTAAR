"""admin mfa totp

Admin MFA (ADR-0051). Adds identity.mfa_credentials — a generic,
account-type-agnostic TOTP credential store (Decision 1: not admin-
specific at the schema level, even though only admin accounts enroll
today). At most one row per account (account_id is the primary key).
No seed data — enrollment is self-service, opt-in.

Revision ID: a1c3e9f7d208
Revises: f2c6a819e3b4
Create Date: 2026-08-28 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1c3e9f7d208"
down_revision: str | None = "f2c6a819e3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mfa_credentials",
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("secret", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="PENDING"
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("confirmed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["identity.accounts.id"]),
        schema="identity",
    )


def downgrade() -> None:
    op.drop_table("mfa_credentials", schema="identity")
