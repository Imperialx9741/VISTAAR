"""Domain-level errors for Wallet.

Reuse existing error codes from docs/05-api/api-contracts.md §49 rather
than inventing new ones.
"""

from __future__ import annotations


class WalletDomainError(Exception):
    code: str = "WALLET_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InsufficientWalletBalanceError(WalletDomainError):
    """BR-012: a driver may accept a ride only if their wallet has
    sufficient balance for the applicable platform fee."""

    code = "INSUFFICIENT_WALLET_BALANCE"


class WalletRechargeRequiredError(WalletDomainError):
    """Sarthi Wallet Low-Balance Rule (ADR-0058, 2026-09-02, owner
    decision): a driver whose wallet balance is at or below
    LOW_BALANCE_THRESHOLD has already used their one allowed
    grace-ride acceptance and must recharge before accepting another
    ride. Deliberately a new code, not a reuse of
    INSUFFICIENT_WALLET_BALANCE — that one means this specific debit
    can't be covered; this one means accepting is blocked outright,
    regardless of whether this ride's own platform fee would fit."""

    code = "WALLET_RECHARGE_REQUIRED"


class WalletTransactionFailedError(WalletDomainError):
    """Defensive backstop: raised if a wallet debit hits an unexpected
    database error (e.g. the CHECK constraint rejecting a would-be
    negative balance despite the row lock already having validated it —
    should not happen in practice, but a clean domain error is
    preferable to a raw IntegrityError reaching the client). See
    repositories.py."""

    code = "WALLET_TRANSACTION_FAILED"
