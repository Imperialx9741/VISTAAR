"""FastAPI dependency wiring for Promotion."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session as DbSession

from core.database import get_db
from modules.promotion.repositories import (
    SqlAlchemyCampaignRepository,
    SqlAlchemyEntitlementRepository,
    SqlAlchemyReservationRepository,
    SqlAlchemyUsageRepository,
)
from modules.promotion.service import PromotionService


def get_promotion_service(
    db: Annotated[DbSession, Depends(get_db)],
) -> PromotionService:
    return PromotionService(
        entitlements=SqlAlchemyEntitlementRepository(db),
        usages=SqlAlchemyUsageRepository(db),
        reservations=SqlAlchemyReservationRepository(db),
        campaigns=SqlAlchemyCampaignRepository(db),
    )
