"""pricing foundation and cab tiers

Phase 04's "Initial fare quote" task, scoped per ADR-0020 (Pricing
Foundation, CAB Tiers, and the Ride-Creation Fare/Promotion
Composition). Creates pricing.fare_rules/fare_quotes exactly as
specified in docs/04-database/database-design.md §15.1-§15.2 (plus one
additive column, fare_rules.minimum_fare — see the ADR), seeds
fare_rules with the owner-approved rates, and adds vehicle.vehicles.
cab_tier / ride.rides.requested_cab_tier (both additive, nullable —
CAB-only sub-tier selection, ADR-0020 Decision 1).

Revision ID: 61a5a80a044e
Revises: ddc5e2ce287d
Create Date: 2026-08-24 16:24:49.591187

"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "61a5a80a044e"
down_revision: str | None = "ddc5e2ce287d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ADR-0020 §1/§2 — the owner-approved fare table. vehicle_category here
# is fare_rules' own key (VARCHAR(20), not a foreign key to any enum —
# database-design.md §15.1 documents it as a free-form string precisely
# so it can outgrow the 3-category VehicleCategory enum without a schema
# change, per business-rules.md §2's "architecture must allow additional
# vehicle categories to be introduced later"). CAB_ECO/CAB_PREMIUM/
# CAB_PREMIUM_PLUS are an engineering choice for that string's content,
# not an invented business rule.
_FARE_RULES = [
    # vehicle_category, base_fare, per_km, per_minute, waiting_per_minute, minimum_fare
    ("BIKE", "29.00", "7.00", "0.00", "1.00", "39.00"),
    ("AUTO", "39.00", "10.00", "0.00", "2.00", "59.00"),
    ("CAB_ECO", "55.00", "12.00", "0.00", "2.00", "79.00"),
    ("CAB_PREMIUM", "65.00", "14.00", "0.00", "2.00", "99.00"),
    ("CAB_PREMIUM_PLUS", "85.00", "18.00", "0.00", "3.00", "129.00"),
]


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS pricing")

    op.create_table(
        "fare_rules",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("vehicle_category", sa.String(length=20), nullable=False),
        sa.Column("base_fare", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("per_km", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("per_minute", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "waiting_per_minute",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
        # Additive beyond database-design.md §15.1 — see ADR-0020
        # Decision 4: the table's own "Minimum fare" line item has no
        # documented column otherwise.
        sa.Column("minimum_fare", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("effective_from", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("effective_until", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="pricing",
    )

    op.create_table(
        "fare_quotes",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "ride_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ride.rides.id"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "base_fare",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "distance_charge",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "time_charge",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "waiting_charge",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "parking_charge",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "toll_charge",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "tax_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "promotion_discount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "additional_charge",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("total", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("reason", sa.String(length=50), nullable=True),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="DRAFT"
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="pricing",
    )
    op.create_index(
        "uq_fare_quote_version",
        "fare_quotes",
        ["ride_id", "version"],
        unique=True,
        schema="pricing",
    )

    # ADR-0020 Decision 1 — CAB-only sub-tier, additive/nullable on both
    # sides of the same selection (driver self-declares at vehicle
    # creation; customer selects at ride request).
    op.add_column(
        "vehicles",
        sa.Column("cab_tier", sa.String(length=20), nullable=True),
        schema="vehicle",
    )
    op.add_column(
        "rides",
        sa.Column("requested_cab_tier", sa.String(length=20), nullable=True),
        schema="ride",
    )

    fare_rules_table = sa.table(
        "fare_rules",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("vehicle_category", sa.String),
        sa.column("base_fare", sa.Numeric),
        sa.column("per_km", sa.Numeric),
        sa.column("per_minute", sa.Numeric),
        sa.column("waiting_per_minute", sa.Numeric),
        sa.column("minimum_fare", sa.Numeric),
        sa.column("effective_from", sa.TIMESTAMP),
        schema="pricing",
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        fare_rules_table,
        [
            {
                "id": uuid.uuid4(),
                "vehicle_category": category,
                "base_fare": base_fare,
                "per_km": per_km,
                "per_minute": per_minute,
                "waiting_per_minute": waiting_per_minute,
                "minimum_fare": minimum_fare,
                "effective_from": now,
            }
            for category, base_fare, per_km, per_minute, waiting_per_minute, minimum_fare in _FARE_RULES
        ],
    )


def downgrade() -> None:
    op.drop_column("rides", "requested_cab_tier", schema="ride")
    op.drop_column("vehicles", "cab_tier", schema="vehicle")
    op.drop_index("uq_fare_quote_version", table_name="fare_quotes", schema="pricing")
    op.drop_table("fare_quotes", schema="pricing")
    op.drop_table("fare_rules", schema="pricing")
    op.execute("DROP SCHEMA IF EXISTS pricing CASCADE")
