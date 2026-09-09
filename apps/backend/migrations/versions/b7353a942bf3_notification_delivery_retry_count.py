"""notification.deliveries retry_count

ADR-0075 (2026-09-04), closing the FAILED-SMS/PUSH-send retry gap
Phase 15's own audit flagged and explicitly left unfixed earlier the
same day. 0 = never retried, 1 = retried once (permanently excluded
from the retry task's own query afterward, whichever way it landed) —
see that ADR for the full account of why one bounded retry, not
open-ended backoff.

Revision ID: b7353a942bf3
Revises: d8f1c3a6e9b2
Create Date: 2026-09-04 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7353a942bf3"
down_revision: str | None = "d8f1c3a6e9b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "deliveries",
        sa.Column(
            "retry_count",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
        ),
        schema="notification",
    )


def downgrade() -> None:
    op.drop_column("deliveries", "retry_count", schema="notification")
