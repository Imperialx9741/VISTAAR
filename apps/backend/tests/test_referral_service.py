"""Unit tests for ReferralService against in-memory fake repositories."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from modules.referral.domain.entities import (
    OwnerType,
    Referral,
    ReferralCode,
    ReferralStatus,
    Reward,
    RewardType,
)
from modules.referral.domain.errors import (
    AlreadyReferredError,
    ReferralCodeNotFoundError,
    ReferralNotAttachedError,
    ReferralNotFoundError,
    SelfReferralError,
)
from modules.referral.service import ReferralService

REFERRER_ID = uuid.uuid4()
REFERRED_ID = uuid.uuid4()
NOW = datetime.now(UTC)


class FakeReferralCodeRepository:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, ReferralCode] = {}

    def create(self, code: ReferralCode) -> ReferralCode:
        self.by_id[code.id] = code
        return code

    def get_by_code(self, code: str) -> ReferralCode | None:
        for row in self.by_id.values():
            if row.code == code:
                return row
        return None

    def get_by_owner(
        self, owner_type: OwnerType, owner_id: uuid.UUID
    ) -> ReferralCode | None:
        for row in self.by_id.values():
            if row.owner_type is owner_type and row.owner_id == owner_id:
                return row
        return None


class FakeReferralRepository:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, Referral] = {}
        self.referred_ids: set[uuid.UUID] = set()

    def create(self, referral: Referral) -> Referral:
        if referral.referred_id in self.referred_ids:
            # uq_referrals_referred_id equivalent.
            raise AlreadyReferredError("This account has already been referred.")
        self.referred_ids.add(referral.referred_id)
        self.by_id[referral.id] = referral
        return referral

    def get_by_id(self, referral_id: uuid.UUID) -> Referral | None:
        return self.by_id.get(referral_id)

    def get_by_referred_id(self, referred_id: uuid.UUID) -> Referral | None:
        for row in self.by_id.values():
            if row.referred_id == referred_id:
                return row
        return None

    def save(self, referral: Referral) -> None:
        self.by_id[referral.id] = referral

    def list_all(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[Referral], int]:
        matches = sorted(
            (
                r
                for r in self.by_id.values()
                if status is None or r.status.value == status
            ),
            key=lambda r: r.created_at,
            reverse=True,
        )
        return matches[offset : offset + limit], len(matches)

    def count_by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.by_id.values():
            key = r.status.value
            counts[key] = counts.get(key, 0) + 1
        return counts


class FakeRewardRepository:
    def __init__(self) -> None:
        self.by_idempotency_key: dict[str, Reward] = {}
        self.created: list[Reward] = []

    def create(self, reward: Reward) -> Reward:
        self.by_idempotency_key[reward.idempotency_key] = reward
        self.created.append(reward)
        return reward

    def get_by_idempotency_key(self, idempotency_key: str) -> Reward | None:
        return self.by_idempotency_key.get(idempotency_key)

    def list_for_referral(self, referral_id: uuid.UUID) -> list[Reward]:
        return [r for r in self.created if r.referral_id == referral_id]

    def sum_amount_issued_in_range(
        self, *, since: datetime, until: datetime
    ) -> Decimal:
        return sum(
            (
                r.amount
                for r in self.created
                if r.amount is not None and since <= r.created_at < until
            ),
            Decimal("0"),
        )


@pytest.fixture
def codes() -> FakeReferralCodeRepository:
    return FakeReferralCodeRepository()


@pytest.fixture
def referrals() -> FakeReferralRepository:
    return FakeReferralRepository()


@pytest.fixture
def rewards() -> FakeRewardRepository:
    return FakeRewardRepository()


@pytest.fixture
def service(
    codes: FakeReferralCodeRepository,
    referrals: FakeReferralRepository,
    rewards: FakeRewardRepository,
) -> ReferralService:
    return ReferralService(codes=codes, referrals=referrals, rewards=rewards)


def test_get_or_create_code_creates_once_per_owner(
    service: ReferralService, codes: FakeReferralCodeRepository
) -> None:
    first = service.get_or_create_code(
        owner_type=OwnerType.CUSTOMER, owner_id=REFERRER_ID, now=NOW
    )
    second = service.get_or_create_code(
        owner_type=OwnerType.CUSTOMER, owner_id=REFERRER_ID, now=NOW
    )

    assert first.id == second.id
    assert len(first.code) == 8
    assert len(codes.by_id) == 1


def test_attach_referral_creates_attached_row(service: ReferralService) -> None:
    code = service.get_or_create_code(
        owner_type=OwnerType.CUSTOMER, owner_id=REFERRER_ID, now=NOW
    )

    referral = service.attach_referral(
        code=code.code,
        referred_id=REFERRED_ID,
        referred_type=OwnerType.CUSTOMER,
        now=NOW,
    )

    assert referral.referrer_id == REFERRER_ID
    assert referral.referred_id == REFERRED_ID
    assert referral.status is ReferralStatus.ATTACHED


def test_attach_referral_rejects_unknown_code(service: ReferralService) -> None:
    with pytest.raises(ReferralCodeNotFoundError):
        service.attach_referral(
            code="NOSUCH01",
            referred_id=REFERRED_ID,
            referred_type=OwnerType.CUSTOMER,
            now=NOW,
        )


def test_attach_referral_rejects_self_referral(service: ReferralService) -> None:
    code = service.get_or_create_code(
        owner_type=OwnerType.CUSTOMER, owner_id=REFERRER_ID, now=NOW
    )

    with pytest.raises(SelfReferralError):
        service.attach_referral(
            code=code.code,
            referred_id=REFERRER_ID,  # BR-025: same account as the code owner
            referred_type=OwnerType.CUSTOMER,
            now=NOW,
        )


def test_attach_referral_rejects_duplicate_referred_id(
    service: ReferralService,
) -> None:
    code = service.get_or_create_code(
        owner_type=OwnerType.CUSTOMER, owner_id=REFERRER_ID, now=NOW
    )
    other_referrer = service.get_or_create_code(
        owner_type=OwnerType.CUSTOMER, owner_id=uuid.uuid4(), now=NOW
    )
    service.attach_referral(
        code=code.code,
        referred_id=REFERRED_ID,
        referred_type=OwnerType.CUSTOMER,
        now=NOW,
    )

    with pytest.raises(AlreadyReferredError):
        service.attach_referral(
            code=other_referrer.code,
            referred_id=REFERRED_ID,  # uq_referrals_referred_id
            referred_type=OwnerType.CUSTOMER,
            now=NOW,
        )


def test_qualify_customer_referral_activates(service: ReferralService) -> None:
    code = service.get_or_create_code(
        owner_type=OwnerType.CUSTOMER, owner_id=REFERRER_ID, now=NOW
    )
    referral = service.attach_referral(
        code=code.code,
        referred_id=REFERRED_ID,
        referred_type=OwnerType.CUSTOMER,
        now=NOW,
    )

    activated = service.qualify_customer_referral(referral_id=referral.id, now=NOW)

    assert activated.status is ReferralStatus.ACTIVATED
    assert activated.activated_at == NOW


def test_qualify_driver_referral_activates(service: ReferralService) -> None:
    code = service.get_or_create_code(
        owner_type=OwnerType.DRIVER, owner_id=REFERRER_ID, now=NOW
    )
    referral = service.attach_referral(
        code=code.code,
        referred_id=REFERRED_ID,
        referred_type=OwnerType.DRIVER,
        now=NOW,
    )

    activated = service.qualify_driver_referral(referral_id=referral.id, now=NOW)

    assert activated.status is ReferralStatus.ACTIVATED


def test_qualify_rejects_unknown_referral(service: ReferralService) -> None:
    with pytest.raises(ReferralNotFoundError):
        service.qualify_customer_referral(referral_id=uuid.uuid4(), now=NOW)


def test_qualify_rejects_already_activated(service: ReferralService) -> None:
    code = service.get_or_create_code(
        owner_type=OwnerType.CUSTOMER, owner_id=REFERRER_ID, now=NOW
    )
    referral = service.attach_referral(
        code=code.code,
        referred_id=REFERRED_ID,
        referred_type=OwnerType.CUSTOMER,
        now=NOW,
    )
    service.qualify_customer_referral(referral_id=referral.id, now=NOW)

    with pytest.raises(ReferralNotAttachedError):
        service.qualify_customer_referral(referral_id=referral.id, now=NOW)


def test_get_referral_by_referred_id(service: ReferralService) -> None:
    code = service.get_or_create_code(
        owner_type=OwnerType.DRIVER, owner_id=REFERRER_ID, now=NOW
    )
    referral = service.attach_referral(
        code=code.code,
        referred_id=REFERRED_ID,
        referred_type=OwnerType.DRIVER,
        now=NOW,
    )

    found = service.get_referral_by_referred_id(REFERRED_ID)

    assert found is not None
    assert found.id == referral.id
    assert service.get_referral_by_referred_id(uuid.uuid4()) is None


def test_record_reward_is_idempotent(
    service: ReferralService, rewards: FakeRewardRepository
) -> None:
    referral_id = uuid.uuid4()

    first = service.record_reward(
        referral_id=referral_id,
        recipient_id=REFERRER_ID,
        reward_type=RewardType.DRIVER_REFERRAL_BONUS,
        amount=Decimal("100"),
        promotion_uses=None,
        idempotency_key="referral:abc:referrer",
        now=NOW,
    )
    second = service.record_reward(
        referral_id=referral_id,
        recipient_id=REFERRER_ID,
        reward_type=RewardType.DRIVER_REFERRAL_BONUS,
        amount=Decimal("100"),
        promotion_uses=None,
        idempotency_key="referral:abc:referrer",
        now=NOW,
    )

    assert first.id == second.id
    assert len(rewards.created) == 1
