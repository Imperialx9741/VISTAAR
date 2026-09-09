"""Abstract interface (port) the application layer depends on.

Concrete implementation lives in repositories.py. Mirrors the other
modules' ports.py role.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol

from modules.admin.domain.entities import (
    AdminModule,
    AdminUser,
    AuditLog,
    Permission,
    Setting,
)


class AdminRepository(Protocol):
    def get_admin_user(self, admin_id: uuid.UUID) -> AdminUser | None: ...

    def create_audit_log(self, audit_log: AuditLog) -> AuditLog: ...

    # --- Admin Management (ADR-0040) ---

    def create_admin_user(self, admin: AdminUser) -> AdminUser: ...

    def save_admin_user(self, admin: AdminUser) -> None: ...

    def list_admin_users(
        self, *, offset: int, limit: int
    ) -> tuple[list[AdminUser], int]: ...

    # --- Audit Logs (Admin Web module #18) ---

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
        """Newest first (id DESC — a BIGSERIAL PK, so equivalent to
        created_at DESC without needing a separate index).
        created_after/created_before bound created_at (the Admin Web
        plan's own "date range" filter, §4.17), inclusive on both ends."""
        ...


class PermissionRepository(Protocol):
    def list_for_admin(self, admin_id: uuid.UUID) -> list[Permission]: ...

    def replace_for_admin(
        self, *, admin_id: uuid.UUID, permissions: list[Permission]
    ) -> list[Permission]: ...

    def get(self, *, admin_id: uuid.UUID, module: AdminModule) -> Permission | None: ...


class SettingRepository(Protocol):
    """ADR-0048 — Admin Settings."""

    def get(self, key: str) -> Setting | None: ...

    def get_for_update(self, key: str) -> Setting | None:
        """Row-locked, for the PATCH transaction."""
        ...

    def save(self, setting: Setting) -> None:
        """Persists `setting`'s current value/updated_by/updated_at
        back onto the existing row — the only mutation this table
        supports (no Create/Delete, ADR-0048 Decision 3)."""
        ...

    def list_all(self, *, category: str | None) -> list[Setting]:
        """Admin Web §4.19's "List (grouped by category)" — every
        seeded key, optionally filtered to one category. Small, fixed
        set (Decision 2) — no pagination."""
        ...
