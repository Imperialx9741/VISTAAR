"""FastAPI dependency wiring for Vehicle.

Reuses modules.identity.dependencies.require_driver as-is — no new auth
code. Ownership (a driver can only ever act on driver_id == the
authenticated account's id) is enforced in service.py, never accepted
from the client — see router.py.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session as DbSession

from core.database import get_db
from modules.vehicle.repositories import (
    SqlAlchemyVehicleDocumentRepository,
    SqlAlchemyVehicleRepository,
)
from modules.vehicle.service import VehicleDocumentService, VehicleService


def get_vehicle_service(
    db: Annotated[DbSession, Depends(get_db)],
) -> VehicleService:
    return VehicleService(vehicles=SqlAlchemyVehicleRepository(db))


def get_vehicle_document_service(
    db: Annotated[DbSession, Depends(get_db)],
) -> VehicleDocumentService:
    """Composed into router.py's document endpoints (ADR-0072,
    2026-09-04) — previously wired to no router at all (ADR-0007)."""
    return VehicleDocumentService(documents=SqlAlchemyVehicleDocumentRepository(db))
