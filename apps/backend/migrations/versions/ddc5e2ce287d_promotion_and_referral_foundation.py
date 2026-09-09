"""promotion and referral: entitlements, usage, reservations, codes,
referrals, rewards

Phase 12 — Growth, Minimal Promotion & Referral Foundation, scoped per
ADR-0019 (domain/service/repository layer + the three documented HTTP
endpoints + two real composition points — no ride-creation composition
yet; see that ADR for why). Creates promotion.entitlements/usage/
reservations and referral.codes/referrals/rewards exactly as specified
in docs/04-database/database-design.md §24-25.

Revision ID: ddc5e2ce287d
Revises: 83c95d7eaf67
Create Date: 2026-08-24 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ddc5e2ce287d"
down_revision: str | None = "83c95d7eaf67"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS promotion")
    op.execute("CREATE SCHEMA IF NOT EXISTS referral")

    op.create_table(
        "entitlements",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customer.customers.id"),
            nullable=False,
        ),
        sa.Column("promotion_type", sa.String(length=50), nullable=False),
        sa.Column("total_uses", sa.Integer(), nullable=False),
        sa.Column("remaining_uses", sa.Integer(), nullable=False),
        sa.Column("discount_percent", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column(
            "max_discount_amount", sa.Numeric(precision=12, scale=2), nullable=True
        ),
        sa.Column("activated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="ACTIVE"
        ),
        schema="promotion",
    )

    op.create_table(
        "usage",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "entitlement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("promotion.entitlements.id"),
            nullable=False,
        ),
        sa.Column(
            "ride_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ride.rides.id"),
            nullable=False,
        ),
        sa.Column("discount_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="promotion",
    )
    op.create_index(
        "uq_promotion_ride_use",
        "usage",
        ["entitlement_id", "ride_id"],
        unique=True,
        schema="promotion",
    )

    op.create_table(
        "reservations",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "entitlement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("promotion.entitlements.id"),
            nullable=False,
        ),
        sa.Column(
            "ride_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ride.rides.id"),
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="RESERVED"
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="promotion",
    )

    op.create_table(
        "codes",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("owner_type", sa.String(length=20), nullable=False),
        # No FK — owner_id is generic across customer.customers and
        # driver.drivers (no single "users" table joins them), same
        # precedent as penalty.penalties.user_id (ADR-0015).
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="ACTIVE"
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("code", name="uq_referral_codes_code"),
        schema="referral",
    )

    op.create_table(
        "referrals",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "referral_code_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("referral.codes.id"),
            nullable=False,
        ),
        # No FK on referrer_id/referred_id — generic across
        # customer.customers/driver.drivers, same reasoning as
        # referral.codes.owner_id above.
        sa.Column("referrer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("referred_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("referred_type", sa.String(length=20), nullable=False),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="ATTACHED"
        ),
        sa.Column("activated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # Beyond the literal documented schema — a concurrency-safety
        # backstop (same UNIQUE-constraint-as-idempotency-guard pattern
        # already established, e.g. ADR-0015's
        # uq_penalties_ride_penalty_type): a referred party can only
        # ever be referred once.
        sa.UniqueConstraint("referred_id", name="uq_referrals_referred_id"),
        schema="referral",
    )

    op.create_table(
        "rewards",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "referral_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("referral.referrals.id"),
            nullable=False,
        ),
        sa.Column("recipient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reward_type", sa.String(length=40), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("promotion_uses", sa.Integer(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="PENDING"
        ),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_referral_rewards_idempotency_key"
        ),
        schema="referral",
    )


def downgrade() -> None:
    op.drop_table("rewards", schema="referral")
    op.drop_table("referrals", schema="referral")
    op.drop_table("codes", schema="referral")
    op.drop_table("reservations", schema="promotion")
    op.drop_index("uq_promotion_ride_use", table_name="usage", schema="promotion")
    op.drop_table("usage", schema="promotion")
    op.drop_table("entitlements", schema="promotion")
    op.execute("DROP SCHEMA IF EXISTS referral CASCADE")
    op.execute("DROP SCHEMA IF EXISTS promotion CASCADE")
