"""Unit tests for AdvertisementService against in-memory fake
repositories."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from modules.advertisement.domain.entities import (
    Campaign,
    CampaignStatus,
    DriverCampaign,
    DriverCampaignStatus,
    Payout,
    PayoutStatus,
    VerificationStatus,
)
from modules.advertisement.domain.errors import (
    CampaignNotActiveError,
    CampaignNotFoundError,
    DriverCampaignNotFoundError,
    InvalidCampaignInputError,
    InvalidCampaignStateTransitionError,
    InvalidDriverCampaignStateError,
    PayoutAlreadyCalculatedError,
    PayoutAlreadySettledError,
    PayoutNotFoundError,
)
from modules.advertisement.service import AdvertisementService

NOW = datetime.now(UTC)
DRIVER_ID = uuid.uuid4()


class FakeCampaignRepository:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, Campaign] = {}

    def create(self, campaign: Campaign) -> Campaign:
        self.by_id[campaign.id] = campaign
        return campaign

    def get_by_id(self, campaign_id: uuid.UUID) -> Campaign | None:
        return self.by_id.get(campaign_id)

    def save(self, campaign: Campaign) -> None:
        self.by_id[campaign.id] = campaign

    def list_all(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[Campaign], int]:
        matches = sorted(
            (
                c
                for c in self.by_id.values()
                if status is None or c.status.value == status
            ),
            key=lambda c: c.created_at,
            reverse=True,
        )
        return matches[offset : offset + limit], len(matches)


class FakeDriverCampaignRepository:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, DriverCampaign] = {}

    def create(self, assignment: DriverCampaign) -> DriverCampaign:
        self.by_id[assignment.id] = assignment
        return assignment

    def get_by_id(self, assignment_id: uuid.UUID) -> DriverCampaign | None:
        return self.by_id.get(assignment_id)

    def save(self, assignment: DriverCampaign) -> None:
        self.by_id[assignment.id] = assignment

    def search(
        self,
        *,
        campaign_id: uuid.UUID | None,
        driver_id: uuid.UUID | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[DriverCampaign], int]:
        matches = sorted(
            (
                a
                for a in self.by_id.values()
                if (campaign_id is None or a.campaign_id == campaign_id)
                and (driver_id is None or a.driver_id == driver_id)
                and (status is None or a.status.value == status)
            ),
            key=lambda a: a.assigned_at,
            reverse=True,
        )
        return matches[offset : offset + limit], len(matches)


class FakePayoutRepository:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, Payout] = {}
        self.by_driver_campaign: dict[uuid.UUID, Payout] = {}

    def create(self, payout: Payout) -> Payout:
        if payout.driver_campaign_id in self.by_driver_campaign:
            raise PayoutAlreadyCalculatedError(
                "A payout has already been calculated for this driver campaign."
            )
        self.by_id[payout.id] = payout
        self.by_driver_campaign[payout.driver_campaign_id] = payout
        return payout

    def get_by_id(self, payout_id: uuid.UUID) -> Payout | None:
        return self.by_id.get(payout_id)

    def get_by_driver_campaign_id(self, driver_campaign_id: uuid.UUID) -> Payout | None:
        return self.by_driver_campaign.get(driver_campaign_id)

    def save(self, payout: Payout) -> None:
        self.by_id[payout.id] = payout
        self.by_driver_campaign[payout.driver_campaign_id] = payout

    def list_by_status(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[Payout], int]:
        matches = sorted(
            (
                p
                for p in self.by_id.values()
                if status is None or p.status.value == status
            ),
            key=lambda p: p.created_at,
            reverse=True,
        )
        return matches[offset : offset + limit], len(matches)


@pytest.fixture
def campaigns() -> FakeCampaignRepository:
    return FakeCampaignRepository()


@pytest.fixture
def driver_campaigns() -> FakeDriverCampaignRepository:
    return FakeDriverCampaignRepository()


@pytest.fixture
def payouts() -> FakePayoutRepository:
    return FakePayoutRepository()


@pytest.fixture
def service(
    campaigns: FakeCampaignRepository,
    driver_campaigns: FakeDriverCampaignRepository,
    payouts: FakePayoutRepository,
) -> AdvertisementService:
    return AdvertisementService(
        campaigns=campaigns, driver_campaigns=driver_campaigns, payouts=payouts
    )


def _create_campaign(
    service: AdvertisementService, *, payout_amount: Decimal = Decimal("1000")
) -> Campaign:
    return service.create_campaign(
        partner_name="Admoto",
        payout_amount=payout_amount,
        starts_at=None,
        ends_at=None,
        now=NOW,
    )


# --- create_campaign ---------------------------------------------------


def test_create_campaign_is_active_by_default(service: AdvertisementService) -> None:
    campaign = _create_campaign(service)
    assert campaign.status.value == "ACTIVE"
    assert campaign.driver_share_percent == Decimal("80")
    assert campaign.vistaar_share_percent == Decimal("20")


def test_create_campaign_rejects_blank_partner_name(
    service: AdvertisementService,
) -> None:
    with pytest.raises(InvalidCampaignInputError):
        service.create_campaign(
            partner_name="   ",
            payout_amount=Decimal("1000"),
            starts_at=None,
            ends_at=None,
            now=NOW,
        )


def test_create_campaign_rejects_shares_not_summing_to_100(
    service: AdvertisementService,
) -> None:
    with pytest.raises(InvalidCampaignInputError):
        service.create_campaign(
            partner_name="Admoto",
            payout_amount=Decimal("1000"),
            driver_share_percent=Decimal("70"),
            vistaar_share_percent=Decimal("20"),
            starts_at=None,
            ends_at=None,
            now=NOW,
        )


def test_create_campaign_rejects_non_positive_payout(
    service: AdvertisementService,
) -> None:
    with pytest.raises(InvalidCampaignInputError):
        service.create_campaign(
            partner_name="Admoto",
            payout_amount=Decimal("0"),
            starts_at=None,
            ends_at=None,
            now=NOW,
        )


# --- assign_driver ------------------------------------------------------


def test_assign_driver_creates_an_assigned_row(service: AdvertisementService) -> None:
    campaign = _create_campaign(service)
    assignment = service.assign_driver(
        campaign_id=campaign.id, driver_id=DRIVER_ID, now=NOW
    )
    assert assignment.status is DriverCampaignStatus.ASSIGNED
    assert assignment.campaign_id == campaign.id
    assert assignment.driver_id == DRIVER_ID


def test_assign_driver_raises_for_unknown_campaign(
    service: AdvertisementService,
) -> None:
    with pytest.raises(CampaignNotFoundError):
        service.assign_driver(campaign_id=uuid.uuid4(), driver_id=DRIVER_ID, now=NOW)


# --- submit_installation_proof ------------------------------------------


def test_submit_installation_proof_transitions_to_proof_submitted(
    service: AdvertisementService,
) -> None:
    campaign = _create_campaign(service)
    assignment = service.assign_driver(
        campaign_id=campaign.id, driver_id=DRIVER_ID, now=NOW
    )

    updated = service.submit_installation_proof(
        assignment_id=assignment.id,
        driver_id=DRIVER_ID,
        proof_uri="ref-photo-1",
        now=NOW,
    )

    assert updated.status is DriverCampaignStatus.PROOF_SUBMITTED
    assert updated.proof_uri == "ref-photo-1"
    assert updated.verification_status is VerificationStatus.PENDING


def test_submit_installation_proof_raises_for_another_drivers_assignment(
    service: AdvertisementService,
) -> None:
    campaign = _create_campaign(service)
    assignment = service.assign_driver(
        campaign_id=campaign.id, driver_id=DRIVER_ID, now=NOW
    )
    with pytest.raises(DriverCampaignNotFoundError):
        service.submit_installation_proof(
            assignment_id=assignment.id,
            driver_id=uuid.uuid4(),
            proof_uri="ref-photo-1",
            now=NOW,
        )


def test_submit_installation_proof_raises_when_already_submitted(
    service: AdvertisementService,
) -> None:
    campaign = _create_campaign(service)
    assignment = service.assign_driver(
        campaign_id=campaign.id, driver_id=DRIVER_ID, now=NOW
    )
    service.submit_installation_proof(
        assignment_id=assignment.id, driver_id=DRIVER_ID, proof_uri="ref-1", now=NOW
    )

    with pytest.raises(InvalidDriverCampaignStateError):
        service.submit_installation_proof(
            assignment_id=assignment.id,
            driver_id=DRIVER_ID,
            proof_uri="ref-2",
            now=NOW,
        )


def test_submit_installation_proof_rejects_blank_uri(
    service: AdvertisementService,
) -> None:
    campaign = _create_campaign(service)
    assignment = service.assign_driver(
        campaign_id=campaign.id, driver_id=DRIVER_ID, now=NOW
    )
    with pytest.raises(InvalidDriverCampaignStateError):
        service.submit_installation_proof(
            assignment_id=assignment.id, driver_id=DRIVER_ID, proof_uri="   ", now=NOW
        )


# --- verify_advertisement -------------------------------------------------


def _assigned_with_proof(
    service: AdvertisementService, campaign: Campaign
) -> DriverCampaign:
    assignment = service.assign_driver(
        campaign_id=campaign.id, driver_id=DRIVER_ID, now=NOW
    )
    return service.submit_installation_proof(
        assignment_id=assignment.id, driver_id=DRIVER_ID, proof_uri="ref-1", now=NOW
    )


def test_verify_advertisement_approved(service: AdvertisementService) -> None:
    campaign = _create_campaign(service)
    assignment = _assigned_with_proof(service, campaign)

    verified = service.verify_advertisement(
        assignment_id=assignment.id, approved=True, now=NOW
    )

    assert verified.status is DriverCampaignStatus.VERIFIED
    assert verified.verification_status is VerificationStatus.APPROVED


def test_verify_advertisement_rejected(service: AdvertisementService) -> None:
    campaign = _create_campaign(service)
    assignment = _assigned_with_proof(service, campaign)

    rejected = service.verify_advertisement(
        assignment_id=assignment.id, approved=False, now=NOW
    )

    assert rejected.status is DriverCampaignStatus.REJECTED
    assert rejected.verification_status is VerificationStatus.REJECTED


def test_verify_advertisement_raises_before_proof_submitted(
    service: AdvertisementService,
) -> None:
    campaign = _create_campaign(service)
    assignment = service.assign_driver(
        campaign_id=campaign.id, driver_id=DRIVER_ID, now=NOW
    )
    with pytest.raises(InvalidDriverCampaignStateError):
        service.verify_advertisement(
            assignment_id=assignment.id, approved=True, now=NOW
        )


# --- calculate_payout / mark_payout_paid ---------------------------------


def _verified_assignment(
    service: AdvertisementService, campaign: Campaign
) -> DriverCampaign:
    assignment = _assigned_with_proof(service, campaign)
    return service.verify_advertisement(
        assignment_id=assignment.id, approved=True, now=NOW
    )


def test_calculate_payout_splits_eighty_twenty(service: AdvertisementService) -> None:
    campaign = _create_campaign(service, payout_amount=Decimal("1000"))
    assignment = _verified_assignment(service, campaign)

    payout = service.calculate_payout(assignment_id=assignment.id, now=NOW)

    assert payout.gross_amount == Decimal("1000")
    assert payout.driver_amount == Decimal("800.00")
    assert payout.vistaar_amount == Decimal("200.00")
    assert payout.status is PayoutStatus.PENDING


def test_calculate_payout_raises_before_verified(
    service: AdvertisementService,
) -> None:
    campaign = _create_campaign(service)
    assignment = _assigned_with_proof(service, campaign)
    with pytest.raises(InvalidDriverCampaignStateError):
        service.calculate_payout(assignment_id=assignment.id, now=NOW)


def test_calculate_payout_is_not_idempotent_raises_on_second_call(
    service: AdvertisementService,
) -> None:
    """Unlike Penalty's idempotent-on-conflict shape, recalculating a
    payout is a caller error worth surfacing (ADR-0018/ports.py)."""
    campaign = _create_campaign(service)
    assignment = _verified_assignment(service, campaign)
    service.calculate_payout(assignment_id=assignment.id, now=NOW)

    with pytest.raises(PayoutAlreadyCalculatedError):
        service.calculate_payout(assignment_id=assignment.id, now=NOW)


def test_mark_payout_paid_transitions_payout_and_assignment(
    service: AdvertisementService,
    driver_campaigns: FakeDriverCampaignRepository,
) -> None:
    campaign = _create_campaign(service)
    assignment = _verified_assignment(service, campaign)
    payout = service.calculate_payout(assignment_id=assignment.id, now=NOW)

    settled = service.mark_payout_paid(payout_id=payout.id)

    assert settled.status is PayoutStatus.PAID
    assert driver_campaigns.by_id[assignment.id].status is DriverCampaignStatus.PAID


def test_mark_payout_paid_raises_for_unknown_payout(
    service: AdvertisementService,
) -> None:
    with pytest.raises(PayoutNotFoundError):
        service.mark_payout_paid(payout_id=uuid.uuid4())


def test_mark_payout_paid_raises_when_already_paid(
    service: AdvertisementService,
) -> None:
    campaign = _create_campaign(service)
    assignment = _verified_assignment(service, campaign)
    payout = service.calculate_payout(assignment_id=assignment.id, now=NOW)
    service.mark_payout_paid(payout_id=payout.id)

    with pytest.raises(PayoutAlreadySettledError):
        service.mark_payout_paid(payout_id=payout.id)


# --- Advertisement Admin API (ADR-0046) --------------------------------


def test_pause_then_resume_campaign(service: AdvertisementService) -> None:
    campaign = _create_campaign(service)

    paused = service.pause_campaign(campaign.id)
    assert paused.status is CampaignStatus.PAUSED

    resumed = service.resume_campaign(campaign.id)
    assert resumed.status is CampaignStatus.ACTIVE


def test_end_campaign_is_terminal(service: AdvertisementService) -> None:
    campaign = _create_campaign(service)

    ended = service.end_campaign(campaign.id)
    assert ended.status is CampaignStatus.ENDED

    with pytest.raises(InvalidCampaignStateTransitionError):
        service.resume_campaign(campaign.id)
    with pytest.raises(InvalidCampaignStateTransitionError):
        service.end_campaign(campaign.id)


def test_pause_a_paused_campaign_is_rejected(service: AdvertisementService) -> None:
    campaign = _create_campaign(service)
    service.pause_campaign(campaign.id)

    with pytest.raises(InvalidCampaignStateTransitionError):
        service.pause_campaign(campaign.id)


def test_resume_an_active_campaign_is_rejected(service: AdvertisementService) -> None:
    campaign = _create_campaign(service)

    with pytest.raises(InvalidCampaignStateTransitionError):
        service.resume_campaign(campaign.id)


def test_assign_driver_to_a_paused_campaign_is_rejected(
    service: AdvertisementService,
) -> None:
    campaign = _create_campaign(service)
    service.pause_campaign(campaign.id)

    with pytest.raises(CampaignNotActiveError):
        service.assign_driver(campaign_id=campaign.id, driver_id=DRIVER_ID, now=NOW)


def test_assign_driver_to_an_ended_campaign_is_rejected(
    service: AdvertisementService,
) -> None:
    campaign = _create_campaign(service)
    service.end_campaign(campaign.id)

    with pytest.raises(CampaignNotActiveError):
        service.assign_driver(campaign_id=campaign.id, driver_id=DRIVER_ID, now=NOW)


def test_pausing_a_campaign_does_not_affect_assignments_already_in_flight(
    service: AdvertisementService,
) -> None:
    """ADR-0046 Decision 1: pausing stops new AssignDriver calls, it
    does not strand drivers already participating."""
    campaign = _create_campaign(service)
    assignment = _verified_assignment(service, campaign)

    service.pause_campaign(campaign.id)
    payout = service.calculate_payout(assignment_id=assignment.id, now=NOW)

    assert payout.gross_amount == campaign.payout_amount


def test_get_campaign_unknown_id_raises(service: AdvertisementService) -> None:
    with pytest.raises(CampaignNotFoundError):
        service.get_campaign(uuid.uuid4())


def test_list_campaigns_filters_by_status(service: AdvertisementService) -> None:
    active = _create_campaign(service)
    paused_campaign = _create_campaign(service)
    service.pause_campaign(paused_campaign.id)

    active_only, total = service.list_campaigns(status="ACTIVE", offset=0, limit=20)

    assert total == 1
    assert active_only[0].id == active.id


def test_search_assignments_filters_by_campaign_and_status(
    service: AdvertisementService,
) -> None:
    campaign = _create_campaign(service)
    assignment = service.assign_driver(
        campaign_id=campaign.id, driver_id=DRIVER_ID, now=NOW
    )

    items, total = service.search_assignments(
        campaign_id=campaign.id,
        driver_id=None,
        status="ASSIGNED",
        offset=0,
        limit=20,
    )

    assert total == 1
    assert items[0].id == assignment.id


def test_list_payouts_filters_by_status(service: AdvertisementService) -> None:
    campaign = _create_campaign(service)
    assignment = _verified_assignment(service, campaign)
    payout = service.calculate_payout(assignment_id=assignment.id, now=NOW)

    pending, total = service.list_payouts(status="PENDING", offset=0, limit=20)

    assert total == 1
    assert pending[0].id == payout.id


def test_get_assignment_unknown_id_raises(service: AdvertisementService) -> None:
    with pytest.raises(DriverCampaignNotFoundError):
        service.get_assignment(uuid.uuid4())


def test_get_payout_unknown_id_raises(service: AdvertisementService) -> None:
    with pytest.raises(PayoutNotFoundError):
        service.get_payout(uuid.uuid4())
