"""Admin domain entities.

Field shapes match docs/04-database/database-design.md §33 (Admin
Tables) exactly.

BR-126/BR-127 (2026-08-26, ADR-0040) resolved business-rules.md §43's
"Admin roles"/"Permission hierarchy" TBD markers — `role` is no longer
an unconstrained free-text field this module only ever writes "ADMIN"
into: it now holds exactly one of `AdminRole.SUPER_ADMIN` or
`AdminRole.ADMIN` ("employee admin" in BR-126's own terms), still a
plain VARCHAR(40) column (no DB-level CHECK constraint — the same
"no source document enumerates a closed set to constrain against"
reasoning `status` still uses), with the closed set now enforced at the
application layer via this StrEnum instead. `status` remains a bare
string (`_ACTIVE_STATUS` below) — BR-126/BR-127 didn't touch it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

_ACTIVE_STATUS = "ACTIVE"  # database-design.md §33.1's documented default
_DISABLED_STATUS = "DISABLED"


class AdminRole(StrEnum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"


class AdminModule(StrEnum):
    """BR-126's own catalog — the same 20 modules the Admin Web's
    navigation uses (docs/15-admin-web/admin-web-implementation-plan.md
    §2.1), one source of truth for both the permission-check dependency
    and (via this same enum, surfaced through the API) the frontend
    nav. ADMIN_MANAGEMENT and SETTINGS are deliberately never grantable
    via `admin.permissions` — BR-126's own rule, enforced in
    service.py, not by omitting them from this enum (they still need to
    exist as valid `AdminModule` values for other purposes, e.g. listing
    "every module" in a UI catalog)."""

    DASHBOARD = "DASHBOARD"
    CUSTOMERS = "CUSTOMERS"
    DRIVERS = "DRIVERS"
    VEHICLES = "VEHICLES"
    VERIFICATION = "VERIFICATION"
    RIDES = "RIDES"
    MATCHING = "MATCHING"
    FINANCE = "FINANCE"
    FARE_MANAGEMENT = "FARE_MANAGEMENT"
    PENALTIES = "PENALTIES"
    OFFERS_COUPONS = "OFFERS_COUPONS"
    REFERRALS = "REFERRALS"
    NOTIFICATIONS = "NOTIFICATIONS"
    SAFETY = "SAFETY"
    SUPPORT = "SUPPORT"
    ADVERTISEMENTS = "ADVERTISEMENTS"
    REPORTS = "REPORTS"
    AUDIT_LOGS = "AUDIT_LOGS"
    ADMIN_MANAGEMENT = "ADMIN_MANAGEMENT"
    SETTINGS = "SETTINGS"


# BR-126: "never grantable to an employee admin — only the Super Admin
# ever holds them, and this is not configurable."
_UNGRANTABLE_MODULES = frozenset({AdminModule.ADMIN_MANAGEMENT, AdminModule.SETTINGS})


class AccessLevel(StrEnum):
    VIEW = "VIEW"
    MANAGE = "MANAGE"

    def satisfies(self, required: AccessLevel) -> bool:
        """MANAGE satisfies a VIEW requirement; VIEW does not satisfy a
        MANAGE requirement."""
        if self is AccessLevel.MANAGE:
            return True
        return self is required


@dataclass(slots=True)
class AdminUser:
    id: uuid.UUID  # == identity.accounts.id (shared primary key)
    role: str
    status: str
    created_at: datetime

    @property
    def is_active(self) -> bool:
        return self.status == _ACTIVE_STATUS

    @property
    def is_super_admin(self) -> bool:
        return self.role == AdminRole.SUPER_ADMIN.value

    def disable(self) -> None:
        self.status = _DISABLED_STATUS

    def enable(self) -> None:
        self.status = _ACTIVE_STATUS


@dataclass(slots=True)
class Permission:
    id: uuid.UUID
    admin_id: uuid.UUID
    module: AdminModule
    access_level: AccessLevel
    updated_at: datetime

    @staticmethod
    def new(
        *,
        admin_id: uuid.UUID,
        module: AdminModule,
        access_level: AccessLevel,
        now: datetime,
    ) -> Permission:
        if module in _UNGRANTABLE_MODULES:
            # Caller (service.py) is expected to have already rejected
            # this — see AdminManagementNotGrantableError. This is a
            # defensive invariant, not the primary enforcement point.
            raise ValueError(f"{module.value} is never grantable.")
        return Permission(
            id=uuid.uuid4(),
            admin_id=admin_id,
            module=module,
            access_level=access_level,
            updated_at=now,
        )


@dataclass(slots=True)
class AuditLog:
    id: int | None  # None until persisted (BIGSERIAL — database-assigned)
    admin_id: uuid.UUID
    action: str
    target_type: str | None
    target_id: uuid.UUID | None
    reason: str | None
    before_state: dict[str, object] | None
    after_state: dict[str, object] | None
    request_id: str | None
    created_at: datetime | None  # None until persisted (server_default NOW())

    @staticmethod
    def new(
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
        return AuditLog(
            id=None,
            admin_id=admin_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            reason=reason,
            before_state=before_state,
            after_state=after_state,
            request_id=request_id,
            created_at=None,
        )


class SettingCategory(StrEnum):
    """ADR-0048 Decision 1 — the four categories `admin.settings`
    actually owns. Fare/platform-fee/referral/notification settings
    are NOT categories here: they already have their own dedicated,
    versioned screens (ADR-0042/0045/0043/0044) — duplicating them into
    this generic table would create two sources of truth for one
    number, the exact mistake ADR-0041 §7 already established this
    codebase avoids."""

    PROMOTION_DEFAULT = "PROMOTION_DEFAULT"
    OPERATIONAL_THRESHOLD = "OPERATIONAL_THRESHOLD"
    FEATURE_FLAG = "FEATURE_FLAG"
    GENERAL = "GENERAL"


@dataclass(slots=True)
class Setting:
    """A single admin.settings row. No Create/Delete — the set of valid
    keys is fixed by what the implementing migration seeds (ADR-0048
    Decision 2); PATCH is the only mutation, and always audited by the
    caller (before_state/after_state capture the full old/new value —
    see modules/admin/router.py)."""

    key: str
    value: object
    category: SettingCategory
    description: str
    updated_by: uuid.UUID
    updated_at: datetime

    def update_value(
        self, *, value: object, updated_by: uuid.UUID, now: datetime
    ) -> None:
        self.value = value
        self.updated_by = updated_by
        self.updated_at = now
