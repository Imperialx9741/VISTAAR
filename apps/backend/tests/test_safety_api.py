"""Integration tests: real HTTP layer (TestClient) + real Postgres,
exercising POST /api/v1/rides/{ride_id}/sos end-to-end (api-contracts.md
§41), plus real-Postgres/real-concurrency tests for
SafetyService.acknowledge_incident()/escalate_incident()/
resolve_incident() — none of which has an HTTP endpoint yet (ADR-0022
Decision 6), so those are called directly against the service, each
concurrent call from its own real thread with its own independent DB
session, matching tests/test_wallet_api.py's established technique.

Setup helpers (login, driver eligibility, matching) are copied from
tests/test_matching_api.py — same "no shared test-helper module"
convention already used across this codebase's integration tests.

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
from modules.admin.models import AdminUserORM
from modules.identity.dependencies import get_sms_provider_dependency
from modules.identity.security import decode_access_token
from modules.safety.domain.errors import IncidentNotAcknowledgeableError
from modules.safety.repositories import (
    SqlAlchemySafetyEventRepository,
    SqlAlchemySafetyIncidentRepository,
)
from modules.safety.service import SafetyService
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


def _random_point() -> tuple[float, float]:
    lat = 20.0 + secrets.randbelow(1000) / 100.0
    lng = 75.0 + secrets.randbelow(1000) / 100.0
    return lat, lng


def _nearby(point: tuple[float, float], *, offset: float = 0.001) -> dict[str, float]:
    return {"latitude": point[0] + offset, "longitude": point[1] + offset}


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


def _login_as_new_customer(
    api_client: TestClient, sms: CapturingSmsProvider
) -> dict[str, str]:
    access_token = _login(api_client, sms, "CUSTOMER")
    return {"Authorization": f"Bearer {access_token}"}


def _provision_admin(account_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        db.add(AdminUserORM(id=account_id, role="SUPER_ADMIN", status="ACTIVE"))
        db.commit()
    finally:
        db.close()


def _login_admin(api_client: TestClient, sms: CapturingSmsProvider) -> dict[str, str]:
    access_token = _login(api_client, sms, "ADMIN")
    _provision_admin(_account_id_from_token(access_token))
    return {"Authorization": f"Bearer {access_token}"}


def _new_driver_with_profile(
    api_client: TestClient, sms: CapturingSmsProvider
) -> dict[str, str]:
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


def _new_online_eligible_driver(
    api_client: TestClient,
    sms: CapturingSmsProvider,
    admin_headers: dict,
    *,
    location: dict[str, float],
) -> dict[str, str]:
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
    _make_vehicle_documents_valid(vehicle["vehicle_id"])
    _approve_vehicle(api_client, admin_headers, vehicle["vehicle_id"])
    api_client.post(
        f"/api/v1/drivers/me/vehicles/{vehicle['vehicle_id']}/activate",
        headers=driver_headers,
    )
    online = api_client.post("/api/v1/drivers/me/online", headers=driver_headers)
    assert online.status_code == 200
    api_client.post(
        "/api/v1/drivers/me/location", json=location, headers=driver_headers
    )
    return driver_headers


def _create_ride(
    api_client: TestClient,
    customer_headers: dict,
    *,
    pickup: dict[str, float],
    destination: dict[str, float],
) -> str:
    response = api_client.post(
        "/api/v1/rides",
        json={
            "pickup": pickup,
            "destination": destination,
            "vehicle_category": "CAB",
            "cab_tier": "ECO",
            "payment_method": "ONLINE",
        },
        headers={**customer_headers, "Idempotency-Key": f"ride-{uuid.uuid4()}"},
    )
    assert response.status_code == 201
    ride_id: str = response.json()["data"]["ride_id"]
    return ride_id


def _seed_wallet_balance(driver_id: str, amount: Decimal) -> None:
    """Same pattern tests/test_wallet_api.py established — no recharge
    endpoint exists (ADR-0013), so tests seed a balance directly via SQL."""
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


# --- Trigger SOS -----------------------------------------------------------


def test_trigger_sos_succeeds_for_the_riding_customer(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    customer_headers = _login_as_new_customer(api_client, sms)
    point = _random_point()
    ride_id = _create_ride(
        api_client,
        customer_headers,
        pickup=_nearby(point),
        destination=_nearby(point, offset=0.02),
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/sos",
        json={
            "incident_type": "EMERGENCY",
            "latitude": point[0],
            "longitude": point[1],
        },
        headers=customer_headers,
    )

    assert response.status_code == 201
    body = response.json()["data"]
    assert body["status"] == "OPEN"
    uuid.UUID(body["incident_id"])


def test_trigger_sos_succeeds_for_the_assigned_driver(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """BR-112: "Both customers and drivers must have access to SOS
    functionality." """
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    driver_headers = _new_online_eligible_driver(
        api_client, sms, admin_headers, location=_nearby(point)
    )
    driver_id = api_client.get("/api/v1/drivers/me", headers=driver_headers).json()[
        "data"
    ]["driver_id"]
    _seed_wallet_balance(driver_id, Decimal("100.00"))  # CAB fee = ₹10
    customer_headers = _login_as_new_customer(api_client, sms)
    ride_id = _create_ride(
        api_client,
        customer_headers,
        pickup=_nearby(point),
        destination=_nearby(point, offset=0.02),
    )
    _accept_first_offer(api_client, driver_headers)

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/sos",
        json={
            "incident_type": "EMERGENCY",
            "latitude": point[0],
            "longitude": point[1],
        },
        headers=driver_headers,
    )

    assert response.status_code == 201
    assert response.json()["data"]["status"] == "OPEN"


def test_trigger_sos_rejects_a_non_participant(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    customer_headers = _login_as_new_customer(api_client, sms)
    point = _random_point()
    ride_id = _create_ride(
        api_client,
        customer_headers,
        pickup=_nearby(point),
        destination=_nearby(point, offset=0.02),
    )
    other_customer_headers = _login_as_new_customer(api_client, sms)

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/sos",
        json={
            "incident_type": "EMERGENCY",
            "latitude": point[0],
            "longitude": point[1],
        },
        headers=other_customer_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RIDE_NOT_FOUND"


def test_trigger_sos_unauthenticated_is_rejected(api_client: TestClient) -> None:
    response = api_client.post(
        f"/api/v1/rides/{uuid.uuid4()}/sos",
        json={"incident_type": "EMERGENCY", "latitude": 25.0, "longitude": 85.0},
    )
    assert response.status_code == 401


def test_trigger_sos_rejects_invalid_coordinates(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    customer_headers = _login_as_new_customer(api_client, sms)
    point = _random_point()
    ride_id = _create_ride(
        api_client,
        customer_headers,
        pickup=_nearby(point),
        destination=_nearby(point, offset=0.02),
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/sos",
        json={"incident_type": "EMERGENCY", "latitude": 999.0, "longitude": 85.0},
        headers=customer_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_trigger_sos_writes_an_sos_triggered_outbox_event(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    customer_headers = _login_as_new_customer(api_client, sms)
    point = _random_point()
    ride_id = _create_ride(
        api_client,
        customer_headers,
        pickup=_nearby(point),
        destination=_nearby(point, offset=0.02),
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/sos",
        json={
            "incident_type": "EMERGENCY",
            "latitude": point[0],
            "longitude": point[1],
        },
        headers=customer_headers,
    )
    incident_id = response.json()["data"]["incident_id"]

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT payload FROM shared.outbox_events "
                "WHERE aggregate_id = :id AND event_type = 'safety.sos_triggered'"
            ),
            {"id": incident_id},
        ).fetchone()
        assert row is not None
        assert row.payload["data"]["incident_id"] == incident_id
        assert row.payload["data"]["ride_id"] == ride_id
        assert row.payload["data"]["location"]["latitude"] == point[0]
        assert row.payload["producer"] == "safety-service"
    finally:
        db.close()


# --- acknowledge / escalate / resolve lifecycle (no HTTP endpoint, ADR-0022) --


def test_acknowledge_escalate_resolve_lifecycle(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    customer_headers = _login_as_new_customer(api_client, sms)
    point = _random_point()
    ride_id = _create_ride(
        api_client,
        customer_headers,
        pickup=_nearby(point),
        destination=_nearby(point, offset=0.02),
    )
    incident_id = uuid.UUID(
        api_client.post(
            f"/api/v1/rides/{ride_id}/sos",
            json={
                "incident_type": "EMERGENCY",
                "latitude": point[0],
                "longitude": point[1],
            },
            headers=customer_headers,
        ).json()["data"]["incident_id"]
    )

    db = SessionLocal()
    try:
        service = SafetyService(
            incidents=SqlAlchemySafetyIncidentRepository(db),
            events=SqlAlchemySafetyEventRepository(db),
        )
        acknowledged = service.acknowledge_incident(
            incident_id=incident_id, actor_id=uuid.uuid4(), now=datetime.now(UTC)
        )
        db.commit()
        assert acknowledged.status.value == "ACKNOWLEDGED"

        escalated = service.escalate_incident(
            incident_id=incident_id, actor_id=uuid.uuid4(), now=datetime.now(UTC)
        )
        db.commit()
        assert escalated.status.value == "IN_PROGRESS"

        resolved = service.resolve_incident(
            incident_id=incident_id, actor_id=uuid.uuid4(), now=datetime.now(UTC)
        )
        db.commit()
        assert resolved.status.value == "RESOLVED"
        assert resolved.resolved_at is not None
    finally:
        db.close()

    db = SessionLocal()
    try:
        event_types = (
            db.execute(
                text(
                    "SELECT event_type FROM safety.events WHERE incident_id = :id "
                    "ORDER BY created_at"
                ),
                {"id": str(incident_id)},
            )
            .scalars()
            .all()
        )
        assert event_types == [
            "SOS_TRIGGERED",
            "ACKNOWLEDGED",
            "ESCALATED",
            "RESOLVED",
        ]
    finally:
        db.close()


def _acknowledge(incident_id: uuid.UUID) -> str:
    """Runs in its own thread with its own DB session/connection.
    Returns "OK" or "NOT_ACKNOWLEDGEABLE"."""
    db = SessionLocal()
    try:
        service = SafetyService(
            incidents=SqlAlchemySafetyIncidentRepository(db),
            events=SqlAlchemySafetyEventRepository(db),
        )
        try:
            service.acknowledge_incident(
                incident_id=incident_id, actor_id=uuid.uuid4(), now=datetime.now(UTC)
            )
        except IncidentNotAcknowledgeableError:
            db.rollback()
            return "NOT_ACKNOWLEDGEABLE"
        db.commit()
        return "OK"
    finally:
        db.close()


def test_concurrent_acknowledge_attempts_apply_exactly_once(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Same real-concurrency technique as
    test_driver_availability_api.py::test_concurrent_suspend_attempts_apply_exactly_once
    — real row-locking (get_by_id_for_update) serializes two concurrent
    acknowledge attempts on the same incident; exactly one must succeed."""
    customer_headers = _login_as_new_customer(api_client, sms)
    point = _random_point()
    ride_id = _create_ride(
        api_client,
        customer_headers,
        pickup=_nearby(point),
        destination=_nearby(point, offset=0.02),
    )
    incident_id = uuid.UUID(
        api_client.post(
            f"/api/v1/rides/{ride_id}/sos",
            json={
                "incident_type": "EMERGENCY",
                "latitude": point[0],
                "longitude": point[1],
            },
            headers=customer_headers,
        ).json()["data"]["incident_id"]
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: _acknowledge(incident_id), range(2)))

    assert results.count("OK") == 1
    assert results.count("NOT_ACKNOWLEDGEABLE") == 1

    db = SessionLocal()
    try:
        status = db.execute(
            text("SELECT status FROM safety.incidents WHERE id = :id"),
            {"id": str(incident_id)},
        ).scalar()
        assert status == "ACKNOWLEDGED"
    finally:
        db.close()
