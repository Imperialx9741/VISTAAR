"""matching ride offers and ride vehicle category

Phase 3 / Task 3.2 (Driver Matching). Two independent changes, bundled
in one migration since both are needed together for Task 3.2 to work
at all:

1. ride.rides gains requested_vehicle_category (ADR-0011 Decision 1,
   database-design.md §9.1) — added NOT NULL directly (no temporary
   server_default/backfill dance needed: ride.rides has zero rows in
   both the dev and test databases as of this migration).
2. matching.ride_offers, created exactly as specified in
   database-design.md §10.1.

Revision ID: 5c30e0859933
Revises: 836ba093820d
Create Date: 2026-08-22 12:10:44.201558

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5c30e0859933"
down_revision: str | None = "836ba093820d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rides",
        sa.Column("requested_vehicle_category", sa.String(length=20), nullable=False),
        schema="ride",
    )

    op.execute("CREATE SCHEMA IF NOT EXISTS matching")

    op.create_table(
        "ride_offers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "ride_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ride.rides.id"),
            nullable=False,
        ),
        sa.Column(
            "driver_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("driver.drivers.id"),
            nullable=False,
        ),
        sa.Column(
            "vehicle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vehicle.vehicles.id"),
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="PENDING"
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("responded_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="matching",
    )
    op.create_index(
        "idx_offers_driver_status",
        "ride_offers",
        ["driver_id", "status"],
        schema="matching",
    )
    op.create_index(
        "idx_offers_ride_status",
        "ride_offers",
        ["ride_id", "status"],
        schema="matching",
    )
    op.create_index(
        "idx_offers_expiry",
        "ride_offers",
        ["expires_at"],
        schema="matching",
        postgresql_where=sa.text("status = 'PENDING'"),
    )


def downgrade() -> None:
    op.drop_index("idx_offers_expiry", table_name="ride_offers", schema="matching")
    op.drop_index("idx_offers_ride_status", table_name="ride_offers", schema="matching")
    op.drop_index(
        "idx_offers_driver_status", table_name="ride_offers", schema="matching"
    )
    op.drop_table("ride_offers", schema="matching")
    op.execute("DROP SCHEMA IF EXISTS matching CASCADE")
    op.drop_column("rides", "requested_vehicle_category", schema="ride")
