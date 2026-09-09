"""customer penalty settlement via driver wallet

Customer Outstanding Penalty Settlement (owner decision, 2026-09-03 —
"FINAL BUSINESS DECISIONS FOR REMAINING OPEN ITEMS", item 2). Adds
`penalty.penalties.settlement_ride_id`: the ride whose completion
settles this penalty, distinct from the existing `ride_id` column (the
ride the penalty was originally INCURRED on, e.g. the cancelled ride —
unchanged). NULL until a later Create Ride durably attaches an
OUTSTANDING, not-yet-attached penalty to that new booking; set back to
NULL if that ride is cancelled before completion (freeing the penalty
for a future ride to attach); the same value is written into `status`/
`settled_at` only once that specific ride actually completes — see
ADR-0066 for the full design and modules/penalty/domain/entities.py for
the state machine this column drives.

Revision ID: a7c3f9e51d4b
Revises: f2a9c6e18b3d
Create Date: 2026-09-03 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a7c3f9e51d4b"
down_revision: str | None = "f2a9c6e18b3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "penalties",
        sa.Column(
            "settlement_ride_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ride.rides.id"),
            nullable=True,
        ),
        schema="penalty",
    )
    # Lookup direction: "which penalties are attached to this ride"
    # (Create Ride's release-on-cancel and Complete Ride's settle-on-
    # completion both query by this column) — a partial index, since
    # the column is NULL for every penalty that was never carried
    # forward to a later ride (the common case).
    op.create_index(
        "ix_penalties_settlement_ride_id",
        "penalties",
        ["settlement_ride_id"],
        unique=False,
        schema="penalty",
        postgresql_where=sa.text("settlement_ride_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_penalties_settlement_ride_id", table_name="penalties", schema="penalty"
    )
    op.drop_column("penalties", "settlement_ride_id", schema="penalty")
