"""Pydantic request DTOs for the Wallet API.

New for Sarthi Wallet Recharge (ADR-0060, 2026-09-02) — every other
Wallet endpoint before this was a GET with no request body
(modules/wallet/__init__.py's own docstring used to note this file
didn't need to exist yet).
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class CreateRechargeOrderBody(BaseModel):
    """api-contracts.md §35's documented Wallet Recharge request —
    `amount >= ₹200` is enforced at the service layer
    (WalletService/the router composing WALLET_RECHARGE_MINIMUM_AMOUNT),
    not here, same "shape here, business rule in the service" split
    every other request DTO in this codebase already follows."""

    amount: Decimal


class ConfirmRechargeBody(BaseModel):
    """The mobile app's checkout step reports these three Razorpay
    Checkout fields back after a completed payment — provider-specific
    field *names* only exist at this one boundary; everything past
    WalletService.credit() is provider-agnostic (ADR-0060)."""

    order_id: str
    payment_id: str
    signature: str
