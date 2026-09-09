"""Unit tests for the pure Admin domain layer (no DB/HTTP)."""

import uuid
from datetime import UTC, datetime

import pytest

from modules.admin.domain.entities import (
    AccessLevel,
    AdminModule,
    AdminRole,
    AdminUser,
    AuditLog,
    Permission,
)

NOW = datetime.now(UTC)


class TestAdminUser:
    def test_is_active_true_for_active_status(self) -> None:
        admin = AdminUser(
            id=uuid.uuid4(), role="ADMIN", status="ACTIVE", created_at=datetime.now(UTC)
        )
        assert admin.is_active is True

    def test_is_active_false_for_non_active_status(self) -> None:
        admin = AdminUser(
            id=uuid.uuid4(),
            role="ADMIN",
            status="SUSPENDED",
            created_at=datetime.now(UTC),
        )
        assert admin.is_active is False

    def test_is_super_admin_true_only_for_super_admin_role(self) -> None:
        super_admin = AdminUser(
            id=uuid.uuid4(), role="SUPER_ADMIN", status="ACTIVE", created_at=NOW
        )
        employee = AdminUser(
            id=uuid.uuid4(), role="ADMIN", status="ACTIVE", created_at=NOW
        )
        assert super_admin.is_super_admin is True
        assert employee.is_super_admin is False

    def test_disable_sets_status_disabled(self) -> None:
        admin = AdminUser(
            id=uuid.uuid4(), role="ADMIN", status="ACTIVE", created_at=NOW
        )
        admin.disable()
        assert admin.status == "DISABLED"
        assert admin.is_active is False

    def test_enable_sets_status_active(self) -> None:
        admin = AdminUser(
            id=uuid.uuid4(), role="ADMIN", status="DISABLED", created_at=NOW
        )
        admin.enable()
        assert admin.status == "ACTIVE"
        assert admin.is_active is True


class TestAccessLevel:
    def test_manage_satisfies_view(self) -> None:
        assert AccessLevel.MANAGE.satisfies(AccessLevel.VIEW) is True

    def test_manage_satisfies_manage(self) -> None:
        assert AccessLevel.MANAGE.satisfies(AccessLevel.MANAGE) is True

    def test_view_satisfies_view(self) -> None:
        assert AccessLevel.VIEW.satisfies(AccessLevel.VIEW) is True

    def test_view_does_not_satisfy_manage(self) -> None:
        assert AccessLevel.VIEW.satisfies(AccessLevel.MANAGE) is False


class TestPermissionNew:
    def test_new_builds_a_permission_for_a_grantable_module(self) -> None:
        admin_id = uuid.uuid4()

        permission = Permission.new(
            admin_id=admin_id,
            module=AdminModule.DRIVERS,
            access_level=AccessLevel.MANAGE,
            now=NOW,
        )

        assert permission.admin_id == admin_id
        assert permission.module is AdminModule.DRIVERS
        assert permission.access_level is AccessLevel.MANAGE
        assert permission.updated_at == NOW

    @pytest.mark.parametrize(
        "module", [AdminModule.ADMIN_MANAGEMENT, AdminModule.SETTINGS]
    )
    def test_new_raises_for_an_ungrantable_module(self, module: AdminModule) -> None:
        """BR-126: ADMIN_MANAGEMENT/SETTINGS are never grantable — this
        is a defensive invariant (service.py is the primary enforcement
        point, via ModuleNotGrantableError), not the only check."""
        with pytest.raises(ValueError, match="never grantable"):
            Permission.new(
                admin_id=uuid.uuid4(),
                module=module,
                access_level=AccessLevel.VIEW,
                now=NOW,
            )


class TestAdminRole:
    def test_role_values_match_br_126(self) -> None:
        assert AdminRole.SUPER_ADMIN.value == "SUPER_ADMIN"
        assert AdminRole.ADMIN.value == "ADMIN"


class TestAuditLogNew:
    def test_new_has_no_id_or_created_at_until_persisted(self) -> None:
        audit_log = AuditLog.new(
            admin_id=uuid.uuid4(),
            action="APPROVE_DRIVER",
            target_type="DRIVER",
            target_id=uuid.uuid4(),
            reason=None,
            before_state={"verification_status": "PENDING"},
            after_state={"verification_status": "APPROVED"},
            request_id="req_abc123",
        )

        assert audit_log.id is None
        assert audit_log.created_at is None
        assert audit_log.action == "APPROVE_DRIVER"
        assert audit_log.after_state == {"verification_status": "APPROVED"}
