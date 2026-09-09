"""SQLAlchemy-backed implementations of Referral's ports."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from modules.referral.domain.entities import (
    CustomerRewardRule,
    DriverBonusRule,
    OwnerType,
    Referral,
    ReferralCode,
    ReferralCodeStatus,
    ReferralStatus,
    Reward,
    RewardConfigStatus,
    RewardStatus,
    RewardType,
)
from modules.referral.domain.errors import AlreadyReferredError
from modules.referral.models import (
    CustomerRewardRuleORM,
    DriverBonusRuleORM,
    ReferralCodeORM,
    ReferralORM,
    RewardORM,
)


def _code_from_orm(row: ReferralCodeORM) -> ReferralCode:
    return ReferralCode(
        id=row.id,
        owner_type=OwnerType(row.owner_type),
        owner_id=row.owner_id,
        code=row.code,
        status=ReferralCodeStatus(row.status),
        created_at=row.created_at,
    )


def _referral_from_orm(row: ReferralORM) -> Referral:
    return Referral(
        id=row.id,
        referral_code_id=row.referral_code_id,
        referrer_id=row.referrer_id,
        referred_id=row.referred_id,
        referred_type=OwnerType(row.referred_type),
        status=ReferralStatus(row.status),
        activated_at=row.activated_at,
        created_at=row.created_at,
    )


def _reward_from_orm(row: RewardORM) -> Reward:
    return Reward(
        id=row.id,
        referral_id=row.referral_id,
        recipient_id=row.recipient_id,
        reward_type=RewardType(row.reward_type),
        amount=row.amount,
        promotion_uses=row.promotion_uses,
        status=RewardStatus(row.status),
        idempotency_key=row.idempotency_key,
        created_at=row.created_at,
    )


def _driver_bonus_rule_from_orm(row: DriverBonusRuleORM) -> DriverBonusRule:
    return DriverBonusRule(
        id=row.id,
        referred_amount=row.referred_amount,
        referrer_amount=row.referrer_amount,
        status=RewardConfigStatus(row.status),
        effective_from=row.effective_from,
        effective_until=row.effective_until,
        created_by=row.created_by,
        created_at=row.created_at,
    )


def _customer_reward_rule_from_orm(row: CustomerRewardRuleORM) -> CustomerRewardRule:
    return CustomerRewardRule(
        id=row.id,
        reward_type=row.reward_type,
        discount_percent=row.discount_percent,
        total_uses=row.total_uses,
        status=RewardConfigStatus(row.status),
        effective_from=row.effective_from,
        effective_until=row.effective_until,
        created_by=row.created_by,
        created_at=row.created_at,
    )


class SqlAlchemyReferralCodeRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, code: ReferralCode) -> ReferralCode:
        row = ReferralCodeORM(
            id=code.id,
            owner_type=code.owner_type.value,
            owner_id=code.owner_id,
            code=code.code,
            status=code.status.value,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _code_from_orm(row)

    def get_by_code(self, code: str) -> ReferralCode | None:
        row = self._db.execute(
            select(ReferralCodeORM).where(ReferralCodeORM.code == code)
        ).scalar_one_or_none()
        return _code_from_orm(row) if row else None

    def get_by_owner(
        self, owner_type: OwnerType, owner_id: uuid.UUID
    ) -> ReferralCode | None:
        row = self._db.execute(
            select(ReferralCodeORM)
            .where(ReferralCodeORM.owner_type == owner_type.value)
            .where(ReferralCodeORM.owner_id == owner_id)
        ).scalar_one_or_none()
        return _code_from_orm(row) if row else None


class SqlAlchemyReferralRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, referral: Referral) -> Referral:
        row = ReferralORM(
            id=referral.id,
            referral_code_id=referral.referral_code_id,
            referrer_id=referral.referrer_id,
            referred_id=referral.referred_id,
            referred_type=referral.referred_type.value,
            status=referral.status.value,
            activated_at=referral.activated_at,
        )
        self._db.add(row)
        try:
            self._db.flush()
        except IntegrityError as exc:
            self._db.rollback()
            raise AlreadyReferredError(
                "This account has already been referred."
            ) from exc
        self._db.refresh(row)
        return _referral_from_orm(row)

    def get_by_id(self, referral_id: uuid.UUID) -> Referral | None:
        row = self._db.get(ReferralORM, referral_id)
        return _referral_from_orm(row) if row else None

    def get_by_referred_id(self, referred_id: uuid.UUID) -> Referral | None:
        row = self._db.execute(
            select(ReferralORM).where(ReferralORM.referred_id == referred_id)
        ).scalar_one_or_none()
        return _referral_from_orm(row) if row else None

    def save(self, referral: Referral) -> None:
        row = self._db.get(ReferralORM, referral.id)
        if row is None:
            raise LookupError(f"Referral {referral.id} not found")
        row.status = referral.status.value
        row.activated_at = referral.activated_at
        self._db.flush()

    def list_all(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[Referral], int]:
        base = select(ReferralORM)
        count_query = select(func.count()).select_from(ReferralORM)
        if status:
            base = base.where(ReferralORM.status == status)
            count_query = count_query.where(ReferralORM.status == status)

        total = self._db.execute(count_query).scalar_one()
        rows = (
            self._db.execute(
                base.order_by(ReferralORM.created_at.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )
        return [_referral_from_orm(row) for row in rows], total

    def count_by_status(self) -> dict[str, int]:
        rows = self._db.execute(
            select(ReferralORM.status, func.count()).group_by(ReferralORM.status)
        ).all()
        return {key: value for key, value in rows}  # noqa: C416


class SqlAlchemyRewardRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, reward: Reward) -> Reward:
        row = RewardORM(
            id=reward.id,
            referral_id=reward.referral_id,
            recipient_id=reward.recipient_id,
            reward_type=reward.reward_type.value,
            amount=reward.amount,
            promotion_uses=reward.promotion_uses,
            status=reward.status.value,
            idempotency_key=reward.idempotency_key,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _reward_from_orm(row)

    def get_by_idempotency_key(self, idempotency_key: str) -> Reward | None:
        row = self._db.execute(
            select(RewardORM).where(RewardORM.idempotency_key == idempotency_key)
        ).scalar_one_or_none()
        return _reward_from_orm(row) if row else None

    def list_for_referral(self, referral_id: uuid.UUID) -> list[Reward]:
        rows = (
            self._db.execute(
                select(RewardORM)
                .where(RewardORM.referral_id == referral_id)
                .order_by(RewardORM.created_at)
            )
            .scalars()
            .all()
        )
        return [_reward_from_orm(row) for row in rows]

    def sum_amount_issued_in_range(
        self, *, since: datetime, until: datetime
    ) -> Decimal:
        total = self._db.execute(
            select(func.coalesce(func.sum(RewardORM.amount), 0))
            .where(RewardORM.amount.is_not(None))
            .where(RewardORM.created_at >= since)
            .where(RewardORM.created_at < until)
        ).scalar_one()
        return Decimal(total) if total is not None else Decimal("0")


class SqlAlchemyDriverBonusRuleRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, rule: DriverBonusRule) -> DriverBonusRule:
        row = DriverBonusRuleORM(
            id=rule.id,
            referred_amount=rule.referred_amount,
            referrer_amount=rule.referrer_amount,
            status=rule.status.value,
            effective_from=rule.effective_from,
            effective_until=rule.effective_until,
            created_by=rule.created_by,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _driver_bonus_rule_from_orm(row)

    def get_by_id(self, rule_id: uuid.UUID) -> DriverBonusRule | None:
        row = self._db.get(DriverBonusRuleORM, rule_id)
        return _driver_bonus_rule_from_orm(row) if row else None

    def get_by_id_for_update(self, rule_id: uuid.UUID) -> DriverBonusRule | None:
        row = self._db.execute(
            select(DriverBonusRuleORM)
            .where(DriverBonusRuleORM.id == rule_id)
            .with_for_update()
        ).scalar_one_or_none()
        return _driver_bonus_rule_from_orm(row) if row else None

    def save(self, rule: DriverBonusRule) -> None:
        row = self._db.get(DriverBonusRuleORM, rule.id)
        if row is None:
            raise LookupError(f"Driver bonus rule {rule.id} not found")
        row.status = rule.status.value
        row.effective_from = rule.effective_from
        row.effective_until = rule.effective_until
        self._db.flush()

    def list_all(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[DriverBonusRule], int]:
        filters: list[ColumnElement[bool]] = []
        if status:
            filters.append(DriverBonusRuleORM.status == status)

        total = self._db.execute(
            select(func.count()).select_from(DriverBonusRuleORM).where(*filters)
        ).scalar_one()
        rows = (
            self._db.execute(
                select(DriverBonusRuleORM)
                .where(*filters)
                .order_by(DriverBonusRuleORM.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_driver_bonus_rule_from_orm(row) for row in rows], total

    def _active_query(self, *, now: datetime) -> Select[tuple[DriverBonusRuleORM]]:
        return (
            select(DriverBonusRuleORM)
            .where(DriverBonusRuleORM.status == RewardConfigStatus.PUBLISHED.value)
            .where(DriverBonusRuleORM.effective_from <= now)
            .where(
                or_(
                    DriverBonusRuleORM.effective_until.is_(None),
                    DriverBonusRuleORM.effective_until > now,
                )
            )
            .order_by(DriverBonusRuleORM.effective_from.desc())
        )

    def get_active(self, *, now: datetime) -> DriverBonusRule | None:
        row = self._db.execute(self._active_query(now=now)).scalars().first()
        return _driver_bonus_rule_from_orm(row) if row else None

    def get_active_for_update(self, *, now: datetime) -> DriverBonusRule | None:
        row = (
            self._db.execute(self._active_query(now=now).with_for_update())
            .scalars()
            .first()
        )
        return _driver_bonus_rule_from_orm(row) if row else None


class SqlAlchemyCustomerRewardRuleRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, rule: CustomerRewardRule) -> CustomerRewardRule:
        row = CustomerRewardRuleORM(
            id=rule.id,
            reward_type=rule.reward_type,
            discount_percent=rule.discount_percent,
            total_uses=rule.total_uses,
            status=rule.status.value,
            effective_from=rule.effective_from,
            effective_until=rule.effective_until,
            created_by=rule.created_by,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _customer_reward_rule_from_orm(row)

    def get_by_id(self, rule_id: uuid.UUID) -> CustomerRewardRule | None:
        row = self._db.get(CustomerRewardRuleORM, rule_id)
        return _customer_reward_rule_from_orm(row) if row else None

    def get_by_id_for_update(self, rule_id: uuid.UUID) -> CustomerRewardRule | None:
        row = self._db.execute(
            select(CustomerRewardRuleORM)
            .where(CustomerRewardRuleORM.id == rule_id)
            .with_for_update()
        ).scalar_one_or_none()
        return _customer_reward_rule_from_orm(row) if row else None

    def save(self, rule: CustomerRewardRule) -> None:
        row = self._db.get(CustomerRewardRuleORM, rule.id)
        if row is None:
            raise LookupError(f"Customer reward rule {rule.id} not found")
        row.status = rule.status.value
        row.effective_from = rule.effective_from
        row.effective_until = rule.effective_until
        self._db.flush()

    def list_all(
        self, *, reward_type: str | None, status: str | None, offset: int, limit: int
    ) -> tuple[list[CustomerRewardRule], int]:
        filters: list[ColumnElement[bool]] = []
        if reward_type:
            filters.append(CustomerRewardRuleORM.reward_type == reward_type)
        if status:
            filters.append(CustomerRewardRuleORM.status == status)

        total = self._db.execute(
            select(func.count()).select_from(CustomerRewardRuleORM).where(*filters)
        ).scalar_one()
        rows = (
            self._db.execute(
                select(CustomerRewardRuleORM)
                .where(*filters)
                .order_by(CustomerRewardRuleORM.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_customer_reward_rule_from_orm(row) for row in rows], total

    def _active_query(
        self, *, reward_type: str, now: datetime
    ) -> Select[tuple[CustomerRewardRuleORM]]:
        return (
            select(CustomerRewardRuleORM)
            .where(CustomerRewardRuleORM.reward_type == reward_type)
            .where(CustomerRewardRuleORM.status == RewardConfigStatus.PUBLISHED.value)
            .where(CustomerRewardRuleORM.effective_from <= now)
            .where(
                or_(
                    CustomerRewardRuleORM.effective_until.is_(None),
                    CustomerRewardRuleORM.effective_until > now,
                )
            )
            .order_by(CustomerRewardRuleORM.effective_from.desc())
        )

    def get_active(
        self, *, reward_type: str, now: datetime
    ) -> CustomerRewardRule | None:
        row = (
            self._db.execute(self._active_query(reward_type=reward_type, now=now))
            .scalars()
            .first()
        )
        return _customer_reward_rule_from_orm(row) if row else None

    def get_active_for_update(
        self, *, reward_type: str, now: datetime
    ) -> CustomerRewardRule | None:
        row = (
            self._db.execute(
                self._active_query(reward_type=reward_type, now=now).with_for_update()
            )
            .scalars()
            .first()
        )
        return _customer_reward_rule_from_orm(row) if row else None
