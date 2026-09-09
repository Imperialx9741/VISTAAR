"""shared.processed_events (consumer idempotency)

Phase 18 reliability work (ADR-0071, 2026-09-04, owner-requested): closes
the roadmap's "Event idempotency: NOT implemented on the consumer side"
gap (ADR-0017 §4 — deferred at the time because no consumer module
existed yet; modules/notification/consumer.py's NotificationConsumer,
ADR-0038, is now a real caller). Creates shared.processed_events exactly
as event-contracts.md §29 recommends — a general (consumer_name,
event_id) dedup record any consumer can check before applying a
redelivered event's business effect, on top of (not replacing) whatever
narrower dedup a specific handler already has (e.g.
NotificationService.send()'s own (user_id, channel, template_key,
event_id) constraint).

Revision ID: d8f1c3a6e9b2
Revises: c2e6a9f4d7b1
Create Date: 2026-09-04 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d8f1c3a6e9b2"
down_revision: str | None = "c2e6a9f4d7b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "processed_events",
        sa.Column("consumer_name", sa.String(length=150), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "processed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("consumer_name", "event_id"),
        schema="shared",
    )


def downgrade() -> None:
    op.drop_table("processed_events", schema="shared")
