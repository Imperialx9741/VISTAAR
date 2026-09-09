"""gps_disputes_and_evidence

BR-124/BR-125 (business-rules.md §39, approved 2026-08-25), ADR-0032.
Creates ride.gps_disputes and ride.gps_dispute_evidence exactly as
specified in docs/04-database/database-design.md §14.2/§14.3.

Revision ID: 691121cccb6a
Revises: 6ce26a4f7fd4
Create Date: 2026-08-25 15:00:16.400938

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "691121cccb6a"
down_revision: str | None = "6ce26a4f7fd4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gps_disputes",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "ride_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ride.rides.id"),
            nullable=False,
        ),
        sa.Column(
            "gps_verification_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ride.gps_verifications.id"),
            nullable=False,
        ),
        sa.Column("verification_type", sa.String(length=30), nullable=False),
        sa.Column(
            "opened_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("evidence_deadline", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="OPEN"
        ),
        sa.Column("decision", sa.String(length=20), nullable=True),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_reason", sa.String(length=500), nullable=True),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="ride",
    )
    op.create_index("idx_gps_disputes_ride", "gps_disputes", ["ride_id"], schema="ride")
    op.create_index(
        "idx_gps_disputes_status", "gps_disputes", ["status"], schema="ride"
    )

    op.create_table(
        "gps_dispute_evidence",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "dispute_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ride.gps_disputes.id"),
            nullable=False,
        ),
        sa.Column("submitted_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_type", sa.String(length=20), nullable=False),
        sa.Column("uri", sa.Text(), nullable=True),
        sa.Column("text_explanation", sa.Text(), nullable=True),
        sa.Column(
            "submitted_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="ride",
    )
    op.create_index(
        "idx_gps_dispute_evidence_dispute",
        "gps_dispute_evidence",
        ["dispute_id"],
        schema="ride",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_gps_dispute_evidence_dispute",
        table_name="gps_dispute_evidence",
        schema="ride",
    )
    op.drop_table("gps_dispute_evidence", schema="ride")
    op.drop_index("idx_gps_disputes_status", table_name="gps_disputes", schema="ride")
    op.drop_index("idx_gps_disputes_ride", table_name="gps_disputes", schema="ride")
    op.drop_table("gps_disputes", schema="ride")
