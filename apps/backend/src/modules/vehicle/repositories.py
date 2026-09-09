"""SQLAlchemy-backed implementation of VehicleRepository."""

from __future__ import annotations

import uuid

from sqlalchemy import ColumnElement, exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from modules.vehicle.domain.entities import (
    CabTier,
    DocumentVerificationStatus,
    Vehicle,
    VehicleCategory,
    VehicleDocument,
    VehicleOperationalStatus,
    VehicleVerificationStatus,
)
from modules.vehicle.domain.errors import VehicleActivationConflictError
from modules.vehicle.models import VehicleDocumentORM, VehicleORM


def _vehicle_from_orm(row: VehicleORM) -> Vehicle:
    return Vehicle(
        id=row.id,
        driver_id=row.driver_id,
        category=VehicleCategory(row.category),
        cab_tier=CabTier(row.cab_tier) if row.cab_tier is not None else None,
        registration_number=row.registration_number,
        make=row.make,
        model=row.model,
        verification_status=VehicleVerificationStatus(row.verification_status),
        operational_status=VehicleOperationalStatus(row.operational_status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyVehicleRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def list_by_driver(self, driver_id: uuid.UUID) -> list[Vehicle]:
        rows = (
            self._db.execute(
                select(VehicleORM)
                .where(VehicleORM.driver_id == driver_id)
                .order_by(VehicleORM.created_at)
            )
            .scalars()
            .all()
        )
        return [_vehicle_from_orm(row) for row in rows]

    def list_by_driver_for_update(self, driver_id: uuid.UUID) -> list[Vehicle]:
        rows = (
            self._db.execute(
                select(VehicleORM)
                .where(VehicleORM.driver_id == driver_id)
                .order_by(VehicleORM.created_at)
                .with_for_update()
            )
            .scalars()
            .all()
        )
        return [_vehicle_from_orm(row) for row in rows]

    def get_by_id(self, vehicle_id: uuid.UUID) -> Vehicle | None:
        row = self._db.get(VehicleORM, vehicle_id)
        return _vehicle_from_orm(row) if row else None

    def registration_number_exists(self, registration_number: str) -> bool:
        result = self._db.execute(
            select(
                exists().where(VehicleORM.registration_number == registration_number)
            )
        ).scalar_one()
        return bool(result)

    def create(self, vehicle: Vehicle) -> Vehicle:
        row = VehicleORM(
            id=vehicle.id,
            driver_id=vehicle.driver_id,
            category=vehicle.category.value,
            cab_tier=vehicle.cab_tier.value if vehicle.cab_tier is not None else None,
            registration_number=vehicle.registration_number,
            make=vehicle.make,
            model=vehicle.model,
            verification_status=vehicle.verification_status.value,
            operational_status=vehicle.operational_status.value,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _vehicle_from_orm(row)

    def save(self, vehicle: Vehicle) -> None:
        row = self._db.get(VehicleORM, vehicle.id)
        if row is None:
            raise LookupError(f"Vehicle {vehicle.id} not found")

        row.category = vehicle.category.value
        row.cab_tier = vehicle.cab_tier.value if vehicle.cab_tier is not None else None
        row.registration_number = vehicle.registration_number
        row.make = vehicle.make
        row.model = vehicle.model
        row.verification_status = vehicle.verification_status.value
        row.operational_status = vehicle.operational_status.value
        try:
            self._db.flush()
        except IntegrityError as exc:
            # Defensive backstop only — VehicleService.activate_vehicle()
            # already prevents this via row locking
            # (list_by_driver_for_update). See
            # domain/errors.py::VehicleActivationConflictError.
            self._db.rollback()
            raise VehicleActivationConflictError(
                "Could not complete this vehicle status change due to a "
                "concurrent update. Please retry."
            ) from exc
        self._db.refresh(row)

        # See modules/customer/repositories.py::save() for why this is
        # necessary: row.updated_at is server-computed (onupdate) and
        # only known accurately after flush+refresh.
        vehicle.updated_at = row.updated_at

    def search(
        self,
        *,
        query: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Vehicle], int]:
        filters: list[ColumnElement[bool]] = []
        if query:
            filters.append(VehicleORM.registration_number.ilike(f"%{query}%"))
        if status:
            filters.append(VehicleORM.verification_status == status)

        total = self._db.execute(
            select(func.count()).select_from(VehicleORM).where(*filters)
        ).scalar_one()
        rows = (
            self._db.execute(
                select(VehicleORM)
                .where(*filters)
                .order_by(VehicleORM.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_vehicle_from_orm(row) for row in rows], total


def _vehicle_document_from_orm(row: VehicleDocumentORM) -> VehicleDocument:
    return VehicleDocument(
        id=row.id,
        vehicle_id=row.vehicle_id,
        document_type=row.document_type,
        document_number=row.document_number,
        evidence_uri=row.evidence_uri,
        verification_status=DocumentVerificationStatus(row.verification_status),
        expires_at=row.expires_at,
        created_at=row.created_at,
    )


class SqlAlchemyVehicleDocumentRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, document: VehicleDocument) -> VehicleDocument:
        row = VehicleDocumentORM(
            id=document.id,
            vehicle_id=document.vehicle_id,
            document_type=document.document_type,
            document_number=document.document_number,
            evidence_uri=document.evidence_uri,
            verification_status=document.verification_status.value,
            expires_at=document.expires_at,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _vehicle_document_from_orm(row)

    def get_by_id(self, document_id: uuid.UUID) -> VehicleDocument | None:
        row = self._db.get(VehicleDocumentORM, document_id)
        return _vehicle_document_from_orm(row) if row else None

    def list_by_vehicle(self, vehicle_id: uuid.UUID) -> list[VehicleDocument]:
        rows = (
            self._db.execute(
                select(VehicleDocumentORM)
                .where(VehicleDocumentORM.vehicle_id == vehicle_id)
                .order_by(VehicleDocumentORM.created_at)
            )
            .scalars()
            .all()
        )
        return [_vehicle_document_from_orm(row) for row in rows]

    def save(self, document: VehicleDocument) -> None:
        row = self._db.get(VehicleDocumentORM, document.id)
        if row is None:
            raise LookupError(f"Vehicle document {document.id} not found")

        row.verification_status = document.verification_status.value
        self._db.flush()
        # No refresh/updated_at write-back — vehicle.documents has no
        # updated_at column (database-design.md §8.2, preserved
        # deliberately since Task 2.5 — see
        # modules/vehicle/domain/entities.py::VehicleDocument).
