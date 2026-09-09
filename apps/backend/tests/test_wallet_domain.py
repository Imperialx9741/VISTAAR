"""Unit tests for the pure Wallet domain layer (no DB)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from modules.wallet.domain.entities import InvalidAmountError, Wallet, validate_amount

DRIVER_ID = uuid.uuid4()
NOW = datetime.now(UTC)


def test_new_wallet_starts_at_zero_balance() -> None:
    wallet = Wallet.new(driver_id=DRIVER_ID, now=NOW)
    assert wallet.balance == Decimal("0")
    assert wallet.version == 1
    assert wallet.driver_id == DRIVER_ID


def test_validate_amount_accepts_positive_value() -> None:
    assert validate_amount(Decimal("20")) == Decimal("20")


@pytest.mark.parametrize("bad_amount", [Decimal("0"), Decimal("-1"), Decimal("-0.01")])
def test_validate_amount_rejects_non_positive_value(bad_amount: Decimal) -> None:
    with pytest.raises(InvalidAmountError):
        validate_amount(bad_amount)
