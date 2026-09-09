"""driver profile: drivers

Phase 2 / Task 2.3 (Driver Profile Foundation). Creates driver.drivers
exactly as specified in docs/04-database/database-design.md §7.1.
driver.documents (§7.2) is not created — out of scope for this task.

Revision ID: 61cda9a5cc10
Revises: dfbd003a14a5
Create Date: 2026-08-21 12:40:53.397319

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "61cda9a5cc10"
down_revision: str | None = "dfbd003a14a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS driver")

    op.create_table(
        "drivers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.accounts.id"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("profile_photo_uri", sa.Text(), nullable=True),
        sa.Column(
            "verification_status",
            sa.String(length=30),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "operational_status",
            sa.String(length=30),
            nullable=False,
            server_default="OFFLINE",
        ),
        sa.Column(
            "strikes",
            sa.Integer(),
            nullable=False,
            server_default="0",
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
        schema="driver",
    )


def downgrade() -> None:
    op.drop_table("drivers", schema="driver")
    op.execute("DROP SCHEMA IF EXISTS driver CASCADE")
