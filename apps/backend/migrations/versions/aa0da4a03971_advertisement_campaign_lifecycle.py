"""advertisement campaign lifecycle

Advertisement Admin API (ADR-0046 Decision 1). Gives
advertisement.campaigns.status a real server-side default now that the
column carries a real lifecycle (ACTIVE <-> PAUSED, (ACTIVE or
PAUSED) -> ENDED, enforced application-side in
modules/advertisement/domain/entities.py::Campaign) rather than
`ACTIVE` being the only value the application layer ever wrote. No
column shape change — `status` was already VARCHAR(30), wide enough
for PAUSED/ENDED; this migration is additive-only (a default, not a
constraint), so it never touches existing rows.

Revision ID: aa0da4a03971
Revises: 67a1ffeaf103
Create Date: 2026-08-26 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "aa0da4a03971"
down_revision: str | None = "67a1ffeaf103"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "campaigns",
        "status",
        server_default="ACTIVE",
        schema="advertisement",
    )


def downgrade() -> None:
    op.alter_column(
        "campaigns",
        "status",
        server_default=None,
        schema="advertisement",
    )
