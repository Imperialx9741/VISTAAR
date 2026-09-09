"""vehicle management: vehicles

Phase 2 / Task 2.4 (Vehicle Management). Creates vehicle.vehicles exactly
as specified in docs/04-database/database-design.md §8.1, including its
indexes. vehicle.documents (§8.2) is not created — out of scope for this
task.

Revision ID: b37c29f328c8
Revises: 61cda9a5cc10
Create Date: 2026-08-21 12:59:15.108396

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b37c29f328c8"
down_revision: str | None = "61cda9a5cc10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS vehicle")

    op.create_table(
        "vehicles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "driver_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("driver.drivers.id"),
            nullable=False,
        ),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("registration_number", sa.String(length=30), nullable=False),
        sa.Column("make", sa.String(length=100), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column(
            "verification_status",
            sa.String(length=30),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "operational_status",
            sa.String(length=20),
            nullable=False,
            server_default="INACTIVE",
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
        sa.UniqueConstraint(
            "registration_number", name="uq_vehicles_registration_number"
        ),
        schema="vehicle",
    )
    op.create_index("idx_vehicles_driver", "vehicles", ["driver_id"], schema="vehicle")
    op.create_index(
        "idx_vehicles_category_status",
        "vehicles",
        ["category", "verification_status", "operational_status"],
        schema="vehicle",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_vehicles_category_status", table_name="vehicles", schema="vehicle"
    )
    op.drop_index("idx_vehicles_driver", table_name="vehicles", schema="vehicle")
    op.drop_table("vehicles", schema="vehicle")
    op.execute("DROP SCHEMA IF EXISTS vehicle CASCADE")
