"""FastAPI dependency wiring for Referral."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session as DbSession

from core.database import get_db
from modules.referral.repositories import (
    SqlAlchemyCustomerRewardRuleRepository,
    SqlAlchemyDriverBonusRuleRepository,
    SqlAlchemyReferralCodeRepository,
    SqlAlchemyReferralRepository,
    SqlAlchemyRewardRepository,
)
from modules.referral.service import ReferralService


def get_referral_service(
    db: Annotated[DbSession, Depends(get_db)],
) -> ReferralService:
    return ReferralService(
        codes=SqlAlchemyReferralCodeRepository(db),
        referrals=SqlAlchemyReferralRepository(db),
        rewards=SqlAlchemyRewardRepository(db),
        driver_bonus_rules=SqlAlchemyDriverBonusRuleRepository(db),
        customer_reward_rules=SqlAlchemyCustomerRewardRuleRepository(db),
    )
