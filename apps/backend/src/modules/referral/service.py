"""Application service (use cases) for Referral.

Implements domain-design.md's Referral commands (GetOrCreateReferralCode,
AttachReferral, QualifyCustomerReferral, QualifyDriverReferral,
RecordReward — RejectReferral is the one command ADR-0019 Decision 1
explicitly excludes, since nothing in this codebase yet drives a reject
path).

QualifyCustomerReferral and QualifyDriverReferral are kept as two
separate methods (rather than one generic "qualify") because they are
triggered by genuinely different real-world events per BR-023 (driver:
only after approval) vs. BR-060 (customer: on first login through the
referral, no completed ride required) — the domain-design.md command
list treats them as distinct commands for the same reason.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from modules.referral.domain.entities import (
    CustomerRewardRule,
    DriverBonusRule,
    OwnerType,
    Referral,
    ReferralCode,
    ReferralStatus,
    Reward,
    RewardType,
)
from modules.referral.domain.errors import (
    ReferralCodeNotFoundError,
    ReferralNotAttachedError,
    ReferralNotFoundError,
    RewardConfigNotFoundError,
    SelfReferralError,
)
from modules.referral.ports import (
    CustomerRewardRuleRepository,
    DriverBonusRuleRepository,
    ReferralCodeRepository,
    ReferralRepository,
    RewardRepository,
)


class ReferralService:
    def __init__(
        self,
        *,
        codes: ReferralCodeRepository,
        referrals: ReferralRepository,
        rewards: RewardRepository,
        driver_bonus_rules: DriverBonusRuleRepository | None = None,
        customer_reward_rules: CustomerRewardRuleRepository | None = None,
    ) -> None:
        self._codes = codes
        self._referrals = referrals
        self._rewards = rewards
        # Optional (default None), same reasoning
        # modules.admin.service.AdminService's own permissions param
        # already established: callers that never touch Reward
        # Configuration (every existing referral attach/qualify flow)
        # don't need to wire dependencies they'll never use.
        self._driver_bonus_rules = driver_bonus_rules
        self._customer_reward_rules = customer_reward_rules

    # --- Code -------------------------------------------------------

    def get_or_create_code(
        self, *, owner_type: OwnerType, owner_id: uuid.UUID, now: datetime
    ) -> ReferralCode:
        """One code per owner, created lazily on first request — no
        endpoint provisions codes ahead of time (matches ADR-0019
        Decision 5: no invented driver-facing code endpoint; codes are
        only ever surfaced via GET /api/v1/customers/me/referral)."""
        existing = self._codes.get_by_owner(owner_type, owner_id)
        if existing is not None:
            return existing
        code = ReferralCode.new(owner_type=owner_type, owner_id=owner_id, now=now)
        return self._codes.create(code)

    # --- Attach -------------------------------------------------------

    def attach_referral(
        self,
        *,
        code: str,
        referred_id: uuid.UUID,
        referred_type: OwnerType,
        now: datetime,
    ) -> Referral:
        """BR-025 (referral abuse: self-referral must not generate a
        reward) is enforced here at attach time, before any reward can
        be earned. uq_referrals_referred_id (a referred party can only
        ever be referred once) is enforced by the repository, which
        raises AlreadyReferredError on a genuine duplicate."""
        referral_code = self._codes.get_by_code(code)
        if referral_code is None:
            raise ReferralCodeNotFoundError("Referral code not found.")
        if referral_code.owner_id == referred_id:
            raise SelfReferralError("A referral code cannot be used on yourself.")

        referral = Referral.new(
            referral_code_id=referral_code.id,
            referrer_id=referral_code.owner_id,
            referred_id=referred_id,
            referred_type=referred_type,
            now=now,
        )
        return self._referrals.create(referral)

    # --- Query --------------------------------------------------------

    def get_referral_by_referred_id(self, referred_id: uuid.UUID) -> Referral | None:
        """Looks up whether `referred_id` was ever the referred party in
        a referral — the composition point in modules/admin/router.py's
        driver-approval endpoint uses this to find out whether the
        driver being approved needs BR-022/023's qualify+reward flow at
        all (most drivers were never referred)."""
        return self._referrals.get_by_referred_id(referred_id)

    # --- Qualify --------------------------------------------------------

    def qualify_customer_referral(
        self, *, referral_id: uuid.UUID, now: datetime
    ) -> Referral:
        """BR-060: activates as soon as the referred customer downloads
        the app and successfully logs in through the referral — a
        completed first ride is explicitly NOT required. Composed
        immediately after attach_referral() in referral/router.py, since
        attach IS that login event for a customer referral."""
        return self._qualify(referral_id=referral_id, now=now)

    def qualify_driver_referral(
        self, *, referral_id: uuid.UUID, now: datetime
    ) -> Referral:
        """BR-023: only becomes successful after the new driver
        registers, completes onboarding, passes verification, AND is
        approved. Composed into modules/admin/router.py's driver-approval
        endpoint, not at attach time."""
        return self._qualify(referral_id=referral_id, now=now)

    def _qualify(self, *, referral_id: uuid.UUID, now: datetime) -> Referral:
        referral = self._referrals.get_by_id(referral_id)
        if referral is None:
            raise ReferralNotFoundError("Referral not found.")
        if referral.status is not ReferralStatus.ATTACHED:
            raise ReferralNotAttachedError(
                "This referral is not in an attachable state."
            )
        referral.status = ReferralStatus.ACTIVATED
        referral.activated_at = now
        self._referrals.save(referral)
        return referral

    # --- Reward -----------------------------------------------------------

    def record_reward(
        self,
        *,
        referral_id: uuid.UUID,
        recipient_id: uuid.UUID,
        reward_type: RewardType,
        amount: Decimal | None,
        promotion_uses: int | None,
        idempotency_key: str,
        now: datetime,
    ) -> Reward:
        """Audit/idempotency record for a reward already granted by the
        real owning module (modules.wallet for BR-022's ₹100 credits,
        modules.promotion for BR-059/060's ride discounts) — this table
        does not itself move money or grant entitlements. Idempotent on
        idempotency_key: a duplicate call (e.g. a retried composition)
        returns the existing record instead of raising."""
        existing = self._rewards.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing
        reward = Reward.new(
            referral_id=referral_id,
            recipient_id=recipient_id,
            reward_type=reward_type,
            amount=amount,
            promotion_uses=promotion_uses,
            idempotency_key=idempotency_key,
            now=now,
        )
        return self._rewards.create(reward)

    # --- Admin (Admin Web §4.11) ------------------------------------

    def search_referrals(
        self, *, status: ReferralStatus | None, offset: int, limit: int
    ) -> tuple[list[Referral], int]:
        return self._referrals.list_all(
            status=status.value if status else None, offset=offset, limit=limit
        )

    def list_rewards_for_referral(self, referral_id: uuid.UUID) -> list[Reward]:
        return self._rewards.list_for_referral(referral_id)

    # --- Reports (Admin Web §4.16, ADR-0047) -------------------------

    def count_referrals_by_status(self) -> dict[str, int]:
        return self._referrals.count_by_status()

    def sum_rewards_issued_in_range(
        self, *, since: datetime, until: datetime
    ) -> Decimal:
        return self._rewards.sum_amount_issued_in_range(since=since, until=until)

    # --- Referral Reward Configuration (ADR-0043) --------------------

    def get_active_driver_bonus_rule(self, *, now: datetime) -> DriverBonusRule | None:
        """Read at driver-referral qualification time (Approve Driver,
        modules/admin/router.py). Returns None if no PUBLISHED row is
        live — the caller falls back to its own last-resort constant
        (ADR-0043 §4, resolved during implementation), not this
        service's job to know what that fallback value is."""
        assert self._driver_bonus_rules is not None
        return self._driver_bonus_rules.get_active(now=now)

    def create_driver_bonus_rule(
        self,
        *,
        referred_amount: Decimal,
        referrer_amount: Decimal,
        created_by: uuid.UUID,
        now: datetime,
    ) -> DriverBonusRule:
        assert self._driver_bonus_rules is not None
        rule = DriverBonusRule.new(
            referred_amount=referred_amount,
            referrer_amount=referrer_amount,
            created_by=created_by,
            now=now,
        )
        return self._driver_bonus_rules.create(rule)

    def get_driver_bonus_rule(self, rule_id: uuid.UUID) -> DriverBonusRule:
        assert self._driver_bonus_rules is not None
        rule = self._driver_bonus_rules.get_by_id(rule_id)
        if rule is None:
            raise RewardConfigNotFoundError("Driver bonus rule not found.")
        return rule

    def list_driver_bonus_rules(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[DriverBonusRule], int]:
        assert self._driver_bonus_rules is not None
        return self._driver_bonus_rules.list_all(
            status=status, offset=offset, limit=limit
        )

    def submit_driver_bonus_rule_for_review(
        self, rule_id: uuid.UUID
    ) -> DriverBonusRule:
        assert self._driver_bonus_rules is not None
        rule = self._driver_bonus_rules.get_by_id_for_update(rule_id)
        if rule is None:
            raise RewardConfigNotFoundError("Driver bonus rule not found.")
        rule.submit_for_review()
        self._driver_bonus_rules.save(rule)
        return rule

    def publish_driver_bonus_rule(
        self, *, rule_id: uuid.UUID, effective_from: datetime | None, now: datetime
    ) -> DriverBonusRule:
        """Closes out the previously-live rule (there is only ever one
        global driver-bonus policy) before publishing the new one — the
        identical mechanism ADR-0042 established for fare rules."""
        assert self._driver_bonus_rules is not None
        rule = self._driver_bonus_rules.get_by_id_for_update(rule_id)
        if rule is None:
            raise RewardConfigNotFoundError("Driver bonus rule not found.")

        publish_at = effective_from if effective_from is not None else now
        previous = self._driver_bonus_rules.get_active_for_update(now=publish_at)
        if previous is not None and previous.id != rule.id:
            previous.effective_until = publish_at
            self._driver_bonus_rules.save(previous)

        rule.publish(effective_from=publish_at)
        self._driver_bonus_rules.save(rule)
        return rule

    def get_active_customer_reward_rule(
        self, *, reward_type: str, now: datetime
    ) -> CustomerRewardRule | None:
        """Read at customer-referral qualification time (Attach
        Referral, modules/referral/router.py). Same "None means fall
        back to the caller's own constant" contract as
        get_active_driver_bonus_rule() above."""
        assert self._customer_reward_rules is not None
        return self._customer_reward_rules.get_active(reward_type=reward_type, now=now)

    def create_customer_reward_rule(
        self,
        *,
        reward_type: str,
        discount_percent: Decimal,
        total_uses: int,
        created_by: uuid.UUID,
        now: datetime,
    ) -> CustomerRewardRule:
        assert self._customer_reward_rules is not None
        rule = CustomerRewardRule.new(
            reward_type=reward_type,
            discount_percent=discount_percent,
            total_uses=total_uses,
            created_by=created_by,
            now=now,
        )
        return self._customer_reward_rules.create(rule)

    def get_customer_reward_rule(self, rule_id: uuid.UUID) -> CustomerRewardRule:
        assert self._customer_reward_rules is not None
        rule = self._customer_reward_rules.get_by_id(rule_id)
        if rule is None:
            raise RewardConfigNotFoundError("Customer reward rule not found.")
        return rule

    def list_customer_reward_rules(
        self, *, reward_type: str | None, status: str | None, offset: int, limit: int
    ) -> tuple[list[CustomerRewardRule], int]:
        assert self._customer_reward_rules is not None
        return self._customer_reward_rules.list_all(
            reward_type=reward_type, status=status, offset=offset, limit=limit
        )

    def submit_customer_reward_rule_for_review(
        self, rule_id: uuid.UUID
    ) -> CustomerRewardRule:
        assert self._customer_reward_rules is not None
        rule = self._customer_reward_rules.get_by_id_for_update(rule_id)
        if rule is None:
            raise RewardConfigNotFoundError("Customer reward rule not found.")
        rule.submit_for_review()
        self._customer_reward_rules.save(rule)
        return rule

    def publish_customer_reward_rule(
        self, *, rule_id: uuid.UUID, effective_from: datetime | None, now: datetime
    ) -> CustomerRewardRule:
        assert self._customer_reward_rules is not None
        rule = self._customer_reward_rules.get_by_id_for_update(rule_id)
        if rule is None:
            raise RewardConfigNotFoundError("Customer reward rule not found.")

        publish_at = effective_from if effective_from is not None else now
        previous = self._customer_reward_rules.get_active_for_update(
            reward_type=rule.reward_type, now=publish_at
        )
        if previous is not None and previous.id != rule.id:
            previous.effective_until = publish_at
            self._customer_reward_rules.save(previous)

        rule.publish(effective_from=publish_at)
        self._customer_reward_rules.save(rule)
        return rule
