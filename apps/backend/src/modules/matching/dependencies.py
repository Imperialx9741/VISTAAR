"""FastAPI dependency wiring for Matching.

ComposedEligibilityChecker is the one place this module imports
modules.driver/modules.vehicle — a narrow, one-directional dependency
(matching -> driver/vehicle, never the reverse), the same shape
modules/vehicle/router.py already has on modules.driver for Go Online
composition. modules/matching/domain/ and service.py never import
either module directly (see ports.py's DriverEligibilityChecker
Protocol).

Reuses modules.identity.dependencies.require_driver as-is for the
router's auth — no new auth code.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.orm import Session as DbSession

from core.database import get_db
from core.redis import get_redis
from modules.driver.dependencies import get_driver_document_service, get_driver_service
from modules.driver.domain.entities import (
    DriverOperationalStatus,
    DriverVerificationStatus,
)
from modules.driver.domain.errors import DriverDomainError
from modules.driver.domain.required_documents import (
    missing_or_invalid_required_documents as driver_missing_or_invalid_docs,
)
from modules.driver.service import DriverDocumentService, DriverService
from modules.matching.ports import DriverEligibilityChecker, EligibilityResult
from modules.matching.repositories import (
    RedisNearbyDriverIndex,
    SqlAlchemyOfferRepository,
)
from modules.matching.service import MatchingService
from modules.vehicle.dependencies import (
    get_vehicle_document_service,
    get_vehicle_service,
)
from modules.vehicle.domain.entities import (
    VehicleOperationalStatus,
    VehicleVerificationStatus,
    matching_category_key,
)
from modules.vehicle.domain.required_documents import (
    missing_or_invalid_required_documents as vehicle_missing_or_invalid_docs,
)
from modules.vehicle.service import VehicleDocumentService, VehicleService


@dataclass
class ComposedEligibilityChecker:
    """Re-derives "is this driver eligible right now" the same way
    modules/driver/router.py::go_online() does — see that router's
    module docstring. Never trusts Redis presence alone (see
    shared/geo.py)."""

    driver_service: DriverService
    driver_document_service: DriverDocumentService
    vehicle_service: VehicleService
    vehicle_document_service: VehicleDocumentService

    def check(
        self, driver_id: uuid.UUID, *, requested_category: str
    ) -> uuid.UUID | None:
        return self.check_with_reason(
            driver_id, requested_category=requested_category
        ).vehicle_id

    def check_with_reason(
        self, driver_id: uuid.UUID, *, requested_category: str
    ) -> EligibilityResult:
        now = datetime.now(UTC)
        driver_ineligible = EligibilityResult(
            vehicle_id=None, ineligible_reason="DRIVER_NOT_ELIGIBLE"
        )
        vehicle_ineligible = EligibilityResult(
            vehicle_id=None, ineligible_reason="VEHICLE_NOT_ELIGIBLE"
        )

        try:
            driver = self.driver_service.get_profile(account_id=driver_id)
        except DriverDomainError:
            return driver_ineligible
        if driver.operational_status is not DriverOperationalStatus.ONLINE:
            return driver_ineligible
        if driver.verification_status is not DriverVerificationStatus.APPROVED:
            return driver_ineligible

        driver_documents = self.driver_document_service.list_documents(
            driver_id=driver_id
        )
        if driver_missing_or_invalid_docs(driver_documents, now=now):
            return driver_ineligible

        # BR-122: at most one of this driver's vehicles is ever ACTIVE.
        vehicles = self.vehicle_service.list_vehicles(driver_id=driver_id)
        active_vehicle = next(
            (
                v
                for v in vehicles
                if v.operational_status is VehicleOperationalStatus.ACTIVE
            ),
            None,
        )
        if active_vehicle is None:
            return vehicle_ineligible
        # ADR-0020 Decision 1: for CAB, the vehicle's own self-declared
        # tier must match the ride's requested tier — not just category.
        if (
            matching_category_key(active_vehicle.category, active_vehicle.cab_tier)
            != requested_category
        ):
            return vehicle_ineligible
        if active_vehicle.verification_status is not VehicleVerificationStatus.APPROVED:
            return vehicle_ineligible

        vehicle_documents = self.vehicle_document_service.list_documents(
            vehicle_id=active_vehicle.id
        )
        if vehicle_missing_or_invalid_docs(vehicle_documents, now=now):
            return vehicle_ineligible

        return EligibilityResult(vehicle_id=active_vehicle.id, ineligible_reason=None)


def get_eligibility_checker(
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
    driver_document_service: Annotated[
        DriverDocumentService, Depends(get_driver_document_service)
    ],
    vehicle_service: Annotated[VehicleService, Depends(get_vehicle_service)],
    vehicle_document_service: Annotated[
        VehicleDocumentService, Depends(get_vehicle_document_service)
    ],
) -> DriverEligibilityChecker:
    return ComposedEligibilityChecker(
        driver_service=driver_service,
        driver_document_service=driver_document_service,
        vehicle_service=vehicle_service,
        vehicle_document_service=vehicle_document_service,
    )


def get_matching_service(
    db: Annotated[DbSession, Depends(get_db)],
    redis_client: Annotated[Redis, Depends(get_redis)],
    eligibility: Annotated[DriverEligibilityChecker, Depends(get_eligibility_checker)],
) -> MatchingService:
    return MatchingService(
        offers=SqlAlchemyOfferRepository(db),
        driver_index=RedisNearbyDriverIndex(redis_client),
        eligibility=eligibility,
    )
