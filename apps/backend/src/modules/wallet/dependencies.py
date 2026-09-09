"""FastAPI dependency wiring for Wallet.

Reuses modules.identity.dependencies.require_driver as-is for the
router's auth — no new auth code.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session as DbSession

from core.database import get_db
from modules.wallet.payment_gateway import (
    WalletRechargeGateway,
    get_wallet_recharge_gateway,
)
from modules.wallet.repositories import SqlAlchemyWalletRepository
from modules.wallet.service import WalletService


def get_wallet_service(
    db: Annotated[DbSession, Depends(get_db)],
) -> WalletService:
    return WalletService(wallets=SqlAlchemyWalletRepository(db))


def get_wallet_recharge_gateway_dependency() -> WalletRechargeGateway:
    """A thin Depends()-compatible wrapper around payment_gateway.
    get_wallet_recharge_gateway() — same reasoning as
    modules.identity.dependencies.get_sms_provider_dependency: kept as
    its own dependency specifically so tests can swap it via
    app.dependency_overrides without touching real DB/Redis wiring."""
    return get_wallet_recharge_gateway()
