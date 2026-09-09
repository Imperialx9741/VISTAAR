"""Pydantic request DTOs for the Promotion API.

Mirrors ADR-0041 Decision 2's sketched redemption request shape — not
previously documented anywhere else, this is the first concrete shape
for it (exact path/fields TBD per the ADR is now resolved here).
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class RedeemCampaignCodeBody(BaseModel):
    """`vehicle_category`/`fare` are the caller's proposed ride's own
    values — validated at the service layer
    (PromotionService.redeem_campaign_code()) against the campaign's
    vehicle_category/minimum_fare, same "shape here, business rule in
    the service" split every other request DTO in this codebase uses."""

    code: str
    vehicle_category: str
    fare: Decimal
