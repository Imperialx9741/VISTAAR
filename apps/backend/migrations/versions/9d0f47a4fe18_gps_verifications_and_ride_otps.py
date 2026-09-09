"""ride domain: gps_verifications, ride_otps

Phase 06/07 (GPS Verification Foundation, ADR-0028, 2026-08-26). Creates
ride.gps_verifications and ride.ride_otps exactly as specified in
docs/04-database/database-design.md §14.1/§13.1. Both tables already had
a full column list documented there before this task — nothing invented.

ride.rides.arrived_at/started_at/completed_at/closed_at already exist
(migration 836ba093820d, unused until now) — no change needed to that
table.

Revision ID: 9d0f47a4fe18
Revises: 92cb1722db09
Create Date: 2026-08-25 10:59:46.680786

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9d0f47a4fe18"
down_revision: str | None = "92cb1722db09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ride_otps",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "ride_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ride.rides.id"),
            nullable=False,
        ),
        sa.Column("otp_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="ACTIVE"
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="ride",
    )
    # database-design.md §13.1: "Only the latest valid OTP can start the
    # ride" — an index on (ride_id, created_at) makes "find the current
    # OTP for this ride" a real index scan, not a sequential one, on the
    # one column combination every read of this table actually filters by.
    op.create_index(
        "idx_ride_otps_ride_created",
        "ride_otps",
        ["ride_id", "created_at"],
        schema="ride",
    )

    op.create_table(
        "gps_verifications",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "ride_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ride.rides.id"),
            nullable=False,
        ),
        sa.Column("verification_type", sa.String(length=30), nullable=False),
        sa.Column("latitude", sa.Numeric(precision=10, scale=7), nullable=False),
        sa.Column("longitude", sa.Numeric(precision=10, scale=7), nullable=False),
        sa.Column(
            "reference_latitude", sa.Numeric(precision=10, scale=7), nullable=True
        ),
        sa.Column(
            "reference_longitude", sa.Numeric(precision=10, scale=7), nullable=True
        ),
        sa.Column("distance_meters", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="ride",
    )
    # Every read of this table this task makes is "count/list attempts for
    # this ride + verification_type" (retry-limit checks, the audit trail
    # a future Dispute-as-Support review would query, ADR-0028 Decision 3).
    op.create_index(
        "idx_gps_verifications_ride_type",
        "gps_verifications",
        ["ride_id", "verification_type"],
        schema="ride",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_gps_verifications_ride_type",
        table_name="gps_verifications",
        schema="ride",
    )
    op.drop_table("gps_verifications", schema="ride")
    op.drop_index("idx_ride_otps_ride_created", table_name="ride_otps", schema="ride")
    op.drop_table("ride_otps", schema="ride")
