"""wallet foundation: wallets and transactions

Minimal Wallet Foundation — pulled forward specifically to unblock the
next ride task (Accept Offer / Ride ACCEPTED), per
docs/VISTAAR_IMPLEMENTATION_ROADMAP.md §2.0 ("Actual next engineering
dependency"). Creates wallet.wallets and wallet.transactions exactly as
specified in docs/04-database/database-design.md §17 — no more.

Deliberately NOT created here (out of this task's scope — see the
planning exchange this task was approved from): wallet.
outstanding_settlements (§18) and wallet.recharges (§19). Neither is
needed to make offer acceptance atomic and safe, and building them now
would be exactly the "implement the entire later Payment/Financial phase
prematurely" the roadmap explicitly warns against.

Revision ID: b360069c4f07
Revises: 5c30e0859933
Create Date: 2026-08-23 09:12:03.774512

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b360069c4f07"
down_revision: str | None = "5c30e0859933"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS wallet")

    op.create_table(
        "wallets",
        sa.Column(
            "driver_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("driver.drivers.id"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "balance",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint("balance >= 0", name="wallet_balance_nonnegative"),
        schema="wallet",
    )

    op.create_table(
        "transactions",
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
        sa.Column("transaction_type", sa.String(length=50), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("balance_before", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("balance_after", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False),
        sa.Column("reference_type", sa.String(length=50), nullable=True),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_wallet_transactions_idempotency_key"
        ),
        schema="wallet",
    )
    op.create_index(
        "idx_wallet_transactions_driver",
        "transactions",
        ["driver_id"],
        schema="wallet",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_wallet_transactions_driver", table_name="transactions", schema="wallet"
    )
    op.drop_table("transactions", schema="wallet")
    op.drop_table("wallets", schema="wallet")
    op.execute("DROP SCHEMA IF EXISTS wallet CASCADE")
