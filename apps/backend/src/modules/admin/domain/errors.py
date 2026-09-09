"""Domain-level errors for Admin.

Reuse existing error codes from docs/05-api/api-contracts.md §49 rather
than inventing new ones — FORBIDDEN already covers "authenticated but
not permitted," the exact shape every new error below needs (ADR-0040).
"""

from __future__ import annotations


class AdminDomainError(Exception):
    code: str = "ADMIN_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AdminProfileNotFoundError(AdminDomainError):
    """Raised when an authenticated ADMIN account (identity.accounts,
    account_type=ADMIN) has no corresponding admin.users row yet. No
    self-service admin-registration endpoint exists — see
    docs/14-decisions/ADR-0009-admin-approval-scope-and-open-items.md
    point B for how admin.users rows are actually provisioned
    (scripts/provision_admin.py, run out-of-band)."""

    code = "RESOURCE_NOT_FOUND"


class AdminSuspendedError(AdminDomainError):
    """Raised when an admin.users row exists but its status is not
    ACTIVE."""

    code = "ACCOUNT_SUSPENDED"


class AdminNotFoundError(AdminDomainError):
    """Raised by the Admin Management endpoints (ADR-0040) when the
    target admin_id has no admin.users row at all — distinct from
    AdminProfileNotFoundError, which is about the *caller's own*
    missing profile."""

    code = "RESOURCE_NOT_FOUND"


class InsufficientPermissionError(AdminDomainError):
    """Raised by AdminService.require_permission() when an employee
    admin's admin.permissions row for the required module is missing or
    below the required access level. BR-126: "enforced server-side on
    every request, not only hidden in the Admin Web's own navigation."
    Also what a non-Super-Admin employee admin gets calling any Admin
    Management endpoint — ADMIN_MANAGEMENT is never grantable (BR-126),
    so this same check naturally rejects them; no separate
    "not a Super Admin" error exists."""

    code = "FORBIDDEN"


class ModuleNotGrantableError(AdminDomainError):
    """Raised when a Super Admin attempts to grant ADMIN_MANAGEMENT or
    SETTINGS to an employee admin via the permissions endpoint — BR-126
    marks both never-grantable, not just grantable-by-default-off."""

    code = "VALIDATION_FAILED"


class AdminAlreadyExistsError(AdminDomainError):
    """Raised by Create Employee Admin when the target phone number
    already resolves to an existing admin.users row — mirrors
    scripts/provision_admin.py's own existing refusal, at the HTTP
    layer this time."""

    code = "VALIDATION_FAILED"


class CannotModifySuperAdminError(AdminDomainError):
    """Raised when an Admin Management endpoint (disable, permission
    change) targets a SUPER_ADMIN account — BR-127: Super Admin
    accounts are provisioned out-of-band (the ops script) and are not
    subject to another Super Admin's own admin-management actions
    through this API. Prevents one Super Admin from locking another
    out, and keeps "who can disable a Super Admin" as an
    infrastructure-access-level decision, not an in-app one."""

    code = "FORBIDDEN"


class SettingNotFoundError(AdminDomainError):
    """Raised by Get/Update Setting when `key` has no admin.settings
    row — the set of valid keys is fixed by what the implementing
    migration seeds (ADR-0048 Decision 2/3), a closed vocabulary, not
    client-invented (no Create endpoint exists)."""

    code = "RESOURCE_NOT_FOUND"
