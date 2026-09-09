"""Application service (use cases) for Wallet.

Only get_wallet() and debit() are implemented — the Minimal Wallet
Foundation (see modules/wallet/__init__.py). debit() never commits its
own transaction: it's designed to be called as one step inside a larger
caller-managed transaction (technical-architecture.md §18's Accept-Ride
Transaction — composed at modules/matching/router.py's accept-offer
endpoint, Phase 3 / Task 3.4: locks the wallet row via get_wallet(),
debits it, then assigns the driver and updates the ride/offer, all in
the same transaction). This module has no dependency on modules.ride or
modules.matching at all — that composition happens the other way
around.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from modules.wallet.domain.entities import (
    LOW_BALANCE_THRESHOLD,
    TransactionDirection,
    TransactionType,
    Wallet,
    WalletTransaction,
    validate_amount,
)
from modules.wallet.domain.errors import (
    InsufficientWalletBalanceError,
    WalletRechargeRequiredError,
)
from modules.wallet.ports import WalletRepository


class WalletService:
    def __init__(self, *, wallets: WalletRepository) -> None:
        self._wallets = wallets

    def get_debit_for_ride(
        self, *, ride_id: uuid.UUID, transaction_type: str
    ) -> WalletTransaction | None:
        """Phase 3 / Task 3.5 (ADR-0015). Thin passthrough to
        WalletRepository.get_debit_for_ride() — kept on the service
        (not called directly against the repository) so every caller
        outside this module goes through WalletService, same as every
        other wallet operation."""
        return self._wallets.get_debit_for_ride(
            ride_id, transaction_type=transaction_type
        )

    def list_transactions(
        self,
        *,
        driver_id: uuid.UUID,
        transaction_type: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[WalletTransaction], int]:
        """Phase 11 (Wallet Transactions / "Financial audit trail",
        ADR-0024). `transaction_type`, if given, must already be a
        validated TransactionType.value — validation happens at the
        router layer (same split every other filtered list endpoint in
        this codebase uses, e.g. modules/admin/router.py's Search
        Rides/Search Penalties)."""
        return self._wallets.list_transactions(
            driver_id, transaction_type=transaction_type, offset=offset, limit=limit
        )

    def sum_debits_since(self, *, transaction_type: str, since: datetime) -> Decimal:
        """Admin Web §3's Dashboard "Platform fee collected (today)"."""
        return self._wallets.sum_debits_since(
            transaction_type=transaction_type, since=since
        )

    # --- Reports (Admin Web §4.16, ADR-0047) -------------------------

    def sum_by_type_and_direction_in_range(
        self,
        *,
        transaction_type: str,
        direction: str,
        since: datetime,
        until: datetime,
    ) -> Decimal:
        return self._wallets.sum_by_type_and_direction_in_range(
            transaction_type=transaction_type,
            direction=direction,
            since=since,
            until=until,
        )

    def count_transactions_by_type_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        return self._wallets.count_by_transaction_type_in_range(
            since=since, until=until
        )

    def get_wallet(self, *, driver_id: uuid.UUID, now: datetime) -> Wallet:
        """Auto-provisions a zero-balance wallet on first access. Does
        not need the row lock get_or_create_for_update() takes for a
        read-only call, but reuses it anyway rather than adding a
        second, unlocked read path — this method is not on any hot
        concurrent path where the lock would cost anything real."""
        return self._wallets.get_or_create_for_update(driver_id, now=now)

    def enforce_low_balance_policy(
        self, *, driver_id: uuid.UUID, now: datetime
    ) -> Wallet:
        """Sarthi Wallet Low-Balance Rule (ADR-0058, 2026-09-02, owner
        decision). Must be called — and its lock relied on — before a
        ride acceptance proceeds any further
        (modules/matching/router.py's accept-offer endpoint, replacing
        what used to be a bare get_wallet() call kept only for its lock
        side effect).

        - Balance above LOW_BALANCE_THRESHOLD: no-op, returns the locked
          wallet unchanged. This is the common case.
        - Balance at or below the threshold, grace not yet used: this
          acceptance IS the driver's one allowed grace ride — marks the
          grace used and returns, allowing the caller to proceed.
        - Balance at or below the threshold, grace already used: raises
          WalletRechargeRequiredError before any ride/offer state
          changes — the caller must not reach matching_service.
          accept_offer()/ride_service.accept_ride() at all in this case.

        Deliberately independent of debit()'s own
        InsufficientWalletBalanceError — that check (a few lines later,
        against the actual platform fee) is unaffected and still runs;
        this method only adds an earlier, coarser gate. No partial debit
        and no new outstanding-balance concept are introduced here, per
        the owner's explicit decision — this is a pure accept/reject
        gate on top of the existing balance.
        """
        wallet = self._wallets.get_or_create_for_update(driver_id, now=now)
        if wallet.balance > LOW_BALANCE_THRESHOLD:
            return wallet
        if wallet.low_balance_grace_ride_used:
            raise WalletRechargeRequiredError(
                f"Wallet balance ({wallet.balance}) is at or below the "
                f"low-balance threshold (₹{LOW_BALANCE_THRESHOLD}) and this "
                "driver has already used their one grace-ride acceptance. "
                "Recharge is required before accepting another ride."
            )
        wallet.low_balance_grace_ride_used = True
        wallet.version += 1
        self._wallets.update_low_balance_grace(wallet)
        return wallet

    def debit(
        self,
        *,
        driver_id: uuid.UUID,
        amount: Decimal,
        transaction_type: str,
        ride_id: uuid.UUID | None,
        idempotency_key: str,
        now: datetime,
    ) -> WalletTransaction:
        """BR-011/BR-012/BR-013: debits `amount` from the driver's
        wallet, refusing if the balance is insufficient
        (InsufficientWalletBalanceError), and recording an immutable
        ledger entry in the same operation. Idempotent on
        `idempotency_key` (wallet.transactions.idempotency_key's own
        UNIQUE constraint, database-design.md §17.2 — a domain-level
        guard distinct from shared.idempotency_keys/shared/
        idempotency.py, which dedupes whole HTTP requests, not
        individual financial operations): a key already used returns
        the original transaction rather than debiting twice.

        Checked both before and after acquiring the wallet row lock —
        the first check is a fast path that avoids taking the lock for
        a pure replay; the second closes the race window against a
        concurrent debit for the same driver+key (get_or_create_for_
        update() serializes concurrent calls for the same driver_id, so
        by the time this method holds the lock, any racing call for the
        same key has either committed — caught by the second check — or
        is still waiting for the lock behind this one).
        """
        validate_amount(amount)
        validated_type = TransactionType(transaction_type)

        existing = self._wallets.get_transaction_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing

        wallet = self._wallets.get_or_create_for_update(driver_id, now=now)

        existing = self._wallets.get_transaction_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing

        if wallet.balance < amount:
            raise InsufficientWalletBalanceError(
                f"Insufficient wallet balance: have {wallet.balance}, need {amount}."
            )

        balance_before = wallet.balance
        balance_after = balance_before - amount
        wallet.balance = balance_after
        wallet.version += 1
        wallet.updated_at = now

        transaction = WalletTransaction(
            id=uuid.uuid4(),
            driver_id=driver_id,
            ride_id=ride_id,
            transaction_type=validated_type,
            amount=amount,
            direction=TransactionDirection.DEBIT,
            balance_before=balance_before,
            balance_after=balance_after,
            idempotency_key=idempotency_key,
            reference_type=None,
            reference_id=None,
            metadata=None,
            created_at=now,
        )
        self._wallets.apply_debit(wallet=wallet, transaction=transaction)
        return transaction

    def debit_or_record_as_debt(
        self,
        *,
        driver_id: uuid.UUID,
        amount: Decimal,
        transaction_type: str,
        ride_id: uuid.UUID | None,
        idempotency_key: str,
        now: datetime,
    ) -> WalletTransaction:
        """Sarthi Unpaid Cancellation-Penalty Recovery (ADR-0062,
        2026-09-03, owner decision). Used only for the driver-
        cancellation penalty debit (modules/ride/router.py's
        driver_cancel_ride()) — every other debit still goes through
        plain debit() above, unchanged, and still hard-fails on
        insufficient balance (e.g. the accept-offer platform fee must
        never silently become a debt).

        Unlike debit(), this method never raises
        InsufficientWalletBalanceError:

        - Balance covers `amount`: debits normally — identical
          behavior to debit().
        - Balance doesn't cover it: debits NOTHING at all (no partial
          deduction — the owner's explicit instruction) and instead
          adds the full `amount` to `wallet.outstanding_debt`, to be
          recovered automatically from a future WALLET_RECHARGE credit
          (see credit()'s own debt-recovery logic). The driver's
          cancellation itself is never blocked by this — the caller
          (driver_cancel_ride()) proceeds with the ride-status
          transition and strike regardless of which branch this method
          takes.

        Either branch still returns a real WalletTransaction — even the
        debt-only branch, with `balance_before == balance_after`
        (nothing was actually paid) and `metadata` marking it as such —
        so the existing idempotency-key guarantee still protects a
        retried cancellation request from double-incurring the debt,
        exactly the same mechanism debit()/credit() already rely on.

        Deliberately independent of, and never interacting with, the
        ₹20 low-balance grace-ride rule (ADR-0058) — an outstanding
        cancellation-penalty debt does not, by itself, change ride-
        acceptance eligibility; only LOW_BALANCE_THRESHOLD/
        low_balance_grace_ride_used does that.
        """
        validate_amount(amount)
        validated_type = TransactionType(transaction_type)

        existing = self._wallets.get_transaction_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing

        wallet = self._wallets.get_or_create_for_update(driver_id, now=now)

        existing = self._wallets.get_transaction_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing

        balance_before = wallet.balance
        metadata: dict[str, object] | None = None
        if balance_before >= amount:
            balance_after = balance_before - amount
            wallet.balance = balance_after
        else:
            # No partial deduction — the balance is left untouched, and
            # the full unpaid amount becomes an outstanding debt instead.
            balance_after = balance_before
            wallet.outstanding_debt += amount
            metadata = {
                "outstanding_debt_incurred": str(amount),
                "reason": "insufficient_balance_at_cancellation",
            }

        wallet.version += 1
        wallet.updated_at = now

        transaction = WalletTransaction(
            id=uuid.uuid4(),
            driver_id=driver_id,
            ride_id=ride_id,
            transaction_type=validated_type,
            amount=amount,
            direction=TransactionDirection.DEBIT,
            balance_before=balance_before,
            balance_after=balance_after,
            idempotency_key=idempotency_key,
            reference_type=None,
            reference_id=None,
            metadata=metadata,
            created_at=now,
        )
        self._wallets.apply_debit(wallet=wallet, transaction=transaction)
        return transaction

    def credit(
        self,
        *,
        driver_id: uuid.UUID,
        amount: Decimal,
        transaction_type: str,
        ride_id: uuid.UUID | None,
        idempotency_key: str,
        now: datetime,
        reference_type: str | None = None,
        reference_id: uuid.UUID | None = None,
        metadata: dict[str, object] | None = None,
    ) -> WalletTransaction:
        """Phase 3 / Task 3.5 (ADR-0015). Credits `amount` to the
        driver's wallet — the mirror of debit(), same row-locked,
        idempotent-on-key, immutable-ledger-entry shape, but with no
        insufficient-balance concern (a credit can never make the
        balance invalid). First caller: modules/ride/router.py's
        post-acceptance cancellation composition, refunding a driver's
        platform fee (BR-046) — `reference_type`/`reference_id` let
        that caller point the new ledger row back at the original
        PLATFORM_FEE debit it reverses, for audit (database-design.md
        §17.2's two nullable columns exist for exactly this).

        `metadata` (ADR-0060, Sarthi Wallet Recharge): a free-form JSONB
        record of provider-specific detail that doesn't fit
        `reference_id`'s UUID typing (a Razorpay order/payment id is a
        string, e.g. `"pay_xxx"`) — kept generic rather than named after
        Razorpay specifically, since the wallet layer itself stays
        gateway-agnostic (ADR-0060 §3).

        Also resets the Sarthi Wallet Low-Balance Rule's (ADR-0058)
        grace flag whenever this credit brings the balance back above
        LOW_BALANCE_THRESHOLD — deliberately keyed off the resulting
        balance, not `transaction_type`: any credit that crosses the
        threshold (a recharge, a fee reversal, a bonus) should have the
        same effect, since the rule is about the balance level itself,
        not why it changed.

        Sarthi Unpaid Cancellation-Penalty Recovery (ADR-0062,
        2026-09-03, owner decision): when `transaction_type` is
        WALLET_RECHARGE and this wallet has an outstanding_debt
        (debit_or_record_as_debt(), above), the recharge first pays
        down that debt — up to the full recharge amount — before any
        remainder is credited to the spendable balance. Deliberately
        scoped to WALLET_RECHARGE only, not every credit type: the
        owner's decision was specifically "recovered from the next
        wallet recharge," and a bonus/fee-reversal credit is a
        different kind of event that shouldn't silently vanish into
        debt repayment without being asked for.

        This is a single ledger row, not two — `amount` always records
        the full, real amount actually verified/paid (audit-accurate,
        reconcilable against the payment gateway's own records), while
        `balance_after` reflects only what actually landed in the
        spendable balance (net of any debt recovered). When they
        differ, `metadata.outstanding_debt_recovered`/
        `outstanding_debt_remaining` explain exactly why, in the same
        row — the one exception in this codebase to "amount always
        equals the balance delta," and clearly marked as such rather
        than silently inconsistent."""
        validate_amount(amount)
        validated_type = TransactionType(transaction_type)

        existing = self._wallets.get_transaction_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing

        wallet = self._wallets.get_or_create_for_update(driver_id, now=now)

        existing = self._wallets.get_transaction_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing

        balance_before = wallet.balance
        amount_to_balance = amount
        debt_recovered = Decimal("0")
        if (
            validated_type is TransactionType.WALLET_RECHARGE
            and wallet.outstanding_debt > 0
        ):
            debt_recovered = min(amount, wallet.outstanding_debt)
            wallet.outstanding_debt -= debt_recovered
            amount_to_balance = amount - debt_recovered

        balance_after = balance_before + amount_to_balance
        wallet.balance = balance_after
        if (
            balance_before <= LOW_BALANCE_THRESHOLD < balance_after
            and wallet.low_balance_grace_ride_used
        ):
            wallet.low_balance_grace_ride_used = False
        wallet.version += 1
        wallet.updated_at = now

        final_metadata = dict(metadata) if metadata else None
        if debt_recovered > 0:
            final_metadata = final_metadata or {}
            final_metadata["outstanding_debt_recovered"] = str(debt_recovered)
            final_metadata["outstanding_debt_remaining"] = str(wallet.outstanding_debt)

        transaction = WalletTransaction(
            id=uuid.uuid4(),
            driver_id=driver_id,
            ride_id=ride_id,
            transaction_type=validated_type,
            amount=amount,
            direction=TransactionDirection.CREDIT,
            balance_before=balance_before,
            balance_after=balance_after,
            idempotency_key=idempotency_key,
            reference_type=reference_type,
            reference_id=reference_id,
            metadata=final_metadata,
            created_at=now,
        )
        self._wallets.apply_credit(wallet=wallet, transaction=transaction)
        return transaction
