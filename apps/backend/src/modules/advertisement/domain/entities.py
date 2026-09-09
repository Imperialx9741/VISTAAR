"""Advertisement domain entities.

Field shapes match docs/04-database/database-design.md §31.1
(advertisement.campaigns), §31.2 (advertisement.driver_campaigns), and
§31.3 (advertisement.payouts) exactly. Status vocabulary (below) is an
engineering completion of an implied-but-undocumented state machine —
see docs/14-decisions/ADR-0018-advertisement-domain-scope-and-open-
items.md Decision 2 for the full reasoning.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from modules.advertisement.domain.errors import (
    InvalidCampaignInputError,
    InvalidCampaignStateTransitionError,
)


class CampaignStatus(StrEnum):
    """A campaign is immediately usable once created — nothing
    documents a draft/approval step before that (ADR-0018 Decision 2).
    Extended by ADR-0046 Decision 1 with a real status lifecycle: ACTIVE
    <-> PAUSED, (ACTIVE or PAUSED) -> ENDED (terminal) — an admin
    campaign-management screen with no way to pause or end a campaign
    isn't real status management, just a permanently-fixed label."""

    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ENDED = "ENDED"


class DriverCampaignStatus(StrEnum):
    """ASSIGNED -> PROOF_SUBMITTED -> VERIFIED | REJECTED -> PAID,
    matching domain-design.md §22.3's six commands' own implied
    ordering (ADR-0018 Decision 2)."""

    ASSIGNED = "ASSIGNED"
    PROOF_SUBMITTED = "PROOF_SUBMITTED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    PAID = "PAID"


class VerificationStatus(StrEnum):
    """Reused verbatim from driver.documents/vehicle.documents'
    verification_status values already established in this codebase
    (ADR-0018 Decision 2) — not a parallel vocabulary."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class PayoutStatus(StrEnum):
    """Matches database-design.md §31.3's documented default and the
    roadmap's own task names ("Payout pending"/"Payout processing")."""

    PENDING = "PENDING"
    PAID = "PAID"


def validate_share_percentages(
    driver_share_percent: Decimal, vistaar_share_percent: Decimal
) -> None:
    """domain-design.md §22.4: "80% -> Driver, 20% -> VISTAAR" — the
    approved current split; campaigns.driver_share_percent/
    vistaar_share_percent (database-design.md §31.1) exist as per-
    campaign columns, not a hard-coded global constant, so a future
    campaign COULD use a different split — but the two must still sum
    to 100, a structural invariant, not a business-rule guess."""
    if driver_share_percent + vistaar_share_percent != Decimal("100"):
        raise InvalidCampaignInputError(
            "driver_share_percent and vistaar_share_percent must sum to 100."
        )
    if driver_share_percent < 0 or vistaar_share_percent < 0:
        raise InvalidCampaignInputError("Share percentages cannot be negative.")


@dataclass(slots=True)
class Campaign:
    id: uuid.UUID
    partner_name: str
    status: CampaignStatus
    payout_amount: Decimal
    driver_share_percent: Decimal
    vistaar_share_percent: Decimal
    starts_at: datetime | None
    ends_at: datetime | None
    created_at: datetime

    @staticmethod
    def new(
        *,
        partner_name: str,
        payout_amount: Decimal,
        driver_share_percent: Decimal = Decimal("80"),
        vistaar_share_percent: Decimal = Decimal("20"),
        starts_at: datetime | None,
        ends_at: datetime | None,
        now: datetime,
    ) -> Campaign:
        if not partner_name.strip():
            raise InvalidCampaignInputError("partner_name cannot be blank.")
        if payout_amount <= 0:
            raise InvalidCampaignInputError("payout_amount must be positive.")
        validate_share_percentages(driver_share_percent, vistaar_share_percent)
        return Campaign(
            id=uuid.uuid4(),
            partner_name=partner_name.strip(),
            status=CampaignStatus.ACTIVE,
            payout_amount=payout_amount,
            driver_share_percent=driver_share_percent,
            vistaar_share_percent=vistaar_share_percent,
            starts_at=starts_at,
            ends_at=ends_at,
            created_at=now,
        )

    def pause(self) -> None:
        """ADR-0046 Decision 1. Existing assignments already in flight
        (PROOF_SUBMITTED, VERIFIED, etc.) are unaffected — pausing stops
        new AssignDriver calls, it does not strand drivers already
        participating."""
        if self.status is not CampaignStatus.ACTIVE:
            raise InvalidCampaignStateTransitionError(
                f"Cannot pause a campaign in status {self.status}."
            )
        self.status = CampaignStatus.PAUSED

    def resume(self) -> None:
        if self.status is not CampaignStatus.PAUSED:
            raise InvalidCampaignStateTransitionError(
                f"Cannot resume a campaign in status {self.status}."
            )
        self.status = CampaignStatus.ACTIVE

    def end(self) -> None:
        """Terminal — no ENDED campaign can be resumed."""
        if self.status not in (CampaignStatus.ACTIVE, CampaignStatus.PAUSED):
            raise InvalidCampaignStateTransitionError(
                f"Cannot end a campaign already in status {self.status}."
            )
        self.status = CampaignStatus.ENDED


@dataclass(slots=True)
class DriverCampaign:
    id: uuid.UUID
    campaign_id: uuid.UUID
    driver_id: uuid.UUID
    status: DriverCampaignStatus
    proof_uri: str | None
    verification_status: VerificationStatus | None
    assigned_at: datetime

    @staticmethod
    def new(
        *, campaign_id: uuid.UUID, driver_id: uuid.UUID, now: datetime
    ) -> DriverCampaign:
        return DriverCampaign(
            id=uuid.uuid4(),
            campaign_id=campaign_id,
            driver_id=driver_id,
            status=DriverCampaignStatus.ASSIGNED,
            proof_uri=None,
            verification_status=None,
            assigned_at=now,
        )


@dataclass(slots=True)
class Payout:
    id: uuid.UUID
    driver_campaign_id: uuid.UUID
    gross_amount: Decimal
    driver_amount: Decimal
    vistaar_amount: Decimal
    status: PayoutStatus
    created_at: datetime

    @staticmethod
    def new(
        *,
        driver_campaign_id: uuid.UUID,
        gross_amount: Decimal,
        driver_share_percent: Decimal,
        vistaar_share_percent: Decimal,
        now: datetime,
    ) -> Payout:
        # NUMERIC(12,2) columns — round to the cent, same precision
        # every other money computation in this codebase already uses.
        driver_amount = (gross_amount * driver_share_percent / Decimal("100")).quantize(
            Decimal("0.01")
        )
        # Derived as the remainder, not computed independently from
        # vistaar_share_percent — guarantees driver_amount +
        # vistaar_amount == gross_amount exactly even after rounding,
        # rather than risking a 1-cent gap from two separate roundings.
        vistaar_amount = gross_amount - driver_amount
        return Payout(
            id=uuid.uuid4(),
            driver_campaign_id=driver_campaign_id,
            gross_amount=gross_amount,
            driver_amount=driver_amount,
            vistaar_amount=vistaar_amount,
            status=PayoutStatus.PENDING,
            created_at=now,
        )
