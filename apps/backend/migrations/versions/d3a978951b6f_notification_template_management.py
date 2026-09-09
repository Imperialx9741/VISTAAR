"""notification template management

Notification Template Management (ADR-0044). Adds
notification.templates — an append-only version chain per
(template_key, channel), DRAFT -> PUBLISHED (not effective-dated, and
not the DRAFT/IN_REVIEW/PUBLISHED lifecycle the other 2026-08-26 config
ADRs use; see ADR-0044 Decision 1 for why templates are simpler:
"version history", not "effective dating"). Adds
notification.deliveries.template_version_id (additive, nullable) so a
delivery row can prove after the fact exactly what content was
rendered, even if the template is edited later. Seeds one PUBLISHED
version-1 row for each of today's two hardcoded SMS templates
(RIDE_ACCEPTED, RIDE_ARRIVED — modules/notification/domain/
templates.py's SMS_TEMPLATES dict) so nothing changes the moment this
ships; that dict remains as a last-resort fallback only, same treatment
ADR-0043 gave its own old hardcoded constants.

Revision ID: d3a978951b6f
Revises: ed6bbec11c17
Create Date: 2026-08-26 00:00:00.000000

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d3a978951b6f"
down_revision: str | None = "ed6bbec11c17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SMS_TEMPLATE_SEED = {
    "RIDE_ACCEPTED": (
        "Your VISTAAR ride has been accepted. Your driver is on the way "
        "to the pickup point."
    ),
    "RIDE_ARRIVED": (
        "Your VISTAAR driver has arrived at the pickup point. Please "
        "share your OTP with the driver to start the ride."
    ),
}


def upgrade() -> None:
    op.create_table(
        "templates",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("template_key", sa.String(length=50), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("event_key", sa.String(length=50), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="DRAFT"
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["created_by"], ["admin.users.id"]),
        schema="notification",
    )
    op.create_index(
        "uq_notification_templates_one_published",
        "templates",
        ["template_key", "channel"],
        unique=True,
        schema="notification",
        postgresql_where=sa.text("status = 'PUBLISHED'"),
    )

    op.add_column(
        "deliveries",
        sa.Column(
            "template_version_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        schema="notification",
    )
    op.create_foreign_key(
        "fk_notification_deliveries_template_version_id",
        "deliveries",
        "templates",
        ["template_version_id"],
        ["id"],
        source_schema="notification",
        referent_schema="notification",
    )

    # Seed one PUBLISHED version-1 row per today's hardcoded SMS
    # template, backed by a real admin.users row — same synthetic-
    # system-admin fallback ADR-0043's migration established, reused
    # verbatim rather than re-derived (ops-only, same trust level as
    # `alembic upgrade head` itself).
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

    for template_key, body in _SMS_TEMPLATE_SEED.items():
        connection.execute(
            sa.text(
                "INSERT INTO notification.templates "
                "(id, template_key, channel, body, version, status, created_by) "
                "VALUES (:id, :template_key, 'SMS', :body, 1, 'PUBLISHED', :admin_id)"
            ),
            {
                "id": str(uuid.uuid4()),
                "template_key": template_key,
                "body": body,
                "admin_id": str(admin_id),
            },
        )


def downgrade() -> None:
    op.drop_constraint(
        "fk_notification_deliveries_template_version_id",
        "deliveries",
        schema="notification",
        type_="foreignkey",
    )
    op.drop_column("deliveries", "template_version_id", schema="notification")
    op.drop_index(
        "uq_notification_templates_one_published",
        table_name="templates",
        schema="notification",
    )
    op.drop_table("templates", schema="notification")
