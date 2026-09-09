"""Integration tests: real HTTP layer (TestClient) + real Postgres,
exercising Sarthi Wallet Recharge end-to-end (ADR-0060) —
POST /api/v1/drivers/me/wallet/recharge,
POST /api/v1/drivers/me/wallet/recharge/confirm, and
POST /api/v1/webhooks/wallet-recharge/razorpay.

The real gateway (Razorpay) is swapped for a fake one via
app.dependency_overrides, same convention every other provider-backed
test in this codebase uses for its own SMS provider — this lets these
tests drive genuine success/failure paths through the real router and
real WalletService.credit() without a live Razorpay account.

Skips (not fails) when Postgres is genuinely unreachable.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Generator
from decimal import Decimal

import pytest
from _integration_db import truncate_integration_tables
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from core.database import SessionLocal, engine
from main import app
from modules.identity.dependencies import get_sms_provider_dependency
from modules.wallet.dependencies import get_wallet_recharge_gateway_dependency
from modules.wallet.payment_gateway import PaymentGatewayError, RechargeOrder


class CapturingSmsProvider:
    def __init__(self) -> None:
        self.sent: dict[str, str] = {}

    async def send_otp(self, phone_number: str, otp: str) -> None:
        self.sent[phone_number] = otp


class FakeGateway:
    """Every method is controllable per-test via plain attributes — no
    real Razorpay call is ever reachable from this fake."""

    def __init__(self) -> None:
        self.create_order_error: PaymentGatewayError | None = None
        self.verify_payment_result: Decimal | None = None
        self.verify_payment_error: PaymentGatewayError | None = None
        self.webhook_signature_valid = True
        self.captured_payment: tuple[uuid.UUID, str, Decimal] | None = None
        self.create_order_calls: list[tuple[uuid.UUID, Decimal]] = []
        self.verify_payment_calls: list[tuple[str, str, str]] = []

    async def create_order(
        self, *, driver_id: uuid.UUID, amount: Decimal
    ) -> RechargeOrder:
        self.create_order_calls.append((driver_id, amount))
        if self.create_order_error is not None:
            raise self.create_order_error
        return RechargeOrder(
            order_id="order_fake_1",
            amount=amount,
            currency="INR",
            client_key="fake_client_key",
        )

    async def verify_payment(
        self, *, order_id: str, payment_id: str, signature: str
    ) -> Decimal | None:
        self.verify_payment_calls.append((order_id, payment_id, signature))
        if self.verify_payment_error is not None:
            raise self.verify_payment_error
        return self.verify_payment_result

    def verify_webhook_signature(self, *, payload: bytes, signature: str) -> bool:
        return self.webhook_signature_valid

    def parse_captured_payment(
        self, payload: dict[str, object]
    ) -> tuple[uuid.UUID, str, Decimal] | None:
        return self.captured_payment


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


@pytest.fixture(autouse=True)
def _clean_integration_tables() -> None:
    """Same essential (not merely tidy) cleanup every other integration
    test file in this directory already applies via this identical
    fixture (e.g. test_destination_change_api.py). Root-caused here on
    2026-09-02: without it, this file's hardcoded literal payment_ids
    ("pay_fake_1", "pay_webhook_1", "pay_shared_1") collide across
    separate test runs against the persistent local test database on
    wallet.transactions.idempotency_key's UNIQUE constraint (global, not
    per-driver — see WalletService.credit()'s own docstring) — a
    *previous* run's already-committed "razorpay:pay_fake_1" row (for
    some earlier, unrelated driver) makes credit() treat this run's
    confirm/webhook call as a replay of that old payment: it returns the
    old transaction (a real balance_after, so the HTTP response looks
    correct) without ever crediting *this* test's new driver, who
    therefore still shows a wallet balance of 0. truncate_integration_
    tables() before every test removes that stale row so each test's
    literal payment_id is genuinely fresh."""
    truncate_integration_tables(engine)


@pytest.fixture
def sms() -> CapturingSmsProvider:
    return CapturingSmsProvider()


@pytest.fixture
def gateway() -> FakeGateway:
    return FakeGateway()


@pytest.fixture
def api_client(
    sms: CapturingSmsProvider, gateway: FakeGateway
) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_sms_provider_dependency] = lambda: sms
    app.dependency_overrides[get_wallet_recharge_gateway_dependency] = lambda: gateway
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_sms_provider_dependency, None)
    app.dependency_overrides.pop(get_wallet_recharge_gateway_dependency, None)


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


def _wallet_balance(driver_id: uuid.UUID) -> Decimal:
    db = SessionLocal()
    try:
        balance = db.execute(
            text("SELECT balance FROM wallet.wallets WHERE driver_id = :id"),
            {"id": str(driver_id)},
        ).scalar()
        return Decimal(balance) if balance is not None else Decimal("0")
    finally:
        db.close()


# --- Create Recharge Order --------------------------------------------------


def test_create_recharge_order_succeeds(
    api_client: TestClient, sms: CapturingSmsProvider, gateway: FakeGateway
) -> None:
    headers, driver_id = _new_driver_with_profile(api_client, sms)

    response = api_client.post(
        "/api/v1/drivers/me/wallet/recharge",
        json={"amount": "500.00"},
        headers=headers,
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["order_id"] == "order_fake_1"
    assert data["amount"] == 500.0
    assert data["currency"] == "INR"
    assert data["client_key"] == "fake_client_key"
    assert gateway.create_order_calls == [(driver_id, Decimal("500.00"))]


def test_create_recharge_order_rejects_amount_below_minimum(
    api_client: TestClient, sms: CapturingSmsProvider, gateway: FakeGateway
) -> None:
    headers, _driver_id = _new_driver_with_profile(api_client, sms)

    response = api_client.post(
        "/api/v1/drivers/me/wallet/recharge",
        json={"amount": "100.00"},  # api-contracts.md §35: minimum ₹200
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RECHARGE_AMOUNT_TOO_LOW"
    assert gateway.create_order_calls == []


def test_create_recharge_order_rejects_a_negative_amount(
    api_client: TestClient, sms: CapturingSmsProvider, gateway: FakeGateway
) -> None:
    """Targeted negative-money test (security review, 2026-09-03) — a
    negative amount is also below the ₹200 minimum, so the sibling test
    above should already cover it in principle, but this proves it
    explicitly through the real endpoint rather than assuming the same
    `amount < minimum` comparison behaves safely for a negative Decimal
    too (no gateway call, no order created, no crash)."""
    headers, _driver_id = _new_driver_with_profile(api_client, sms)

    response = api_client.post(
        "/api/v1/drivers/me/wallet/recharge",
        json={"amount": "-500.00"},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RECHARGE_AMOUNT_TOO_LOW"
    assert gateway.create_order_calls == []


def test_create_recharge_order_surfaces_a_gateway_error(
    api_client: TestClient, sms: CapturingSmsProvider, gateway: FakeGateway
) -> None:
    gateway.create_order_error = PaymentGatewayError("simulated outage")
    headers, _driver_id = _new_driver_with_profile(api_client, sms)

    response = api_client.post(
        "/api/v1/drivers/me/wallet/recharge",
        json={"amount": "500.00"},
        headers=headers,
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "PAYMENT_GATEWAY_ERROR"


def test_create_recharge_order_unauthenticated_is_rejected(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/api/v1/drivers/me/wallet/recharge", json={"amount": "500.00"}
    )
    assert response.status_code == 401


def test_customer_cannot_create_a_recharge_order(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "CUSTOMER")
    response = api_client.post(
        "/api/v1/drivers/me/wallet/recharge",
        json={"amount": "500.00"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 403


# --- Confirm Recharge --------------------------------------------------


def test_confirm_recharge_credits_the_wallet_on_verified_payment(
    api_client: TestClient, sms: CapturingSmsProvider, gateway: FakeGateway
) -> None:
    headers, driver_id = _new_driver_with_profile(api_client, sms)
    gateway.verify_payment_result = Decimal("500.00")

    response = api_client.post(
        "/api/v1/drivers/me/wallet/recharge/confirm",
        json={
            "order_id": "order_fake_1",
            "payment_id": "pay_fake_1",
            "signature": "sig",
        },
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "CREDITED"
    assert data["wallet_balance"] == 500.0
    assert _wallet_balance(driver_id) == Decimal("500.00")

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT transaction_type, direction, amount, metadata "
                "FROM wallet.transactions WHERE driver_id = :id"
            ),
            {"id": str(driver_id)},
        ).fetchone()
        assert row is not None
        assert row.transaction_type == "WALLET_RECHARGE"
        assert row.direction == "CREDIT"
        assert row.amount == Decimal("500.00")
        assert row.metadata == {
            "provider": "razorpay",
            "order_id": "order_fake_1",
            "payment_id": "pay_fake_1",
        }
    finally:
        db.close()


def test_confirm_recharge_never_credits_an_unverified_payment(
    api_client: TestClient, sms: CapturingSmsProvider, gateway: FakeGateway
) -> None:
    headers, driver_id = _new_driver_with_profile(api_client, sms)
    gateway.verify_payment_result = None  # signature/status check failed

    response = api_client.post(
        "/api/v1/drivers/me/wallet/recharge/confirm",
        json={
            "order_id": "order_fake_1",
            "payment_id": "pay_fake_1",
            "signature": "bad-sig",
        },
        headers=headers,
    )

    assert response.status_code == 402
    assert response.json()["error"]["code"] == "PAYMENT_VERIFICATION_FAILED"
    assert _wallet_balance(driver_id) == Decimal("0")


def test_confirm_recharge_is_idempotent_on_the_same_payment_id(
    api_client: TestClient, sms: CapturingSmsProvider, gateway: FakeGateway
) -> None:
    """Calling confirm twice for the same real payment (e.g. a retried
    mobile request after a dropped response) must not double-credit —
    WalletService.credit()'s own idempotency-key guarantee, exercised
    through the real HTTP endpoint."""
    headers, driver_id = _new_driver_with_profile(api_client, sms)
    gateway.verify_payment_result = Decimal("500.00")
    body = {
        "order_id": "order_fake_1",
        "payment_id": "pay_fake_idempotent_1",
        "signature": "sig",
    }

    first = api_client.post(
        "/api/v1/drivers/me/wallet/recharge/confirm", json=body, headers=headers
    )
    second = api_client.post(
        "/api/v1/drivers/me/wallet/recharge/confirm", json=body, headers=headers
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert _wallet_balance(driver_id) == Decimal("500.00")  # not 1000


def test_confirm_recharge_surfaces_a_gateway_error(
    api_client: TestClient, sms: CapturingSmsProvider, gateway: FakeGateway
) -> None:
    gateway.verify_payment_error = PaymentGatewayError("simulated outage")
    headers, _driver_id = _new_driver_with_profile(api_client, sms)

    response = api_client.post(
        "/api/v1/drivers/me/wallet/recharge/confirm",
        json={"order_id": "order_1", "payment_id": "pay_1", "signature": "sig"},
        headers=headers,
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "PAYMENT_GATEWAY_ERROR"


# --- Webhook --------------------------------------------------


def test_webhook_rejects_an_invalid_signature(
    api_client: TestClient, gateway: FakeGateway
) -> None:
    gateway.webhook_signature_valid = False

    response = api_client.post(
        "/api/v1/webhooks/wallet-recharge/razorpay",
        json={"event": "payment.captured"},
        headers={"X-Razorpay-Signature": "bad-signature"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_WEBHOOK_SIGNATURE"


def test_webhook_rejects_a_missing_signature_header(
    api_client: TestClient, gateway: FakeGateway
) -> None:
    response = api_client.post(
        "/api/v1/webhooks/wallet-recharge/razorpay",
        json={"event": "payment.captured"},
    )
    assert response.status_code == 401


def test_webhook_rejects_malformed_json_cleanly(
    api_client: TestClient, gateway: FakeGateway
) -> None:
    """Targeted negative-webhook test (security review, 2026-09-03) —
    found as a real bug, not assumed safe: a genuinely-signed-but-
    malformed body (`gateway.webhook_signature_valid` defaults True on
    the fake, standing in for "the signature check passed") previously
    reached `request.json()` completely unguarded. Reproduced for real
    first — a raw `json.JSONDecodeError` propagated to an unhandled 500
    instead of this codebase's standard structured error response — then
    fixed (`modules/wallet/router.py`'s `razorpay_webhook`) and verified
    here."""
    response = api_client.post(
        "/api/v1/webhooks/wallet-recharge/razorpay",
        content=b"not-json-garbage",
        headers={
            "X-Razorpay-Signature": "whatever-the-fake-gateway-accepts-anything",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_webhook_ignores_a_non_capture_event(
    api_client: TestClient, sms: CapturingSmsProvider, gateway: FakeGateway
) -> None:
    _headers, driver_id = _new_driver_with_profile(api_client, sms)
    gateway.captured_payment = None  # a real gateway would also return
    # None for e.g. payment.failed

    response = api_client.post(
        "/api/v1/webhooks/wallet-recharge/razorpay",
        json={"event": "payment.failed"},
        headers={"X-Razorpay-Signature": "valid"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "IGNORED"
    assert _wallet_balance(driver_id) == Decimal("0")


def test_webhook_credits_the_wallet_on_a_captured_payment(
    api_client: TestClient, sms: CapturingSmsProvider, gateway: FakeGateway
) -> None:
    _headers, driver_id = _new_driver_with_profile(api_client, sms)
    gateway.captured_payment = (driver_id, "pay_webhook_1", Decimal("500.00"))

    response = api_client.post(
        "/api/v1/webhooks/wallet-recharge/razorpay",
        json={"event": "payment.captured"},
        headers={"X-Razorpay-Signature": "valid"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "PROCESSED"
    assert _wallet_balance(driver_id) == Decimal("500.00")


def test_webhook_and_confirm_for_the_same_payment_credit_exactly_once(
    api_client: TestClient, sms: CapturingSmsProvider, gateway: FakeGateway
) -> None:
    """The resilience scenario ADR-0060 is built for: the mobile confirm
    call *and* the webhook both arrive for the same real payment —
    whichever reaches this backend first credits the wallet, the second
    is a safe no-op replay (the shared f"razorpay:{payment_id}"
    idempotency key)."""
    headers, driver_id = _new_driver_with_profile(api_client, sms)
    gateway.verify_payment_result = Decimal("500.00")
    gateway.captured_payment = (driver_id, "pay_shared_1", Decimal("500.00"))

    confirm_response = api_client.post(
        "/api/v1/drivers/me/wallet/recharge/confirm",
        json={
            "order_id": "order_fake_1",
            "payment_id": "pay_shared_1",
            "signature": "sig",
        },
        headers=headers,
    )
    webhook_response = api_client.post(
        "/api/v1/webhooks/wallet-recharge/razorpay",
        json={"event": "payment.captured"},
        headers={"X-Razorpay-Signature": "valid"},
    )

    assert confirm_response.status_code == 200
    assert webhook_response.status_code == 200
    assert _wallet_balance(driver_id) == Decimal("500.00")  # not 1000

    db = SessionLocal()
    try:
        count = db.execute(
            text(
                "SELECT COUNT(*) FROM wallet.transactions "
                "WHERE driver_id = :id AND transaction_type = 'WALLET_RECHARGE'"
            ),
            {"id": str(driver_id)},
        ).scalar()
        assert count == 1
    finally:
        db.close()
