"""promotion campaigns

Coupon/Campaign Schema (ADR-0041). Adds promotion.campaigns and
promotion.campaign_eligible_customers, plus one additive nullable
column on the existing promotion.entitlements — no other change to
that table (ADR-0041 Decision 1/6.1: a FLAT-discount campaign's
redemption is represented via the existing discount_percent=100 +
max_discount_amount=<flat value> combination, not a new column).

Revision ID: 92cda537e9c7
Revises: 5150fb4352b4
Create Date: 2026-08-26 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "92cda537e9c7"
down_revision: str | None = "5150fb4352b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("code", sa.String(length=30), nullable=True, unique=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("vehicle_category", sa.String(length=20), nullable=True),
        sa.Column("discount_type", sa.String(length=10), nullable=False),
        sa.Column("discount_value", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "max_discount_amount", sa.Numeric(precision=12, scale=2), nullable=True
        ),
        sa.Column("minimum_fare", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column(
            "eligible_scope",
            sa.String(length=20),
            nullable=False,
            server_default="ALL",
        ),
        sa.Column(
            "per_customer_use_limit",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("total_usage_limit", sa.Integer(), nullable=True),
        sa.Column("ride_count_limit", sa.Integer(), nullable=True),
        sa.Column("starts_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("ends_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="DRAFT"
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["created_by"], ["admin.users.id"]),
        schema="promotion",
    )

    op.create_table(
        "campaign_eligible_customers",
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["promotion.campaigns.id"]
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.customers.id"]),
        sa.PrimaryKeyConstraint("campaign_id", "customer_id"),
        schema="promotion",
    )

    op.add_column(
        "entitlements",
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="promotion",
    )
    op.create_foreign_key(
        "fk_entitlements_campaign_id",
        "entitlements",
        "campaigns",
        ["campaign_id"],
        ["id"],
        source_schema="promotion",
        referent_schema="promotion",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_entitlements_campaign_id", "entitlements", schema="promotion"
    )
    op.drop_column("entitlements", "campaign_id", schema="promotion")
    op.drop_table("campaign_eligible_customers", schema="promotion")
    op.drop_table("campaigns", schema="promotion")
