"""schedule a ride and book for someone else

Schedule a Ride & Book for Someone Else (ADR-0057, 2026-08-31). Four
additive/nullable columns on ride.rides — NULL for every ride created
before this migration and for every ordinary immediate/self-booked ride
since (zero behavior change to the existing flow):

    scheduled_for          customer-chosen future pickup time
    lock_in_at              = scheduled_for - 30 minutes, computed and
                            stored at scheduling time (ADR-0057 Decision
                            1) so the Celery Beat task
                            (modules/ride/tasks.py) can index/query it
                            cheaply rather than computing it on every
                            poll
    linked_contact_name     Book for Someone Else's linked contact —
    linked_contact_phone    both set together or both NULL

A new partial index supports that Beat task's "find due SCHEDULED
rides" poll efficiently (kept tiny — only ever a handful of SCHEDULED
rides exist at once).

Revision ID: a3f7c8d1e2b4
Revises: f1a4c8e29b6d
Create Date: 2026-08-31 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3f7c8d1e2b4"
down_revision: str | None = "f1a4c8e29b6d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rides",
        sa.Column("scheduled_for", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="ride",
    )
    op.add_column(
        "rides",
        sa.Column("lock_in_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="ride",
    )
    op.add_column(
        "rides",
        sa.Column("linked_contact_name", sa.String(length=200), nullable=True),
        schema="ride",
    )
    op.add_column(
        "rides",
        sa.Column("linked_contact_phone", sa.String(length=20), nullable=True),
        schema="ride",
    )
    op.create_index(
        "idx_rides_lock_in_at",
        "rides",
        ["lock_in_at"],
        schema="ride",
        postgresql_where=sa.text("status = 'SCHEDULED'"),
    )


def downgrade() -> None:
    op.drop_index("idx_rides_lock_in_at", table_name="rides", schema="ride")
    op.drop_column("rides", "linked_contact_phone", schema="ride")
    op.drop_column("rides", "linked_contact_name", schema="ride")
    op.drop_column("rides", "lock_in_at", schema="ride")
    op.drop_column("rides", "scheduled_for", schema="ride")
