"""penalty foundation: penalties and strikes

Minimal Penalty Foundation — pulled forward specifically to unblock
post-acceptance customer cancellation (ACCEPTED/ARRIVED) and driver
cancellation, per docs/VISTAAR_IMPLEMENTATION_ROADMAP.md §2.0 ("Actual
next engineering dependency") and ADR-0015. Creates penalty.penalties
and penalty.strikes exactly as specified in docs/04-database/
database-design.md §26 — no more.

`penalty.penalties.user_id` has no foreign key (matches
database-design.md §26.1 exactly) — it is deliberately generic across
both customer.customers and driver.drivers, since there is no single
"users" table joining them.

uq_penalties_ride_penalty_type (ride_id, penalty_type) is an addition
beyond database-design.md's literal column list — a concurrency-safety
backstop, the same UNIQUE-constraint-as-idempotency-guard pattern
wallet.transactions.idempotency_key already established (ADR-0013),
here enforcing database-design.md §39's "One qualifying business event
must not create duplicate penalties" at the database level, not just in
application code.

Revision ID: 383b55c70732
Revises: b360069c4f07
Create Date: 2026-08-24 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "383b55c70732"
down_revision: str | None = "b360069c4f07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS penalty")

    op.create_table(
        "penalties",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "ride_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ride.rides.id"),
            nullable=True,
        ),
        sa.Column("penalty_type", sa.String(length=50), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="OUTSTANDING"
        ),
        sa.Column(
            "issued_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("settled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "ride_id", "penalty_type", name="uq_penalties_ride_penalty_type"
        ),
        schema="penalty",
    )
    op.create_index(
        "idx_open_penalties",
        "penalties",
        ["user_id", "expires_at"],
        schema="penalty",
        postgresql_where=sa.text("status = 'OUTSTANDING'"),
    )

    op.create_table(
        "strikes",
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
        sa.Column(
            "ride_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ride.rides.id"),
            nullable=True,
        ),
        sa.Column("reason", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="penalty",
    )


def downgrade() -> None:
    op.drop_table("strikes", schema="penalty")
    op.drop_index("idx_open_penalties", table_name="penalties", schema="penalty")
    op.drop_table("penalties", schema="penalty")
    op.execute("DROP SCHEMA IF EXISTS penalty CASCADE")
