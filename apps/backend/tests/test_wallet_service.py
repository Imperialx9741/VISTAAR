"""Unit tests for WalletService against an in-memory fake repository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from modules.wallet.domain.entities import (
    InvalidAmountError,
    TransactionDirection,
    TransactionType,
    Wallet,
    WalletTransaction,
)
from modules.wallet.domain.errors import (
    InsufficientWalletBalanceError,
    WalletRechargeRequiredError,
)
from modules.wallet.service import WalletService

DRIVER_ID = uuid.uuid4()
NOW = datetime.now(UTC)


class FakeWalletRepository:
    def __init__(self) -> None:
        self.wallets: dict[uuid.UUID, Wallet] = {}
        self.transactions_by_key: dict[str, WalletTransaction] = {}

    def get_or_create_for_update(
        self, driver_id: uuid.UUID, *, now: datetime
    ) -> Wallet:
        if driver_id not in self.wallets:
            self.wallets[driver_id] = Wallet.new(driver_id=driver_id, now=now)
        return self.wallets[driver_id]

    def get_transaction_by_idempotency_key(
        self, idempotency_key: str
    ) -> WalletTransaction | None:
        return self.transactions_by_key.get(idempotency_key)

    def get_debit_for_ride(
        self, ride_id: uuid.UUID, *, transaction_type: str
    ) -> WalletTransaction | None:
        for transaction in self.transactions_by_key.values():
            if (
                transaction.ride_id == ride_id
                and transaction.transaction_type.value == transaction_type
                and transaction.direction is TransactionDirection.DEBIT
            ):
                return transaction
        return None

    def apply_debit(self, *, wallet: Wallet, transaction: WalletTransaction) -> None:
        self.wallets[wallet.driver_id] = wallet
        self.transactions_by_key[transaction.idempotency_key] = transaction

    def apply_credit(self, *, wallet: Wallet, transaction: WalletTransaction) -> None:
        self.wallets[wallet.driver_id] = wallet
        self.transactions_by_key[transaction.idempotency_key] = transaction

    def update_low_balance_grace(self, wallet: Wallet) -> None:
        self.wallets[wallet.driver_id] = wallet

    def list_transactions(
        self,
        driver_id: uuid.UUID,
        *,
        transaction_type: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[WalletTransaction], int]:
        matches = sorted(
            (
                t
                for t in self.transactions_by_key.values()
                if t.driver_id == driver_id
                and (
                    transaction_type is None
                    or t.transaction_type.value == transaction_type
                )
            ),
            key=lambda t: t.created_at,
            reverse=True,
        )
        return matches[offset : offset + limit], len(matches)

    def sum_debits_since(self, *, transaction_type: str, since: datetime) -> Decimal:
        return sum(
            (
                t.amount
                for t in self.transactions_by_key.values()
                if t.transaction_type.value == transaction_type
                and t.direction is TransactionDirection.DEBIT
                and t.created_at >= since
            ),
            Decimal("0"),
        )

    def sum_by_type_and_direction_in_range(
        self,
        *,
        transaction_type: str,
        direction: str,
        since: datetime,
        until: datetime,
    ) -> Decimal:
        return sum(
            (
                t.amount
                for t in self.transactions_by_key.values()
                if t.transaction_type.value == transaction_type
                and t.direction.value == direction
                and since <= t.created_at < until
            ),
            Decimal("0"),
        )

    def count_by_transaction_type_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for t in self.transactions_by_key.values():
            if since <= t.created_at < until:
                key = t.transaction_type.value
                counts[key] = counts.get(key, 0) + 1
        return counts


@pytest.fixture
def repo() -> FakeWalletRepository:
    return FakeWalletRepository()


@pytest.fixture
def service(repo: FakeWalletRepository) -> WalletService:
    return WalletService(wallets=repo)


def _seed_balance(
    repo: FakeWalletRepository,
    amount: Decimal,
    *,
    grace_used: bool = False,
    outstanding_debt: Decimal = Decimal("0"),
) -> None:
    repo.wallets[DRIVER_ID] = Wallet(
        driver_id=DRIVER_ID,
        balance=amount,
        version=1,
        updated_at=NOW,
        low_balance_grace_ride_used=grace_used,
        outstanding_debt=outstanding_debt,
    )


def test_get_wallet_auto_provisions_zero_balance(service: WalletService) -> None:
    wallet = service.get_wallet(driver_id=DRIVER_ID, now=NOW)
    assert wallet.balance == Decimal("0")


def test_debit_reduces_balance(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    _seed_balance(repo, Decimal("100"))

    service.debit(
        driver_id=DRIVER_ID,
        amount=Decimal("20"),
        transaction_type="PLATFORM_FEE",
        ride_id=None,
        idempotency_key="ride:1:platform-fee",
        now=NOW,
    )

    assert repo.wallets[DRIVER_ID].balance == Decimal("80")


def test_debit_creates_ledger_entry_with_correct_before_after(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    _seed_balance(repo, Decimal("100"))
    ride_id = uuid.uuid4()

    transaction = service.debit(
        driver_id=DRIVER_ID,
        amount=Decimal("20"),
        transaction_type="PLATFORM_FEE",
        ride_id=ride_id,
        idempotency_key="ride:1:platform-fee",
        now=NOW,
    )

    assert transaction.direction is TransactionDirection.DEBIT
    assert transaction.transaction_type is TransactionType.PLATFORM_FEE
    assert transaction.amount == Decimal("20")
    assert transaction.balance_before == Decimal("100")
    assert transaction.balance_after == Decimal("80")
    assert transaction.ride_id == ride_id
    assert transaction.driver_id == DRIVER_ID


def test_debit_raises_when_balance_insufficient(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    _seed_balance(repo, Decimal("15"))

    with pytest.raises(InsufficientWalletBalanceError):
        service.debit(
            driver_id=DRIVER_ID,
            amount=Decimal("20"),
            transaction_type="PLATFORM_FEE",
            ride_id=None,
            idempotency_key="ride:1:platform-fee",
            now=NOW,
        )

    # Balance must be untouched — a failed debit is not a partial debit.
    assert repo.wallets[DRIVER_ID].balance == Decimal("15")


def test_debit_zero_balance_wallet_raises_insufficient(service: WalletService) -> None:
    with pytest.raises(InsufficientWalletBalanceError):
        service.debit(
            driver_id=DRIVER_ID,
            amount=Decimal("10"),
            transaction_type="PLATFORM_FEE",
            ride_id=None,
            idempotency_key="ride:1:platform-fee",
            now=NOW,
        )


def test_debit_rejects_non_positive_amount(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    _seed_balance(repo, Decimal("100"))

    with pytest.raises(InvalidAmountError):
        service.debit(
            driver_id=DRIVER_ID,
            amount=Decimal("0"),
            transaction_type="PLATFORM_FEE",
            ride_id=None,
            idempotency_key="ride:1:platform-fee",
            now=NOW,
        )


def test_debit_is_idempotent_on_repeated_key(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    _seed_balance(repo, Decimal("100"))
    key = "ride:1:platform-fee"

    first = service.debit(
        driver_id=DRIVER_ID,
        amount=Decimal("20"),
        transaction_type="PLATFORM_FEE",
        ride_id=None,
        idempotency_key=key,
        now=NOW,
    )
    second = service.debit(
        driver_id=DRIVER_ID,
        amount=Decimal("20"),
        transaction_type="PLATFORM_FEE",
        ride_id=None,
        idempotency_key=key,
        now=NOW,
    )

    assert first.id == second.id
    # Only debited once — the second call replayed the first result
    # rather than debiting again.
    assert repo.wallets[DRIVER_ID].balance == Decimal("80")


# --- credit() / get_debit_for_ride() (Phase 3 / Task 3.5, ADR-0015) --------


def test_credit_increases_balance(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    _seed_balance(repo, Decimal("50"))

    service.credit(
        driver_id=DRIVER_ID,
        amount=Decimal("20"),
        transaction_type="FEE_REVERSAL",
        ride_id=None,
        idempotency_key="ride:1:platform-fee-reversal",
        now=NOW,
    )

    assert repo.wallets[DRIVER_ID].balance == Decimal("70")


def test_credit_creates_ledger_entry_with_correct_before_after(
    service: WalletService,
) -> None:
    ride_id = uuid.uuid4()
    original_fee_id = uuid.uuid4()

    transaction = service.credit(
        driver_id=DRIVER_ID,
        amount=Decimal("20"),
        transaction_type="FEE_REVERSAL",
        ride_id=ride_id,
        idempotency_key="ride:1:platform-fee-reversal",
        now=NOW,
        reference_type="wallet_transaction",
        reference_id=original_fee_id,
    )

    assert transaction.direction is TransactionDirection.CREDIT
    assert transaction.transaction_type is TransactionType.FEE_REVERSAL
    assert transaction.balance_before == Decimal("0")
    assert transaction.balance_after == Decimal("20")
    assert transaction.reference_type == "wallet_transaction"
    assert transaction.reference_id == original_fee_id


def test_credit_never_raises_insufficient_balance(service: WalletService) -> None:
    """Unlike debit(), credit() has no balance floor to violate — a
    zero-balance wallet can always receive a credit."""
    transaction = service.credit(
        driver_id=DRIVER_ID,
        amount=Decimal("20"),
        transaction_type="FEE_REVERSAL",
        ride_id=None,
        idempotency_key="ride:1:platform-fee-reversal",
        now=NOW,
    )
    assert transaction.balance_after == Decimal("20")


def test_credit_is_idempotent_on_repeated_key(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    key = "ride:1:platform-fee-reversal"

    first = service.credit(
        driver_id=DRIVER_ID,
        amount=Decimal("20"),
        transaction_type="FEE_REVERSAL",
        ride_id=None,
        idempotency_key=key,
        now=NOW,
    )
    second = service.credit(
        driver_id=DRIVER_ID,
        amount=Decimal("20"),
        transaction_type="FEE_REVERSAL",
        ride_id=None,
        idempotency_key=key,
        now=NOW,
    )

    assert first.id == second.id
    # Only credited once, not twice.
    assert repo.wallets[DRIVER_ID].balance == Decimal("20")


def test_get_debit_for_ride_finds_the_matching_transaction(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    ride_id = uuid.uuid4()
    _seed_balance(repo, Decimal("100"))
    debited = service.debit(
        driver_id=DRIVER_ID,
        amount=Decimal("20"),
        transaction_type="PLATFORM_FEE",
        ride_id=ride_id,
        idempotency_key="ride:1:platform-fee",
        now=NOW,
    )

    found = service.get_debit_for_ride(ride_id=ride_id, transaction_type="PLATFORM_FEE")

    assert found is not None
    assert found.id == debited.id


def test_get_debit_for_ride_returns_none_when_no_such_transaction(
    service: WalletService,
) -> None:
    found = service.get_debit_for_ride(
        ride_id=uuid.uuid4(), transaction_type="PLATFORM_FEE"
    )
    assert found is None


# --- list_transactions() (Phase 11, ADR-0024) ------------------------------


def test_list_transactions_returns_only_this_drivers_rows(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    _seed_balance(repo, Decimal("100"))
    service.debit(
        driver_id=DRIVER_ID,
        amount=Decimal("10"),
        transaction_type="PLATFORM_FEE",
        ride_id=None,
        idempotency_key="k1",
        now=NOW,
    )
    other_driver = uuid.uuid4()
    repo.wallets[other_driver] = Wallet(
        driver_id=other_driver, balance=Decimal("100"), version=1, updated_at=NOW
    )
    service.debit(
        driver_id=other_driver,
        amount=Decimal("5"),
        transaction_type="PLATFORM_FEE",
        ride_id=None,
        idempotency_key="k2",
        now=NOW,
    )

    results, total = service.list_transactions(
        driver_id=DRIVER_ID, transaction_type=None, offset=0, limit=20
    )

    assert total == 1
    assert [t.driver_id for t in results] == [DRIVER_ID]


def test_list_transactions_filters_by_type(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    _seed_balance(repo, Decimal("100"))
    service.debit(
        driver_id=DRIVER_ID,
        amount=Decimal("10"),
        transaction_type="PLATFORM_FEE",
        ride_id=None,
        idempotency_key="k1",
        now=NOW,
    )
    service.credit(
        driver_id=DRIVER_ID,
        amount=Decimal("10"),
        transaction_type="FEE_REVERSAL",
        ride_id=None,
        idempotency_key="k2",
        now=NOW,
    )

    results, total = service.list_transactions(
        driver_id=DRIVER_ID, transaction_type="FEE_REVERSAL", offset=0, limit=20
    )

    assert total == 1
    assert results[0].transaction_type.value == "FEE_REVERSAL"


def test_list_transactions_paginates(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    _seed_balance(repo, Decimal("100"))
    for i in range(3):
        service.debit(
            driver_id=DRIVER_ID,
            amount=Decimal("1"),
            transaction_type="PLATFORM_FEE",
            ride_id=None,
            idempotency_key=f"k{i}",
            now=NOW,
        )

    page, total = service.list_transactions(
        driver_id=DRIVER_ID, transaction_type=None, offset=0, limit=2
    )

    assert total == 3
    assert len(page) == 2


def test_list_transactions_empty_for_unknown_driver(service: WalletService) -> None:
    results, total = service.list_transactions(
        driver_id=uuid.uuid4(), transaction_type=None, offset=0, limit=20
    )
    assert results == []
    assert total == 0


# --- Sarthi Wallet Low-Balance Rule (ADR-0058, 2026-09-02) -----------------


def test_enforce_low_balance_policy_is_a_noop_above_threshold(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    _seed_balance(repo, Decimal("100.00"))

    wallet = service.enforce_low_balance_policy(driver_id=DRIVER_ID, now=NOW)

    assert wallet.low_balance_grace_ride_used is False
    assert repo.wallets[DRIVER_ID].low_balance_grace_ride_used is False


def test_enforce_low_balance_policy_at_exactly_threshold_is_low_balance(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    """₹20 itself counts as "at or below" — the rule's own wording."""
    _seed_balance(repo, Decimal("20.00"))

    wallet = service.enforce_low_balance_policy(driver_id=DRIVER_ID, now=NOW)

    assert wallet.low_balance_grace_ride_used is True


def test_enforce_low_balance_policy_first_time_low_consumes_the_grace_ride(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    _seed_balance(repo, Decimal("15.00"), grace_used=False)

    wallet = service.enforce_low_balance_policy(driver_id=DRIVER_ID, now=NOW)

    assert wallet.low_balance_grace_ride_used is True
    assert repo.wallets[DRIVER_ID].low_balance_grace_ride_used is True
    # Balance itself is untouched — this method never debits anything.
    assert wallet.balance == Decimal("15.00")


def test_enforce_low_balance_policy_blocks_once_grace_already_used(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    _seed_balance(repo, Decimal("15.00"), grace_used=True)

    with pytest.raises(WalletRechargeRequiredError):
        service.enforce_low_balance_policy(driver_id=DRIVER_ID, now=NOW)

    # Blocked before any mutation — balance and the flag are unchanged.
    assert repo.wallets[DRIVER_ID].balance == Decimal("15.00")
    assert repo.wallets[DRIVER_ID].low_balance_grace_ride_used is True


def test_enforce_low_balance_policy_does_not_create_a_partial_debit(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    """The owner's decision explicitly rules out a partial-debit
    mechanism — confirms no transaction/ledger row is ever created by
    this method, only debit()/credit() ever do that."""
    _seed_balance(repo, Decimal("15.00"))

    service.enforce_low_balance_policy(driver_id=DRIVER_ID, now=NOW)

    assert repo.transactions_by_key == {}


def test_credit_resets_grace_flag_when_crossing_back_above_threshold(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    _seed_balance(repo, Decimal("15.00"), grace_used=True)

    transaction = service.credit(
        driver_id=DRIVER_ID,
        amount=Decimal("200.00"),
        transaction_type="WALLET_RECHARGE",
        ride_id=None,
        idempotency_key="recharge-1",
        now=NOW,
    )

    assert transaction.balance_after == Decimal("215.00")
    assert repo.wallets[DRIVER_ID].low_balance_grace_ride_used is False


def test_credit_leaves_grace_flag_set_if_still_at_or_below_threshold(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    """A small credit that doesn't actually cross back above ₹20 must
    not clear the flag — the driver is still low-balance."""
    _seed_balance(repo, Decimal("5.00"), grace_used=True)

    service.credit(
        driver_id=DRIVER_ID,
        amount=Decimal("10.00"),
        transaction_type="WALLET_RECHARGE",
        ride_id=None,
        idempotency_key="recharge-2",
        now=NOW,
    )

    assert repo.wallets[DRIVER_ID].balance == Decimal("15.00")
    assert repo.wallets[DRIVER_ID].low_balance_grace_ride_used is True


def test_credit_leaves_grace_flag_unset_when_it_was_already_unset(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    """A credit crossing the threshold while grace was never used stays
    unset — nothing to reset."""
    _seed_balance(repo, Decimal("15.00"), grace_used=False)

    service.credit(
        driver_id=DRIVER_ID,
        amount=Decimal("50.00"),
        transaction_type="WALLET_RECHARGE",
        ride_id=None,
        idempotency_key="recharge-3",
        now=NOW,
    )

    assert repo.wallets[DRIVER_ID].low_balance_grace_ride_used is False


# --- Sarthi Unpaid Cancellation-Penalty Recovery (ADR-0062, 2026-09-03) -----


def test_debit_or_record_as_debt_debits_normally_when_balance_covers_it(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    _seed_balance(repo, Decimal("100.00"))

    transaction = service.debit_or_record_as_debt(
        driver_id=DRIVER_ID,
        amount=Decimal("30.00"),
        transaction_type="DRIVER_PENALTY",
        ride_id=None,
        idempotency_key="cancel-1",
        now=NOW,
    )

    assert transaction.balance_before == Decimal("100.00")
    assert transaction.balance_after == Decimal("70.00")
    assert transaction.metadata is None
    assert repo.wallets[DRIVER_ID].balance == Decimal("70.00")
    assert repo.wallets[DRIVER_ID].outstanding_debt == Decimal("0")


def test_debit_or_record_as_debt_never_raises_on_insufficient_balance(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    _seed_balance(repo, Decimal("10.00"))

    transaction = service.debit_or_record_as_debt(
        driver_id=DRIVER_ID,
        amount=Decimal("30.00"),
        transaction_type="DRIVER_PENALTY",
        ride_id=None,
        idempotency_key="cancel-2",
        now=NOW,
    )

    # No partial deduction — balance is completely untouched.
    assert transaction.balance_before == Decimal("10.00")
    assert transaction.balance_after == Decimal("10.00")
    assert repo.wallets[DRIVER_ID].balance == Decimal("10.00")
    assert repo.wallets[DRIVER_ID].outstanding_debt == Decimal("30.00")
    assert transaction.metadata is not None
    assert transaction.metadata["outstanding_debt_incurred"] == "30.00"


def test_debit_or_record_as_debt_is_idempotent_on_the_debt_only_branch(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    """A retried cancellation request (same idempotency_key) must not
    double-incur the debt, even though no real DEBIT ever happened."""
    _seed_balance(repo, Decimal("10.00"))

    first = service.debit_or_record_as_debt(
        driver_id=DRIVER_ID,
        amount=Decimal("30.00"),
        transaction_type="DRIVER_PENALTY",
        ride_id=None,
        idempotency_key="cancel-3",
        now=NOW,
    )
    second = service.debit_or_record_as_debt(
        driver_id=DRIVER_ID,
        amount=Decimal("30.00"),
        transaction_type="DRIVER_PENALTY",
        ride_id=None,
        idempotency_key="cancel-3",
        now=NOW,
    )

    assert first.id == second.id
    assert repo.wallets[DRIVER_ID].outstanding_debt == Decimal("30.00")  # not 60


def test_debit_or_record_as_debt_does_not_touch_the_low_balance_grace_flag(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    """The ₹20 low-balance rule (ADR-0058) and the cancellation-penalty
    debt (ADR-0062) are deliberately independent mechanisms."""
    _seed_balance(repo, Decimal("10.00"), grace_used=True)

    service.debit_or_record_as_debt(
        driver_id=DRIVER_ID,
        amount=Decimal("30.00"),
        transaction_type="DRIVER_PENALTY",
        ride_id=None,
        idempotency_key="cancel-4",
        now=NOW,
    )

    assert repo.wallets[DRIVER_ID].low_balance_grace_ride_used is True


def test_credit_recharge_recovers_outstanding_debt_before_crediting_balance(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    _seed_balance(repo, Decimal("10.00"), outstanding_debt=Decimal("30.00"))

    transaction = service.credit(
        driver_id=DRIVER_ID,
        amount=Decimal("500.00"),
        transaction_type="WALLET_RECHARGE",
        ride_id=None,
        idempotency_key="recharge-debt-1",
        now=NOW,
    )

    # The full ₹500 is recorded (what was actually paid), but only
    # ₹470 actually lands in the spendable balance.
    assert transaction.amount == Decimal("500.00")
    assert transaction.balance_before == Decimal("10.00")
    assert transaction.balance_after == Decimal("480.00")
    assert repo.wallets[DRIVER_ID].balance == Decimal("480.00")
    assert repo.wallets[DRIVER_ID].outstanding_debt == Decimal("0")
    assert transaction.metadata is not None
    assert transaction.metadata["outstanding_debt_recovered"] == "30.00"
    assert transaction.metadata["outstanding_debt_remaining"] == "0.00"


def test_credit_recharge_smaller_than_debt_recovers_only_part_of_it(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    _seed_balance(repo, Decimal("0"), outstanding_debt=Decimal("30.00"))

    transaction = service.credit(
        driver_id=DRIVER_ID,
        amount=Decimal("20.00"),
        transaction_type="WALLET_RECHARGE",
        ride_id=None,
        idempotency_key="recharge-debt-2",
        now=NOW,
    )

    # Entire recharge absorbed by debt — nothing credited to balance.
    assert transaction.balance_before == Decimal("0")
    assert transaction.balance_after == Decimal("0")
    assert repo.wallets[DRIVER_ID].balance == Decimal("0")
    assert repo.wallets[DRIVER_ID].outstanding_debt == Decimal("10.00")
    assert transaction.metadata is not None
    assert transaction.metadata["outstanding_debt_recovered"] == "20.00"
    assert transaction.metadata["outstanding_debt_remaining"] == "10.00"


def test_credit_non_recharge_types_never_recover_debt(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    """Only WALLET_RECHARGE triggers debt recovery — a bonus/fee-
    reversal credit must not silently vanish into debt repayment."""
    _seed_balance(repo, Decimal("10.00"), outstanding_debt=Decimal("30.00"))

    transaction = service.credit(
        driver_id=DRIVER_ID,
        amount=Decimal("50.00"),
        transaction_type="JOINING_BONUS",
        ride_id=None,
        idempotency_key="bonus-1",
        now=NOW,
    )

    assert transaction.balance_after == Decimal("60.00")
    assert transaction.metadata is None
    assert repo.wallets[DRIVER_ID].outstanding_debt == Decimal("30.00")


def test_credit_recharge_with_no_debt_behaves_exactly_as_before(
    service: WalletService, repo: FakeWalletRepository
) -> None:
    _seed_balance(repo, Decimal("10.00"))

    transaction = service.credit(
        driver_id=DRIVER_ID,
        amount=Decimal("500.00"),
        transaction_type="WALLET_RECHARGE",
        ride_id=None,
        idempotency_key="recharge-no-debt-1",
        now=NOW,
    )

    assert transaction.amount == Decimal("500.00")
    assert transaction.balance_after == Decimal("510.00")
    assert transaction.metadata is None
