"""ride domain: rides, state_history

Phase 3 / Task 3.1 (Ride Booking — Create Ride Request). Creates
ride.rides and ride.state_history exactly as specified in
docs/04-database/database-design.md §9.1/§9.2. database-design.md is the
authoritative ride schema (ADR-0010 Decision 7) —
docs/03-architecture/technical-architecture.md §11's earlier flat-table
draft is superseded and not implemented here.

Enables the `postgis` extension first (ADR-0010 Decision 4): the
`original_pickup`/`current_pickup`/`original_destination`/
`current_destination` columns are `geometry(Point,4326)`, which requires
it. `docker-compose.dev.yml`'s Postgres image was switched to
`postgis/postgis:16-3.4` alongside this migration.

The geometry column type is defined locally (`_GeometryPoint4326`,
DDL-only — `get_col_spec` describes the column type for CREATE TABLE and
nothing else) rather than imported from `shared.geometry`, so this
migration stays self-contained and reproducible independent of any
future change to that application-side type. `modules/ride/models.py`
uses the equivalent full type (with bind/result expressions for reading
and writing WKT through the ORM) — see that module's docstring.

`active_fare_quote_id` is a bare nullable UUID with no foreign key, per
database-design.md §9.1 exactly — no `pricing.*` tables are required for
this migration (ADR-0010 Decision 1: fare quotes aren't created by
Task 3.1 at all).

Revision ID: 836ba093820d
Revises: bcc64f18ebad
Create Date: 2026-08-22 11:24:07.512933

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "836ba093820d"
down_revision: str | None = "bcc64f18ebad"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class _GeometryPoint4326(sa.types.UserDefinedType):
    """DDL-only description of a PostGIS `geometry(Point,4326)` column —
    used solely so op.create_table() can declare the column type. Does
    not implement bind/result processing (that lives in the equivalent
    type in modules/ride/models.py, used by the ORM at runtime)."""

    cache_ok = True

    def get_col_spec(self, **kw: object) -> str:
        return "geometry(Point,4326)"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE SCHEMA IF NOT EXISTS ride")

    op.create_table(
        "rides",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customer.customers.id"),
            nullable=False,
        ),
        sa.Column(
            "driver_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("driver.drivers.id"),
            nullable=True,
        ),
        sa.Column(
            "vehicle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vehicle.vehicles.id"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("original_pickup", _GeometryPoint4326(), nullable=False),
        sa.Column("current_pickup", _GeometryPoint4326(), nullable=False),
        sa.Column("original_destination", _GeometryPoint4326(), nullable=False),
        sa.Column("current_destination", _GeometryPoint4326(), nullable=False),
        sa.Column("active_fare_quote_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "requested_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("accepted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("arrived_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("closed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
        schema="ride",
    )
    op.create_index(
        "idx_rides_pickup_geo",
        "rides",
        ["original_pickup"],
        schema="ride",
        postgresql_using="gist",
    )
    op.create_index(
        "idx_rides_destination_geo",
        "rides",
        ["original_destination"],
        schema="ride",
        postgresql_using="gist",
    )

    op.create_table(
        "state_history",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "ride_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ride.rides.id"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(length=30), nullable=True),
        sa.Column("to_status", sa.String(length=30), nullable=False),
        sa.Column("reason", sa.String(length=100), nullable=True),
        sa.Column("actor_type", sa.String(length=30), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="ride",
    )


def downgrade() -> None:
    op.drop_table("state_history", schema="ride")
    op.drop_index("idx_rides_destination_geo", table_name="rides", schema="ride")
    op.drop_index("idx_rides_pickup_geo", table_name="rides", schema="ride")
    op.drop_table("rides", schema="ride")
    op.execute("DROP SCHEMA IF EXISTS ride CASCADE")
