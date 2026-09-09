"""sarthi wallet low-balance grace ride

Sarthi Wallet Low-Balance Rule (ADR-0058, 2026-09-02, owner decision).
One additive, non-nullable column with a hard default — zero behavior
change for any existing row: every wallet starts (and stays, until the
new rule actually exercises it) with grace unused.

    low_balance_grace_ride_used   whether this driver has already used
                                   their one allowed ride-acceptance
                                   while their balance is at or below
                                   the low-balance threshold (₹20,
                                   modules.wallet.domain.entities.
                                   LOW_BALANCE_THRESHOLD). Reset to
                                   false the moment any credit brings
                                   the balance back above the
                                   threshold.

Revision ID: d4e8f1a52c6b
Revises: a3f7c8d1e2b4
Create Date: 2026-09-02 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4e8f1a52c6b"
down_revision: str | None = "a3f7c8d1e2b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "wallets",
        sa.Column(
            "low_balance_grace_ride_used",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        schema="wallet",
    )


def downgrade() -> None:
    op.drop_column("wallets", "low_balance_grace_ride_used", schema="wallet")
