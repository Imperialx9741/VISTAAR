"""SQLAlchemy-backed implementations of DriverRepository and
DriverDocumentRepository.

Translates between the ORM row (models.py) and the pure domain entity
(domain/entities.py) — mirrors modules/customer/repositories.py's role.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session as DbSession

from modules.driver.domain.entities import (
    DocumentVerificationStatus,
    Driver,
    DriverDocument,
    DriverOperationalStatus,
    DriverVerificationStatus,
)
from modules.driver.models import DriverDocumentORM, DriverORM


def _driver_from_orm(row: DriverORM) -> Driver:
    return Driver(
        id=row.id,
        full_name=row.full_name,
        profile_photo_uri=row.profile_photo_uri,
        verification_status=DriverVerificationStatus(row.verification_status),
        operational_status=DriverOperationalStatus(row.operational_status),
        strikes=row.strikes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyDriverRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def get_by_id(self, driver_id: uuid.UUID) -> Driver | None:
        row = self._db.get(DriverORM, driver_id)
        return _driver_from_orm(row) if row else None

    def get_by_id_for_update(self, driver_id: uuid.UUID) -> Driver | None:
        row = (
            self._db.execute(
                select(DriverORM).where(DriverORM.id == driver_id).with_for_update()
            )
            .scalars()
            .one_or_none()
        )
        return _driver_from_orm(row) if row else None

    def create(self, driver: Driver) -> Driver:
        row = DriverORM(
            id=driver.id,
            full_name=driver.full_name,
            profile_photo_uri=driver.profile_photo_uri,
            verification_status=driver.verification_status.value,
            operational_status=driver.operational_status.value,
            strikes=driver.strikes,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _driver_from_orm(row)

    def save(self, driver: Driver) -> None:
        row = self._db.get(DriverORM, driver.id)
        if row is None:
            raise LookupError(f"Driver {driver.id} not found")

        # Only full_name/profile_photo_uri are ever client-writable
        # (service.py never changes verification_status/
        # operational_status/strikes), but this method stays generic and
        # writes every field from the passed-in entity — same pattern as
        # modules/customer/repositories.py::save().
        row.full_name = driver.full_name
        row.profile_photo_uri = driver.profile_photo_uri
        row.verification_status = driver.verification_status.value
        row.operational_status = driver.operational_status.value
        row.strikes = driver.strikes
        self._db.flush()
        self._db.refresh(row)

        # See modules/customer/repositories.py::save() for why this is
        # necessary: row.updated_at is server-computed (onupdate) and
        # only known accurately after flush+refresh.
        driver.updated_at = row.updated_at

    def search(
        self,
        *,
        query: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Driver], int]:
        filters: list[ColumnElement[bool]] = []
        if query:
            filters.append(DriverORM.full_name.ilike(f"%{query}%"))
        if status:
            filters.append(DriverORM.verification_status == status)

        total = self._db.execute(
            select(func.count()).select_from(DriverORM).where(*filters)
        ).scalar_one()
        rows = (
            self._db.execute(
                select(DriverORM)
                .where(*filters)
                .order_by(DriverORM.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_driver_from_orm(row) for row in rows], total

    def count_total(self) -> int:
        return self._db.execute(
            select(func.count()).select_from(DriverORM)
        ).scalar_one()

    def count_by_verification_status(self) -> dict[str, int]:
        rows = self._db.execute(
            select(DriverORM.verification_status, func.count()).group_by(
                DriverORM.verification_status
            )
        ).all()
        return {key: value for key, value in rows}  # noqa: C416

    def count_by_operational_status(self) -> dict[str, int]:
        rows = self._db.execute(
            select(DriverORM.operational_status, func.count()).group_by(
                DriverORM.operational_status
            )
        ).all()
        return {key: value for key, value in rows}  # noqa: C416

    def count_created_in_range(self, *, since: datetime, until: datetime) -> int:
        return self._db.execute(
            select(func.count())
            .select_from(DriverORM)
            .where(DriverORM.created_at >= since)
            .where(DriverORM.created_at < until)
        ).scalar_one()

    def list_all_ids(self) -> list[uuid.UUID]:
        return list(self._db.execute(select(DriverORM.id)).scalars().all())


def _document_from_orm(row: DriverDocumentORM) -> DriverDocument:
    return DriverDocument(
        id=row.id,
        driver_id=row.driver_id,
        document_type=row.document_type,
        document_number=row.document_number,
        evidence_uri=row.evidence_uri,
        verification_status=DocumentVerificationStatus(row.verification_status),
        expires_at=row.expires_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyDriverDocumentRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, document: DriverDocument) -> DriverDocument:
        row = DriverDocumentORM(
            id=document.id,
            driver_id=document.driver_id,
            document_type=document.document_type,
            document_number=document.document_number,
            evidence_uri=document.evidence_uri,
            verification_status=document.verification_status.value,
            expires_at=document.expires_at,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _document_from_orm(row)

    def get_by_id(self, document_id: uuid.UUID) -> DriverDocument | None:
        row = self._db.get(DriverDocumentORM, document_id)
        return _document_from_orm(row) if row else None

    def list_by_driver(self, driver_id: uuid.UUID) -> list[DriverDocument]:
        rows = (
            self._db.execute(
                select(DriverDocumentORM)
                .where(DriverDocumentORM.driver_id == driver_id)
                .order_by(DriverDocumentORM.created_at)
            )
            .scalars()
            .all()
        )
        return [_document_from_orm(row) for row in rows]

    def save(self, document: DriverDocument) -> None:
        row = self._db.get(DriverDocumentORM, document.id)
        if row is None:
            raise LookupError(f"Driver document {document.id} not found")

        row.verification_status = document.verification_status.value
        self._db.flush()
        self._db.refresh(row)

        # See modules/customer/repositories.py::save() for why this is
        # necessary: row.updated_at is server-computed (onupdate) and
        # only known accurately after flush+refresh.
        document.updated_at = row.updated_at
