"""platform fee management

Platform Fee Management (ADR-0045). Adds pricing.platform_fee_rules —
versioned/effective-dated config for BR-011's driver platform fee,
identical DRAFT/IN_REVIEW/PUBLISHED lifecycle to pricing.fare_rules
(ADR-0042), but a separate table (driver economics, not customer
fare) keyed by the plain 3-value vehicle_category set (BIKE/AUTO/CAB).
Seeds one PUBLISHED row per category with today's approved values
(BIKE ₹2, AUTO ₹5, CAB ₹10 — matching_router.py's own
_PLATFORM_FEE_BY_CATEGORY dict, which remains only as a last-resort
fallback — see that router's own comment and ADR-0045's implementation
note) so nothing changes the moment this ships.

Revision ID: 67a1ffeaf103
Revises: d3a978951b6f
Create Date: 2026-08-26 00:00:00.000000

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "67a1ffeaf103"
down_revision: str | None = "d3a978951b6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PLATFORM_FEE_SEED = {
    "BIKE": "2",
    "AUTO": "5",
    "CAB": "10",
}


def upgrade() -> None:
    op.create_table(
        "platform_fee_rules",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("vehicle_category", sa.String(length=20), nullable=False),
        sa.Column("fee_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="DRAFT"
        ),
        sa.Column("effective_from", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("effective_until", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["created_by"], ["admin.users.id"]),
        schema="pricing",
    )

    # Same synthetic-system-admin fallback ADR-0043/ADR-0044's
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

    for vehicle_category, fee_amount in _PLATFORM_FEE_SEED.items():
        connection.execute(
            sa.text(
                "INSERT INTO pricing.platform_fee_rules "
                "(id, vehicle_category, fee_amount, status, effective_from, "
                "created_by) "
                "VALUES (:id, :vehicle_category, :fee_amount, 'PUBLISHED', "
                "now(), :admin_id)"
            ),
            {
                "id": str(uuid.uuid4()),
                "vehicle_category": vehicle_category,
                "fee_amount": fee_amount,
                "admin_id": str(admin_id),
            },
        )


def downgrade() -> None:
    op.drop_table("platform_fee_rules", schema="pricing")
