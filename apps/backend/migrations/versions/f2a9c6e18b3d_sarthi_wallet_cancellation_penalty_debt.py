"""sarthi wallet cancellation-penalty outstanding debt

Sarthi Unpaid Cancellation-Penalty Recovery (ADR-0062, 2026-09-03,
owner decision). One additive, non-nullable column with a hard default
of zero — no behavior change for any existing row until the new
recovery logic actually exercises it.

    outstanding_debt   the unpaid portion of a driver-cancellation
                        penalty (BR-011's _DRIVER_CANCELLATION_PENALTY,
                        modules/ride/router.py) the driver's wallet
                        balance could not cover at cancellation time.
                        Recorded instead of blocking the cancellation
                        or partially debiting the balance — recovered
                        automatically, in full or in part, from the
                        driver's next WALLET_RECHARGE credit
                        (WalletService.credit()), before any remainder
                        is credited to the spendable balance. Distinct
                        from and independent of the ₹20 low-balance
                        grace-ride rule (low_balance_grace_ride_used,
                        ADR-0058) — that rule alone still gates ride
                        acceptance; an outstanding debt does not, by
                        itself, block a driver from accepting rides.

Revision ID: f2a9c6e18b3d
Revises: d4e8f1a52c6b
Create Date: 2026-09-03 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2a9c6e18b3d"
down_revision: str | None = "d4e8f1a52c6b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "wallets",
        sa.Column(
            "outstanding_debt",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
        schema="wallet",
    )
    op.create_check_constraint(
        "wallet_outstanding_debt_nonnegative",
        "wallets",
        "outstanding_debt >= 0",
        schema="wallet",
    )


def downgrade() -> None:
    op.drop_constraint(
        "wallet_outstanding_debt_nonnegative", "wallets", schema="wallet"
    )
    op.drop_column("wallets", "outstanding_debt", schema="wallet")
