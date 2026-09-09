"""FastAPI dependency wiring for Ride.

Reuses modules.identity.dependencies.require_customer as-is — no new
auth code. customer_id is always the authenticated account's id, never
accepted from the request body — see router.py.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session as DbSession

from core.config import settings
from core.database import get_db
from modules.ride.repositories import (
    SqlAlchemyChangeRequestRepository,
    SqlAlchemyEarlyDropRequestRepository,
    SqlAlchemyGpsDisputeEvidenceRepository,
    SqlAlchemyGpsDisputeRepository,
    SqlAlchemyGpsVerificationRepository,
    SqlAlchemyRideOtpRepository,
    SqlAlchemyRideRepository,
)
from modules.ride.service import RideService
from shared.storage import ObjectStorage, S3ObjectStorage


def get_ride_service(
    db: Annotated[DbSession, Depends(get_db)],
) -> RideService:
    # Phase 06/07 (ADR-0028) — always wires gps_verifications/ride_otps
    # too now; Phase 08 (ADR-0030) — always wires early_drop_requests
    # too; BR-124/BR-125 (ADR-0032) — always wires gps_disputes/
    # gps_dispute_evidence too; Ride Modifications (ADR-0033) — always
    # wires change_requests too. RideService's own __init__ keeps them
    # optional only for callers (tests, modules/matching/router.py) that
    # construct it directly without needing these methods.
    return RideService(
        rides=SqlAlchemyRideRepository(db),
        gps_verifications=SqlAlchemyGpsVerificationRepository(db),
        ride_otps=SqlAlchemyRideOtpRepository(db),
        early_drop_requests=SqlAlchemyEarlyDropRequestRepository(db),
        gps_disputes=SqlAlchemyGpsDisputeRepository(db),
        gps_dispute_evidence=SqlAlchemyGpsDisputeEvidenceRepository(db),
        change_requests=SqlAlchemyChangeRequestRepository(db),
    )


def get_gps_dispute_object_storage() -> ObjectStorage:
    """ADR-0032 Decision 3 — the same shared.storage.ObjectStorage
    modules.driver.dependencies.get_object_storage() already constructs
    (ADR-0031), duplicated here rather than imported: modules/ride/ has
    no existing dependency on modules/driver/, and this one-line
    construction isn't worth introducing one for.

    key_prefix is "gps-dispute-evidence", distinct from
    modules.driver.dependencies.get_object_storage()'s "driver-uploads"
    — owner decision, 2026-09-03 ("authorized object-key scope"). Before
    this, both callers shared the same hardcoded prefix, so GPS dispute
    evidence was being filed under the driver-document namespace despite
    being a different kind of upload."""
    return S3ObjectStorage(
        bucket=settings.STORAGE_BUCKET,
        region=settings.STORAGE_REGION,
        endpoint_url=settings.STORAGE_ENDPOINT,
        access_key=settings.STORAGE_ACCESS_KEY,
        secret_key=settings.STORAGE_SECRET_KEY,
        key_prefix="gps-dispute-evidence",
    )
