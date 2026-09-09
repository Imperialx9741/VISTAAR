"""Abstract interfaces (ports) the application layer depends on."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from modules.wallet.domain.entities import Wallet, WalletTransaction


class WalletRepository(Protocol):
    def get_or_create_for_update(
        self, driver_id: uuid.UUID, *, now: datetime
    ) -> Wallet:
        """Returns the driver's wallet row, locked for the remainder of
        the current transaction (SELECT ... FOR UPDATE, database-design.md
        §42). Auto-creates a zero-balance row first if none exists yet —
        same pattern as
        modules.customer.service.CustomerService._get_or_provision().
        Safe under concurrent first-access for the same driver_id: if a
        concurrent transaction wins the race to create the row, this
        retries the lookup under lock rather than raising. Requires
        driver.drivers to already have a row for this driver_id
        (wallet.wallets.driver_id's foreign key) — the caller establishes
        this first, same precondition-check pattern
        modules/vehicle/router.py already uses for driver.drivers."""
        ...

    def get_transaction_by_idempotency_key(
        self, idempotency_key: str
    ) -> WalletTransaction | None: ...

    def get_debit_for_ride(
        self, ride_id: uuid.UUID, *, transaction_type: str
    ) -> WalletTransaction | None:
        """Phase 3 / Task 3.5 (ADR-0015). Finds the specific DEBIT
        transaction of `transaction_type` recorded for this ride (e.g.
        the PLATFORM_FEE debit Accept Offer produced) — used to refund
        the *exact* amount actually taken (BR-046: "the driver's
        platform fee is refunded"), not a value re-derived from the
        current fee constant, which could have changed since. Returns
        None if no such debit was ever recorded (defensive — should not
        happen for an ACCEPTED/ARRIVED ride, since accepting always
        debits one)."""
        ...

    def apply_debit(self, *, wallet: Wallet, transaction: WalletTransaction) -> None:
        """Persists the new balance on `wallet` (already locked via
        get_or_create_for_update() in the same transaction) and inserts
        `transaction` as one atomic unit — database-design.md §41's
        "both records must succeed or both must fail" rule."""
        ...

    def apply_credit(self, *, wallet: Wallet, transaction: WalletTransaction) -> None:
        """Phase 3 / Task 3.5 (ADR-0015). Same atomicity contract as
        apply_debit() — persists the new (increased) balance and inserts
        `transaction` as one unit — but for a CREDIT. No balance-
        validity concern the way apply_debit() has (crediting can never
        make the balance invalid)."""
        ...

    def update_low_balance_grace(self, wallet: Wallet) -> None:
        """Sarthi Wallet Low-Balance Rule (ADR-0058, 2026-09-02) —
        persists `wallet.low_balance_grace_ride_used`/`.version` only
        (no ledger row — this isn't a financial transaction). The
        caller already holds this row's lock via
        get_or_create_for_update() in the same transaction."""
        ...

    def list_transactions(
        self,
        driver_id: uuid.UUID,
        *,
        transaction_type: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[WalletTransaction], int]:
        """Phase 11 (Wallet Transactions / "Financial audit trail",
        ADR-0024). Ordered newest-first (`created_at DESC`). Returns
        (page, total matching count) — same shape as
        modules.ride.ports.RideRepository.search()."""
        ...

    def sum_debits_since(self, *, transaction_type: str, since: datetime) -> Decimal:
        """Admin Web §3's Dashboard "Platform fee collected (today)"
        widget — sums `amount` for every DEBIT transaction of
        `transaction_type` created at or after `since`."""
        ...

    def sum_by_type_and_direction_in_range(
        self,
        *,
        transaction_type: str,
        direction: str,
        since: datetime,
        until: datetime,
    ) -> Decimal:
        """Admin Web §4.16 Financial report (ADR-0047) — generalizes
        sum_debits_since() with an explicit direction and a bounded
        [since, until) window rather than an open-ended one. 0 if no
        matching transaction exists."""
        ...

    def count_by_transaction_type_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        """Same report's "by_transaction_type" breakdown."""
        ...
