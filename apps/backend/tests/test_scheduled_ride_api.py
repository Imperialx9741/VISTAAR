"""Integration tests: real HTTP layer (TestClient) + real Postgres,
exercising Schedule a Ride end-to-end (ADR-0057):

    POST /api/v1/rides             extended with scheduled_for
    POST /api/v1/rides/{id}/cancel extended for a SCHEDULED ride
    GET  /api/v1/rides             List My Rides

A SCHEDULED ride never has a driver assigned (matching hasn't started
yet — ADR-0057 Decision 1), so unlike tests/test_ride_lifecycle_api.py
none of this needs the driver/vehicle-approval setup helpers; only
tests/test_ride_api.py's simpler customer-only fixtures.

Skips (not fails) when Postgres is genuinely unreachable.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from core.database import SessionLocal
from main import app
from modules.identity.dependencies import get_sms_provider_dependency


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


def _login_as_new_customer(api_client: TestClient, sms: CapturingSmsProvider) -> str:
    phone = _random_phone()
    request_response = api_client.post(
        "/api/v1/auth/otp/request",
        json={"phone": phone, "account_type": "CUSTOMER"},
    )
    challenge_id = request_response.json()["data"]["challenge_id"]
    otp = sms.sent[phone]
    tokens = api_client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "otp": otp},
    ).json()["data"]
    access_token: str = tokens["access_token"]
    return access_token


def _idempotency_key() -> str:
    return f"test-{uuid.uuid4()}"


def _ride_body(**overrides: object) -> dict:
    body: dict[str, object] = {
        "pickup": {"latitude": 25.5941, "longitude": 85.1376},
        "destination": {"latitude": 25.6120, "longitude": 85.1580},
        "vehicle_category": "CAB",
        "cab_tier": "ECO",
        "payment_method": "ONLINE",
    }
    body.update(overrides)
    return body


def _create_ride(
    api_client: TestClient, headers: dict, **body_overrides: object
) -> dict:
    response = api_client.post(
        "/api/v1/rides",
        json=_ride_body(**body_overrides),
        headers={**headers, "Idempotency-Key": _idempotency_key()},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


# --- Create: scheduled_for --------------------------------------------


def test_create_scheduled_ride_enters_scheduled_status(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    headers = {"Authorization": f"Bearer {access_token}"}
    scheduled_for = (datetime.now(UTC) + timedelta(hours=2)).isoformat()

    data = _create_ride(api_client, headers, scheduled_for=scheduled_for)

    assert data["status"] == "SCHEDULED"
    # ADR-0057 Decision 1 — the fare is locked at this same moment,
    # exactly as an immediate ride's own fare already is.
    assert data["fare"] is not None
    assert data["fare"]["total"] > 0


def test_get_ride_includes_scheduled_for(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    headers = {"Authorization": f"Bearer {access_token}"}
    scheduled_for = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    ride = _create_ride(api_client, headers, scheduled_for=scheduled_for)

    response = api_client.get(f"/api/v1/rides/{ride['ride_id']}", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["scheduled_for"] is not None


def test_get_ride_for_an_immediate_ride_has_no_scheduled_for(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    headers = {"Authorization": f"Bearer {access_token}"}
    ride = _create_ride(api_client, headers)

    response = api_client.get(f"/api/v1/rides/{ride['ride_id']}", headers=headers)

    assert response.json()["data"]["scheduled_for"] is None


def test_create_scheduled_ride_does_not_dispatch_a_matching_offer(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Matching does not begin until the Beat task promotes this ride
    to SEARCHING (ADR-0057 Decision 1) — no matching.offers row should
    exist for it yet, unlike an ordinary immediate ride."""
    access_token = _login_as_new_customer(api_client, sms)
    headers = {"Authorization": f"Bearer {access_token}"}
    scheduled_for = (datetime.now(UTC) + timedelta(hours=2)).isoformat()

    data = _create_ride(api_client, headers, scheduled_for=scheduled_for)

    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT COUNT(*) FROM matching.ride_offers WHERE ride_id = :ride_id"),
            {"ride_id": data["ride_id"]},
        ).scalar_one()
        assert row == 0
    finally:
        db.close()


@pytest.mark.parametrize(
    "lead_time",
    [timedelta(minutes=30), timedelta(hours=24, minutes=30)],
)
def test_create_ride_rejects_a_scheduled_for_outside_the_window(
    api_client: TestClient, sms: CapturingSmsProvider, lead_time: timedelta
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    headers = {"Authorization": f"Bearer {access_token}"}
    scheduled_for = (datetime.now(UTC) + lead_time).isoformat()

    response = api_client.post(
        "/api/v1/rides",
        json=_ride_body(scheduled_for=scheduled_for),
        headers={**headers, "Idempotency-Key": _idempotency_key()},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_create_ride_with_no_scheduled_for_is_unaffected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Zero behavior change to the existing flow — same assertion
    tests/test_ride_api.py's own create-ride test already makes."""
    access_token = _login_as_new_customer(api_client, sms)
    headers = {"Authorization": f"Bearer {access_token}"}

    data = _create_ride(api_client, headers)

    assert data["status"] == "SEARCHING"


# --- Cancel: a SCHEDULED ride (BR-135) ----------------------------------


def test_cancelling_a_scheduled_ride_at_least_3_hours_before_is_free(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    headers = {"Authorization": f"Bearer {access_token}"}
    scheduled_for = (datetime.now(UTC) + timedelta(hours=4)).isoformat()
    ride = _create_ride(api_client, headers, scheduled_for=scheduled_for)

    response = api_client.post(
        f"/api/v1/rides/{ride['ride_id']}/cancel",
        json={"reason": "Change of plans"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["ride_status"] == "CANCELLED"
    assert body["charge"] == {"amount": 0, "currency": "INR"}


def test_cancelling_a_scheduled_ride_less_than_3_hours_before_charges_30(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    headers = {"Authorization": f"Bearer {access_token}"}
    scheduled_for = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    ride = _create_ride(api_client, headers, scheduled_for=scheduled_for)

    response = api_client.post(
        f"/api/v1/rides/{ride['ride_id']}/cancel",
        json={"reason": "Change of plans"},
        headers=headers,
    )

    assert response.status_code == 200
    charge = response.json()["data"]["charge"]
    assert charge["amount"] == 30
    assert charge["currency"] == "INR"
    assert "expires_at" not in charge  # BR-049 (ADR-0069): never expires
    assert charge["penalty_id"] is not None

    db = SessionLocal()
    try:
        penalty_type = db.execute(
            text("SELECT penalty_type FROM penalty.penalties WHERE id = :id"),
            {"id": charge["penalty_id"]},
        ).scalar_one()
        assert penalty_type == "SCHEDULED_RIDE_LATE_CANCELLATION"
    finally:
        db.close()


def test_cancelling_a_scheduled_ride_refunds_no_platform_fee(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Unlike a post-acceptance cancellation, a SCHEDULED ride never had
    a driver assigned, so there is no PLATFORM_FEE debit to reverse —
    confirms _scheduled_ride_cancellation_charge() never calls
    WalletService at all."""
    access_token = _login_as_new_customer(api_client, sms)
    headers = {"Authorization": f"Bearer {access_token}"}
    scheduled_for = (datetime.now(UTC) + timedelta(hours=1, minutes=10)).isoformat()
    ride = _create_ride(api_client, headers, scheduled_for=scheduled_for)

    api_client.post(
        f"/api/v1/rides/{ride['ride_id']}/cancel",
        json={"reason": "Change of plans"},
        headers=headers,
    )

    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT COUNT(*) FROM wallet.transactions WHERE ride_id = :ride_id"),
            {"ride_id": ride["ride_id"]},
        ).scalar_one()
        assert row == 0
    finally:
        db.close()


# --- List My Rides -------------------------------------------------------


def test_list_my_rides_filters_by_scheduled_status(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    headers = {"Authorization": f"Bearer {access_token}"}
    scheduled_for = (datetime.now(UTC) + timedelta(hours=3)).isoformat()
    scheduled_ride = _create_ride(api_client, headers, scheduled_for=scheduled_for)
    _create_ride(api_client, headers)  # an ordinary immediate ride

    response = api_client.get(
        "/api/v1/rides", params={"status": "SCHEDULED"}, headers=headers
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    ride_ids = {item["ride_id"] for item in items}
    assert ride_ids == {scheduled_ride["ride_id"]}
    assert items[0]["status"] == "SCHEDULED"
    assert items[0]["scheduled_for"] is not None


def test_list_my_rides_only_returns_the_caller_own_rides(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    token_a = _login_as_new_customer(api_client, sms)
    headers_a = {"Authorization": f"Bearer {token_a}"}
    ride_a = _create_ride(api_client, headers_a)

    token_b = _login_as_new_customer(api_client, sms)
    headers_b = {"Authorization": f"Bearer {token_b}"}
    ride_b = _create_ride(api_client, headers_b)

    response = api_client.get("/api/v1/rides", headers=headers_a)

    ride_ids = {item["ride_id"] for item in response.json()["data"]["items"]}
    assert ride_a["ride_id"] in ride_ids
    assert ride_b["ride_id"] not in ride_ids


def test_list_my_rides_rejects_an_unknown_status(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    headers = {"Authorization": f"Bearer {access_token}"}

    response = api_client.get(
        "/api/v1/rides", params={"status": "NOT_A_REAL_STATUS"}, headers=headers
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


# --- Book for Someone Else: linked_contact validation --------------------


def test_create_ride_with_a_linked_contact_succeeds(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    headers = {"Authorization": f"Bearer {access_token}"}

    data = _create_ride(
        api_client,
        headers,
        linked_contact={"name": "Priya Singh", "phone": "9999999999"},
    )

    assert data["status"] == "SEARCHING"
