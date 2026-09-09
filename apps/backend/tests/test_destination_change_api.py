"""Integration tests: real HTTP layer (TestClient) + real Postgres,
exercising the Ride Modifications — Destination Change endpoints
end-to-end (ADR-0033 Decision 9):

    POST /api/v1/rides/{ride_id}/destination-change
    POST /api/v1/rides/{ride_id}/destination-change/confirm

Reuses the same driver/vehicle-approval + ride-lifecycle setup helpers as
tests/test_pickup_change_api.py (duplicated, not imported — same
per-file-duplication convention every other test_*_api.py in this
codebase already follows), extended one step further to STARTED
(destination change only makes sense mid-ride, after pickup — unlike
pickup change, which only makes sense before arrival).

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

# Verified classifications against this exact pickup/destination pair
# (see the unit tests in test_pricing_service.py for the pure-function
# equivalents; these were also verified directly before writing this
# file).
_WITHIN_ROUTE_LAT, _WITHIN_ROUTE_LON = 25.60305, 85.1478
_BEYOND_ORIGINAL_LAT, _BEYOND_ORIGINAL_LON = 25.6299, 85.1784
_DIFFERENT_ROUTE_LAT, _DIFFERENT_ROUTE_LON = 25.55, 85.25


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


def _started_ride(
    api_client: TestClient, sms: CapturingSmsProvider, admin_headers: dict
) -> tuple[str, dict, dict]:
    """Returns (ride_id, customer_headers, driver_headers), ride STARTED."""
    driver_headers, _driver_id, _vehicle_id = _new_online_eligible_driver(
        api_client, sms, admin_headers
    )
    customer_token = _login(api_client, sms, "CUSTOMER")
    customer_headers = {"Authorization": f"Bearer {customer_token}"}
    ride_id = _create_ride(api_client, customer_headers)
    _accept_first_offer(api_client, driver_headers)

    arrived = api_client.post(
        f"/api/v1/rides/{ride_id}/arrived",
        json={"latitude": 25.5941, "longitude": 85.1376},
        headers=driver_headers,
    )
    assert arrived.status_code == 200
    otp = api_client.post(
        f"/api/v1/rides/{ride_id}/otp/refresh", headers=customer_headers
    ).json()["data"]["otp"]
    started = api_client.post(
        f"/api/v1/rides/{ride_id}/start", json={"otp": otp}, headers=driver_headers
    )
    assert started.status_code == 200
    return ride_id, customer_headers, driver_headers


# --- WITHIN_ROUTE: applied immediately --------------------------------------


def test_within_route_destination_change_is_applied_immediately(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, _driver_headers = _started_ride(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/destination-change",
        json={"latitude": _WITHIN_ROUTE_LAT, "longitude": _WITHIN_ROUTE_LON},
        headers=customer_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["applied"] is True
    assert data["case"] == "WITHIN_ROUTE"

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT ST_Y(current_destination) AS lat, "
                "ST_X(current_destination) AS lng, active_fare_quote_id "
                "FROM ride.rides WHERE id = :id"
            ),
            {"id": ride_id},
        ).fetchone()
        assert row is not None
        assert row.lat == pytest.approx(_WITHIN_ROUTE_LAT, abs=1e-4)
        assert row.lng == pytest.approx(_WITHIN_ROUTE_LON, abs=1e-4)

        quote_row = db.execute(
            text("SELECT version FROM pricing.fare_quotes WHERE id = :id"),
            {"id": str(row.active_fare_quote_id)},
        ).fetchone()
        assert quote_row is not None
        assert quote_row.version == 1  # unchanged, no new quote created

        count = db.execute(
            text(
                "SELECT COUNT(*) FROM ride.change_requests WHERE ride_id = :id "
                "AND request_type = 'DESTINATION_CHANGE'"
            ),
            {"id": ride_id},
        ).scalar()
        assert count == 0
    finally:
        db.close()


# --- BEYOND_ORIGINAL: pending confirmation ----------------------------------


def test_beyond_original_destination_change_requires_confirmation(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, _driver_headers = _started_ride(
        api_client, sms, admin_headers
    )

    requested = api_client.post(
        f"/api/v1/rides/{ride_id}/destination-change",
        json={"latitude": _BEYOND_ORIGINAL_LAT, "longitude": _BEYOND_ORIGINAL_LON},
        headers=customer_headers,
    )
    assert requested.status_code == 201
    requested_data = requested.json()["data"]
    assert requested_data["applied"] is False
    assert requested_data["case"] == "BEYOND_ORIGINAL"
    change_request_id = requested_data["change_request_id"]

    confirm = api_client.post(
        f"/api/v1/rides/{ride_id}/destination-change/confirm",
        json={"change_request_id": change_request_id, "confirmed": True},
        headers=customer_headers,
    )

    assert confirm.status_code == 200
    confirm_data = confirm.json()["data"]
    assert confirm_data["status"] == "CONFIRMED"
    assert confirm_data["fare"]["additional_charge"] > 0
    assert confirm_data["fare"]["new_total"] == pytest.approx(
        confirm_data["fare"]["previous_total"]
        + confirm_data["fare"]["additional_charge"]
    )
    assert confirm_data["fare"]["currency"] == "INR"

    db = SessionLocal()
    try:
        ride_row = db.execute(
            text(
                "SELECT ST_Y(current_destination) AS lat, "
                "ST_X(current_destination) AS lng, active_fare_quote_id "
                "FROM ride.rides WHERE id = :id"
            ),
            {"id": ride_id},
        ).fetchone()
        assert ride_row is not None
        assert ride_row.lat == pytest.approx(_BEYOND_ORIGINAL_LAT, abs=1e-4)
        assert ride_row.lng == pytest.approx(_BEYOND_ORIGINAL_LON, abs=1e-4)

        quote_row = db.execute(
            text(
                "SELECT version, reason, additional_charge FROM "
                "pricing.fare_quotes WHERE id = :id"
            ),
            {"id": str(ride_row.active_fare_quote_id)},
        ).fetchone()
        assert quote_row is not None
        assert quote_row.version == 2
        assert quote_row.reason == "DESTINATION_CHANGE"
        assert quote_row.additional_charge > 0

        outbox_row = db.execute(
            text(
                "SELECT payload FROM shared.outbox_events "
                "WHERE aggregate_id = :id AND event_type = 'ride.destination_changed'"
            ),
            {"id": ride_id},
        ).fetchone()
        assert outbox_row is not None
        assert outbox_row.payload["data"]["customer_confirmed"] is True
    finally:
        db.close()


def test_customer_can_reject_a_beyond_original_change(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, _driver_headers = _started_ride(
        api_client, sms, admin_headers
    )
    requested = api_client.post(
        f"/api/v1/rides/{ride_id}/destination-change",
        json={"latitude": _BEYOND_ORIGINAL_LAT, "longitude": _BEYOND_ORIGINAL_LON},
        headers=customer_headers,
    )
    change_request_id = requested.json()["data"]["change_request_id"]

    reject = api_client.post(
        f"/api/v1/rides/{ride_id}/destination-change/confirm",
        json={"change_request_id": change_request_id, "confirmed": False},
        headers=customer_headers,
    )

    assert reject.status_code == 200
    assert reject.json()["data"]["status"] == "REJECTED"
    assert "fare" not in reject.json()["data"]

    db = SessionLocal()
    try:
        ride_row = db.execute(
            text(
                "SELECT ST_Y(current_destination) AS lat, active_fare_quote_id "
                "FROM ride.rides WHERE id = :id"
            ),
            {"id": ride_id},
        ).fetchone()
        assert ride_row is not None
        # Original destination unchanged.
        assert ride_row.lat == pytest.approx(25.6120, abs=1e-4)
        quote_row = db.execute(
            text("SELECT version FROM pricing.fare_quotes WHERE id = :id"),
            {"id": str(ride_row.active_fare_quote_id)},
        ).fetchone()
        assert quote_row is not None
        assert quote_row.version == 1
    finally:
        db.close()


# --- DIFFERENT_ROUTE: full recalculation ------------------------------------


def test_different_route_destination_change_recalculates_fare(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, _driver_headers = _started_ride(
        api_client, sms, admin_headers
    )

    requested = api_client.post(
        f"/api/v1/rides/{ride_id}/destination-change",
        json={"latitude": _DIFFERENT_ROUTE_LAT, "longitude": _DIFFERENT_ROUTE_LON},
        headers=customer_headers,
    )
    assert requested.status_code == 201
    assert requested.json()["data"]["case"] == "DIFFERENT_ROUTE"
    change_request_id = requested.json()["data"]["change_request_id"]

    confirm = api_client.post(
        f"/api/v1/rides/{ride_id}/destination-change/confirm",
        json={"change_request_id": change_request_id, "confirmed": True},
        headers=customer_headers,
    )

    assert confirm.status_code == 200
    fare = confirm.json()["data"]["fare"]
    assert fare["new_total"] > 0

    db = SessionLocal()
    try:
        ride_row = db.execute(
            text(
                "SELECT ST_Y(current_destination) AS lat, "
                "ST_X(current_destination) AS lng, active_fare_quote_id "
                "FROM ride.rides WHERE id = :id"
            ),
            {"id": ride_id},
        ).fetchone()
        assert ride_row is not None
        assert ride_row.lat == pytest.approx(_DIFFERENT_ROUTE_LAT, abs=1e-4)
        assert ride_row.lng == pytest.approx(_DIFFERENT_ROUTE_LON, abs=1e-4)

        quote_row = db.execute(
            text(
                "SELECT additional_charge, distance_charge FROM "
                "pricing.fare_quotes WHERE id = :id"
            ),
            {"id": str(ride_row.active_fare_quote_id)},
        ).fetchone()
        assert quote_row is not None
        # A full recalculation, not a flat surcharge.
        assert quote_row.additional_charge == 0
        assert quote_row.distance_charge > 0
    finally:
        db.close()


# --- Ownership / validation --------------------------------------------------


def test_driver_cannot_request_a_destination_change(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, _customer_headers, driver_headers = _started_ride(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/destination-change",
        json={"latitude": _WITHIN_ROUTE_LAT, "longitude": _WITHIN_ROUTE_LON},
        headers=driver_headers,
    )

    assert response.status_code == 403


def test_unrelated_customer_cannot_request_a_destination_change(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """IDOR-safe: a customer who is not this ride's own customer gets
    the same RIDE_NOT_FOUND a genuinely missing ride would — same
    "not found either way" treatment every other module's ownership
    check already uses (see modules/ride/service.py's
    get_ride_for_destination_change())."""
    admin_headers = _login_admin(api_client, sms)
    ride_id, _customer_headers, _driver_headers = _started_ride(
        api_client, sms, admin_headers
    )
    other_customer_token = _login(api_client, sms, "CUSTOMER")
    other_customer_headers = {"Authorization": f"Bearer {other_customer_token}"}

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/destination-change",
        json={"latitude": _WITHIN_ROUTE_LAT, "longitude": _WITHIN_ROUTE_LON},
        headers=other_customer_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RIDE_NOT_FOUND"


def test_unrelated_customer_cannot_confirm_a_destination_change(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Same IDOR-safe treatment as the request-side test above, for
    confirm_destination_change()'s own ownership check."""
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, _driver_headers = _started_ride(
        api_client, sms, admin_headers
    )
    requested = api_client.post(
        f"/api/v1/rides/{ride_id}/destination-change",
        json={"latitude": _BEYOND_ORIGINAL_LAT, "longitude": _BEYOND_ORIGINAL_LON},
        headers=customer_headers,
    )
    change_request_id = requested.json()["data"]["change_request_id"]
    other_customer_token = _login(api_client, sms, "CUSTOMER")
    other_customer_headers = {"Authorization": f"Bearer {other_customer_token}"}

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/destination-change/confirm",
        json={"change_request_id": change_request_id, "confirmed": True},
        headers=other_customer_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RIDE_NOT_FOUND"


def test_second_destination_change_request_while_pending_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, _driver_headers = _started_ride(
        api_client, sms, admin_headers
    )
    api_client.post(
        f"/api/v1/rides/{ride_id}/destination-change",
        json={"latitude": _BEYOND_ORIGINAL_LAT, "longitude": _BEYOND_ORIGINAL_LON},
        headers=customer_headers,
    )

    second = api_client.post(
        f"/api/v1/rides/{ride_id}/destination-change",
        json={"latitude": _BEYOND_ORIGINAL_LAT, "longitude": _BEYOND_ORIGINAL_LON},
        headers=customer_headers,
    )

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_destination_change_before_started_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    driver_headers, _did, _vid = _new_online_eligible_driver(
        api_client, sms, admin_headers
    )
    customer_token = _login(api_client, sms, "CUSTOMER")
    customer_headers = {"Authorization": f"Bearer {customer_token}"}
    ride_id = _create_ride(api_client, customer_headers)
    _accept_first_offer(api_client, driver_headers)  # still only ACCEPTED

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/destination-change",
        json={"latitude": _WITHIN_ROUTE_LAT, "longitude": _WITHIN_ROUTE_LON},
        headers=customer_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_mismatched_change_request_id_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, _driver_headers = _started_ride(
        api_client, sms, admin_headers
    )
    api_client.post(
        f"/api/v1/rides/{ride_id}/destination-change",
        json={"latitude": _BEYOND_ORIGINAL_LAT, "longitude": _BEYOND_ORIGINAL_LON},
        headers=customer_headers,
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/destination-change/confirm",
        json={"change_request_id": str(uuid.uuid4()), "confirmed": True},
        headers=customer_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_confirm_with_no_pending_request_is_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, _driver_headers = _started_ride(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/destination-change/confirm",
        json={"change_request_id": str(uuid.uuid4()), "confirmed": True},
        headers=customer_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RIDE_NOT_FOUND"
