"""SQLAlchemy-backed implementation of AdminRepository/PermissionRepository.

Translates between the ORM row (models.py) and the pure domain entity
(domain/entities.py) — mirrors the other modules' repositories.py role.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from modules.admin.domain.entities import (
    AccessLevel,
    AdminModule,
    AdminUser,
    AuditLog,
    Permission,
    Setting,
    SettingCategory,
)
from modules.admin.models import (
    AdminUserORM,
    AuditLogORM,
    PermissionORM,
    SettingORM,
)


def _admin_user_from_orm(row: AdminUserORM) -> AdminUser:
    return AdminUser(
        id=row.id,
        role=row.role,
        status=row.status,
        created_at=row.created_at,
    )


def _audit_log_from_orm(row: AuditLogORM) -> AuditLog:
    return AuditLog(
        id=row.id,
        admin_id=row.admin_id,
        action=row.action,
        target_type=row.target_type,
        target_id=row.target_id,
        reason=row.reason,
        before_state=row.before_state,
        after_state=row.after_state,
        request_id=row.request_id,
        created_at=row.created_at,
    )


def _permission_from_orm(row: PermissionORM) -> Permission:
    return Permission(
        id=row.id,
        admin_id=row.admin_id,
        module=AdminModule(row.module),
        access_level=AccessLevel(row.access_level),
        updated_at=row.updated_at,
    )


class SqlAlchemyAdminRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def get_admin_user(self, admin_id: uuid.UUID) -> AdminUser | None:
        row = self._db.get(AdminUserORM, admin_id)
        return _admin_user_from_orm(row) if row else None

    def create_audit_log(self, audit_log: AuditLog) -> AuditLog:
        row = AuditLogORM(
            admin_id=audit_log.admin_id,
            action=audit_log.action,
            target_type=audit_log.target_type,
            target_id=audit_log.target_id,
            reason=audit_log.reason,
            before_state=audit_log.before_state,
            after_state=audit_log.after_state,
            request_id=audit_log.request_id,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _audit_log_from_orm(row)

    # --- Admin Management (ADR-0040) ---

    def create_admin_user(self, admin: AdminUser) -> AdminUser:
        row = AdminUserORM(id=admin.id, role=admin.role, status=admin.status)
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _admin_user_from_orm(row)

    def save_admin_user(self, admin: AdminUser) -> None:
        row = self._db.get(AdminUserORM, admin.id)
        if row is None:
            raise LookupError(f"AdminUser {admin.id} not found")
        row.status = admin.status
        self._db.flush()

    def list_admin_users(
        self, *, offset: int, limit: int
    ) -> tuple[list[AdminUser], int]:
        total = self._db.execute(
            select(func.count()).select_from(AdminUserORM)
        ).scalar_one()
        rows = (
            self._db.execute(
                select(AdminUserORM)
                .order_by(AdminUserORM.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_admin_user_from_orm(row) for row in rows], total

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
        filters = []
        if admin_id is not None:
            filters.append(AuditLogORM.admin_id == admin_id)
        if target_type is not None:
            filters.append(AuditLogORM.target_type == target_type)
        if target_id is not None:
            filters.append(AuditLogORM.target_id == target_id)
        if action is not None:
            filters.append(AuditLogORM.action == action)
        if created_after is not None:
            filters.append(AuditLogORM.created_at >= created_after)
        if created_before is not None:
            filters.append(AuditLogORM.created_at <= created_before)

        total = self._db.execute(
            select(func.count()).select_from(AuditLogORM).where(*filters)
        ).scalar_one()
        rows = (
            self._db.execute(
                select(AuditLogORM)
                .where(*filters)
                .order_by(AuditLogORM.id.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_audit_log_from_orm(row) for row in rows], total


class SqlAlchemyPermissionRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def list_for_admin(self, admin_id: uuid.UUID) -> list[Permission]:
        rows = (
            self._db.execute(
                select(PermissionORM).where(PermissionORM.admin_id == admin_id)
            )
            .scalars()
            .all()
        )
        return [_permission_from_orm(row) for row in rows]

    def replace_for_admin(
        self, *, admin_id: uuid.UUID, permissions: list[Permission]
    ) -> list[Permission]:
        """Deletes every existing admin.permissions row for this admin
        and inserts the new set in one transaction — PATCH .../
        permissions replaces the whole set, matching the Admin Web
        plan's own "replace permission set" framing rather than a
        finer-grained add/remove API this codebase doesn't need yet."""
        self._db.execute(
            PermissionORM.__table__.delete().where(PermissionORM.admin_id == admin_id)
        )
        rows = [
            PermissionORM(
                id=p.id,
                admin_id=p.admin_id,
                module=p.module.value,
                access_level=p.access_level.value,
            )
            for p in permissions
        ]
        self._db.add_all(rows)
        self._db.flush()
        return self.list_for_admin(admin_id)

    def get(self, *, admin_id: uuid.UUID, module: AdminModule) -> Permission | None:
        row = self._db.execute(
            select(PermissionORM).where(
                PermissionORM.admin_id == admin_id,
                PermissionORM.module == module.value,
            )
        ).scalar_one_or_none()
        return _permission_from_orm(row) if row is not None else None


def _setting_from_orm(row: SettingORM) -> Setting:
    return Setting(
        key=row.key,
        value=row.value,
        category=SettingCategory(row.category),
        description=row.description,
        updated_by=row.updated_by,
        updated_at=row.updated_at,
    )


class SqlAlchemySettingRepository:
    """ADR-0048 — Admin Settings."""

    def __init__(self, db: DbSession) -> None:
        self._db = db

    def get(self, key: str) -> Setting | None:
        row = self._db.get(SettingORM, key)
        return _setting_from_orm(row) if row else None

    def get_for_update(self, key: str) -> Setting | None:
        row = self._db.execute(
            select(SettingORM).where(SettingORM.key == key).with_for_update()
        ).scalar_one_or_none()
        return _setting_from_orm(row) if row else None

    def save(self, setting: Setting) -> None:
        row = self._db.get(SettingORM, setting.key)
        if row is None:
            raise LookupError(f"Setting {setting.key!r} not found")
        row.value = setting.value
        row.updated_by = setting.updated_by
        self._db.flush()
        self._db.refresh(row)
        setting.updated_at = row.updated_at

    def list_all(self, *, category: str | None) -> list[Setting]:
        stmt = select(SettingORM)
        if category:
            stmt = stmt.where(SettingORM.category == category)
        rows = self._db.execute(stmt.order_by(SettingORM.key)).scalars().all()
        return [_setting_from_orm(row) for row in rows]
