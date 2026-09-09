"""safety and support foundation

Phase 14 — Safety & Support, scoped per ADR-0022 (Minimal Foundation
Scope). Creates safety.incidents/events and support.cases/messages
exactly as specified in docs/04-database/database-design.md §28-30,
plus one additive column (support.cases.ride_id — see the ADR).

Revision ID: 92cb1722db09
Revises: 61a5a80a044e
Create Date: 2026-08-24 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "92cb1722db09"
down_revision: str | None = "61a5a80a044e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class _GeometryPoint4326(sa.types.UserDefinedType):
    """DDL-only description of a PostGIS `geometry(Point,4326)` column —
    used solely so op.create_table() can declare the column type. Same
    pattern migrations/versions/836ba093820d_ride_domain_rides_state_history.py
    already established; the equivalent type used by the ORM at runtime
    lives in shared/geometry.py."""

    cache_ok = True

    def get_col_spec(self, **kw: object) -> str:
        return "geometry(Point,4326)"


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS safety")
    op.execute("CREATE SCHEMA IF NOT EXISTS support")

    op.create_table(
        "incidents",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "ride_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ride.rides.id"),
            nullable=True,
        ),
        # No FK — polymorphic across customer.customers/driver.drivers
        # (BR-112: "Both customers and drivers"), same precedent as
        # penalty.penalties.user_id (ADR-0015).
        sa.Column("reporter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_type", sa.String(length=50), nullable=False),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="OPEN"
        ),
        sa.Column("location", _GeometryPoint4326(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="safety",
    )

    op.create_table(
        "events",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("safety.incidents.id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="safety",
    )

    op.create_table(
        "cases",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        # No FK — polymorphic across customer.customers/driver.drivers,
        # same reasoning as safety.incidents.reporter_id above.
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Additive beyond database-design.md §30.1 — see ADR-0022
        # Decision 1: api-contracts.md §44's documented request body
        # includes ride_id, with no column to store it otherwise.
        sa.Column(
            "ride_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ride.rides.id"),
            nullable=True,
        ),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column(
            "priority", sa.String(length=20), nullable=False, server_default="NORMAL"
        ),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="OPEN"
        ),
        sa.Column("assigned_admin_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        schema="support",
    )

    op.create_table(
        "messages",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("support.cases.id"),
            nullable=False,
        ),
        sa.Column("sender_type", sa.String(length=20), nullable=False),
        sa.Column("sender_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="support",
    )


def downgrade() -> None:
    op.drop_table("messages", schema="support")
    op.drop_table("cases", schema="support")
    op.drop_table("events", schema="safety")
    op.drop_table("incidents", schema="safety")
    op.execute("DROP SCHEMA IF EXISTS support CASCADE")
    op.execute("DROP SCHEMA IF EXISTS safety CASCADE")
