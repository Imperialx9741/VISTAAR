"""FastAPI dependency wiring for Advertisement.

No router exists yet (ADR-0018) — this factory exists so tests and any
future router can construct a real, Postgres-backed AdvertisementService
without duplicating the wiring.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session as DbSession

from core.database import get_db
from modules.advertisement.repositories import (
    SqlAlchemyCampaignRepository,
    SqlAlchemyDriverCampaignRepository,
    SqlAlchemyPayoutRepository,
)
from modules.advertisement.service import AdvertisementService


def get_advertisement_service(
    db: Annotated[DbSession, Depends(get_db)],
) -> AdvertisementService:
    return AdvertisementService(
        campaigns=SqlAlchemyCampaignRepository(db),
        driver_campaigns=SqlAlchemyDriverCampaignRepository(db),
        payouts=SqlAlchemyPayoutRepository(db),
    )
