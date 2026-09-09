"""fare rule workflow status

Fare Management Workflow (ADR-0042). Replaces pricing.fare_rules.active
with a DRAFT | IN_REVIEW | PUBLISHED status column — see the ADR for why
this is a replacement, not an additive column kept alongside `active`.
Existing active=TRUE rows are backfilled to PUBLISHED so no currently
-live rate silently disappears from PricingService.calculate_fare()'s
query when this migration runs. Also relaxes effective_from to nullable
— a DRAFT/IN_REVIEW row has none yet; Publish is the action that sets
it (ADR-0042 Decision 2).

Revision ID: d9a2976f73d9
Revises: 92cda537e9c7
Create Date: 2026-08-26 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d9a2976f73d9"
down_revision: str | None = "92cda537e9c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fare_rules",
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="DRAFT"
        ),
        schema="pricing",
    )
    op.execute(
        "UPDATE pricing.fare_rules SET status = 'PUBLISHED' WHERE active = TRUE"
    )
    op.drop_column("fare_rules", "active", schema="pricing")
    op.alter_column(
        "fare_rules", "effective_from", nullable=True, schema="pricing"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE pricing.fare_rules SET effective_from = created_at "
        "WHERE effective_from IS NULL"
    )
    op.alter_column(
        "fare_rules", "effective_from", nullable=False, schema="pricing"
    )
    op.add_column(
        "fare_rules",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        schema="pricing",
    )
    op.execute(
        "UPDATE pricing.fare_rules SET active = (status = 'PUBLISHED')"
    )
    op.drop_column("fare_rules", "status", schema="pricing")
