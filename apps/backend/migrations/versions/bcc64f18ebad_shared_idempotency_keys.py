"""shared idempotency keys

Phase 3 / Task 3.1 (Ride Booking — Create Ride Request). Creates
shared.idempotency_keys exactly as specified in
docs/04-database/database-design.md §35. This is shared infrastructure
(implementation-readiness.md §22: "Shared infrastructure must not
contain domain-specific business rules"), not part of the Ride domain,
even though Task 3.1 is its first consumer (POST /api/v1/rides's
documented Idempotency-Key header — see ADR-0010 Decision 5).

Revision ID: bcc64f18ebad
Revises: 43fa7e5bb02c
Create Date: 2026-08-22 11:19:39.089785

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bcc64f18ebad"
down_revision: str | None = "43fa7e5bb02c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS shared")

    op.create_table(
        "idempotency_keys",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("key", sa.String(length=180), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("operation", sa.String(length=100), nullable=False),
        sa.Column("request_hash", sa.String(length=128), nullable=False),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column(
            "response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("key", name="uq_idempotency_keys_key"),
        schema="shared",
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys", schema="shared")
    op.execute("DROP SCHEMA IF EXISTS shared CASCADE")
