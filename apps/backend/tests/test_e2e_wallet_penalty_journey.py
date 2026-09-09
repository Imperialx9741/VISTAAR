"""E2E: the Sarthi (Driver) wallet + penalty journey — testing-strategy.md
§4.4/§84 ("End-to-End Insufficient Wallet Path").

One real, previously-undocumented blocker was found and confirmed here
against real Postgres, not assumed from reading code — see the
DOCUMENTED BLOCKER test below and
`docs/10-testing/e2e-findings-2026-09-02.md`. It is recorded as a
failing-as-expected test (not skipped, not silently worked around) so a
future fix makes this file's own suite go red until the test itself is
updated to match the new intended behavior.

Skips (not fails) when Postgres is genuinely unreachable, same
convention as this file's sibling E2E/integration tests.
"""

from __future__ import annotations

import asyncio
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
from core.redis import get_redis_client
from main import app
from modules.admin.models import AdminUserORM
from modules.identity.dependencies import get_sms_provider_dependency
from modules.identity.security import decode_access_token
from modules.vehicle.repositories import SqlAlchemyVehicleDocumentRepository
from modules.vehicle.service import VehicleDocumentService
from modules.wallet.dependencies import get_wallet_recharge_gateway_dependency
from modules.wallet.payment_gateway import RechargeOrder


class CapturingSmsProvider:
    def __init__(self) -> None:
        self.sent: dict[str, str] = {}

    async def send_otp(self, phone_number: str, otp: str) -> None:
        self.sent[phone_number] = otp


class FakeGateway:
    """Minimal stand-in for WalletRechargeGateway (ADR-0060) — only what
    the debt-recovery journey test below needs (create_order +
    verify_payment); same convention tests/test_wallet_recharge_api.py's
    own, fuller FakeGateway already establishes."""

    def __init__(self) -> None:
        self.verify_payment_result: Decimal | None = None

    async def create_order(
        self, *, driver_id: uuid.UUID, amount: Decimal
    ) -> RechargeOrder:
        return RechargeOrder(
            order_id="order_fake_1",
            amount=amount,
            currency="INR",
            client_key="fake_client_key",
        )

    async def verify_payment(
        self, *, order_id: str, payment_id: str, signature: str
    ) -> Decimal | None:
        return self.verify_payment_result

    def verify_webhook_signature(self, *, payload: bytes, signature: str) -> bool:
        return True

    def parse_captured_payment(
        self, payload: dict[str, object]
    ) -> tuple[uuid.UUID, str, Decimal] | None:
        return None


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
    truncate_integration_tables(engine)
    asyncio.run(_clean_matching_geo_index())


async def _clean_matching_geo_index() -> None:
    client = get_redis_client()
    try:
        async for key in client.scan_iter(match="geo:drivers:*"):
            await client.delete(key)
        async for key in client.scan_iter(match="driver:online:*"):
            await client.delete(key)
    finally:
        await client.aclose()


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


def _random_registration() -> str:
    return "BR01" + "".join(str(secrets.randbelow(10)) for _ in range(6))


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


def _account_id_from_token(access_token: str) -> uuid.UUID:
    payload = decode_access_token(access_token)
    return uuid.UUID(payload["sub"])


def _provision_admin(account_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        db.add(AdminUserORM(id=account_id, role="SUPER_ADMIN", status="ACTIVE"))
        db.commit()
    finally:
        db.close()


def _login_admin(api_client: TestClient, sms: CapturingSmsProvider) -> dict:
    access_token = _login(api_client, sms, "ADMIN")
    account_id = _account_id_from_token(access_token)
    _provision_admin(account_id)
    return {"Authorization": f"Bearer {access_token}"}


def _new_driver_with_profile(api_client: TestClient, sms: CapturingSmsProvider) -> dict:
    access_token = _login(api_client, sms, "DRIVER")
    headers = {"Authorization": f"Bearer {access_token}"}
    api_client.patch(
        "/api/v1/drivers/me", json={"full_name": "Ravi Kumar"}, headers=headers
    )
    return headers


def _submit_driver_document(
    api_client: TestClient, driver_headers: dict, document_type: str
) -> str:
    response = api_client.post(
        "/api/v1/drivers/me/documents",
        json={"document_type": document_type, "evidence_uri": "ref-1"},
        headers=driver_headers,
    )
    document_id: str = response.json()["data"]["document_id"]
    return document_id


def _mark_driver_document_approved(document_id: str) -> None:
    db = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE driver.documents SET verification_status = 'APPROVED' "
                "WHERE id = :id"
            ),
            {"id": document_id},
        )
        db.commit()
    finally:
        db.close()


def _make_driver_documents_valid(api_client: TestClient, driver_headers: dict) -> None:
    for document_type in ("GOVERNMENT_ID", "DRIVING_LICENSE"):
        document_id = _submit_driver_document(api_client, driver_headers, document_type)
        _mark_driver_document_approved(document_id)


def _submit_vehicle_document(vehicle_id: str, document_type: str) -> str:
    db = SessionLocal()
    try:
        service = VehicleDocumentService(
            documents=SqlAlchemyVehicleDocumentRepository(db)
        )
        document = service.submit_document(
            vehicle_id=uuid.UUID(vehicle_id),
            document_type=document_type,
            document_number=None,
            evidence_uri="ref-1",
            expires_at=None,
        )
        db.commit()
        return str(document.id)
    finally:
        db.close()


def _mark_vehicle_document_approved(document_id: str) -> None:
    db = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE vehicle.documents SET verification_status = 'APPROVED' "
                "WHERE id = :id"
            ),
            {"id": document_id},
        )
        db.commit()
    finally:
        db.close()


def _make_vehicle_documents_valid(vehicle_id: str) -> None:
    for document_type in ("RC", "INSURANCE"):
        document_id = _submit_vehicle_document(vehicle_id, document_type)
        _mark_vehicle_document_approved(document_id)


def _approve_driver(
    api_client: TestClient, admin_headers: dict, driver_id: str
) -> None:
    response = api_client.post(
        f"/api/v1/admin/drivers/{driver_id}/approve", headers=admin_headers
    )
    assert response.status_code == 200


def _approve_vehicle(
    api_client: TestClient, admin_headers: dict, vehicle_id: str
) -> None:
    response = api_client.post(
        f"/api/v1/admin/vehicles/{vehicle_id}/approve", headers=admin_headers
    )
    assert response.status_code == 200


def _seed_wallet_balance(driver_id: str, amount: Decimal) -> None:
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO wallet.wallets (driver_id, balance) "
                "VALUES (:driver_id, :amount) "
                "ON CONFLICT (driver_id) DO UPDATE SET balance = :amount"
            ),
            {"driver_id": driver_id, "amount": amount},
        )
        db.commit()
    finally:
        db.close()


def _new_online_eligible_driver(
    api_client: TestClient,
    sms: CapturingSmsProvider,
    admin_headers: dict,
    *,
    wallet_balance: Decimal = Decimal("100.00"),
) -> tuple[dict, str, str]:
    """Returns (driver_headers, driver_id, vehicle_id). Unlike the sibling
    E2E files' identical-named helper, this one takes wallet_balance as a
    parameter — the whole point of this file is exercising both the
    sufficient- and insufficient-balance paths."""
    driver_headers = _new_driver_with_profile(api_client, sms)
    driver_id = api_client.get("/api/v1/drivers/me", headers=driver_headers).json()[
        "data"
    ]["driver_id"]
    _make_driver_documents_valid(api_client, driver_headers)
    _approve_driver(api_client, admin_headers, driver_id)

    vehicle = api_client.post(
        "/api/v1/drivers/me/vehicles",
        json={
            "category": "CAB",
            "cab_tier": "ECO",
            "registration_number": _random_registration(),
        },
        headers=driver_headers,
    ).json()["data"]
    vehicle_id = vehicle["vehicle_id"]
    _make_vehicle_documents_valid(vehicle_id)
    _approve_vehicle(api_client, admin_headers, vehicle_id)
    api_client.post(
        f"/api/v1/drivers/me/vehicles/{vehicle_id}/activate", headers=driver_headers
    )
    _seed_wallet_balance(driver_id, wallet_balance)
    online = api_client.post("/api/v1/drivers/me/online", headers=driver_headers)
    assert online.status_code == 200
    api_client.post(
        "/api/v1/drivers/me/location",
        json={"latitude": 25.5941, "longitude": 85.1376},
        headers=driver_headers,
    )
    return driver_headers, driver_id, vehicle_id


VALID_RIDE_BODY = {
    "pickup": {"latitude": 25.5941, "longitude": 85.1376},
    "destination": {"latitude": 25.6120, "longitude": 85.1580},
    "vehicle_category": "CAB",
    "cab_tier": "ECO",
    "payment_method": "ONLINE",
}


def _accepted_ride_with_driver(
    api_client: TestClient, sms: CapturingSmsProvider, driver_headers: dict
) -> str:
    customer_token = _login(api_client, sms, "CUSTOMER")
    customer_headers = {"Authorization": f"Bearer {customer_token}"}
    create_response = api_client.post(
        "/api/v1/rides",
        json=VALID_RIDE_BODY,
        headers={**customer_headers, "Idempotency-Key": f"ride-{uuid.uuid4()}"},
    )
    ride_id = create_response.json()["data"]["ride_id"]
    offers = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=driver_headers
    ).json()["data"]["offers"]
    api_client.post(
        f"/api/v1/drivers/me/ride-offers/{offers[0]['offer_id']}/accept",
        headers={**driver_headers, "Idempotency-Key": f"accept-{uuid.uuid4()}"},
    )
    return ride_id


def test_driver_cancellation_with_sufficient_balance_debits_wallet_and_strikes(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """The real, working half of §84's story: a driver with a sufficient
    balance cancelling incurs the real ₹30 penalty (BR-011,
    `_DRIVER_CANCELLATION_PENALTY` in modules/ride/router.py) and a
    strike, both actually persisted — not the insufficient-balance
    scenario itself, which is the next test.

    Also confirms a real interaction this test's first draft got wrong
    (fixed after actually running it, not assumed from reading code
    alone): accepting the offer itself already debits a CAB platform fee
    (₹10, `_PLATFORM_FEE_BY_CATEGORY` in modules/matching/router.py, ADR
    Accept Offer) before the ride is ever cancelled — so the expected
    ending balance is ₹100 - ₹10 (accept) - ₹30 (cancellation) = ₹60,
    not ₹100 - ₹30."""
    admin_headers = _login_admin(api_client, sms)
    driver_headers, driver_id, _vehicle_id = _new_online_eligible_driver(
        api_client, sms, admin_headers, wallet_balance=Decimal("100.00")
    )
    ride_id = _accepted_ride_with_driver(api_client, sms, driver_headers)

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/driver-cancel",
        json={"reason": "VEHICLE_BREAKDOWN"},
        headers=driver_headers,
    )

    assert response.status_code == 200

    db = SessionLocal()
    try:
        wallet_row = db.execute(
            text("SELECT balance FROM wallet.wallets WHERE driver_id = :id"),
            {"id": driver_id},
        ).fetchone()
        assert wallet_row is not None
        assert wallet_row.balance == Decimal("60.00")

        strike_row = db.execute(
            text(
                "SELECT reason FROM penalty.strikes WHERE driver_id = :id "
                "AND ride_id = :ride_id"
            ),
            {"id": driver_id, "ride_id": ride_id},
        ).fetchone()
        assert strike_row is not None
        assert strike_row.reason == "VEHICLE_BREAKDOWN"
    finally:
        db.close()


def test_driver_cancellation_with_insufficient_balance_records_a_debt_and_still_cancels(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """RESOLVED (ADR-0062, 2026-09-03, owner decision) — this test used
    to assert the opposite of what's below, on purpose (see git history/
    the ADR itself for the full account): a driver with an insufficient
    wallet balance used to be blocked from cancelling a ride at all,
    with the whole cancellation rolled back. The owner's decision:
    cancellation must never be blocked by this — instead, the unpaid
    penalty becomes a tracked `wallet.outstanding_debt`, recovered
    automatically from a future wallet recharge (the next test in this
    file exercises that recovery end to end).

    Seeded at ₹20, not literally security.md §25's own "₹10" — accepting
    the offer itself already debits a ₹10 CAB platform fee (see the
    sibling test above), so ₹20 seeded here reaches the same real ₹10
    balance §25's worked example describes by the time the ₹30
    cancellation penalty is attempted.
    """
    admin_headers = _login_admin(api_client, sms)
    driver_headers, driver_id, _vehicle_id = _new_online_eligible_driver(
        api_client, sms, admin_headers, wallet_balance=Decimal("20.00")
    )
    ride_id = _accepted_ride_with_driver(api_client, sms, driver_headers)

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/driver-cancel",
        json={"reason": "VEHICLE_BREAKDOWN"},
        headers=driver_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["ride_status"] == "CANCELLED"

    db = SessionLocal()
    try:
        ride_row = db.execute(
            text("SELECT status FROM ride.rides WHERE id = :id"), {"id": ride_id}
        ).fetchone()
        assert ride_row is not None
        assert ride_row.status == "CANCELLED"

        wallet_row = db.execute(
            text(
                "SELECT balance, outstanding_debt FROM wallet.wallets "
                "WHERE driver_id = :id"
            ),
            {"id": driver_id},
        ).fetchone()
        assert wallet_row is not None
        # ₹20 seeded - ₹10 accept-time platform fee = ₹10 — untouched,
        # no partial deduction — with the full ₹30 penalty tracked as
        # debt instead.
        assert wallet_row.balance == Decimal("10.00")
        assert wallet_row.outstanding_debt == Decimal("30.00")

        strike_row = db.execute(
            text("SELECT id FROM penalty.strikes WHERE driver_id = :id"),
            {"id": driver_id},
        ).fetchone()
        assert strike_row is not None, (
            "the strike still applies — only the debit path changed"
        )
    finally:
        db.close()


def test_wallet_recharge_recovers_outstanding_debt(
    api_client: TestClient, sms: CapturingSmsProvider, gateway: FakeGateway
) -> None:
    """testing-strategy.md §84's second half, now genuinely real
    end-to-end (ADR-0062, 2026-09-03) — a driver cancels with an
    insufficient balance (incurring a ₹30 debt, exactly the scenario the
    sibling test above proves), then recharges through the real
    POST /wallet/recharge + /recharge/confirm HTTP endpoints (Razorpay
    TEST-mode gateway faked, same convention test_wallet_recharge_api.py
    already uses) — the recharge should pay down the debt first, then
    credit only the remainder to the spendable balance."""
    admin_headers = _login_admin(api_client, sms)
    driver_headers, driver_id, _vehicle_id = _new_online_eligible_driver(
        api_client, sms, admin_headers, wallet_balance=Decimal("20.00")
    )
    ride_id = _accepted_ride_with_driver(api_client, sms, driver_headers)
    cancel_response = api_client.post(
        f"/api/v1/rides/{ride_id}/driver-cancel",
        json={"reason": "VEHICLE_BREAKDOWN"},
        headers=driver_headers,
    )
    assert cancel_response.status_code == 200

    gateway.verify_payment_result = Decimal("500.00")
    confirm_response = api_client.post(
        "/api/v1/drivers/me/wallet/recharge/confirm",
        json={
            "order_id": "order_fake_1",
            "payment_id": "pay_fake_1",
            "signature": "sig",
        },
        headers=driver_headers,
    )

    assert confirm_response.status_code == 200
    confirm_data = confirm_response.json()["data"]
    assert confirm_data["debt_recovered"] == 30.0
    assert confirm_data["outstanding_debt_remaining"] == 0.0
    # ₹10 (post-accept, pre-recharge) + ₹500 recharge - ₹30 debt = ₹480.
    assert confirm_data["wallet_balance"] == 480.0

    db = SessionLocal()
    try:
        wallet_row = db.execute(
            text(
                "SELECT balance, outstanding_debt FROM wallet.wallets "
                "WHERE driver_id = :id"
            ),
            {"id": driver_id},
        ).fetchone()
        assert wallet_row is not None
        assert wallet_row.balance == Decimal("480.00")
        assert wallet_row.outstanding_debt == Decimal("0")
    finally:
        db.close()
