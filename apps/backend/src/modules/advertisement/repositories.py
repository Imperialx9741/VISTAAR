"""SQLAlchemy-backed implementations of Advertisement's ports."""

from __future__ import annotations

import uuid

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from modules.advertisement.domain.entities import (
    Campaign,
    CampaignStatus,
    DriverCampaign,
    DriverCampaignStatus,
    Payout,
    PayoutStatus,
    VerificationStatus,
)
from modules.advertisement.domain.errors import PayoutAlreadyCalculatedError
from modules.advertisement.models import CampaignORM, DriverCampaignORM, PayoutORM


def _campaign_from_orm(row: CampaignORM) -> Campaign:
    return Campaign(
        id=row.id,
        partner_name=row.partner_name,
        status=CampaignStatus(row.status),
        payout_amount=row.payout_amount,
        driver_share_percent=row.driver_share_percent,
        vistaar_share_percent=row.vistaar_share_percent,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        created_at=row.created_at,
    )


def _driver_campaign_from_orm(row: DriverCampaignORM) -> DriverCampaign:
    return DriverCampaign(
        id=row.id,
        campaign_id=row.campaign_id,
        driver_id=row.driver_id,
        status=DriverCampaignStatus(row.status),
        proof_uri=row.proof_uri,
        verification_status=(
            VerificationStatus(row.verification_status)
            if row.verification_status
            else None
        ),
        assigned_at=row.assigned_at,
    )


def _payout_from_orm(row: PayoutORM) -> Payout:
    return Payout(
        id=row.id,
        driver_campaign_id=row.driver_campaign_id,
        gross_amount=row.gross_amount,
        driver_amount=row.driver_amount,
        vistaar_amount=row.vistaar_amount,
        status=PayoutStatus(row.status),
        created_at=row.created_at,
    )


class SqlAlchemyCampaignRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, campaign: Campaign) -> Campaign:
        row = CampaignORM(
            id=campaign.id,
            partner_name=campaign.partner_name,
            status=campaign.status.value,
            payout_amount=campaign.payout_amount,
            driver_share_percent=campaign.driver_share_percent,
            vistaar_share_percent=campaign.vistaar_share_percent,
            starts_at=campaign.starts_at,
            ends_at=campaign.ends_at,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _campaign_from_orm(row)

    def get_by_id(self, campaign_id: uuid.UUID) -> Campaign | None:
        row = self._db.get(CampaignORM, campaign_id)
        return _campaign_from_orm(row) if row else None

    def save(self, campaign: Campaign) -> None:
        row = self._db.get(CampaignORM, campaign.id)
        if row is None:
            raise LookupError(f"Campaign {campaign.id} not found")
        row.status = campaign.status.value
        self._db.flush()

    def list_all(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[Campaign], int]:
        filters: list[ColumnElement[bool]] = []
        if status:
            filters.append(CampaignORM.status == status)

        total = self._db.execute(
            select(func.count()).select_from(CampaignORM).where(*filters)
        ).scalar_one()
        rows = (
            self._db.execute(
                select(CampaignORM)
                .where(*filters)
                .order_by(CampaignORM.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_campaign_from_orm(row) for row in rows], total


class SqlAlchemyDriverCampaignRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, assignment: DriverCampaign) -> DriverCampaign:
        row = DriverCampaignORM(
            id=assignment.id,
            campaign_id=assignment.campaign_id,
            driver_id=assignment.driver_id,
            status=assignment.status.value,
            proof_uri=assignment.proof_uri,
            verification_status=(
                assignment.verification_status.value
                if assignment.verification_status
                else None
            ),
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _driver_campaign_from_orm(row)

    def get_by_id(self, assignment_id: uuid.UUID) -> DriverCampaign | None:
        row = self._db.get(DriverCampaignORM, assignment_id)
        return _driver_campaign_from_orm(row) if row else None

    def save(self, assignment: DriverCampaign) -> None:
        row = self._db.get(DriverCampaignORM, assignment.id)
        if row is None:
            raise LookupError(f"DriverCampaign {assignment.id} not found")
        row.status = assignment.status.value
        row.proof_uri = assignment.proof_uri
        row.verification_status = (
            assignment.verification_status.value
            if assignment.verification_status
            else None
        )
        self._db.flush()

    def search(
        self,
        *,
        campaign_id: uuid.UUID | None,
        driver_id: uuid.UUID | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[DriverCampaign], int]:
        filters: list[ColumnElement[bool]] = []
        if campaign_id is not None:
            filters.append(DriverCampaignORM.campaign_id == campaign_id)
        if driver_id is not None:
            filters.append(DriverCampaignORM.driver_id == driver_id)
        if status:
            filters.append(DriverCampaignORM.status == status)

        total = self._db.execute(
            select(func.count()).select_from(DriverCampaignORM).where(*filters)
        ).scalar_one()
        rows = (
            self._db.execute(
                select(DriverCampaignORM)
                .where(*filters)
                .order_by(DriverCampaignORM.assigned_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_driver_campaign_from_orm(row) for row in rows], total


class SqlAlchemyPayoutRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, payout: Payout) -> Payout:
        row = PayoutORM(
            id=payout.id,
            driver_campaign_id=payout.driver_campaign_id,
            gross_amount=payout.gross_amount,
            driver_amount=payout.driver_amount,
            vistaar_amount=payout.vistaar_amount,
            status=payout.status.value,
        )
        self._db.add(row)
        try:
            self._db.flush()
        except IntegrityError as exc:
            # uq_payouts_driver_campaign — a payout already exists for
            # this driver_campaign_id.
            self._db.rollback()
            raise PayoutAlreadyCalculatedError(
                "A payout has already been calculated for this driver campaign."
            ) from exc
        self._db.refresh(row)
        return _payout_from_orm(row)

    def get_by_id(self, payout_id: uuid.UUID) -> Payout | None:
        row = self._db.get(PayoutORM, payout_id)
        return _payout_from_orm(row) if row else None

    def get_by_driver_campaign_id(self, driver_campaign_id: uuid.UUID) -> Payout | None:
        row = self._db.execute(
            select(PayoutORM).where(PayoutORM.driver_campaign_id == driver_campaign_id)
        ).scalar_one_or_none()
        return _payout_from_orm(row) if row else None

    def save(self, payout: Payout) -> None:
        row = self._db.get(PayoutORM, payout.id)
        if row is None:
            raise LookupError(f"Payout {payout.id} not found")
        row.status = payout.status.value
        self._db.flush()

    def list_by_status(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[Payout], int]:
        filters: list[ColumnElement[bool]] = []
        if status:
            filters.append(PayoutORM.status == status)

        total = self._db.execute(
            select(func.count()).select_from(PayoutORM).where(*filters)
        ).scalar_one()
        rows = (
            self._db.execute(
                select(PayoutORM)
                .where(*filters)
                .order_by(PayoutORM.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_payout_from_orm(row) for row in rows], total
