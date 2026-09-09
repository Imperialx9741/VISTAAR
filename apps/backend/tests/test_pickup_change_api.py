"""Integration tests: real HTTP layer (TestClient) + real Postgres,
exercising the Ride Modifications — Pickup Change endpoint end-to-end.

Originally ADR-0033 (driver PROCEED/PASS beyond a 250m threshold);
simplified by ADR-0056 (2026-08-31, owner decision) to a flat 100m
hard threshold with no driver decision and no charge:

    POST /api/v1/rides/{ride_id}/pickup-change

`.../pickup-change/driver-decision` and `.../pickup-change/confirm`
(ADR-0033) were removed by that same decision — a couple of tests below
confirm they're genuinely gone (404), not just behaving differently.

Reuses the same driver/vehicle-approval + ride-lifecycle setup helpers as
tests/test_gps_dispute_api.py (duplicated, not imported — same per-file-
duplication convention every other test_*_api.py in this codebase already
follows), stopped one step earlier at ACCEPTED (pickup change only makes
sense before the driver has arrived).

Skips (not fails) when Postgres is genuinely unreachable.
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


@pytest.fixture(autouse=True)
def _clean_integration_tables() -> None:
    """Same essential (not merely tidy) cleanup as
    tests/test_ride_lifecycle_api.py's identical fixture — see that
    file's own docstring for the full Redis-pollution reasoning."""
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
def api_client(sms: CapturingSmsProvider) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_sms_provider_dependency] = lambda: sms
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_sms_provider_dependency, None)


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
    latitude: float = 25.5941,
    longitude: float = 85.1376,
) -> tuple[dict, str, str]:
    """Returns (driver_headers, driver_id, vehicle_id)."""
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
    _seed_wallet_balance(driver_id, Decimal("100.00"))
    online = api_client.post("/api/v1/drivers/me/online", headers=driver_headers)
    assert online.status_code == 200
    api_client.post(
        "/api/v1/drivers/me/location",
        json={"latitude": latitude, "longitude": longitude},
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

# ~50m from the pickup point — within the 100m threshold (ADR-0056).
_NEAR_LAT, _NEAR_LON = 25.5945, 85.1376
# ~1.1km from the pickup point — well beyond the 100m threshold.
_FAR_LAT, _FAR_LON = 25.6041, 85.1376


def _create_ride(api_client: TestClient, customer_headers: dict) -> str:
    response = api_client.post(
        "/api/v1/rides",
        json=VALID_RIDE_BODY,
        headers={**customer_headers, "Idempotency-Key": f"ride-{uuid.uuid4()}"},
    )
    assert response.status_code == 201
    ride_id: str = response.json()["data"]["ride_id"]
    return ride_id


def _accept_first_offer(api_client: TestClient, driver_headers: dict) -> None:
    offers = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=driver_headers
    ).json()["data"]["offers"]
    assert len(offers) == 1
    response = api_client.post(
        f"/api/v1/drivers/me/ride-offers/{offers[0]['offer_id']}/accept",
        headers={**driver_headers, "Idempotency-Key": f"accept-{uuid.uuid4()}"},
    )
    assert response.status_code == 200


def _accepted_ride(
    api_client: TestClient, sms: CapturingSmsProvider, admin_headers: dict
) -> tuple[str, dict, dict]:
    """Returns (ride_id, customer_headers, driver_headers), ride ACCEPTED."""
    driver_headers, _driver_id, _vehicle_id = _new_online_eligible_driver(
        api_client, sms, admin_headers
    )
    customer_token = _login(api_client, sms, "CUSTOMER")
    customer_headers = {"Authorization": f"Bearer {customer_token}"}
    ride_id = _create_ride(api_client, customer_headers)
    _accept_first_offer(api_client, driver_headers)
    return ride_id, customer_headers, driver_headers


# --- ≤100m: applied immediately -----------------------------------------


def test_a_near_pickup_change_is_applied_immediately(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, _driver_headers = _accepted_ride(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/pickup-change",
        json={"latitude": _NEAR_LAT, "longitude": _NEAR_LON},
        headers=customer_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["applied"] is True
    assert data["distance_meters"] < 100

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT ST_Y(current_pickup) AS lat, ST_X(current_pickup) AS lng "
                "FROM ride.rides WHERE id = :id"
            ),
            {"id": ride_id},
        ).fetchone()
        assert row is not None
        assert row.lat == pytest.approx(_NEAR_LAT, abs=1e-4)
        assert row.lng == pytest.approx(_NEAR_LON, abs=1e-4)

        count = db.execute(
            text(
                "SELECT COUNT(*) FROM ride.change_requests WHERE ride_id = :id "
                "AND request_type = 'PICKUP_CHANGE'"
            ),
            {"id": ride_id},
        ).scalar()
        assert count == 0
    finally:
        db.close()


# --- >100m: rejected outright (ADR-0056, 2026-08-31) ----------------------


def test_far_pickup_change_is_rejected_outright(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Replaces the old driver-PROCEED/PASS tests (ADR-0033) — ADR-0056
    removed that whole flow. A change beyond the threshold is now a
    plain rejection: no driver decision, no charge, and the ride is left
    completely unchanged."""
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, driver_headers = _accepted_ride(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/pickup-change",
        json={"latitude": _FAR_LAT, "longitude": _FAR_LON},
        headers=customer_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PICKUP_CHANGE_TOO_FAR"

    db = SessionLocal()
    try:
        ride_row = db.execute(
            text(
                "SELECT status, driver_id, vehicle_id, "
                "ST_Y(current_pickup) AS lat, ST_X(current_pickup) AS lng "
                "FROM ride.rides WHERE id = :id"
            ),
            {"id": ride_id},
        ).fetchone()
        assert ride_row is not None
        assert ride_row.status == "ACCEPTED"
        assert ride_row.driver_id is not None
        assert ride_row.vehicle_id is not None
        # Original pickup unchanged.
        assert ride_row.lat == pytest.approx(25.5941, abs=1e-4)
        assert ride_row.lng == pytest.approx(85.1376, abs=1e-4)

        count = db.execute(
            text(
                "SELECT COUNT(*) FROM ride.change_requests WHERE ride_id = :id "
                "AND request_type = 'PICKUP_CHANGE'"
            ),
            {"id": ride_id},
        ).scalar()
        assert count == 0

        # No rematch, no new offer for anyone.
        offers = api_client.get(
            "/api/v1/drivers/me/ride-offers", headers=driver_headers
        ).json()["data"]["offers"]
        assert offers == []
    finally:
        db.close()

    # The customer's only path forward is to cancel and rebook — a fresh
    # pickup-change request on the same (still-ACCEPTED) ride is still
    # possible, and still rejected the same way.
    again = api_client.post(
        f"/api/v1/rides/{ride_id}/pickup-change",
        json={"latitude": _FAR_LAT, "longitude": _FAR_LON},
        headers=customer_headers,
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "PICKUP_CHANGE_TOO_FAR"


# --- Ownership / validation -----------------------------------------------


def test_driver_cannot_request_a_pickup_change(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, _customer_headers, driver_headers = _accepted_ride(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/pickup-change",
        json={"latitude": _NEAR_LAT, "longitude": _NEAR_LON},
        headers=driver_headers,
    )

    assert response.status_code == 403


# --- Removed endpoints (ADR-0056) ------------------------------------------


def test_driver_decision_endpoint_no_longer_exists(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, _customer_headers, driver_headers = _accepted_ride(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/pickup-change/driver-decision",
        json={"decision": "PROCEED"},
        headers=driver_headers,
    )

    assert response.status_code == 404


def test_pickup_change_confirm_endpoint_no_longer_exists(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, _driver_headers = _accepted_ride(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/pickup-change/confirm",
        json={"confirmed": True},
        headers=customer_headers,
    )

    assert response.status_code == 404
