"""admin permissions

Admin Permission Model (ADR-0040, BR-126/BR-127). Adds admin.permissions
exactly as database-design.md §33.3 now specifies — one row per
(admin_id, module) an employee admin has some access to. Absence of a
row means no access; a Super Admin never has rows here at all (implicit
full access, ADR-0040 Decision 1).

Does NOT alter admin.users.role — it was already an unconstrained
VARCHAR(40) with no CHECK constraint (database-design.md §33.1), so no
migration is needed to let it hold "SUPER_ADMIN" alongside "ADMIN"; the
closed set (AdminRole) is enforced at the application layer only
(domain/entities.py), matching this column's existing convention.

Revision ID: 5150fb4352b4
Revises: b8e4f27a5c93
Create Date: 2026-08-26 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5150fb4352b4"
down_revision: str | None = "b8e4f27a5c93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "permissions",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("admin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module", sa.String(length=40), nullable=False),
        sa.Column("access_level", sa.String(length=10), nullable=False),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["admin_id"], ["admin.users.id"]),
        sa.UniqueConstraint(
            "admin_id", "module", name="uq_admin_permissions_admin_module"
        ),
        schema="admin",
    )
    op.create_index(
        "idx_admin_permissions_admin",
        "permissions",
        ["admin_id"],
        schema="admin",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_admin_permissions_admin", table_name="permissions", schema="admin"
    )
    op.drop_table("permissions", schema="admin")
