"""Integration tests: real HTTP layer (TestClient) + real Postgres,
exercising GET /api/v1/drivers/me/wallet end-to-end, plus real-concurrency
tests for WalletService.debit() (no HTTP endpoint calls it yet — see
modules/wallet/__init__.py — so those tests call the service directly,
each from its own real thread with its own independent DB session/
connection, same technique tests/test_vehicle_api.py's BR-122 activation
test already established).

No recharge/credit endpoint exists (out of scope — see
modules/wallet/__init__.py), so tests seed a wallet balance directly via
SQL, the same pattern already used throughout this codebase to reach
states no endpoint produces yet.

Skips (not fails) when Postgres is genuinely unreachable.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from core.database import SessionLocal
from main import app
from modules.identity.dependencies import get_sms_provider_dependency
from modules.wallet.domain.errors import InsufficientWalletBalanceError
from modules.wallet.repositories import SqlAlchemyWalletRepository
from modules.wallet.service import WalletService


class CapturingSmsProvider:
    def __init__(self) -> None:
        self.sent: dict[str, str] = {}

    async def send_otp(self, phone_number: str, otp: str) -> None:
        self.sent[phone_number] = otp


def _infra_available() -> bool:
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except OperationalError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _infra_available(),
    reason="Postgres is offline/unreachable (start docker-compose.dev.yml)",
)


@pytest.fixture
def sms() -> CapturingSmsProvider:
    return CapturingSmsProvider()


@pytest.fixture
def api_client(sms: CapturingSmsProvider) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_sms_provider_dependency] = lambda: sms
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_sms_provider_dependency, None)


def _random_phone() -> str:
    return "+91" + "".join(str(secrets.randbelow(10)) for _ in range(10))


def _login(api_client: TestClient, sms: CapturingSmsProvider, account_type: str) -> str:
    phone = _random_phone()
    request_response = api_client.post(
        "/api/v1/auth/otp/request",
        json={"phone": phone, "account_type": account_type},
    )
    challenge_id = request_response.json()["data"]["challenge_id"]
    otp = sms.sent[phone]
    tokens = api_client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "otp": otp},
    ).json()["data"]
    access_token: str = tokens["access_token"]
    return access_token


def _new_driver_with_profile(
    api_client: TestClient, sms: CapturingSmsProvider
) -> tuple[dict[str, str], uuid.UUID]:
    access_token = _login(api_client, sms, "DRIVER")
    headers = {"Authorization": f"Bearer {access_token}"}
    profile = api_client.patch(
        "/api/v1/drivers/me", json={"full_name": "Ravi Kumar"}, headers=headers
    ).json()["data"]
    return headers, uuid.UUID(profile["driver_id"])


def _seed_wallet_balance(driver_id: uuid.UUID, amount: Decimal) -> None:
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO wallet.wallets (driver_id, balance) "
                "VALUES (:driver_id, :amount) "
                "ON CONFLICT (driver_id) DO UPDATE SET balance = :amount"
            ),
            {"driver_id": str(driver_id), "amount": amount},
        )
        db.commit()
    finally:
        db.close()


# --- Get Wallet --------------------------------------------------------


def test_get_wallet_auto_provisions_zero_balance(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_headers, _ = _new_driver_with_profile(api_client, sms)

    response = api_client.get("/api/v1/drivers/me/wallet", headers=driver_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["balance"] == 0
    assert data["currency"] == "INR"
    assert data["outstanding_settlement"] == 0


def test_get_wallet_reflects_seeded_balance(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_headers, driver_id = _new_driver_with_profile(api_client, sms)
    _seed_wallet_balance(driver_id, Decimal("170.00"))

    response = api_client.get("/api/v1/drivers/me/wallet", headers=driver_headers)

    assert response.status_code == 200
    assert response.json()["data"]["balance"] == 170.0


def test_get_wallet_persists_the_auto_provisioned_row_in_postgres(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_headers, driver_id = _new_driver_with_profile(api_client, sms)

    api_client.get("/api/v1/drivers/me/wallet", headers=driver_headers)

    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT balance FROM wallet.wallets WHERE driver_id = :id"),
            {"id": str(driver_id)},
        ).fetchone()
        assert row is not None
        assert row.balance == Decimal("0")
    finally:
        db.close()


def test_get_wallet_unauthenticated_is_rejected(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/drivers/me/wallet")
    assert response.status_code == 401


def test_customer_cannot_access_driver_wallet(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    customer_token = _login(api_client, sms, "CUSTOMER")
    response = api_client.get(
        "/api/v1/drivers/me/wallet",
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert response.status_code == 403


def test_get_wallet_without_driver_profile_is_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "DRIVER")
    response = api_client.get(
        "/api/v1/drivers/me/wallet",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


# --- WalletService.debit() real-concurrency tests -----------------------
#
# No HTTP endpoint calls debit() yet (the next task, Accept Offer, is what
# composes it) — these call the service directly, each from a real OS
# thread with its own independent DB session, matching
# tests/test_vehicle_api.py's BR-122 activation-conflict test technique.


def _debit(
    driver_id: uuid.UUID, *, amount: Decimal, idempotency_key: str
) -> tuple[str, str | None]:
    """Runs in its own thread with its own DB session/connection.
    Returns (outcome, transaction_id) — outcome is "OK" or
    "INSUFFICIENT"."""
    db = SessionLocal()
    try:
        service = WalletService(wallets=SqlAlchemyWalletRepository(db))
        try:
            transaction = service.debit(
                driver_id=driver_id,
                amount=amount,
                transaction_type="PLATFORM_FEE",
                ride_id=None,
                idempotency_key=idempotency_key,
                now=datetime.now(UTC),
            )
        except InsufficientWalletBalanceError:
            db.rollback()
            return "INSUFFICIENT", None
        db.commit()
        return "OK", str(transaction.id)
    finally:
        db.close()


def test_concurrent_debits_never_allow_the_balance_to_go_negative(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """BR-013: prevent negative balance caused by concurrency. Wallet has
    exactly enough for one ₹20 debit; two concurrent debits (different
    idempotency keys, simulating two different rides) race for it —
    exactly one must succeed."""
    _, driver_id = _new_driver_with_profile(api_client, sms)
    _seed_wallet_balance(driver_id, Decimal("20.00"))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda key: _debit(
                    driver_id, amount=Decimal("20"), idempotency_key=key
                ),
                [
                    f"ride:{uuid.uuid4()}:platform-fee",
                    f"ride:{uuid.uuid4()}:platform-fee",
                ],
            )
        )

    outcomes = [outcome for outcome, _ in results]
    assert outcomes.count("OK") == 1
    assert outcomes.count("INSUFFICIENT") == 1

    db = SessionLocal()
    try:
        balance = db.execute(
            text("SELECT balance FROM wallet.wallets WHERE driver_id = :id"),
            {"id": str(driver_id)},
        ).scalar()
        assert balance == Decimal("0.00")

        ledger_count = db.execute(
            text("SELECT COUNT(*) FROM wallet.transactions WHERE driver_id = :id"),
            {"id": str(driver_id)},
        ).scalar()
        assert ledger_count == 1
    finally:
        db.close()


def test_concurrent_debits_with_the_same_idempotency_key_debit_exactly_once(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """A retried debit (same key, e.g. a network retry racing itself)
    must never double-debit, even under real concurrency."""
    _, driver_id = _new_driver_with_profile(api_client, sms)
    _seed_wallet_balance(driver_id, Decimal("100.00"))
    key = f"ride:{uuid.uuid4()}:platform-fee"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: _debit(driver_id, amount=Decimal("20"), idempotency_key=key),
                range(2),
            )
        )

    assert all(outcome == "OK" for outcome, _ in results)
    transaction_ids = {tx_id for _, tx_id in results}
    assert len(transaction_ids) == 1  # both calls returned the same transaction

    db = SessionLocal()
    try:
        balance = db.execute(
            text("SELECT balance FROM wallet.wallets WHERE driver_id = :id"),
            {"id": str(driver_id)},
        ).scalar()
        assert balance == Decimal("80.00")  # debited exactly once, not twice

        ledger_count = db.execute(
            text(
                "SELECT COUNT(*) FROM wallet.transactions WHERE idempotency_key = :key"
            ),
            {"key": key},
        ).scalar()
        assert ledger_count == 1
    finally:
        db.close()


def test_debit_writes_an_immutable_ledger_entry(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """ride_id is left None here — wallet.transactions.ride_id has a
    real foreign key to ride.rides, and standing up a real ride is
    unrelated machinery this wallet-focused test doesn't need; ride_id
    propagation through the service layer is already covered by
    tests/test_wallet_service.py's fake-repository test."""
    _, driver_id = _new_driver_with_profile(api_client, sms)
    _seed_wallet_balance(driver_id, Decimal("50.00"))
    key = f"driver:{driver_id}:platform-fee:{uuid.uuid4()}"

    db = SessionLocal()
    try:
        service = WalletService(wallets=SqlAlchemyWalletRepository(db))
        service.debit(
            driver_id=driver_id,
            amount=Decimal("20"),
            transaction_type="PLATFORM_FEE",
            ride_id=None,
            idempotency_key=key,
            now=datetime.now(UTC),
        )
        db.commit()
    finally:
        db.close()

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT transaction_type, direction, amount, balance_before, "
                "balance_after, ride_id FROM wallet.transactions "
                "WHERE idempotency_key = :key"
            ),
            {"key": key},
        ).fetchone()
        assert row is not None
        assert row.transaction_type == "PLATFORM_FEE"
        assert row.direction == "DEBIT"
        assert row.amount == Decimal("20.00")
        assert row.balance_before == Decimal("50.00")
        assert row.balance_after == Decimal("30.00")
        assert row.ride_id is None
    finally:
        db.close()


# --- Wallet Transactions (Phase 11, ADR-0024) ------------------------------


def _debit_directly(
    driver_id: uuid.UUID, *, amount: Decimal, transaction_type: str = "PLATFORM_FEE"
) -> None:
    db = SessionLocal()
    try:
        service = WalletService(wallets=SqlAlchemyWalletRepository(db))
        service.debit(
            driver_id=driver_id,
            amount=amount,
            transaction_type=transaction_type,
            ride_id=None,
            idempotency_key=f"test:{uuid.uuid4()}",
            now=datetime.now(UTC),
        )
        db.commit()
    finally:
        db.close()


def _credit_directly(
    driver_id: uuid.UUID,
    *,
    amount: Decimal,
    transaction_type: str = "FEE_REVERSAL",
    reference_type: str | None = None,
    reference_id: uuid.UUID | None = None,
) -> None:
    db = SessionLocal()
    try:
        service = WalletService(wallets=SqlAlchemyWalletRepository(db))
        service.credit(
            driver_id=driver_id,
            amount=amount,
            transaction_type=transaction_type,
            ride_id=None,
            idempotency_key=f"test:{uuid.uuid4()}",
            now=datetime.now(UTC),
            reference_type=reference_type,
            reference_id=reference_id,
        )
        db.commit()
    finally:
        db.close()


def test_list_transactions_returns_the_driver_own_ledger(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_headers, driver_id = _new_driver_with_profile(api_client, sms)
    _seed_wallet_balance(driver_id, Decimal("100.00"))
    _debit_directly(driver_id, amount=Decimal("10.00"))

    response = api_client.get(
        "/api/v1/drivers/me/wallet/transactions", headers=driver_headers
    )

    assert response.status_code == 200
    body = response.json()
    items = body["data"]["items"]
    assert len(items) == 1
    assert items[0]["transaction_type"] == "PLATFORM_FEE"
    assert items[0]["direction"] == "DEBIT"
    assert items[0]["amount"] == 10.0
    assert items[0]["balance_before"] == 100.0
    assert items[0]["balance_after"] == 90.0
    pagination = body["data"]["pagination"]
    assert pagination["total"] == 1


def test_list_transactions_orders_newest_first(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_headers, driver_id = _new_driver_with_profile(api_client, sms)
    _seed_wallet_balance(driver_id, Decimal("100.00"))
    _debit_directly(driver_id, amount=Decimal("10.00"))
    _debit_directly(driver_id, amount=Decimal("5.00"))

    response = api_client.get(
        "/api/v1/drivers/me/wallet/transactions", headers=driver_headers
    )

    items = response.json()["data"]["items"]
    assert [item["amount"] for item in items] == [5.0, 10.0]


def test_list_transactions_filters_by_type(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_headers, driver_id = _new_driver_with_profile(api_client, sms)
    _seed_wallet_balance(driver_id, Decimal("100.00"))
    _debit_directly(driver_id, amount=Decimal("10.00"), transaction_type="PLATFORM_FEE")
    _credit_directly(
        driver_id, amount=Decimal("10.00"), transaction_type="FEE_REVERSAL"
    )

    response = api_client.get(
        "/api/v1/drivers/me/wallet/transactions",
        params={"type": "FEE_REVERSAL"},
        headers=driver_headers,
    )

    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["transaction_type"] == "FEE_REVERSAL"


def test_list_transactions_includes_reference_fields(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_headers, driver_id = _new_driver_with_profile(api_client, sms)
    _seed_wallet_balance(driver_id, Decimal("100.00"))
    original_debit_id = uuid.uuid4()
    _credit_directly(
        driver_id,
        amount=Decimal("10.00"),
        reference_type="PLATFORM_FEE",
        reference_id=original_debit_id,
    )

    response = api_client.get(
        "/api/v1/drivers/me/wallet/transactions", headers=driver_headers
    )

    item = response.json()["data"]["items"][0]
    assert item["reference_type"] == "PLATFORM_FEE"
    assert item["reference_id"] == str(original_debit_id)


def test_list_transactions_rejects_unknown_type(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_headers, _ = _new_driver_with_profile(api_client, sms)

    response = api_client.get(
        "/api/v1/drivers/me/wallet/transactions",
        params={"type": "NOT_A_TYPE"},
        headers=driver_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_list_transactions_unauthenticated_is_rejected(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/drivers/me/wallet/transactions")
    assert response.status_code == 401


def test_list_transactions_without_driver_profile_is_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "DRIVER")
    response = api_client.get(
        "/api/v1/drivers/me/wallet/transactions",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 404


def test_list_transactions_empty_for_a_wallet_with_no_activity(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_headers, _ = _new_driver_with_profile(api_client, sms)

    response = api_client.get(
        "/api/v1/drivers/me/wallet/transactions", headers=driver_headers
    )

    assert response.status_code == 200
    assert response.json()["data"]["items"] == []
    assert response.json()["data"]["pagination"]["total"] == 0
