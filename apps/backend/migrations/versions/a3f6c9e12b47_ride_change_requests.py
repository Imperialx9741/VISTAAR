"""ride_change_requests

Ride Modifications (ADR-0033). Creates ride.change_requests exactly as
specified in docs/04-database/database-design.md §11.1 — a unified table
for both Pickup Change and Destination Change, discriminated by
`request_type` (PICKUP_CHANGE/DESTINATION_CHANGE), rather than two
separate tables. This ADR only implements the PICKUP_CHANGE side; the
schema is shared so a future DESTINATION_CHANGE task can reuse it
without a new migration.

`old_location`/`new_location` reuse the same DDL-only
`_GeometryPoint4326` type 836ba093820d/6ce26a4f7fd4/691121cccb6a already
defined — duplicated here rather than imported, matching those
migrations' own "stays self-contained and reproducible independent of
any future change" reasoning. `old_fare_quote_id`/`new_fare_quote_id`
are both nullable per the documented schema — `old_fare_quote_id` is the
ride's active_fare_quote_id captured at request time (useful for
audit), `new_fare_quote_id` is set only once a driver's PROCEED decision
computes a revised quote (ADR-0033 Decision 6).

Revision ID: a3f6c9e12b47
Revises: 691121cccb6a
Create Date: 2026-08-25 15:12:04.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f6c9e12b47"
down_revision: str | None = "691121cccb6a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class _GeometryPoint4326(sa.types.UserDefinedType):
    """DDL-only description of a PostGIS `geometry(Point,4326)` column —
    see 836ba093820d for the full rationale."""

    cache_ok = True

    def get_col_spec(self, **kw: object) -> str:
        return "geometry(Point,4326)"


def upgrade() -> None:
    op.create_table(
        "change_requests",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "ride_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ride.rides.id"),
            nullable=False,
        ),
        sa.Column("request_type", sa.String(length=30), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("old_location", _GeometryPoint4326(), nullable=True),
        sa.Column("new_location", _GeometryPoint4326(), nullable=True),
        sa.Column(
            "old_fare_quote_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pricing.fare_quotes.id"),
            nullable=True,
        ),
        sa.Column(
            "new_fare_quote_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pricing.fare_quotes.id"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("driver_decision", sa.String(length=30), nullable=True),
        sa.Column("customer_decision", sa.String(length=30), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="ride",
    )
    op.create_index(
        "idx_change_requests_ride",
        "change_requests",
        ["ride_id"],
        schema="ride",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_change_requests_ride",
        table_name="change_requests",
        schema="ride",
    )
    op.drop_table("change_requests", schema="ride")
