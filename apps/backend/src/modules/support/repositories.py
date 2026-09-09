"""SQLAlchemy-backed implementations of Support's ports."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from modules.support.domain.entities import (
    CaseStatus,
    SenderType,
    SupportCase,
    SupportMessage,
)
from modules.support.models import SupportCaseORM, SupportMessageORM


def _case_from_orm(row: SupportCaseORM) -> SupportCase:
    return SupportCase(
        id=row.id,
        user_id=row.user_id,
        ride_id=row.ride_id,
        category=row.category,
        priority=row.priority,
        status=CaseStatus(row.status),
        assigned_admin_id=row.assigned_admin_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _message_from_orm(row: SupportMessageORM) -> SupportMessage:
    return SupportMessage(
        id=row.id,
        case_id=row.case_id,
        sender_type=SenderType(row.sender_type),
        sender_id=row.sender_id,
        message=row.message,
        created_at=row.created_at,
    )


class SqlAlchemySupportCaseRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, case: SupportCase) -> SupportCase:
        row = SupportCaseORM(
            id=case.id,
            user_id=case.user_id,
            ride_id=case.ride_id,
            category=case.category,
            priority=case.priority,
            status=case.status.value,
            assigned_admin_id=case.assigned_admin_id,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _case_from_orm(row)

    def get_by_id(self, case_id: uuid.UUID) -> SupportCase | None:
        row = self._db.get(SupportCaseORM, case_id)
        return _case_from_orm(row) if row else None

    def get_by_id_for_update(self, case_id: uuid.UUID) -> SupportCase | None:
        row = self._db.execute(
            select(SupportCaseORM).where(SupportCaseORM.id == case_id).with_for_update()
        ).scalar_one_or_none()
        return _case_from_orm(row) if row else None

    def save(self, case: SupportCase) -> None:
        row = self._db.get(SupportCaseORM, case.id)
        if row is None:
            raise LookupError(f"Support case {case.id} not found")
        row.status = case.status.value
        row.assigned_admin_id = case.assigned_admin_id
        self._db.flush()
        self._db.refresh(row)
        # row.updated_at is server-computed (onupdate) — only known
        # accurately after flush+refresh, same pattern
        # modules/customer/repositories.py::save() already established.
        case.updated_at = row.updated_at

    def search(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[SupportCase], int]:
        filters = []
        if status:
            filters.append(SupportCaseORM.status == status)

        total = self._db.execute(
            select(func.count()).select_from(SupportCaseORM).where(*filters)
        ).scalar_one()
        rows = (
            self._db.execute(
                select(SupportCaseORM)
                .where(*filters)
                .order_by(SupportCaseORM.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_case_from_orm(row) for row in rows], total

    def list_for_user(
        self, *, user_id: uuid.UUID, status: str | None, offset: int, limit: int
    ) -> tuple[list[SupportCase], int]:
        filters = [SupportCaseORM.user_id == user_id]
        if status:
            filters.append(SupportCaseORM.status == status)

        total = self._db.execute(
            select(func.count()).select_from(SupportCaseORM).where(*filters)
        ).scalar_one()
        rows = (
            self._db.execute(
                select(SupportCaseORM)
                .where(*filters)
                .order_by(SupportCaseORM.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_case_from_orm(row) for row in rows], total

    def count_unresolved(self) -> int:
        return self._db.execute(
            select(func.count())
            .select_from(SupportCaseORM)
            .where(SupportCaseORM.status.notin_(["RESOLVED", "CLOSED"]))
        ).scalar_one()

    def count_by_status(self) -> dict[str, int]:
        rows = self._db.execute(
            select(SupportCaseORM.status, func.count()).group_by(SupportCaseORM.status)
        ).all()
        return {key: value for key, value in rows}  # noqa: C416

    def average_resolution_minutes_in_range(
        self, *, since: datetime, until: datetime
    ) -> Decimal:
        minutes = (
            func.extract("epoch", SupportCaseORM.updated_at - SupportCaseORM.created_at)
            / 60
        )
        average = self._db.execute(
            select(func.coalesce(func.avg(minutes), 0))
            .where(SupportCaseORM.status == "RESOLVED")
            .where(SupportCaseORM.updated_at >= since)
            .where(SupportCaseORM.updated_at < until)
        ).scalar_one()
        return Decimal(average)


class SqlAlchemySupportMessageRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, message: SupportMessage) -> SupportMessage:
        row = SupportMessageORM(
            id=message.id,
            case_id=message.case_id,
            sender_type=message.sender_type.value,
            sender_id=message.sender_id,
            message=message.message,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _message_from_orm(row)

    def list_by_case(self, case_id: uuid.UUID) -> list[SupportMessage]:
        rows = (
            self._db.execute(
                select(SupportMessageORM)
                .where(SupportMessageORM.case_id == case_id)
                .order_by(SupportMessageORM.created_at)
            )
            .scalars()
            .all()
        )
        return [_message_from_orm(row) for row in rows]
