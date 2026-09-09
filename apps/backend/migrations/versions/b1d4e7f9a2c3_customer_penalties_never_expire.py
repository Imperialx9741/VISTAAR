"""customer penalties never expire

BR-049 correction (owner decision, 2026-09-04, ADR-0069): "Customer
penalties in VISTAAR NEVER EXPIRE. Once a customer penalty is created,
it remains outstanding indefinitely until the customer actually pays
it. There is no automatic expiry date, no cancellation of the penalty
due to time passing, and no expiry enforcement job."

Drops `penalty.penalties.expires_at` (previously NOT NULL, always
computed as issued_at + 30 days, per the now-superseded BR-049 reading)
and narrows `idx_open_penalties` from `(user_id, expires_at)` to just
`(user_id)` — still supports the real query pattern the index exists
for ("does this user have any OUTSTANDING penalty"), which never needed
expires_at itself.

Does not touch `wallet.wallets.outstanding_debt` (Sarthi cancellation-
penalty debt, ADR-0062) — a completely separate mechanism that never
had an expiry concept, unaffected by this correction. See ADR-0069 for
the full account distinguishing the two.

Revision ID: b1d4e7f9a2c3
Revises: a7c3f9e51d4b
Create Date: 2026-09-04 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1d4e7f9a2c3"
down_revision: str | None = "a7c3f9e51d4b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("idx_open_penalties", table_name="penalties", schema="penalty")
    op.drop_column("penalties", "expires_at", schema="penalty")
    op.create_index(
        "idx_open_penalties",
        "penalties",
        ["user_id"],
        unique=False,
        schema="penalty",
        postgresql_where=sa.text("status = 'OUTSTANDING'"),
    )


def downgrade() -> None:
    op.drop_index("idx_open_penalties", table_name="penalties", schema="penalty")
    # Down-migration only: a real downgrade needs a real value for every
    # existing row, since the column was NOT NULL before. Not a business
    # value this migration invents — 30 days from re-adding the column
    # (now(), not issued_at, since issued_at's original relationship to
    # a 30-day window no longer has any meaning going forward) is a
    # deliberately conservative placeholder for a downgrade path that
    # only exists for schema-reversibility testing, not intended to be
    # run against real data.
    op.add_column(
        "penalties",
        sa.Column(
            "expires_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now() + interval '30 days'"),
        ),
        schema="penalty",
    )
    op.alter_column("penalties", "expires_at", server_default=None, schema="penalty")
    op.create_index(
        "idx_open_penalties",
        "penalties",
        ["user_id", "expires_at"],
        unique=False,
        schema="penalty",
        postgresql_where=sa.text("status = 'OUTSTANDING'"),
    )
