"""Integration tests: real HTTP layer (TestClient) + real Postgres,
exercising GET /api/v1/rides/{ride_id} end-to-end (Phase 04, ADR-0024).

Skips (not fails) when Postgres is genuinely unreachable.
"""

from __future__ import annotations

import asyncio
import secrets
import uuid
from collections.abc import Generator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from core.database import SessionLocal
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
def _clean_matching_geo_index_fixture() -> None:
    """Test-isolation correction (same pattern as
    tests/test_ride_lifecycle_api.py/test_early_drop_api.py — see
    test_ride_lifecycle_api.py's own docstring for the full reasoning,
    including why this stays necessary even though go_offline now
    cleans up its own caller's Redis entry, 2026-08-28): this file's one
    dispatch-dependent test
    (test_customer_and_driver_see_driver_and_vehicle_after_acceptance)
    asserts the ride's one offer went to the specific driver THIS test
    just created. None of this file's tests ever call POST .../me/
    offline, so drivers from earlier runs (here and elsewhere) stay
    ONLINE in Redis indefinitely — across a full-suite run, enough
    accumulate to occasionally push that test's own driver out of
    dispatch_offer()'s candidate_limit-bounded GEOSEARCH results,
    confirmed by direct reproduction independent of any of this file's
    own code."""
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
    api_client: TestClient, sms: CapturingSmsProvider, admin_headers: dict
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


# --- Get Ride ---------------------------------------------------------------


def test_customer_can_view_their_own_searching_ride(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "CUSTOMER")
    customer_headers = {"Authorization": f"Bearer {access_token}"}
    ride_id = _create_ride(api_client, customer_headers)

    response = api_client.get(f"/api/v1/rides/{ride_id}", headers=customer_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["ride_id"] == ride_id
    assert data["status"] == "SEARCHING"
    assert data["driver"] is None
    assert data["vehicle"] is None
    assert data["payment"] is None
    assert data["fare"]["total"] == 89.25  # matches test_ride_api.py's own math
    assert data["pickup"]["latitude"] == pytest.approx(25.5941)


def test_customer_and_driver_see_driver_and_vehicle_after_acceptance(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    driver_headers, driver_id, vehicle_id = _new_online_eligible_driver(
        api_client, sms, admin_headers
    )
    access_token = _login(api_client, sms, "CUSTOMER")
    customer_headers = {"Authorization": f"Bearer {access_token}"}
    ride_id = _create_ride(api_client, customer_headers)
    _accept_first_offer(api_client, driver_headers)

    customer_view = api_client.get(f"/api/v1/rides/{ride_id}", headers=customer_headers)
    driver_view = api_client.get(f"/api/v1/rides/{ride_id}", headers=driver_headers)

    for response in (customer_view, driver_view):
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "ACCEPTED"
        assert data["driver"]["driver_id"] == driver_id
        assert data["driver"]["full_name"] == "Ravi Kumar"
        assert "phone" not in data["driver"]  # ADR-0024 Decision 1
        assert data["vehicle"]["vehicle_id"] == vehicle_id
        assert data["vehicle"]["category"] == "CAB"


def test_other_customer_cannot_view_a_ride_they_do_not_own(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "CUSTOMER")
    owner_headers = {"Authorization": f"Bearer {access_token}"}
    ride_id = _create_ride(api_client, owner_headers)

    other_token = _login(api_client, sms, "CUSTOMER")
    other_headers = {"Authorization": f"Bearer {other_token}"}
    response = api_client.get(f"/api/v1/rides/{ride_id}", headers=other_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RIDE_NOT_FOUND"


def test_unassigned_driver_cannot_view_a_searching_ride(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "CUSTOMER")
    customer_headers = {"Authorization": f"Bearer {access_token}"}
    ride_id = _create_ride(api_client, customer_headers)

    driver_headers = _new_driver_with_profile(api_client, sms)
    response = api_client.get(f"/api/v1/rides/{ride_id}", headers=driver_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RIDE_NOT_FOUND"


def test_get_unknown_ride_returns_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "CUSTOMER")
    headers = {"Authorization": f"Bearer {access_token}"}
    response = api_client.get(f"/api/v1/rides/{uuid.uuid4()}", headers=headers)
    assert response.status_code == 404


def test_unauthenticated_get_ride_is_rejected(api_client: TestClient) -> None:
    response = api_client.get(f"/api/v1/rides/{uuid.uuid4()}")
    assert response.status_code == 401


def test_admin_account_cannot_use_this_endpoint(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """require_customer_or_driver rejects ADMIN — the admin-facing ride
    view is the separate GET /api/v1/admin/rides/{ride_id} (ADR-0023)."""
    admin_headers = _login_admin(api_client, sms)
    response = api_client.get(f"/api/v1/rides/{uuid.uuid4()}", headers=admin_headers)
    assert response.status_code == 403
