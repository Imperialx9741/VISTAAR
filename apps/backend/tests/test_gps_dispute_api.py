"""Integration tests: real HTTP layer (TestClient) + real Postgres,
exercising the GPS Dispute Manual Review endpoints end-to-end (BR-124/
BR-125, ADR-0032):

    GET  /api/v1/rides/{ride_id}/gps-disputes/{dispute_id}
    POST /api/v1/rides/{ride_id}/gps-disputes/{dispute_id}/evidence/upload-url
    POST /api/v1/rides/{ride_id}/gps-disputes/{dispute_id}/evidence
    GET  /api/v1/admin/gps-disputes
    POST /api/v1/admin/gps-disputes/{dispute_id}/resolve

Reuses the same driver/vehicle-approval + ride-lifecycle setup helpers as
tests/test_ride_lifecycle_api.py and tests/test_early_drop_api.py
(duplicated, not imported — same per-file-duplication convention every
other test_*_api.py in this codebase already follows), extended one step
further: driving `RIDE_GPS_MAX_ATTEMPTS_BEFORE_REVIEW` (default 3)
out-of-radius attempts at either the arrived or complete endpoint to open
a dispute.

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

from core.config import settings
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

# ~1.1km from the pickup point — well outside both the arrival and
# completion GPS radii, same fixed offset test_ride_lifecycle_api.py uses.
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


def _started_ride(
    api_client: TestClient, sms: CapturingSmsProvider, admin_headers: dict
) -> tuple[str, dict, dict]:
    """Returns (ride_id, customer_headers, driver_headers), ride STARTED."""
    ride_id, customer_headers, driver_headers = _accepted_ride(
        api_client, sms, admin_headers
    )

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


def _open_arrival_dispute(
    api_client: TestClient, sms: CapturingSmsProvider, admin_headers: dict
) -> tuple[str, dict, dict, str]:
    """Drives POST .../arrived with an out-of-radius location through
    RIDE_GPS_MAX_ATTEMPTS_BEFORE_REVIEW retriable failures, then one more
    that opens a dispute. Returns (ride_id, customer_headers,
    driver_headers, dispute_id)."""
    ride_id, customer_headers, driver_headers = _accepted_ride(
        api_client, sms, admin_headers
    )

    for _ in range(settings.RIDE_GPS_MAX_ATTEMPTS_BEFORE_REVIEW):
        retriable = api_client.post(
            f"/api/v1/rides/{ride_id}/arrived",
            json={"latitude": _FAR_LAT, "longitude": _FAR_LON},
            headers=driver_headers,
        )
        assert retriable.status_code == 409
        assert retriable.json()["error"]["code"] == "NOT_WITHIN_PICKUP_RADIUS"

    terminal = api_client.post(
        f"/api/v1/rides/{ride_id}/arrived",
        json={"latitude": _FAR_LAT, "longitude": _FAR_LON},
        headers=driver_headers,
    )
    assert terminal.status_code == 409
    assert terminal.json()["error"]["code"] == "GPS_VERIFICATION_FAILED"
    dispute_id = terminal.json()["error"]["details"]["dispute_id"]
    return ride_id, customer_headers, driver_headers, dispute_id


# --- Get Dispute + Submit Evidence (customer/driver) -------------------------


def test_terminal_gps_failure_opens_a_dispute_visible_to_both_parties(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, driver_headers, dispute_id = _open_arrival_dispute(
        api_client, sms, admin_headers
    )

    for headers in (customer_headers, driver_headers):
        response = api_client.get(
            f"/api/v1/rides/{ride_id}/gps-disputes/{dispute_id}", headers=headers
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["dispute_id"] == dispute_id
        assert data["ride_id"] == ride_id
        assert data["verification_type"] == "ARRIVAL"
        assert data["status"] == "OPEN"
        assert data["evidence"] == []

    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT status, ride_id FROM ride.gps_disputes WHERE id = :id"),
            {"id": dispute_id},
        ).fetchone()
        assert row is not None
        assert row.status == "OPEN"
        assert str(row.ride_id) == ride_id

        outbox_row = db.execute(
            text(
                "SELECT payload FROM shared.outbox_events "
                "WHERE aggregate_id = :id AND event_type = 'ride.gps_dispute_opened'"
            ),
            {"id": ride_id},
        ).fetchone()
        assert outbox_row is not None
        assert outbox_row.payload["data"]["dispute_id"] == dispute_id
        assert outbox_row.payload["data"]["verification_type"] == "ARRIVAL"
    finally:
        db.close()


def test_unrelated_account_cannot_view_the_dispute(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, _customer_headers, _driver_headers, dispute_id = _open_arrival_dispute(
        api_client, sms, admin_headers
    )
    other_token = _login(api_client, sms, "CUSTOMER")
    other_headers = {"Authorization": f"Bearer {other_token}"}

    response = api_client.get(
        f"/api/v1/rides/{ride_id}/gps-disputes/{dispute_id}", headers=other_headers
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RIDE_NOT_FOUND"


# --- List GPS Disputes for a Ride (ADR-0074) ----------------------------------


def test_list_gps_disputes_returns_the_open_dispute_to_both_parties(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, driver_headers, dispute_id = _open_arrival_dispute(
        api_client, sms, admin_headers
    )

    for headers in (customer_headers, driver_headers):
        response = api_client.get(
            f"/api/v1/rides/{ride_id}/gps-disputes", headers=headers
        )
        assert response.status_code == 200
        disputes = response.json()["data"]["disputes"]
        assert len(disputes) == 1
        assert disputes[0]["dispute_id"] == dispute_id
        assert disputes[0]["ride_id"] == ride_id
        assert disputes[0]["status"] == "OPEN"


def test_list_gps_disputes_is_empty_for_a_ride_with_none(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, _driver_headers = _accepted_ride(
        api_client, sms, admin_headers
    )

    response = api_client.get(
        f"/api/v1/rides/{ride_id}/gps-disputes", headers=customer_headers
    )

    assert response.status_code == 200
    assert response.json()["data"]["disputes"] == []


def test_list_gps_disputes_for_unrelated_account_returns_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, _customer_headers, _driver_headers, _dispute_id = _open_arrival_dispute(
        api_client, sms, admin_headers
    )
    other_token = _login(api_client, sms, "CUSTOMER")
    other_headers = {"Authorization": f"Bearer {other_token}"}

    response = api_client.get(
        f"/api/v1/rides/{ride_id}/gps-disputes", headers=other_headers
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RIDE_NOT_FOUND"


def test_list_gps_disputes_unauthenticated_is_rejected(
    api_client: TestClient,
) -> None:
    response = api_client.get(
        f"/api/v1/rides/{uuid.uuid4()}/gps-disputes"
    )
    assert response.status_code == 401


def test_driver_can_request_an_evidence_upload_url(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, _customer_headers, driver_headers, dispute_id = _open_arrival_dispute(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/gps-disputes/{dispute_id}/evidence/upload-url",
        json={"content_type": "image/jpeg"},
        headers=driver_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["upload_url"].startswith("http")
    assert data["uri"]
    assert data["expires_at"]
    # Presigned POST, not PUT (owner decision, 2026-09-03) — scoped to
    # its own "gps-dispute-evidence" key namespace, distinct from the
    # driver-document upload endpoint's "driver-uploads" (see
    # shared/storage.py, modules/ride/dependencies.py).
    assert "/gps-dispute-evidence/" in data["uri"]
    assert data["upload_fields"]["key"]
    assert data["upload_fields"]["Content-Type"] == "image/jpeg"


def test_unrelated_account_cannot_request_an_evidence_upload_url(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Targeted negative-auth test (security review, 2026-09-03) — the
    upload-url endpoint's ownership check
    (RideService.get_gps_dispute(account_id=..., is_admin=False))
    already existed in code, confirmed correct during a code review, but
    had no test proving it — unlike the sibling GET-dispute and submit-
    evidence endpoints, both already covered above. Presigned upload
    URLs are the real abuse surface here (unlimited S3 PUT targets), not
    the eventual document submission, so this is the more important of
    the two to actually prove."""
    admin_headers = _login_admin(api_client, sms)
    ride_id, _customer_headers, _driver_headers, dispute_id = _open_arrival_dispute(
        api_client, sms, admin_headers
    )
    other_token = _login(api_client, sms, "CUSTOMER")
    other_headers = {"Authorization": f"Bearer {other_token}"}

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/gps-disputes/{dispute_id}/evidence/upload-url",
        json={"content_type": "image/jpeg"},
        headers=other_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RIDE_NOT_FOUND"


def test_customer_can_submit_text_evidence(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, _driver_headers, dispute_id = _open_arrival_dispute(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/gps-disputes/{dispute_id}/evidence",
        json={"evidence_type": "TEXT", "text": "I was standing at the gate."},
        headers=customer_headers,
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["evidence_type"] == "TEXT"
    assert data["text_explanation"] == "I was standing at the gate."

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT evidence_type, text_explanation FROM "
                "ride.gps_dispute_evidence WHERE dispute_id = :id"
            ),
            {"id": dispute_id},
        ).fetchone()
        assert row is not None
        assert row.evidence_type == "TEXT"
        assert row.text_explanation == "I was standing at the gate."
    finally:
        db.close()


def test_driver_can_submit_photo_evidence_via_the_uploaded_uri(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, _customer_headers, driver_headers, dispute_id = _open_arrival_dispute(
        api_client, sms, admin_headers
    )
    upload = api_client.post(
        f"/api/v1/rides/{ride_id}/gps-disputes/{dispute_id}/evidence/upload-url",
        json={"content_type": "image/jpeg"},
        headers=driver_headers,
    ).json()["data"]

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/gps-disputes/{dispute_id}/evidence",
        json={"evidence_type": "PHOTO", "uri": upload["uri"]},
        headers=driver_headers,
    )

    assert response.status_code == 201
    assert response.json()["data"]["uri"] == upload["uri"]


def test_unrelated_account_cannot_submit_evidence(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, _customer_headers, _driver_headers, dispute_id = _open_arrival_dispute(
        api_client, sms, admin_headers
    )
    other_token = _login(api_client, sms, "CUSTOMER")
    other_headers = {"Authorization": f"Bearer {other_token}"}

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/gps-disputes/{dispute_id}/evidence",
        json={"evidence_type": "TEXT", "text": "Not my ride."},
        headers=other_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RIDE_NOT_FOUND"


def test_evidence_missing_uri_for_a_photo_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, _customer_headers, driver_headers, dispute_id = _open_arrival_dispute(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/gps-disputes/{dispute_id}/evidence",
        json={"evidence_type": "PHOTO"},
        headers=driver_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


# --- Admin: Search Disputes + Resolve Dispute --------------------------------


def test_admin_can_search_open_disputes(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, _customer_headers, _driver_headers, dispute_id = _open_arrival_dispute(
        api_client, sms, admin_headers
    )

    response = api_client.get(
        "/api/v1/admin/gps-disputes", params={"status": "OPEN"}, headers=admin_headers
    )

    assert response.status_code == 200
    body = response.json()["data"]
    items = body["items"]
    assert any(item["dispute_id"] == dispute_id for item in items)
    match = next(item for item in items if item["dispute_id"] == dispute_id)
    assert match["ride_id"] == ride_id
    assert match["status"] == "OPEN"


def test_non_admin_cannot_search_disputes(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    _open_arrival_dispute(api_client, sms, admin_headers)
    customer_token = _login(api_client, sms, "CUSTOMER")
    customer_headers = {"Authorization": f"Bearer {customer_token}"}

    response = api_client.get("/api/v1/admin/gps-disputes", headers=customer_headers)

    assert response.status_code == 403


def test_admin_can_get_dispute_detail_with_evidence(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Admin Web §4.14 — the admin-facing counterpart to this file's own
    customer/driver-scoped Get Dispute endpoint (RideService.
    get_gps_dispute(), same method, is_admin=True). Includes evidence,
    unlike Search Disputes' own list rows."""
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, _driver_headers, dispute_id = _open_arrival_dispute(
        api_client, sms, admin_headers
    )
    api_client.post(
        f"/api/v1/rides/{ride_id}/gps-disputes/{dispute_id}/evidence",
        json={"evidence_type": "TEXT", "text": "I was standing at the gate."},
        headers=customer_headers,
    )

    response = api_client.get(
        f"/api/v1/admin/gps-disputes/{dispute_id}", headers=admin_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["dispute_id"] == dispute_id
    assert data["ride_id"] == ride_id
    assert data["status"] == "OPEN"
    assert len(data["evidence"]) == 1
    assert data["evidence"][0]["evidence_type"] == "TEXT"
    assert data["evidence"][0]["text_explanation"] == "I was standing at the gate."


def test_get_dispute_requires_admin(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    _ride_id, customer_headers, _driver_headers, dispute_id = _open_arrival_dispute(
        api_client, sms, admin_headers
    )

    response = api_client.get(
        f"/api/v1/admin/gps-disputes/{dispute_id}", headers=customer_headers
    )

    assert response.status_code == 403


def test_get_unknown_dispute_returns_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)

    response = api_client.get(
        f"/api/v1/admin/gps-disputes/{uuid.uuid4()}", headers=admin_headers
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RIDE_NOT_FOUND"


def test_admin_approve_transitions_the_blocked_arrival(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, driver_headers, dispute_id = _open_arrival_dispute(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/admin/gps-disputes/{dispute_id}/resolve",
        json={
            "action": "APPROVE",
            "reason": "Photo evidence confirms the driver was at the pickup point.",
        },
        headers=admin_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "RESOLVED"
    assert data["decision"] == "APPROVE"
    assert data["ride_status"] == "ARRIVED"

    db = SessionLocal()
    try:
        ride_row = db.execute(
            text("SELECT status FROM ride.rides WHERE id = :id"), {"id": ride_id}
        ).fetchone()
        assert ride_row is not None
        assert ride_row.status == "ARRIVED"

        audit_row = db.execute(
            text(
                "SELECT action, target_type FROM admin.audit_logs WHERE target_id = :id"
            ),
            {"id": dispute_id},
        ).fetchone()
        assert audit_row is not None
        assert audit_row.action == "RESOLVE_GPS_DISPUTE"
        assert audit_row.target_type == "GPS_DISPUTE"

        outbox_row = db.execute(
            text(
                "SELECT payload FROM shared.outbox_events "
                "WHERE aggregate_id = :id AND event_type = 'ride.gps_dispute_resolved'"
            ),
            {"id": ride_id},
        ).fetchone()
        assert outbox_row is not None
        assert outbox_row.payload["data"]["decision"] == "APPROVE"
    finally:
        db.close()

    # The now-ARRIVED ride can proceed normally — an OTP was auto-issued
    # by the same finalization mark_arrived() itself would have used.
    otp_response = api_client.post(
        f"/api/v1/rides/{ride_id}/otp/refresh", headers=customer_headers
    )
    assert otp_response.status_code == 200
    start_response = api_client.post(
        f"/api/v1/rides/{ride_id}/start",
        json={"otp": otp_response.json()["data"]["otp"]},
        headers=driver_headers,
    )
    assert start_response.status_code == 200


def test_admin_reject_leaves_the_ride_blocked(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, _customer_headers, _driver_headers, dispute_id = _open_arrival_dispute(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/admin/gps-disputes/{dispute_id}/resolve",
        json={
            "action": "REJECT",
            "reason": "No evidence was submitted supporting the driver's location.",
        },
        headers=admin_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "RESOLVED"
    assert data["decision"] == "REJECT"
    assert data["ride_status"] is None

    db = SessionLocal()
    try:
        ride_row = db.execute(
            text("SELECT status FROM ride.rides WHERE id = :id"), {"id": ride_id}
        ).fetchone()
        assert ride_row is not None
        assert ride_row.status == "ACCEPTED"
    finally:
        db.close()


def test_resolving_an_already_resolved_dispute_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    _ride_id, _customer_headers, _driver_headers, dispute_id = _open_arrival_dispute(
        api_client, sms, admin_headers
    )
    api_client.post(
        f"/api/v1/admin/gps-disputes/{dispute_id}/resolve",
        json={"action": "REJECT", "reason": "First decision."},
        headers=admin_headers,
    )

    second = api_client.post(
        f"/api/v1/admin/gps-disputes/{dispute_id}/resolve",
        json={"action": "APPROVE", "reason": "Second decision, should be rejected."},
        headers=admin_headers,
    )

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_resolve_dispute_requires_a_reason(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    _ride_id, _customer_headers, _driver_headers, dispute_id = _open_arrival_dispute(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/admin/gps-disputes/{dispute_id}/resolve",
        json={"action": "REJECT"},
        headers=admin_headers,
    )

    assert response.status_code == 422
