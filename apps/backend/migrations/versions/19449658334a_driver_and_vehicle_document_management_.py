"""driver and vehicle document management foundation

Phase 2 / Task 2.5 (Driver & Vehicle Document Management Foundation).
Creates driver.documents (database-design.md §7.2) and vehicle.documents
(§8.2) exactly as specified, preserving the documented asymmetry between
them: driver.documents has updated_at and two named indexes;
vehicle.documents has neither (no updated_at, no documented indexes).

Revision ID: 19449658334a
Revises: 1f10a4e53685
Create Date: 2026-08-21 13:40:29.627347

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "19449658334a"
down_revision: str | None = "1f10a4e53685"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "driver_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("driver.drivers.id"),
            nullable=False,
        ),
        sa.Column("document_type", sa.String(length=40), nullable=False),
        sa.Column("document_number", sa.String(length=100), nullable=True),
        sa.Column("evidence_uri", sa.Text(), nullable=True),
        sa.Column(
            "verification_status",
            sa.String(length=30),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="driver",
    )
    op.create_index(
        "idx_driver_documents_expiry", "documents", ["expires_at"], schema="driver"
    )
    op.create_index(
        "idx_driver_documents_driver", "documents", ["driver_id"], schema="driver"
    )

    op.create_table(
        "documents",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "vehicle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vehicle.vehicles.id"),
            nullable=False,
        ),
        sa.Column("document_type", sa.String(length=40), nullable=False),
        sa.Column("document_number", sa.String(length=100), nullable=True),
        sa.Column("evidence_uri", sa.Text(), nullable=True),
        sa.Column(
            "verification_status",
            sa.String(length=30),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # No updated_at — database-design.md §8.2 does not document one
        # for vehicle.documents (unlike driver.documents above).
        schema="vehicle",
    )
    # No indexes — database-design.md §8.2 does not document any for
    # vehicle.documents (unlike driver.documents above).


def downgrade() -> None:
    op.drop_table("documents", schema="vehicle")
    op.drop_index(
        "idx_driver_documents_driver", table_name="documents", schema="driver"
    )
    op.drop_index(
        "idx_driver_documents_expiry", table_name="documents", schema="driver"
    )
    op.drop_table("documents", schema="driver")
