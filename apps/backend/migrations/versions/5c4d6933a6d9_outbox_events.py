"""outbox: shared.outbox_events

Minimal Event & Outbox Foundation — pulled forward to unblock real
domain-event publishing for the modules that have been deferring it
since Task 3.1, per docs/VISTAAR_IMPLEMENTATION_ROADMAP.md §2.0 and
ADR-0017. Creates shared.outbox_events exactly as specified in
docs/04-database/database-design.md §34 — no more.

Deliberately NOT created here (ADR-0017 §4 — out of this task's scope):
shared.processed_events (event-contracts.md §29) — no consumer module
exists yet to use it.

Revision ID: 5c4d6933a6d9
Revises: 383b55c70732
Create Date: 2026-08-24 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5c4d6933a6d9"
down_revision: str | None = "383b55c70732"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # shared.idempotency_keys already lives in this schema (Task 3.1) —
    # CREATE SCHEMA IF NOT EXISTS is idempotent either way.
    op.execute("CREATE SCHEMA IF NOT EXISTS shared")

    op.create_table(
        "outbox_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("aggregate_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=150), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="shared",
    )
    op.create_index(
        "idx_outbox_unpublished",
        "outbox_events",
        ["created_at"],
        schema="shared",
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_outbox_unpublished", table_name="outbox_events", schema="shared")
    op.drop_table("outbox_events", schema="shared")
