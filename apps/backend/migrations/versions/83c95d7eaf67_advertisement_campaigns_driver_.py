"""advertisement: campaigns, driver_campaigns, payouts

Phase 17 — Advertisements, scoped per ADR-0018 (domain/service/
repository layer only — no HTTP router, no Admoto integration; see
that ADR for why). Creates advertisement.campaigns,
advertisement.driver_campaigns, and advertisement.payouts exactly as
specified in docs/04-database/database-design.md §31.

uq_payouts_driver_campaign (driver_campaign_id) is an addition beyond
the documented schema — a concurrency-safety backstop, the same
UNIQUE-constraint-as-idempotency-guard pattern
wallet.transactions.idempotency_key (ADR-0013) and
penalty.penalties' uq_penalties_ride_penalty_type (ADR-0015) already
established: at most one payout may ever be calculated per driver
campaign.

Revision ID: 83c95d7eaf67
Revises: 5c4d6933a6d9
Create Date: 2026-08-24 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "83c95d7eaf67"
down_revision: str | None = "5c4d6933a6d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS advertisement")

    op.create_table(
        "campaigns",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("partner_name", sa.String(length=150), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("payout_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "driver_share_percent",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="80",
        ),
        sa.Column(
            "vistaar_share_percent",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="20",
        ),
        sa.Column("starts_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("ends_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="advertisement",
    )

    op.create_table(
        "driver_campaigns",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("advertisement.campaigns.id"),
            nullable=False,
        ),
        sa.Column(
            "driver_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("driver.drivers.id"),
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="ASSIGNED"
        ),
        sa.Column("proof_uri", sa.Text(), nullable=True),
        sa.Column("verification_status", sa.String(length=30), nullable=True),
        sa.Column(
            "assigned_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="advertisement",
    )

    op.create_table(
        "payouts",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "driver_campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("advertisement.driver_campaigns.id"),
            nullable=False,
        ),
        sa.Column("gross_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("driver_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("vistaar_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="PENDING"
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("driver_campaign_id", name="uq_payouts_driver_campaign"),
        schema="advertisement",
    )


def downgrade() -> None:
    op.drop_table("payouts", schema="advertisement")
    op.drop_table("driver_campaigns", schema="advertisement")
    op.drop_table("campaigns", schema="advertisement")
    op.execute("DROP SCHEMA IF EXISTS advertisement CASCADE")
