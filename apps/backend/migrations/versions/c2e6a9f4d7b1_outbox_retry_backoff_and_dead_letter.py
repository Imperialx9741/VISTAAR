"""outbox retry/backoff and dead-letter columns

Phase 18 reliability work (ADR-0071, 2026-09-04, owner-requested): closes
the roadmap's "Event retry: PARTIAL" / "Dead-letter handling: NOT
implemented" gap (ADR-0017 §4) — a failed Kafka publish previously left
its shared.outbox_events row unpublished, retried forever at the fixed
poll interval, with no backoff, no maximum-attempts, and no dead-letter
path. Adds the per-row attempt-tracking columns ADR-0017 Decision 2
explicitly named as the missing piece for event-contracts.md §30's retry
policy and §31's Dead Letter Topics.

New columns:
- status: explicit processing status (PENDING/PUBLISHED/DEAD_LETTERED) —
  the authoritative state going forward; published_at/dead_lettered_at
  keep recording *when*, same "status enum + timestamp" pairing this
  codebase already uses elsewhere (e.g. penalty.penalties).
- attempt_count: retry/attempt count.
- last_attempt_at / first_failure_at: last and first failure timestamps
  (event-contracts.md §31's "first failure"/"last failure").
- next_attempt_at: when this row is next eligible for a publish attempt
  — defaults to NOW() so every existing/new row is immediately due,
  unaffected until its first real failure. The publisher's query filters
  on this so a failed row is never retried before it's actually due (no
  tight retry loop).
- last_error: the most recent failure's error message.
- dead_lettered_at: when this row was marked DEAD_LETTERED.

idx_outbox_unpublished (`published_at IS NULL`) is replaced by
idx_outbox_due (`next_attempt_at WHERE status = 'PENDING'`) — the actual
query shape shared/outbox_publisher.py now uses; published_at itself is
kept for backward-compatible reads.

Revision ID: c2e6a9f4d7b1
Revises: b1d4e7f9a2c3
Create Date: 2026-09-04 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2e6a9f4d7b1"
down_revision: str | None = "b1d4e7f9a2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "outbox_events",
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="PENDING"
        ),
        schema="shared",
    )
    op.add_column(
        "outbox_events",
        sa.Column(
            "attempt_count", sa.Integer(), nullable=False, server_default="0"
        ),
        schema="shared",
    )
    op.add_column(
        "outbox_events",
        sa.Column("last_attempt_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="shared",
    )
    op.add_column(
        "outbox_events",
        sa.Column("first_failure_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="shared",
    )
    op.add_column(
        "outbox_events",
        sa.Column(
            "next_attempt_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="shared",
    )
    op.add_column(
        "outbox_events",
        sa.Column("last_error", sa.Text(), nullable=True),
        schema="shared",
    )
    op.add_column(
        "outbox_events",
        sa.Column("dead_lettered_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="shared",
    )

    # Backfill: every already-PUBLISHED row (published_at already set by
    # the pre-existing publisher) is marked status='PUBLISHED' so the new
    # status column agrees with the pre-existing published_at column for
    # rows that predate this migration — a fresh installation has none,
    # but a live environment upgrading in place would otherwise show
    # every historical row as PENDING.
    op.execute(
        "UPDATE shared.outbox_events SET status = 'PUBLISHED' "
        "WHERE published_at IS NOT NULL"
    )

    op.drop_index("idx_outbox_unpublished", table_name="outbox_events", schema="shared")
    op.create_index(
        "idx_outbox_due",
        "outbox_events",
        ["next_attempt_at"],
        schema="shared",
        postgresql_where=sa.text("status = 'PENDING'"),
    )


def downgrade() -> None:
    op.drop_index("idx_outbox_due", table_name="outbox_events", schema="shared")
    op.create_index(
        "idx_outbox_unpublished",
        "outbox_events",
        ["created_at"],
        schema="shared",
        postgresql_where=sa.text("published_at IS NULL"),
    )

    op.drop_column("outbox_events", "dead_lettered_at", schema="shared")
    op.drop_column("outbox_events", "last_error", schema="shared")
    op.drop_column("outbox_events", "next_attempt_at", schema="shared")
    op.drop_column("outbox_events", "first_failure_at", schema="shared")
    op.drop_column("outbox_events", "last_attempt_at", schema="shared")
    op.drop_column("outbox_events", "attempt_count", schema="shared")
    op.drop_column("outbox_events", "status", schema="shared")
