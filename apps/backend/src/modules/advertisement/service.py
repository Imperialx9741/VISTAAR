"""Application service (use cases) for Advertisement.

Implements domain-design.md §22.3's six commands (CreateCampaign,
AssignDriver, SubmitInstallationProof, VerifyAdvertisement,
CalculatePayout, SettlePayout — the last split into calculate_payout()
+ mark_payout_paid() here, see below) — scoped per ADR-0018: no HTTP
router, no Admoto integration (VerifyAdvertisement is a manual admin
decision instead), no wallet/outbox composition inside this service
(that belongs to a future router/composition layer this module has no
dependency on, matching every other module's architecture in this
codebase).

calculate_payout()/mark_payout_paid() are two separate methods, not one
SettlePayout, because crediting the driver's wallet (a different
module, WalletService.credit()) must happen BETWEEN them — the same
"lock/validate/act, then let the caller do the cross-module part"
shape modules.wallet.service.WalletService.debit() already established
for Accept Offer. A future router would call: calculate_payout() ->
WalletService.credit(...) -> mark_payout_paid() — see
tests/test_advertisement_service.py's
test_full_campaign_to_payout_flow_composes_with_wallet_credit for a
worked example of that composition.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

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
    InvalidDriverCampaignStateError,
    PayoutAlreadySettledError,
    PayoutNotFoundError,
)
from modules.advertisement.ports import (
    CampaignRepository,
    DriverCampaignRepository,
    PayoutRepository,
)


class AdvertisementService:
    def __init__(
        self,
        *,
        campaigns: CampaignRepository,
        driver_campaigns: DriverCampaignRepository,
        payouts: PayoutRepository,
    ) -> None:
        self._campaigns = campaigns
        self._driver_campaigns = driver_campaigns
        self._payouts = payouts

    def create_campaign(
        self,
        *,
        partner_name: str,
        payout_amount: Decimal,
        driver_share_percent: Decimal = Decimal("80"),
        vistaar_share_percent: Decimal = Decimal("20"),
        starts_at: datetime | None,
        ends_at: datetime | None,
        now: datetime,
    ) -> Campaign:
        campaign = Campaign.new(
            partner_name=partner_name,
            payout_amount=payout_amount,
            driver_share_percent=driver_share_percent,
            vistaar_share_percent=vistaar_share_percent,
            starts_at=starts_at,
            ends_at=ends_at,
            now=now,
        )
        return self._campaigns.create(campaign)

    def assign_driver(
        self, *, campaign_id: uuid.UUID, driver_id: uuid.UUID, now: datetime
    ) -> DriverCampaign:
        campaign = self._campaigns.get_by_id(campaign_id)
        if campaign is None:
            raise CampaignNotFoundError("Campaign not found.")
        if campaign.status is not CampaignStatus.ACTIVE:
            # ADR-0046 Decision 1: a PAUSED/ENDED campaign accepts no
            # new assignments — existing ones already in flight are
            # unaffected.
            raise CampaignNotActiveError(
                f"Campaign is {campaign.status.value}, not ACTIVE."
            )
        assignment = DriverCampaign.new(
            campaign_id=campaign_id, driver_id=driver_id, now=now
        )
        return self._driver_campaigns.create(assignment)

    def submit_installation_proof(
        self,
        *,
        assignment_id: uuid.UUID,
        driver_id: uuid.UUID,
        proof_uri: str,
        now: datetime,
    ) -> DriverCampaign:
        assignment = self._driver_campaigns.get_by_id(assignment_id)
        if assignment is None or assignment.driver_id != driver_id:
            # IDOR-safe "not found either way" — same pattern used
            # throughout this codebase.
            raise DriverCampaignNotFoundError("Assignment not found.")
        if assignment.status is not DriverCampaignStatus.ASSIGNED:
            raise InvalidDriverCampaignStateError(
                "Proof can only be submitted for an ASSIGNED campaign."
            )
        if not proof_uri.strip():
            raise InvalidDriverCampaignStateError("proof_uri cannot be blank.")

        assignment.proof_uri = proof_uri.strip()
        assignment.status = DriverCampaignStatus.PROOF_SUBMITTED
        assignment.verification_status = VerificationStatus.PENDING
        self._driver_campaigns.save(assignment)
        return assignment

    def verify_advertisement(
        self, *, assignment_id: uuid.UUID, approved: bool, now: datetime
    ) -> DriverCampaign:
        """ADR-0018 Decision 1: a manual admin decision — Admoto (or any
        automated verification provider) is not integrated."""
        assignment = self._driver_campaigns.get_by_id(assignment_id)
        if assignment is None:
            raise DriverCampaignNotFoundError("Assignment not found.")
        if assignment.status is not DriverCampaignStatus.PROOF_SUBMITTED:
            raise InvalidDriverCampaignStateError(
                "Only a PROOF_SUBMITTED assignment can be verified."
            )

        assignment.status = (
            DriverCampaignStatus.VERIFIED if approved else DriverCampaignStatus.REJECTED
        )
        assignment.verification_status = (
            VerificationStatus.APPROVED if approved else VerificationStatus.REJECTED
        )
        self._driver_campaigns.save(assignment)
        return assignment

    def calculate_payout(self, *, assignment_id: uuid.UUID, now: datetime) -> Payout:
        assignment = self._driver_campaigns.get_by_id(assignment_id)
        if assignment is None:
            raise DriverCampaignNotFoundError("Assignment not found.")
        if assignment.status is not DriverCampaignStatus.VERIFIED:
            raise InvalidDriverCampaignStateError(
                "Only a VERIFIED assignment can have a payout calculated."
            )
        campaign = self._campaigns.get_by_id(assignment.campaign_id)
        if campaign is None:
            raise CampaignNotFoundError("Campaign not found.")

        payout = Payout.new(
            driver_campaign_id=assignment.id,
            gross_amount=campaign.payout_amount,
            driver_share_percent=campaign.driver_share_percent,
            vistaar_share_percent=campaign.vistaar_share_percent,
            now=now,
        )
        # PayoutRepository.create() raises PayoutAlreadyCalculatedError
        # on a duplicate (uq_payouts_driver_campaign) — propagates as-is.
        return self._payouts.create(payout)

    def mark_payout_paid(self, *, payout_id: uuid.UUID) -> Payout:
        """Called after the caller has already credited the driver's
        wallet (WalletService.credit(), transaction_type=
        ADVERTISEMENT_PAYOUT) — this method only records that the
        payout is now settled; it does not move money itself (this
        module has no dependency on modules.wallet)."""
        payout = self._payouts.get_by_id(payout_id)
        if payout is None:
            raise PayoutNotFoundError("Payout not found.")
        if payout.status is not PayoutStatus.PENDING:
            raise PayoutAlreadySettledError("This payout has already been settled.")

        payout.status = PayoutStatus.PAID
        self._payouts.save(payout)

        assignment = self._driver_campaigns.get_by_id(payout.driver_campaign_id)
        if assignment is not None:
            assignment.status = DriverCampaignStatus.PAID
            self._driver_campaigns.save(assignment)

        return payout

    # --- Advertisement Admin API (Admin Web §4.15, ADR-0046) --------------

    def get_campaign(self, campaign_id: uuid.UUID) -> Campaign:
        campaign = self._campaigns.get_by_id(campaign_id)
        if campaign is None:
            raise CampaignNotFoundError("Campaign not found.")
        return campaign

    def list_campaigns(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[Campaign], int]:
        return self._campaigns.list_all(status=status, offset=offset, limit=limit)

    def pause_campaign(self, campaign_id: uuid.UUID) -> Campaign:
        campaign = self._campaigns.get_by_id(campaign_id)
        if campaign is None:
            raise CampaignNotFoundError("Campaign not found.")
        campaign.pause()
        self._campaigns.save(campaign)
        return campaign

    def resume_campaign(self, campaign_id: uuid.UUID) -> Campaign:
        campaign = self._campaigns.get_by_id(campaign_id)
        if campaign is None:
            raise CampaignNotFoundError("Campaign not found.")
        campaign.resume()
        self._campaigns.save(campaign)
        return campaign

    def end_campaign(self, campaign_id: uuid.UUID) -> Campaign:
        campaign = self._campaigns.get_by_id(campaign_id)
        if campaign is None:
            raise CampaignNotFoundError("Campaign not found.")
        campaign.end()
        self._campaigns.save(campaign)
        return campaign

    def get_assignment(self, assignment_id: uuid.UUID) -> DriverCampaign:
        assignment = self._driver_campaigns.get_by_id(assignment_id)
        if assignment is None:
            raise DriverCampaignNotFoundError("Assignment not found.")
        return assignment

    def search_assignments(
        self,
        *,
        campaign_id: uuid.UUID | None,
        driver_id: uuid.UUID | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[DriverCampaign], int]:
        return self._driver_campaigns.search(
            campaign_id=campaign_id,
            driver_id=driver_id,
            status=status,
            offset=offset,
            limit=limit,
        )

    def get_payout(self, payout_id: uuid.UUID) -> Payout:
        payout = self._payouts.get_by_id(payout_id)
        if payout is None:
            raise PayoutNotFoundError("Payout not found.")
        return payout

    def list_payouts(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[Payout], int]:
        return self._payouts.list_by_status(status=status, offset=offset, limit=limit)
