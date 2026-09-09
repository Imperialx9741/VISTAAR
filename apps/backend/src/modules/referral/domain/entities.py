"""Referral domain entities.

Field shapes match docs/04-database/database-design.md §25.1
(referral.codes), §25.2 (referral.referrals), and §25.3
(referral.rewards) exactly.
"""

from __future__ import annotations

import secrets
import string
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from modules.referral.domain.errors import (
    InvalidRewardConfigInputError,
    InvalidRewardConfigStateTransitionError,
)

_CODE_LENGTH = 8
_CODE_ALPHABET = string.ascii_uppercase + string.digits


class OwnerType(StrEnum):
    """referral.codes.owner_type / referral.referrals.referred_type —
    generic across the two account types that can refer/be referred
    (BR-022 driver-to-driver, BR-059/060 customer-to-customer)."""

    CUSTOMER = "CUSTOMER"
    DRIVER = "DRIVER"


class ReferralCodeStatus(StrEnum):
    ACTIVE = "ACTIVE"


class ReferralStatus(StrEnum):
    """Exactly database-design.md §25.2's documented default
    ('ATTACHED') plus the one outcome QualifyCustomerReferral/
    QualifyDriverReferral produces."""

    ATTACHED = "ATTACHED"
    ACTIVATED = "ACTIVATED"


class RewardType(StrEnum):
    """referral.rewards.reward_type — matches modules.wallet.domain.
    entities.TransactionType.DRIVER_REFERRAL_BONUS's existing naming for
    the driver flow (BR-022, a wallet credit); the customer flow
    (BR-059/060) is a promotion grant instead, recorded here for audit/
    idempotency purposes even though modules.promotion owns the actual
    entitlement."""

    DRIVER_REFERRAL_BONUS = "DRIVER_REFERRAL_BONUS"
    CUSTOMER_REFERRAL_PROMOTION = "CUSTOMER_REFERRAL_PROMOTION"


class RewardStatus(StrEnum):
    ISSUED = "ISSUED"


def generate_referral_code() -> str:
    """8 uppercase-alphanumeric characters — matches api-contracts.md
    §38's own "ABC123"-style example length/shape; no canonical
    generation algorithm is documented, so this is an engineering
    choice (implementation-readiness.md §75's same treatment other
    unspecified-format values already received in this codebase), not
    an invented business rule."""
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


@dataclass(slots=True)
class ReferralCode:
    id: uuid.UUID
    owner_type: OwnerType
    owner_id: uuid.UUID
    code: str
    status: ReferralCodeStatus
    created_at: datetime

    @staticmethod
    def new(
        *, owner_type: OwnerType, owner_id: uuid.UUID, now: datetime
    ) -> ReferralCode:
        return ReferralCode(
            id=uuid.uuid4(),
            owner_type=owner_type,
            owner_id=owner_id,
            code=generate_referral_code(),
            status=ReferralCodeStatus.ACTIVE,
            created_at=now,
        )


@dataclass(slots=True)
class Referral:
    id: uuid.UUID
    referral_code_id: uuid.UUID
    referrer_id: uuid.UUID
    referred_id: uuid.UUID
    referred_type: OwnerType
    status: ReferralStatus
    activated_at: datetime | None
    created_at: datetime

    @staticmethod
    def new(
        *,
        referral_code_id: uuid.UUID,
        referrer_id: uuid.UUID,
        referred_id: uuid.UUID,
        referred_type: OwnerType,
        now: datetime,
    ) -> Referral:
        return Referral(
            id=uuid.uuid4(),
            referral_code_id=referral_code_id,
            referrer_id=referrer_id,
            referred_id=referred_id,
            referred_type=referred_type,
            status=ReferralStatus.ATTACHED,
            activated_at=None,
            created_at=now,
        )


@dataclass(slots=True)
class Reward:
    id: uuid.UUID
    referral_id: uuid.UUID
    recipient_id: uuid.UUID
    reward_type: RewardType
    amount: Decimal | None
    promotion_uses: int | None
    status: RewardStatus
    idempotency_key: str
    created_at: datetime

    @staticmethod
    def new(
        *,
        referral_id: uuid.UUID,
        recipient_id: uuid.UUID,
        reward_type: RewardType,
        amount: Decimal | None,
        promotion_uses: int | None,
        idempotency_key: str,
        now: datetime,
    ) -> Reward:
        return Reward(
            id=uuid.uuid4(),
            referral_id=referral_id,
            recipient_id=recipient_id,
            reward_type=reward_type,
            amount=amount,
            promotion_uses=promotion_uses,
            status=RewardStatus.ISSUED,
            idempotency_key=idempotency_key,
            created_at=now,
        )


# --- Referral Reward Configuration (ADR-0043) ---------------------------


class RewardConfigStatus(StrEnum):
    """DRAFT -> IN_REVIEW -> PUBLISHED — identical lifecycle to
    modules.pricing.domain.entities.FareRuleStatus (ADR-0042)."""

    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    PUBLISHED = "PUBLISHED"


_ALLOWED_TRANSITIONS_TO_PUBLISHED = {
    RewardConfigStatus.DRAFT,
    RewardConfigStatus.IN_REVIEW,
}


@dataclass(slots=True)
class DriverBonusRule:
    """BR-022/023's driver referral bonus — a single global policy, no
    key column (unlike CustomerRewardRule below)."""

    id: uuid.UUID
    referred_amount: Decimal
    referrer_amount: Decimal
    status: RewardConfigStatus
    effective_from: datetime | None
    effective_until: datetime | None
    created_by: uuid.UUID
    created_at: datetime

    @staticmethod
    def new(
        *,
        referred_amount: Decimal,
        referrer_amount: Decimal,
        created_by: uuid.UUID,
        now: datetime,
    ) -> DriverBonusRule:
        if referred_amount <= 0 or referrer_amount <= 0:
            raise InvalidRewardConfigInputError(
                "referred_amount/referrer_amount must be positive."
            )
        return DriverBonusRule(
            id=uuid.uuid4(),
            referred_amount=referred_amount,
            referrer_amount=referrer_amount,
            status=RewardConfigStatus.DRAFT,
            effective_from=None,
            effective_until=None,
            created_by=created_by,
            created_at=now,
        )

    def submit_for_review(self) -> None:
        if self.status is not RewardConfigStatus.DRAFT:
            raise InvalidRewardConfigStateTransitionError(
                f"Cannot submit a rule in status {self.status} for review."
            )
        self.status = RewardConfigStatus.IN_REVIEW

    def publish(self, *, effective_from: datetime) -> None:
        if self.status not in _ALLOWED_TRANSITIONS_TO_PUBLISHED:
            raise InvalidRewardConfigStateTransitionError(
                f"Cannot publish a rule already in status {self.status}."
            )
        self.status = RewardConfigStatus.PUBLISHED
        self.effective_from = effective_from


@dataclass(slots=True)
class CustomerRewardRule:
    """BR-059/060's customer referral promotion grant. `reward_type`
    matches PromotionType.REFERRAL_REFERRED/REFERRAL_REFERRING exactly
    (modules.promotion.domain.entities) — two independent config
    streams, since the referred/referring values already differ."""

    id: uuid.UUID
    reward_type: str  # 'REFERRAL_REFERRED' | 'REFERRAL_REFERRING'
    discount_percent: Decimal
    total_uses: int
    status: RewardConfigStatus
    effective_from: datetime | None
    effective_until: datetime | None
    created_by: uuid.UUID
    created_at: datetime

    @staticmethod
    def new(
        *,
        reward_type: str,
        discount_percent: Decimal,
        total_uses: int,
        created_by: uuid.UUID,
        now: datetime,
    ) -> CustomerRewardRule:
        if reward_type not in ("REFERRAL_REFERRED", "REFERRAL_REFERRING"):
            raise InvalidRewardConfigInputError(
                "reward_type must be REFERRAL_REFERRED or REFERRAL_REFERRING."
            )
        if discount_percent <= 0 or discount_percent > 100:
            raise InvalidRewardConfigInputError(
                "discount_percent must be between 0 and 100."
            )
        if total_uses <= 0:
            raise InvalidRewardConfigInputError("total_uses must be at least 1.")
        return CustomerRewardRule(
            id=uuid.uuid4(),
            reward_type=reward_type,
            discount_percent=discount_percent,
            total_uses=total_uses,
            status=RewardConfigStatus.DRAFT,
            effective_from=None,
            effective_until=None,
            created_by=created_by,
            created_at=now,
        )

    def submit_for_review(self) -> None:
        if self.status is not RewardConfigStatus.DRAFT:
            raise InvalidRewardConfigStateTransitionError(
                f"Cannot submit a rule in status {self.status} for review."
            )
        self.status = RewardConfigStatus.IN_REVIEW

    def publish(self, *, effective_from: datetime) -> None:
        if self.status not in _ALLOWED_TRANSITIONS_TO_PUBLISHED:
            raise InvalidRewardConfigStateTransitionError(
                f"Cannot publish a rule already in status {self.status}."
            )
        self.status = RewardConfigStatus.PUBLISHED
        self.effective_from = effective_from
