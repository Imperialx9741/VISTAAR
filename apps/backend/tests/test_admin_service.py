"""Unit tests for AdminService against in-memory fake repositories."""

from __future__ import annotations

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
from modules.admin.domain.errors import (
    AdminAlreadyExistsError,
    AdminNotFoundError,
    AdminProfileNotFoundError,
    AdminSuspendedError,
    CannotModifySuperAdminError,
    InsufficientPermissionError,
    ModuleNotGrantableError,
)
from modules.admin.service import AdminService
from modules.identity.domain.entities import Account, AccountStatus, AccountType

NOW = datetime.now(UTC)


class FakeAdminRepository:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, AdminUser] = {}
        self.audit_logs: list[AuditLog] = []

    def get_admin_user(self, admin_id: uuid.UUID) -> AdminUser | None:
        return self.by_id.get(admin_id)

    def create_audit_log(self, audit_log: AuditLog) -> AuditLog:
        persisted = AuditLog(
            id=len(self.audit_logs) + 1,
            admin_id=audit_log.admin_id,
            action=audit_log.action,
            target_type=audit_log.target_type,
            target_id=audit_log.target_id,
            reason=audit_log.reason,
            before_state=audit_log.before_state,
            after_state=audit_log.after_state,
            request_id=audit_log.request_id,
            created_at=datetime.now(UTC),
        )
        self.audit_logs.append(persisted)
        return persisted

    def create_admin_user(self, admin: AdminUser) -> AdminUser:
        self.by_id[admin.id] = admin
        return admin

    def save_admin_user(self, admin: AdminUser) -> None:
        if admin.id not in self.by_id:
            raise LookupError(f"AdminUser {admin.id} not found")
        self.by_id[admin.id] = admin

    def list_admin_users(
        self, *, offset: int, limit: int
    ) -> tuple[list[AdminUser], int]:
        rows = sorted(self.by_id.values(), key=lambda a: a.created_at, reverse=True)
        return rows[offset : offset + limit], len(rows)

    def search_audit_logs(
        self,
        *,
        admin_id: uuid.UUID | None,
        target_type: str | None,
        target_id: uuid.UUID | None,
        action: str | None,
        created_after: datetime | None,
        created_before: datetime | None,
        offset: int,
        limit: int,
    ) -> tuple[list[AuditLog], int]:
        def matches(log: AuditLog) -> bool:
            if admin_id is not None and log.admin_id != admin_id:
                return False
            if target_type is not None and log.target_type != target_type:
                return False
            if target_id is not None and log.target_id != target_id:
                return False
            if action is not None and log.action != action:
                return False
            if created_after is not None and (
                log.created_at is None or log.created_at < created_after
            ):
                return False
            if created_before is not None and (
                log.created_at is None or log.created_at > created_before
            ):
                return False
            return True

        matched = sorted(
            (log for log in self.audit_logs if matches(log)),
            key=lambda log: log.id or 0,
            reverse=True,
        )
        return matched[offset : offset + limit], len(matched)


class FakePermissionRepository:
    def __init__(self) -> None:
        self.rows: dict[tuple[uuid.UUID, AdminModule], Permission] = {}

    def list_for_admin(self, admin_id: uuid.UUID) -> list[Permission]:
        return [p for (aid, _module), p in self.rows.items() if aid == admin_id]

    def replace_for_admin(
        self, *, admin_id: uuid.UUID, permissions: list[Permission]
    ) -> list[Permission]:
        for key in [k for k in self.rows if k[0] == admin_id]:
            del self.rows[key]
        for p in permissions:
            self.rows[(admin_id, p.module)] = p
        return self.list_for_admin(admin_id)

    def get(self, *, admin_id: uuid.UUID, module: AdminModule) -> Permission | None:
        return self.rows.get((admin_id, module))


class FakeAccountRepository:
    def __init__(self) -> None:
        self.by_phone: dict[str, Account] = {}
        self.by_id: dict[uuid.UUID, Account] = {}

    def get_by_phone(self, phone: str) -> Account | None:
        return self.by_phone.get(phone)

    def get_by_id(self, account_id: uuid.UUID) -> Account | None:
        return self.by_id.get(account_id)

    def create(self, *, account_type: AccountType, phone: str) -> Account:
        account = Account(
            id=uuid.uuid4(),
            account_type=account_type,
            phone=phone,
            status=AccountStatus.ACTIVE,
            created_at=NOW,
            updated_at=NOW,
        )
        self.by_phone[phone] = account
        self.by_id[account.id] = account
        return account


@pytest.fixture
def repo() -> FakeAdminRepository:
    return FakeAdminRepository()


@pytest.fixture
def permissions() -> FakePermissionRepository:
    return FakePermissionRepository()


@pytest.fixture
def accounts() -> FakeAccountRepository:
    return FakeAccountRepository()


@pytest.fixture
def service(
    repo: FakeAdminRepository,
    permissions: FakePermissionRepository,
    accounts: FakeAccountRepository,
) -> AdminService:
    return AdminService(admins=repo, permissions=permissions, accounts=accounts)


ADMIN_ID = uuid.uuid4()


def test_require_active_admin_raises_when_no_admin_user_row(
    service: AdminService, repo: FakeAdminRepository
) -> None:
    with pytest.raises(AdminProfileNotFoundError):
        service.require_active_admin(account_id=ADMIN_ID)


def test_require_active_admin_raises_when_suspended(
    service: AdminService, repo: FakeAdminRepository
) -> None:
    repo.by_id[ADMIN_ID] = AdminUser(
        id=ADMIN_ID, role="ADMIN", status="SUSPENDED", created_at=datetime.now(UTC)
    )

    with pytest.raises(AdminSuspendedError):
        service.require_active_admin(account_id=ADMIN_ID)


def test_require_active_admin_succeeds_when_active(
    service: AdminService, repo: FakeAdminRepository
) -> None:
    repo.by_id[ADMIN_ID] = AdminUser(
        id=ADMIN_ID, role="ADMIN", status="ACTIVE", created_at=datetime.now(UTC)
    )

    admin = service.require_active_admin(account_id=ADMIN_ID)

    assert admin.id == ADMIN_ID


def test_record_audit_log_persists_and_returns_the_row(
    service: AdminService, repo: FakeAdminRepository
) -> None:
    target_id = uuid.uuid4()

    audit_log = service.record_audit_log(
        admin_id=ADMIN_ID,
        action="APPROVE_DRIVER",
        target_type="DRIVER",
        target_id=target_id,
        reason=None,
        before_state={"verification_status": "PENDING"},
        after_state={"verification_status": "APPROVED"},
        request_id="req_abc123",
    )

    assert audit_log.id is not None
    assert audit_log.created_at is not None
    assert len(repo.audit_logs) == 1
    assert repo.audit_logs[0].target_id == target_id


# --- require_permission() (ADR-0040) ----------------------------------


def test_require_permission_super_admin_bypasses_the_permission_table(
    service: AdminService, repo: FakeAdminRepository
) -> None:
    repo.by_id[ADMIN_ID] = AdminUser(
        id=ADMIN_ID, role=AdminRole.SUPER_ADMIN.value, status="ACTIVE", created_at=NOW
    )

    admin = service.require_permission(
        account_id=ADMIN_ID, module=AdminModule.DRIVERS, level=AccessLevel.MANAGE
    )

    assert admin.is_super_admin


def test_require_permission_raises_when_no_permission_row_exists(
    service: AdminService, repo: FakeAdminRepository
) -> None:
    repo.by_id[ADMIN_ID] = AdminUser(
        id=ADMIN_ID, role=AdminRole.ADMIN.value, status="ACTIVE", created_at=NOW
    )

    with pytest.raises(InsufficientPermissionError):
        service.require_permission(
            account_id=ADMIN_ID, module=AdminModule.DRIVERS, level=AccessLevel.VIEW
        )


def test_require_permission_view_row_does_not_satisfy_manage(
    service: AdminService,
    repo: FakeAdminRepository,
    permissions: FakePermissionRepository,
) -> None:
    repo.by_id[ADMIN_ID] = AdminUser(
        id=ADMIN_ID, role=AdminRole.ADMIN.value, status="ACTIVE", created_at=NOW
    )
    permissions.rows[(ADMIN_ID, AdminModule.DRIVERS)] = Permission.new(
        admin_id=ADMIN_ID,
        module=AdminModule.DRIVERS,
        access_level=AccessLevel.VIEW,
        now=NOW,
    )

    with pytest.raises(InsufficientPermissionError):
        service.require_permission(
            account_id=ADMIN_ID, module=AdminModule.DRIVERS, level=AccessLevel.MANAGE
        )


def test_require_permission_manage_row_satisfies_view(
    service: AdminService,
    repo: FakeAdminRepository,
    permissions: FakePermissionRepository,
) -> None:
    repo.by_id[ADMIN_ID] = AdminUser(
        id=ADMIN_ID, role=AdminRole.ADMIN.value, status="ACTIVE", created_at=NOW
    )
    permissions.rows[(ADMIN_ID, AdminModule.DRIVERS)] = Permission.new(
        admin_id=ADMIN_ID,
        module=AdminModule.DRIVERS,
        access_level=AccessLevel.MANAGE,
        now=NOW,
    )

    admin = service.require_permission(
        account_id=ADMIN_ID, module=AdminModule.DRIVERS, level=AccessLevel.VIEW
    )

    assert admin.id == ADMIN_ID


def test_require_permission_employee_admin_cannot_reach_admin_management(
    service: AdminService,
    repo: FakeAdminRepository,
    permissions: FakePermissionRepository,
) -> None:
    """ADMIN_MANAGEMENT is never grantable (BR-126) — there is no row
    to ever satisfy this check for an employee admin, even one with
    permissions on every other module."""
    repo.by_id[ADMIN_ID] = AdminUser(
        id=ADMIN_ID, role=AdminRole.ADMIN.value, status="ACTIVE", created_at=NOW
    )

    with pytest.raises(InsufficientPermissionError):
        service.require_permission(
            account_id=ADMIN_ID,
            module=AdminModule.ADMIN_MANAGEMENT,
            level=AccessLevel.VIEW,
        )


# --- create_employee_admin() (ADR-0040) --------------------------------


def test_create_employee_admin_creates_a_new_account_and_admin_row(
    service: AdminService,
    repo: FakeAdminRepository,
    accounts: FakeAccountRepository,
) -> None:
    admin, perms = service.create_employee_admin(
        phone_raw="+919876543210",
        grants=[(AdminModule.DRIVERS, AccessLevel.MANAGE)],
        now=NOW,
    )

    assert admin.role == AdminRole.ADMIN.value
    assert admin.status == "ACTIVE"
    assert repo.by_id[admin.id] is admin
    assert accounts.by_id[admin.id].account_type is AccountType.ADMIN
    assert len(perms) == 1
    assert perms[0].module is AdminModule.DRIVERS


def test_create_employee_admin_reuses_an_existing_admin_type_account(
    service: AdminService, accounts: FakeAccountRepository
) -> None:
    existing = accounts.create(account_type=AccountType.ADMIN, phone="+919876543210")

    admin, _perms = service.create_employee_admin(
        phone_raw="+919876543210", grants=[], now=NOW
    )

    assert admin.id == existing.id


def test_create_employee_admin_refuses_a_non_admin_account(
    service: AdminService, accounts: FakeAccountRepository
) -> None:
    accounts.create(account_type=AccountType.DRIVER, phone="+919876543210")

    with pytest.raises(AdminAlreadyExistsError):
        service.create_employee_admin(phone_raw="+919876543210", grants=[], now=NOW)


def test_create_employee_admin_refuses_a_phone_already_provisioned_as_admin(
    service: AdminService, repo: FakeAdminRepository, accounts: FakeAccountRepository
) -> None:
    account = accounts.create(account_type=AccountType.ADMIN, phone="+919876543210")
    repo.by_id[account.id] = AdminUser(
        id=account.id, role=AdminRole.ADMIN.value, status="ACTIVE", created_at=NOW
    )

    with pytest.raises(AdminAlreadyExistsError):
        service.create_employee_admin(phone_raw="+919876543210", grants=[], now=NOW)


def test_create_employee_admin_refuses_granting_admin_management(
    service: AdminService,
) -> None:
    with pytest.raises(ModuleNotGrantableError):
        service.create_employee_admin(
            phone_raw="+919876543210",
            grants=[(AdminModule.ADMIN_MANAGEMENT, AccessLevel.VIEW)],
            now=NOW,
        )


def test_create_employee_admin_refuses_granting_settings(
    service: AdminService,
) -> None:
    with pytest.raises(ModuleNotGrantableError):
        service.create_employee_admin(
            phone_raw="+919876543210",
            grants=[(AdminModule.SETTINGS, AccessLevel.VIEW)],
            now=NOW,
        )


# --- list_admins() / get_admin() ---------------------------------------


def test_list_admins_paginates_and_counts(
    service: AdminService, repo: FakeAdminRepository
) -> None:
    for _ in range(3):
        aid = uuid.uuid4()
        repo.by_id[aid] = AdminUser(
            id=aid, role=AdminRole.ADMIN.value, status="ACTIVE", created_at=NOW
        )

    admins, total = service.list_admins(offset=0, limit=2)

    assert total == 3
    assert len(admins) == 2


def test_get_admin_raises_when_not_found(service: AdminService) -> None:
    with pytest.raises(AdminNotFoundError):
        service.get_admin(uuid.uuid4())


def test_get_admin_returns_its_permissions(
    service: AdminService,
    repo: FakeAdminRepository,
    permissions: FakePermissionRepository,
) -> None:
    repo.by_id[ADMIN_ID] = AdminUser(
        id=ADMIN_ID, role=AdminRole.ADMIN.value, status="ACTIVE", created_at=NOW
    )
    permissions.rows[(ADMIN_ID, AdminModule.RIDES)] = Permission.new(
        admin_id=ADMIN_ID,
        module=AdminModule.RIDES,
        access_level=AccessLevel.VIEW,
        now=NOW,
    )

    admin, perms = service.get_admin(ADMIN_ID)

    assert admin.id == ADMIN_ID
    assert [p.module for p in perms] == [AdminModule.RIDES]


def test_get_admin_never_lists_permission_rows_for_a_super_admin(
    service: AdminService,
    repo: FakeAdminRepository,
    permissions: FakePermissionRepository,
) -> None:
    repo.by_id[ADMIN_ID] = AdminUser(
        id=ADMIN_ID, role=AdminRole.SUPER_ADMIN.value, status="ACTIVE", created_at=NOW
    )

    _admin, perms = service.get_admin(ADMIN_ID)

    assert perms == []


# --- update_permissions() / disable_admin() / enable_admin() -----------


def test_update_permissions_replaces_the_whole_set(
    service: AdminService,
    repo: FakeAdminRepository,
    permissions: FakePermissionRepository,
) -> None:
    repo.by_id[ADMIN_ID] = AdminUser(
        id=ADMIN_ID, role=AdminRole.ADMIN.value, status="ACTIVE", created_at=NOW
    )
    permissions.rows[(ADMIN_ID, AdminModule.RIDES)] = Permission.new(
        admin_id=ADMIN_ID,
        module=AdminModule.RIDES,
        access_level=AccessLevel.VIEW,
        now=NOW,
    )

    result = service.update_permissions(
        admin_id=ADMIN_ID,
        grants=[(AdminModule.DRIVERS, AccessLevel.MANAGE)],
        now=NOW,
    )

    assert [p.module for p in result] == [AdminModule.DRIVERS]
    assert permissions.get(admin_id=ADMIN_ID, module=AdminModule.RIDES) is None


def test_update_permissions_refuses_to_target_a_super_admin(
    service: AdminService, repo: FakeAdminRepository
) -> None:
    repo.by_id[ADMIN_ID] = AdminUser(
        id=ADMIN_ID, role=AdminRole.SUPER_ADMIN.value, status="ACTIVE", created_at=NOW
    )

    with pytest.raises(CannotModifySuperAdminError):
        service.update_permissions(admin_id=ADMIN_ID, grants=[], now=NOW)


def test_update_permissions_refuses_ungrantable_modules(
    service: AdminService, repo: FakeAdminRepository
) -> None:
    repo.by_id[ADMIN_ID] = AdminUser(
        id=ADMIN_ID, role=AdminRole.ADMIN.value, status="ACTIVE", created_at=NOW
    )

    with pytest.raises(ModuleNotGrantableError):
        service.update_permissions(
            admin_id=ADMIN_ID,
            grants=[(AdminModule.SETTINGS, AccessLevel.MANAGE)],
            now=NOW,
        )


def test_disable_admin_sets_status_disabled(
    service: AdminService, repo: FakeAdminRepository
) -> None:
    repo.by_id[ADMIN_ID] = AdminUser(
        id=ADMIN_ID, role=AdminRole.ADMIN.value, status="ACTIVE", created_at=NOW
    )

    admin = service.disable_admin(ADMIN_ID)

    assert admin.status == "DISABLED"
    assert repo.by_id[ADMIN_ID].status == "DISABLED"


def test_disable_admin_refuses_to_target_a_super_admin(
    service: AdminService, repo: FakeAdminRepository
) -> None:
    repo.by_id[ADMIN_ID] = AdminUser(
        id=ADMIN_ID, role=AdminRole.SUPER_ADMIN.value, status="ACTIVE", created_at=NOW
    )

    with pytest.raises(CannotModifySuperAdminError):
        service.disable_admin(ADMIN_ID)


def test_enable_admin_sets_status_active(
    service: AdminService, repo: FakeAdminRepository
) -> None:
    repo.by_id[ADMIN_ID] = AdminUser(
        id=ADMIN_ID, role=AdminRole.ADMIN.value, status="DISABLED", created_at=NOW
    )

    admin = service.enable_admin(ADMIN_ID)

    assert admin.status == "ACTIVE"


def test_disabled_admin_fails_require_active_admin(
    service: AdminService, repo: FakeAdminRepository
) -> None:
    repo.by_id[ADMIN_ID] = AdminUser(
        id=ADMIN_ID, role=AdminRole.ADMIN.value, status="ACTIVE", created_at=NOW
    )
    service.disable_admin(ADMIN_ID)

    with pytest.raises(AdminSuspendedError):
        service.require_active_admin(account_id=ADMIN_ID)
