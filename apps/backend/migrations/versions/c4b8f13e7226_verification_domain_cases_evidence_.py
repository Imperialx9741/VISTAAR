"""verification domain cases evidence results

Phase 2 / Task 2.6 (Driver & Vehicle Verification / Compliance
Foundation). Creates the `verification` schema and its three tables
exactly as specified in docs/04-database/database-design.md §27
(Verification Tables) — verification.cases, verification.evidence,
verification.results. No additive columns, no additive indexes (none are
documented). See docs/14-decisions/ADR-0008-verification-case-scope-and-open-items.md.

Revision ID: c4b8f13e7226
Revises: 19449658334a
Create Date: 2026-08-21 14:20:09.351933

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4b8f13e7226"
down_revision: str | None = "19449658334a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS verification")

    op.create_table(
        "cases",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("subject_type", sa.String(length=30), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("verification_type", sa.String(length=40), nullable=False),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="PENDING"
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="verification",
    )

    op.create_table(
        "evidence",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("verification.cases.id"),
            nullable=False,
        ),
        sa.Column("evidence_uri", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="verification",
    )

    op.create_table(
        "results",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("verification.cases.id"),
            nullable=False,
        ),
        sa.Column("result", sa.String(length=30), nullable=False),
        sa.Column("confidence", sa.Numeric(6, 5), nullable=True),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="verification",
    )


def downgrade() -> None:
    op.drop_table("results", schema="verification")
    op.drop_table("evidence", schema="verification")
    op.drop_table("cases", schema="verification")
    op.execute("DROP SCHEMA IF EXISTS verification CASCADE")
