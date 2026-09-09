"""Application service (use cases) for Admin.

Phase 2 / Task 2.7A. Owns exactly two things: verifying that an
authenticated ADMIN account (identity.accounts.account_type=ADMIN,
modules.identity's existing require_admin) is also a real, ACTIVE
admin.users record, and writing admin.audit_logs rows. Does not itself
implement ApproveDriver/RejectDriver/ApproveVehicle/RejectVehicle — those
are Driver-domain/Vehicle-domain commands (modules/driver/service.py,
modules/vehicle/service.py) composed with this service at the router
layer — see modules/admin/router.py and modules/admin/__init__.py.

ADR-0040 (BR-126/BR-127) extends this with Admin Management: creating/
disabling employee admins and granting/revoking their per-module
permissions. `require_permission()` below is this codebase's actual
implementation of ADR-0040 Decision 4's "require_permission() dependency"
— built as a plain service method called from inside each route's own
try block (like `require_active_admin()` already is), not a separate
FastAPI `Depends()` chain, matching this router's existing convention
for every other DB-backed authorization check.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from modules.admin.domain.entities import (
    AccessLevel,
    AdminModule,
    AdminRole,
    AdminUser,
    AuditLog,
    Permission,
    Setting,
)
from modules.admin.domain.errors import (
    AdminAlreadyExistsError,
    AdminNotFoundError,
    AdminProfileNotFoundError,
    AdminSuspendedError,
    CannotModifySuperAdminError,
    InsufficientPermissionError,
    ModuleNotGrantableError,
    SettingNotFoundError,
)
from modules.admin.ports import AdminRepository, PermissionRepository, SettingRepository
from modules.identity.domain.entities import AccountType
from modules.identity.domain.phone_number import PhoneNumber
from modules.identity.ports import AccountRepository

# BR-126: never grantable to an employee admin via the permissions
# endpoint — only the Super Admin ever holds them.
_UNGRANTABLE_MODULES = frozenset({AdminModule.ADMIN_MANAGEMENT, AdminModule.SETTINGS})


class AdminService:
    def __init__(
        self,
        *,
        admins: AdminRepository,
        permissions: PermissionRepository | None = None,
        accounts: AccountRepository | None = None,
        settings: SettingRepository | None = None,
    ) -> None:
        self._admins = admins
        # Optional (default None), same reasoning
        # modules.notification.service.NotificationService's own
        # sms_provider param already established: callers that never
        # touch Admin Management (every existing driver/vehicle/ride/
        # penalty/gps-dispute route) don't need to wire dependencies
        # they'll never use.
        self._permissions = permissions
        self._accounts = accounts
        # Optional (default None), same reasoning — routes that never
        # touch Settings (everything except ADR-0048's own endpoints)
        # don't need it wired.
        self._settings = settings

    def require_active_admin(self, *, account_id: uuid.UUID) -> AdminUser:
        """No self-service admin-registration endpoint exists — see
        docs/14-decisions/ADR-0009-admin-approval-scope-and-open-items.md
        point B. An authenticated ADMIN-type account with no admin.users
        row yet (not provisioned via scripts/provision_admin.py) is
        rejected here, not silently treated as authorized."""
        admin = self._admins.get_admin_user(account_id)
        if admin is None:
            raise AdminProfileNotFoundError("No admin profile exists for this account.")
        if not admin.is_active:
            raise AdminSuspendedError("This admin account is not active.")
        return admin

    def require_permission(
        self, *, account_id: uuid.UUID, module: AdminModule, level: AccessLevel
    ) -> AdminUser:
        """ADR-0040 Decision 4 / BR-126: a Super Admin passes
        automatically; an employee admin's admin.permissions row for
        `module` must exist and satisfy `level`, or InsufficientPermissionError
        (FORBIDDEN). Calls require_active_admin() first — every existing
        route's separate call to that method is replaced by this one,
        not stacked alongside it."""
        admin = self.require_active_admin(account_id=account_id)
        if admin.is_super_admin:
            return admin
        assert self._permissions is not None, "require_permission() needs permissions"
        granted = self._permissions.get(admin_id=admin.id, module=module)
        if granted is None or not granted.access_level.satisfies(level):
            raise InsufficientPermissionError(
                f"This admin does not have {level.value} access to {module.value}."
            )
        return admin

    def record_audit_log(
        self,
        *,
        admin_id: uuid.UUID,
        action: str,
        target_type: str | None,
        target_id: uuid.UUID | None,
        reason: str | None,
        before_state: dict[str, object] | None,
        after_state: dict[str, object] | None,
        request_id: str | None,
    ) -> AuditLog:
        audit_log = AuditLog.new(
            admin_id=admin_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            reason=reason,
            before_state=before_state,
            after_state=after_state,
            request_id=request_id,
        )
        return self._admins.create_audit_log(audit_log)

    # ------------------------------------------------------------------
    # Admin Management (ADR-0040, BR-126/BR-127) — Super-Admin-only,
    # enforced by the router calling require_permission() with a module
    # no employee admin can ever hold (ADMIN_MANAGEMENT).
    # ------------------------------------------------------------------

    def create_employee_admin(
        self,
        *,
        phone_raw: str,
        grants: list[tuple[AdminModule, AccessLevel]],
        now: datetime,
    ) -> tuple[AdminUser, list[Permission]]:
        """Same identity.accounts reuse-or-create + admin.users insert
        shape as scripts/provision_admin.py's own script (BR-127: "the
        same one scripts/provision_admin.py already uses — no new
        account-creation code") — this is that same operation, now
        reachable by a Super Admin over HTTP instead of only by whoever
        holds infrastructure access."""
        assert self._accounts is not None, "create_employee_admin() needs accounts"
        phone = str(PhoneNumber.parse(phone_raw))
        account = self._accounts.get_by_phone(phone)
        if account is None:
            account = self._accounts.create(account_type=AccountType.ADMIN, phone=phone)
        elif account.account_type is not AccountType.ADMIN:
            raise AdminAlreadyExistsError(
                f"{phone} already exists as a {account.account_type.value} "
                "account, not ADMIN."
            )

        if self._admins.get_admin_user(account.id) is not None:
            raise AdminAlreadyExistsError(
                f"An admin.users row already exists for {phone}."
            )

        admin = self._admins.create_admin_user(
            AdminUser(
                id=account.id,
                role=AdminRole.ADMIN.value,
                status="ACTIVE",
                created_at=now,
            )
        )
        permissions = self._grant(admin_id=admin.id, grants=grants, now=now)
        return admin, permissions

    def list_admins(self, *, offset: int, limit: int) -> tuple[list[AdminUser], int]:
        return self._admins.list_admin_users(offset=offset, limit=limit)

    # ------------------------------------------------------------------
    # Audit Logs (Admin Web module #18) — read-only, so not itself
    # audited (matching Search Rides/Search Penalties' own precedent:
    # only admin *mutations* are audited, never reads).
    # ------------------------------------------------------------------

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
        return self._admins.search_audit_logs(
            admin_id=admin_id,
            target_type=target_type,
            target_id=target_id,
            action=action,
            created_after=created_after,
            created_before=created_before,
            offset=offset,
            limit=limit,
        )

    def get_admin(self, admin_id: uuid.UUID) -> tuple[AdminUser, list[Permission]]:
        admin = self._admins.get_admin_user(admin_id)
        if admin is None:
            raise AdminNotFoundError(f"No admin found for {admin_id}.")
        assert self._permissions is not None, "get_admin() needs permissions"
        return admin, (
            [] if admin.is_super_admin else self._permissions.list_for_admin(admin_id)
        )

    def update_permissions(
        self,
        *,
        admin_id: uuid.UUID,
        grants: list[tuple[AdminModule, AccessLevel]],
        now: datetime,
    ) -> list[Permission]:
        admin = self._admins.get_admin_user(admin_id)
        if admin is None:
            raise AdminNotFoundError(f"No admin found for {admin_id}.")
        if admin.is_super_admin:
            raise CannotModifySuperAdminError(
                "Super Admin accounts are not managed through this endpoint."
            )
        return self._grant(admin_id=admin_id, grants=grants, now=now)

    def _grant(
        self,
        *,
        admin_id: uuid.UUID,
        grants: list[tuple[AdminModule, AccessLevel]],
        now: datetime,
    ) -> list[Permission]:
        for module, _level in grants:
            if module in _UNGRANTABLE_MODULES:
                raise ModuleNotGrantableError(
                    f"{module.value} is never grantable to an employee admin."
                )
        assert self._permissions is not None, "_grant() needs permissions"
        permissions = [
            Permission.new(
                admin_id=admin_id, module=module, access_level=level, now=now
            )
            for module, level in grants
        ]
        return self._permissions.replace_for_admin(
            admin_id=admin_id, permissions=permissions
        )

    def disable_admin(self, admin_id: uuid.UUID) -> AdminUser:
        admin = self._admins.get_admin_user(admin_id)
        if admin is None:
            raise AdminNotFoundError(f"No admin found for {admin_id}.")
        if admin.is_super_admin:
            raise CannotModifySuperAdminError(
                "Super Admin accounts are not managed through this endpoint."
            )
        admin.disable()
        self._admins.save_admin_user(admin)
        return admin

    def enable_admin(self, admin_id: uuid.UUID) -> AdminUser:
        admin = self._admins.get_admin_user(admin_id)
        if admin is None:
            raise AdminNotFoundError(f"No admin found for {admin_id}.")
        if admin.is_super_admin:
            raise CannotModifySuperAdminError(
                "Super Admin accounts are not managed through this endpoint."
            )
        admin.enable()
        self._admins.save_admin_user(admin)
        return admin

    # ------------------------------------------------------------------
    # Settings (ADR-0048) — a fixed, closed vocabulary of keys (Decision
    # 3: no Create/Delete endpoint). PATCH is the only mutation, always
    # audited by the caller (router.py), matching every other admin
    # mutation in this module.
    # ------------------------------------------------------------------

    def get_setting(self, key: str) -> Setting:
        assert self._settings is not None, "get_setting() needs settings"
        setting = self._settings.get(key)
        if setting is None:
            raise SettingNotFoundError(f"No setting found for key {key!r}.")
        return setting

    def list_settings(self, *, category: str | None) -> list[Setting]:
        assert self._settings is not None, "list_settings() needs settings"
        return self._settings.list_all(category=category)

    def update_setting(
        self, *, key: str, value: object, updated_by: uuid.UUID, now: datetime
    ) -> Setting:
        assert self._settings is not None, "update_setting() needs settings"
        setting = self._settings.get_for_update(key)
        if setting is None:
            raise SettingNotFoundError(f"No setting found for key {key!r}.")
        setting.update_value(value=value, updated_by=updated_by, now=now)
        self._settings.save(setting)
        return setting
