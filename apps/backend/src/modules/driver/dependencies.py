"""FastAPI dependency wiring for Driver.

Reuses modules.identity.dependencies.require_driver as-is — no new auth
code. /me routes are self-scoped, same reasoning as
modules/customer/dependencies.py.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session as DbSession

from core.config import settings
from core.database import get_db
from modules.driver.repositories import (
    SqlAlchemyDriverDocumentRepository,
    SqlAlchemyDriverRepository,
)
from modules.driver.service import DriverDocumentService, DriverService
from shared.storage import ObjectStorage, S3ObjectStorage


def get_driver_service(
    db: Annotated[DbSession, Depends(get_db)],
) -> DriverService:
    return DriverService(drivers=SqlAlchemyDriverRepository(db))


def get_driver_document_service(
    db: Annotated[DbSession, Depends(get_db)],
) -> DriverDocumentService:
    return DriverDocumentService(documents=SqlAlchemyDriverDocumentRepository(db))


def get_object_storage() -> ObjectStorage:
    """ADR-0031 (2026-08-25). Constructed fresh per request — boto3
    clients are cheap to create and this avoids any shared-mutable-state
    concern; no per-request resource (DB session, Redis connection) is
    actually needed here, unlike get_driver_service() above."""
    return S3ObjectStorage(
        bucket=settings.STORAGE_BUCKET,
        region=settings.STORAGE_REGION,
        endpoint_url=settings.STORAGE_ENDPOINT,
        access_key=settings.STORAGE_ACCESS_KEY,
        secret_key=settings.STORAGE_SECRET_KEY,
        key_prefix="driver-uploads",
    )
