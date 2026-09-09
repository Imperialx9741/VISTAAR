"""early_drop_requests

Phase 08 (Early Drop, ADR-0030). Creates ride.early_drop_requests exactly
as specified in docs/04-database/database-design.md §12.1, plus one
additive column (`reason` — ADR-0030 Decision 4, the same "documented
API request field, nowhere to store it" gap ADR-0022 Decision 1 already
fixed for support.cases.ride_id).

`gps_location` reuses the same DDL-only `_GeometryPoint4326` type
836ba093820d already defined for ride.rides — duplicated here rather
than imported, matching that migration's own "stays self-contained and
reproducible independent of any future change" reasoning. No `result`/
status column exists (ADR-0030 Decision 1): GPS/location is recorded as
evidence only, never verified against a threshold.

Revision ID: 6ce26a4f7fd4
Revises: 9d0f47a4fe18
Create Date: 2026-08-25 13:43:36.041826

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6ce26a4f7fd4"
down_revision: str | None = "9d0f47a4fe18"
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
        "early_drop_requests",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "ride_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ride.rides.id"),
            nullable=False,
        ),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.String(length=100), nullable=True),
        sa.Column(
            "customer_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "driver_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("gps_location", _GeometryPoint4326(), nullable=True),
        sa.Column(
            "requested_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("confirmed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="ride",
    )
    op.create_index(
        "idx_early_drop_requests_ride",
        "early_drop_requests",
        ["ride_id"],
        schema="ride",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_early_drop_requests_ride",
        table_name="early_drop_requests",
        schema="ride",
    )
    op.drop_table("early_drop_requests", schema="ride")
