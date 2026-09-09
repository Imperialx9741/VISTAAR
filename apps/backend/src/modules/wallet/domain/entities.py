"""Wallet domain entities and validation.

Field shapes match docs/04-database/database-design.md §17.1 (wallet.wallets)
and §17.2 (wallet.transactions) exactly.

Only the debit primitive is implemented (Minimal Wallet Foundation — see
modules/wallet/__init__.py). Balance-changing logic itself lives in
service.py (WalletService.debit()), not here — these entities are plain
data plus the input validation a caller must pass, matching the style
every other module's domain/entities.py already uses (e.g.
modules.vehicle.domain.entities.Vehicle).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from modules.wallet.domain.errors import WalletDomainError


class InvalidAmountError(WalletDomainError):
    code = "VALIDATION_FAILED"


def validate_amount(amount: Decimal) -> Decimal:
    if amount <= 0:
        raise InvalidAmountError("amount must be positive.")
    return amount


class TransactionDirection(StrEnum):
    """Exactly database-design.md §17.2's documented directions."""

    CREDIT = "CREDIT"
    DEBIT = "DEBIT"


class TransactionType(StrEnum):
    """Exactly database-design.md §17.2's documented "Transaction types
    may include" list. Only PLATFORM_FEE is ever produced by this task's
    code (WalletService.debit(), called nowhere yet — this foundation
    has no caller until the next task, Accept Offer, composes it). The
    others exist here because they're part of the same documented enum
    a future task will use — not because this module can produce them
    yet."""

    PLATFORM_FEE = "PLATFORM_FEE"
    WALLET_RECHARGE = "WALLET_RECHARGE"
    JOINING_BONUS = "JOINING_BONUS"
    DRIVER_REFERRAL_BONUS = "DRIVER_REFERRAL_BONUS"
    ADVERTISEMENT_PAYOUT = "ADVERTISEMENT_PAYOUT"
    DRIVER_PENALTY = "DRIVER_PENALTY"
    CASH_SETTLEMENT = "CASH_SETTLEMENT"
    FEE_REVERSAL = "FEE_REVERSAL"
    PENALTY_REVERSAL = "PENALTY_REVERSAL"
    ADMIN_ADJUSTMENT = "ADMIN_ADJUSTMENT"


# Sarthi Wallet Low-Balance Rule (ADR-0058, 2026-09-02, owner decision).
# At or below this balance, a driver may accept exactly one more ride
# (WalletService.enforce_low_balance_policy()) before being blocked from
# accepting another until a recharge brings the balance back above it.
# Deliberately not a partial-debit/outstanding-balance mechanism for
# ride-*acceptance* eligibility (the owner's decision explicitly ruled
# both out for this specific rule) — purely a yes/no gate at accept
# time, independent of debit()'s own existing
# InsufficientWalletBalanceError check for genuinely insufficient funds.
#
# Not to be confused with `Wallet.outstanding_debt` below (ADR-0062) —
# a separate, later owner decision that DOES introduce a real
# outstanding-balance concept, but scoped specifically to an unpaid
# driver-*cancellation* penalty, recovered only from a future wallet
# recharge. The two mechanisms are independent: an outstanding
# cancellation-penalty debt does not, by itself, block ride acceptance
# (only LOW_BALANCE_THRESHOLD/low_balance_grace_ride_used does that).
LOW_BALANCE_THRESHOLD = Decimal("20")


@dataclass(slots=True)
class Wallet:
    driver_id: uuid.UUID
    balance: Decimal
    version: int
    updated_at: datetime
    low_balance_grace_ride_used: bool = False
    # Sarthi Unpaid Cancellation-Penalty Recovery (ADR-0062, 2026-09-03,
    # owner decision) — the unpaid portion of a driver-cancellation
    # penalty the wallet balance couldn't cover at cancellation time.
    # Never partially debited from `balance`; recovered automatically
    # from the driver's next WALLET_RECHARGE credit instead. See this
    # module's own service.py for the full incur/recover logic.
    outstanding_debt: Decimal = Decimal("0")

    @staticmethod
    def new(*, driver_id: uuid.UUID, now: datetime) -> Wallet:
        """Auto-provisioned with a zero balance on first access — same
        pattern as modules.customer.service.CustomerService.
        _get_or_provision(). Requires driver.drivers to already have a
        row for this driver_id (wallet.wallets.driver_id's foreign key,
        database-design.md §17.1) — the caller (router.py) establishes
        this first, same precondition-check pattern
        modules/vehicle/router.py already uses for driver.drivers."""
        return Wallet(
            driver_id=driver_id,
            balance=Decimal("0"),
            version=1,
            updated_at=now,
            low_balance_grace_ride_used=False,
            outstanding_debt=Decimal("0"),
        )


@dataclass(slots=True)
class WalletTransaction:
    id: uuid.UUID
    driver_id: uuid.UUID
    ride_id: uuid.UUID | None
    transaction_type: TransactionType
    amount: Decimal
    direction: TransactionDirection
    balance_before: Decimal
    balance_after: Decimal
    idempotency_key: str
    reference_type: str | None
    reference_id: uuid.UUID | None
    metadata: dict[str, object] | None
    created_at: datetime
