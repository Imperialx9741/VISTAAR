"""Celery periodic task for Schedule a Ride (ADR-0057).

Mirrors modules/notification/tasks.py's send_scheduled_broadcasts() —
same "pure, directly-testable async function wrapped by a thin Celery
entrypoint with its own fresh DB session" shape (ADR-0039's own
established pattern), same `crontab(minute="*/5")` polling cadence
(shared/celery_app.py) for the same "correct first, not fastest
possible" reason ADR-0055 accepted for scheduled broadcasts.

promote_due_scheduled_rides() does, for every SCHEDULED ride whose
lock_in_at has arrived: transition it to SEARCHING
(RideService.promote_scheduled_ride_to_searching()), publish
`ride.schedule_promoted`, then dispatch matching exactly the way
modules/ride/router.py's create_ride() already does for an immediate
ride — from this point on, the ride is indistinguishable from any
other SEARCHING ride to every other endpoint in this codebase. No fare
calculation happens here: the ride's fare was already locked at
scheduling time (ADR-0057 Decision 1), by router.py's own
unconditional calculate_fare() call right after ride creation.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session as DbSession

from core.config import settings
from core.database import SessionLocal
from core.redis import get_redis_client
from modules.driver.repositories import (
    SqlAlchemyDriverDocumentRepository,
    SqlAlchemyDriverRepository,
)
from modules.driver.service import DriverDocumentService, DriverService
from modules.matching.dependencies import ComposedEligibilityChecker
from modules.matching.repositories import (
    RedisNearbyDriverIndex,
    SqlAlchemyOfferRepository,
)
from modules.matching.service import MatchingService
from modules.ride.domain.errors import RideDomainError
from modules.ride.repositories import SqlAlchemyRideRepository
from modules.ride.service import RideService
from modules.vehicle.domain.entities import matching_category_key
from modules.vehicle.repositories import (
    SqlAlchemyVehicleDocumentRepository,
    SqlAlchemyVehicleRepository,
)
from modules.vehicle.service import VehicleDocumentService, VehicleService
from shared.celery_app import celery_app
from shared.outbox import OutboxStore, new_envelope

logger = logging.getLogger("vistaar.ride.tasks")

# Same engineering choice, not a documented business value, as
# modules/ride/router.py's own identical constant.
_CANDIDATE_LIMIT = 20

# One poll's worth of work — a backlog larger than this just gets
# picked up on the next 5-minute tick (RideRepository.list_due_scheduled's
# own doc comment).
_BATCH_LIMIT = 100


async def promote_due_scheduled_rides(*, db: DbSession, now: datetime) -> int:
    """Returns the number of rides actually promoted (for logging
    only)."""
    rides = SqlAlchemyRideRepository(db)
    ride_service = RideService(rides=rides)
    due = rides.list_due_scheduled(before=now, limit=_BATCH_LIMIT)
    if not due:
        return 0

    eligibility = ComposedEligibilityChecker(
        driver_service=DriverService(drivers=SqlAlchemyDriverRepository(db)),
        driver_document_service=DriverDocumentService(
            documents=SqlAlchemyDriverDocumentRepository(db)
        ),
        vehicle_service=VehicleService(vehicles=SqlAlchemyVehicleRepository(db)),
        vehicle_document_service=VehicleDocumentService(
            documents=SqlAlchemyVehicleDocumentRepository(db)
        ),
    )
    redis_client = get_redis_client()
    matching_service = MatchingService(
        offers=SqlAlchemyOfferRepository(db),
        driver_index=RedisNearbyDriverIndex(redis_client),
        eligibility=eligibility,
    )

    promoted = 0
    try:
        for stale_ride in due:
            try:
                ride = ride_service.promote_scheduled_ride_to_searching(
                    ride_id=stale_ride.id, now=now
                )
            except RideDomainError:
                # Already cancelled between this poll's list_due_scheduled()
                # and this ride's own turn in the loop — skip, not an
                # error (ScheduledRideNotFoundError's own doc comment).
                db.rollback()
                continue

            OutboxStore(db).append(
                new_envelope(
                    event_type="ride.schedule_promoted",
                    producer="ride-service",
                    aggregate_type="ride",
                    aggregate_id=ride.id,
                    data={"ride_id": str(ride.id), "promoted_at": now.isoformat()},
                    now=now,
                )
            )
            db.commit()
            promoted += 1

            try:
                await matching_service.dispatch_offer(
                    ride_id=ride.id,
                    requested_category=matching_category_key(
                        ride.requested_vehicle_category, ride.requested_cab_tier
                    ),
                    pickup_latitude=ride.original_pickup.latitude,
                    pickup_longitude=ride.original_pickup.longitude,
                    search_radius_km=settings.MATCHING_SEARCH_RADIUS_KM,
                    offer_ttl_seconds=settings.MATCHING_OFFER_TTL_SECONDS,
                    candidate_limit=_CANDIDATE_LIMIT,
                    now=now,
                )
                db.commit()
            except Exception:
                # Same "a matching failure must never undo an
                # already-successful state transition" reasoning
                # router.py's own create_ride() dispatch already
                # documents — the ride stays SEARCHING with no active
                # offer, a legitimate outcome (ADR-0011 Item 5).
                db.rollback()
    finally:
        await redis_client.aclose()
    return promoted


def _run_with_fresh_session() -> int:
    """Same bridge shape modules/notification/tasks.py's own
    _run_with_fresh_session() already establishes — its own doc comment
    applies unchanged here."""
    import asyncio

    db = SessionLocal()
    try:
        return asyncio.run(promote_due_scheduled_rides(db=db, now=datetime.now(UTC)))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@celery_app.task(name="ride.promote_due_scheduled_rides")
def promote_due_scheduled_rides_task() -> int:
    count = _run_with_fresh_session()
    logger.info("promote_due_scheduled_rides_task promoted %s ride(s).", count)
    return count
