"""referral reward configuration

Referral Reward Configuration (ADR-0043). Adds referral.driver_bonus_
rules and referral.customer_reward_rules — versioned/effective-dated
config for BR-022/023's driver bonus and BR-059/060's customer
promotion grants, identical DRAFT/IN_REVIEW/PUBLISHED lifecycle to
pricing.fare_rules (ADR-0042). Seeds one PUBLISHED row in each table
with today's approved values so nothing changes the moment this ships.

Revision ID: ed6bbec11c17
Revises: d9a2976f73d9
Create Date: 2026-08-26 00:00:00.000000

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "ed6bbec11c17"
down_revision: str | None = "d9a2976f73d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "driver_bonus_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("referred_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("referrer_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("effective_from", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("effective_until", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["created_by"], ["admin.users.id"]),
        schema="referral",
    )

    op.create_table(
        "customer_reward_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("reward_type", sa.String(length=30), nullable=False),
        sa.Column("discount_percent", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("total_uses", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("effective_from", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("effective_until", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["created_by"], ["admin.users.id"]),
        schema="referral",
    )

    # Seed one PUBLISHED row per table/type with today's approved
    # values, backed by a real admin.users row (created_by has a real
    # FK). Reuses the first existing SUPER_ADMIN if the database
    # already has one; otherwise provisions a fixed-UUID synthetic
    # "system" admin here (same trust level as this migration itself —
    # matching scripts/provision_admin.py's own "ops-only, same trust
    # as alembic upgrade head" precedent) so seeding never depends on
    # migration ordering relative to the first real admin's creation. A
    # fresh/test database always hits this synthetic-admin path; a
    # long-running production database picks up its real Super Admin
    # instead.
    connection = op.get_bind()
    admin_id = connection.execute(
        sa.text("SELECT id FROM admin.users WHERE role = 'SUPER_ADMIN' LIMIT 1")
    ).scalar()
    if admin_id is None:
        system_account_id = "00000000-0000-0000-0000-000000000001"
        connection.execute(
            sa.text(
                "INSERT INTO identity.accounts (id, account_type, phone, status) "
                "VALUES (:id, 'ADMIN', '+910000000001', 'ACTIVE') "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"id": system_account_id},
        )
        connection.execute(
            sa.text(
                "INSERT INTO admin.users (id, role, status) "
                "VALUES (:id, 'SUPER_ADMIN', 'ACTIVE') "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"id": system_account_id},
        )
        admin_id = system_account_id

    connection.execute(
        sa.text(
            "INSERT INTO referral.driver_bonus_rules "
            "(id, referred_amount, referrer_amount, status, effective_from, created_by) "
            "VALUES (:id, 100, 100, 'PUBLISHED', now(), :admin_id)"
        ),
        {"id": str(uuid.uuid4()), "admin_id": str(admin_id)},
    )
    connection.execute(
        sa.text(
            "INSERT INTO referral.customer_reward_rules "
            "(id, reward_type, discount_percent, total_uses, status, effective_from, created_by) "
            "VALUES (:id, 'REFERRAL_REFERRED', 50, 3, 'PUBLISHED', now(), :admin_id)"
        ),
        {"id": str(uuid.uuid4()), "admin_id": str(admin_id)},
    )
    connection.execute(
        sa.text(
            "INSERT INTO referral.customer_reward_rules "
            "(id, reward_type, discount_percent, total_uses, status, effective_from, created_by) "
            "VALUES (:id, 'REFERRAL_REFERRING', 50, 2, 'PUBLISHED', now(), :admin_id)"
        ),
        {"id": str(uuid.uuid4()), "admin_id": str(admin_id)},
    )


def downgrade() -> None:
    op.drop_table("customer_reward_rules", schema="referral")
    op.drop_table("driver_bonus_rules", schema="referral")
