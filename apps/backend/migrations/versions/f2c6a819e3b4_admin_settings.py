"""admin settings

Admin Settings (ADR-0048). Adds admin.settings — a flat key-value store
for promotion defaults/operational thresholds/feature flags/general
settings only (Decision 1). No lifecycle (no draft/review/publish —
Decision 3's "closed vocabulary, no Create/Delete"): a plain audited
overwrite, since nothing reads it live at the moment of a financial
transaction the way fare_rules/platform_fee_rules do.

Seeds ONLY the two PROMOTION_DEFAULT keys that were previously
hardcoded constants in the promotion module (welcome_discount_percent=
50, welcome_total_uses=3) — deliberately NOT seeding
OPERATIONAL_THRESHOLD/FEATURE_FLAG/GENERAL, per ADR-0048 Decision 2's
explicit restraint against inventing settings no other ADR asked for.

Revision ID: f2c6a819e3b4
Revises: aa0da4a03971
Create Date: 2026-08-28 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f2c6a819e3b4"
down_revision: str | None = "aa0da4a03971"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SETTINGS_SEED = [
    {
        "key": "welcome_discount_percent",
        "value": "50",
        "category": "PROMOTION_DEFAULT",
        "description": (
            "Discount percentage applied by the welcome coupon granted "
            "to a newly registered customer."
        ),
    },
    {
        "key": "welcome_total_uses",
        "value": "3",
        "category": "PROMOTION_DEFAULT",
        "description": (
            "Number of times the welcome coupon entitlement may be "
            "redeemed before it is exhausted."
        ),
    },
]


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=100), primary_key=True, nullable=False),
        sa.Column("value", postgresql.JSONB, nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["admin.users.id"]),
        schema="admin",
    )

    # Same synthetic-system-admin fallback ADR-0043/0044/0045's
    # migrations already established, reused verbatim.
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

    for setting in _SETTINGS_SEED:
        connection.execute(
            # CAST(... AS jsonb), not a `::jsonb` suffix — SQLAlchemy's
            # text() bind-param parser treats a colon immediately after
            # a named param as ambiguous with Postgres's `::` cast
            # operator, so the inline-suffix form silently fails to
            # bind `:value` at all.
            sa.text(
                "INSERT INTO admin.settings "
                "(key, value, category, description, updated_by) "
                "VALUES (:key, CAST(:value AS jsonb), :category, "
                ":description, :admin_id)"
            ),
            {
                "key": setting["key"],
                # A bare number, not a JSON object — plain
                # `to_jsonb(50)`-equivalent — matches how the seeded
                # value is consumed as a raw int/percent elsewhere.
                "value": setting["value"],
                "category": setting["category"],
                "description": setting["description"],
                "admin_id": str(admin_id),
            },
        )


def downgrade() -> None:
    op.drop_table("settings", schema="admin")
