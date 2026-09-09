"""vehicle lifecycle: one active vehicle per driver

Vehicle Lifecycle Decision & API Contract Clarification follow-up to
Phase 2 / Task 2.4. Adds the database-level backstop for the newly
approved business rule (business-rules.md BR-122): at most one of a
driver's vehicles may be ACTIVE at a time. See
docs/04-database/database-design.md §8.1's added
uq_vehicles_one_active_per_driver documentation and
docs/14-decisions/ADR-0006-vehicle-lifecycle-single-active-vehicle.md.

No new table. No column changes.

Revision ID: 1f10a4e53685
Revises: b37c29f328c8
Create Date: 2026-08-21 13:09:22.289082

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1f10a4e53685"
down_revision: str | None = "b37c29f328c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX uq_vehicles_one_active_per_driver "
        "ON vehicle.vehicles(driver_id) "
        "WHERE operational_status = 'ACTIVE'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX vehicle.uq_vehicles_one_active_per_driver")
