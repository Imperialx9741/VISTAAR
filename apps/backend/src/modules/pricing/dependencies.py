"""FastAPI dependency wiring for Pricing."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session as DbSession

from core.database import get_db
from modules.pricing.repositories import (
    SqlAlchemyFareQuoteRepository,
    SqlAlchemyFareRuleRepository,
    SqlAlchemyPlatformFeeRuleRepository,
)
from modules.pricing.service import PricingService


def get_pricing_service(
    db: Annotated[DbSession, Depends(get_db)],
) -> PricingService:
    return PricingService(
        fare_rules=SqlAlchemyFareRuleRepository(db),
        fare_quotes=SqlAlchemyFareQuoteRepository(db),
        platform_fee_rules=SqlAlchemyPlatformFeeRuleRepository(db),
    )
