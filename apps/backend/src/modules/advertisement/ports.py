"""Abstract interfaces (ports) the application layer depends on."""

from __future__ import annotations

import uuid
from typing import Protocol

from modules.advertisement.domain.entities import Campaign, DriverCampaign, Payout


class CampaignRepository(Protocol):
    def create(self, campaign: Campaign) -> Campaign: ...

    def get_by_id(self, campaign_id: uuid.UUID) -> Campaign | None: ...

    def save(self, campaign: Campaign) -> None:
        """ADR-0046 — Pause/Resume/End write back to an existing
        campaign row; Create was the only write before this."""
        ...

    def list_all(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[Campaign], int]:
        """Admin Web §4.15's "List/Search" — newest first."""
        ...


class DriverCampaignRepository(Protocol):
    def create(self, assignment: DriverCampaign) -> DriverCampaign: ...

    def get_by_id(self, assignment_id: uuid.UUID) -> DriverCampaign | None: ...

    def save(self, assignment: DriverCampaign) -> None: ...

    def search(
        self,
        *,
        campaign_id: uuid.UUID | None,
        driver_id: uuid.UUID | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[DriverCampaign], int]:
        """Admin Web §4.15's installation/proof review queue. Newest
        first."""
        ...


class PayoutRepository(Protocol):
    def create(self, payout: Payout) -> Payout:
        """Insert. Safe under concurrent double-calculation for the same
        driver_campaign_id: uq_payouts_driver_campaign (migration
        83c95d7eaf67) means a genuine duplicate raises IntegrityError —
        the implementation catches this and raises
        PayoutAlreadyCalculatedError rather than silently returning the
        existing row (unlike Penalty's idempotent-on-conflict shape,
        recalculating a payout is a caller error worth surfacing, not a
        legitimate retry to replay quietly)."""
        ...

    def get_by_id(self, payout_id: uuid.UUID) -> Payout | None: ...

    def get_by_driver_campaign_id(
        self, driver_campaign_id: uuid.UUID
    ) -> Payout | None: ...

    def save(self, payout: Payout) -> None: ...

    def list_by_status(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[Payout], int]:
        """Admin Web §4.15's payout/settlement monitoring. Newest
        first."""
        ...
