"""Abstract interfaces (ports) the application layer depends on."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from modules.referral.domain.entities import (
    CustomerRewardRule,
    DriverBonusRule,
    OwnerType,
    Referral,
    ReferralCode,
    Reward,
)


class ReferralCodeRepository(Protocol):
    def create(self, code: ReferralCode) -> ReferralCode: ...

    def get_by_code(self, code: str) -> ReferralCode | None: ...

    def get_by_owner(
        self, owner_type: OwnerType, owner_id: uuid.UUID
    ) -> ReferralCode | None: ...


class ReferralRepository(Protocol):
    def create(self, referral: Referral) -> Referral:
        """Insert. uq_referrals_referred_id means a genuine duplicate
        (this party already referred) raises IntegrityError — the
        implementation catches this and raises AlreadyReferredError."""
        ...

    def get_by_id(self, referral_id: uuid.UUID) -> Referral | None: ...

    def get_by_referred_id(self, referred_id: uuid.UUID) -> Referral | None: ...

    def save(self, referral: Referral) -> None: ...

    def list_all(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[Referral], int]:
        """Admin Web §4.11's "Search/list referrals" — no owner_id
        filter (an admin browsing referrals generally doesn't already
        have one on hand; referrer_id/referred_id are still visible on
        each row for follow-up lookups)."""
        ...

    def count_by_status(self) -> dict[str, int]:
        """Admin Web §4.16 Promotions/Referrals report (ADR-0047) — a
        current snapshot, not date-ranged."""
        ...


class RewardRepository(Protocol):
    def create(self, reward: Reward) -> Reward: ...

    def get_by_idempotency_key(self, idempotency_key: str) -> Reward | None: ...

    def list_for_referral(self, referral_id: uuid.UUID) -> list[Reward]:
        """Admin Web §4.11's "(with ... reward)" — a referral search
        result composes each row's own reward(s), if any exist yet."""
        ...

    def sum_amount_issued_in_range(
        self, *, since: datetime, until: datetime
    ) -> Decimal:
        """Admin Web §4.16 report's "rewards_issued_in_range" —
        SUM(amount) over rewards with `created_at` in [since, until).
        Excludes rows where amount is NULL (a customer-side reward,
        recorded via `promotion_uses` instead — see ADR-0043 §2)."""
        ...


class DriverBonusRuleRepository(Protocol):
    """ADR-0043. BR-022/023's driver referral bonus — a single global
    policy, no key column."""

    def create(self, rule: DriverBonusRule) -> DriverBonusRule: ...

    def get_by_id(self, rule_id: uuid.UUID) -> DriverBonusRule | None: ...

    def get_by_id_for_update(self, rule_id: uuid.UUID) -> DriverBonusRule | None: ...

    def save(self, rule: DriverBonusRule) -> None: ...

    def list_all(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[DriverBonusRule], int]: ...

    def get_active(self, *, now: datetime) -> DriverBonusRule | None:
        """The one currently-live rule (status=PUBLISHED, within the
        effective window) — read at driver-referral qualification
        time."""
        ...

    def get_active_for_update(self, *, now: datetime) -> DriverBonusRule | None:
        """Locked variant — used by Publish to close out the prior live
        rule (ADR-0042 Decision 2 pattern)."""
        ...


class CustomerRewardRuleRepository(Protocol):
    """ADR-0043. BR-059/060's customer referral promotion grants —
    keyed by reward_type ('REFERRAL_REFERRED' | 'REFERRAL_REFERRING'),
    two independent config streams."""

    def create(self, rule: CustomerRewardRule) -> CustomerRewardRule: ...

    def get_by_id(self, rule_id: uuid.UUID) -> CustomerRewardRule | None: ...

    def get_by_id_for_update(self, rule_id: uuid.UUID) -> CustomerRewardRule | None: ...

    def save(self, rule: CustomerRewardRule) -> None: ...

    def list_all(
        self, *, reward_type: str | None, status: str | None, offset: int, limit: int
    ) -> tuple[list[CustomerRewardRule], int]: ...

    def get_active(
        self, *, reward_type: str, now: datetime
    ) -> CustomerRewardRule | None: ...

    def get_active_for_update(
        self, *, reward_type: str, now: datetime
    ) -> CustomerRewardRule | None: ...
