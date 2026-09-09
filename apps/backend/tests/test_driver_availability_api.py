"""Integration tests: real HTTP layer (TestClient) + real Postgres,
exercising POST /api/v1/drivers/me/online and .../offline end-to-end
(Phase 2 / Task 2.7B), authenticated via a real OTP login and driven
through the real Admin approval endpoints (Task 2.7A) rather than raw SQL
writes wherever an HTTP path already exists for that state — same
layering as tests/test_admin_api.py, which this file's setup helpers are
copied from (no shared test-helper module exists in this codebase; each
integration test file keeps its own copies, same as
tests/test_vehicle_api.py vs tests/test_driver_api.py).

Skips (not fails) when Postgres is genuinely unreachable.
"""

from __future__ import annotations

import asyncio
import secrets
import uuid
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from core.database import SessionLocal
from core.redis import get_redis_client
from main import app
from modules.admin.models import AdminUserORM
from modules.driver.domain.errors import DriverAlreadySuspendedError
from modules.driver.repositories import SqlAlchemyDriverRepository
from modules.driver.service import DriverService
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
    """Stands in for the not-yet-triggered manual-review completion (Task
    2.6B) — same "reach a state no endpoint produces yet" pattern as
    tests/test_admin_api.py."""
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
    """No HTTP endpoint exists for vehicle documents (ADR-0007) — same
    pattern as tests/test_admin_api.py."""
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


def _new_eligible_driver_and_active_vehicle(
    api_client: TestClient, sms: CapturingSmsProvider, admin_headers: dict
) -> tuple[dict, str]:
    """Builds a driver that is fully eligible to go online: APPROVED,
    required documents valid, and an APPROVED + ACTIVE vehicle whose own
    required documents are valid. Returns (driver_headers, vehicle_id)."""
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
            "cab_tier": "ECO",  # ADR-0020 Decision 1
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
    return driver_headers, vehicle["vehicle_id"]


# --- Go Online -----------------------------------------------------------


def test_go_online_succeeds_when_fully_eligible(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    driver_headers, vehicle_id = _new_eligible_driver_and_active_vehicle(
        api_client, sms, admin_headers
    )

    response = api_client.post("/api/v1/drivers/me/online", headers=driver_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "ONLINE"
    assert data["vehicle_id"] == vehicle_id

    profile = api_client.get("/api/v1/drivers/me", headers=driver_headers).json()[
        "data"
    ]
    assert profile["operational_status"] == "ONLINE"


def test_go_online_rejected_without_driver_profile(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "DRIVER")
    headers = {"Authorization": f"Bearer {access_token}"}

    response = api_client.post("/api/v1/drivers/me/online", headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_go_online_rejected_when_driver_not_approved(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_headers = _new_driver_with_profile(api_client, sms)

    response = api_client.post("/api/v1/drivers/me/online", headers=driver_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DRIVER_NOT_ELIGIBLE"


def test_go_online_rejected_when_no_active_vehicle(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    driver_headers = _new_driver_with_profile(api_client, sms)
    driver_id = api_client.get("/api/v1/drivers/me", headers=driver_headers).json()[
        "data"
    ]["driver_id"]
    _make_driver_documents_valid(api_client, driver_headers)
    _approve_driver(api_client, admin_headers, driver_id)

    response = api_client.post("/api/v1/drivers/me/online", headers=driver_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DRIVER_NOT_ELIGIBLE"


def test_go_online_rejected_when_vehicle_documents_expired(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    driver_headers, vehicle_id = _new_eligible_driver_and_active_vehicle(
        api_client, sms, admin_headers
    )
    # Expire the vehicle's insurance after approval — same "regresses
    # after approval" scenario BR-123's re-check exists for.
    db = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE vehicle.documents SET expires_at = NOW() - INTERVAL '1 day' "
                "WHERE vehicle_id = :id AND document_type = 'INSURANCE'"
            ),
            {"id": vehicle_id},
        )
        db.commit()
    finally:
        db.close()

    response = api_client.post("/api/v1/drivers/me/online", headers=driver_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DRIVER_NOT_ELIGIBLE"


def test_go_online_rejected_when_already_online(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    driver_headers, _ = _new_eligible_driver_and_active_vehicle(
        api_client, sms, admin_headers
    )
    api_client.post("/api/v1/drivers/me/online", headers=driver_headers)

    response = api_client.post("/api/v1/drivers/me/online", headers=driver_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_go_online_unauthenticated_is_rejected(api_client: TestClient) -> None:
    response = api_client.post("/api/v1/drivers/me/online")
    assert response.status_code == 401


def test_go_online_customer_account_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "CUSTOMER")

    response = api_client.post(
        "/api/v1/drivers/me/online",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 403


# --- Go Offline ------------------------------------------------------------


def test_go_offline_succeeds_when_online(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    driver_headers, _ = _new_eligible_driver_and_active_vehicle(
        api_client, sms, admin_headers
    )
    api_client.post("/api/v1/drivers/me/online", headers=driver_headers)

    response = api_client.post("/api/v1/drivers/me/offline", headers=driver_headers)

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "OFFLINE"

    profile = api_client.get("/api/v1/drivers/me", headers=driver_headers).json()[
        "data"
    ]
    assert profile["operational_status"] == "OFFLINE"


async def _redis_online_state(driver_id: str) -> tuple[bool, bool]:
    """(driver:online:{id} hash exists, geo:drivers:CAB:ECO membership) —
    both should flip from (True, True) to (False, False) across
    go_offline now that modules/driver/router.py composes shared/
    geo.py's remove_driver_location() (fixed 2026-08-28; see that
    module's own docstring for the "previously written, never called"
    history)."""
    client = get_redis_client()
    try:
        hash_exists = await client.exists(f"driver:online:{driver_id}") == 1
        geo_score = await client.zscore("geo:drivers:CAB:ECO", driver_id)
        return hash_exists, geo_score is not None
    finally:
        await client.aclose()


def test_go_offline_removes_the_driver_from_the_redis_geo_index(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    driver_headers, _ = _new_eligible_driver_and_active_vehicle(
        api_client, sms, admin_headers
    )
    driver_id = api_client.get("/api/v1/drivers/me", headers=driver_headers).json()[
        "data"
    ]["driver_id"]
    api_client.post("/api/v1/drivers/me/online", headers=driver_headers)
    location_response = api_client.post(
        "/api/v1/drivers/me/location",
        json={"latitude": 21.234, "longitude": 79.456},
        headers=driver_headers,
    )
    assert location_response.status_code == 200

    hash_exists, geo_member = asyncio.run(_redis_online_state(driver_id))
    assert hash_exists is True
    assert geo_member is True

    response = api_client.post("/api/v1/drivers/me/offline", headers=driver_headers)
    assert response.status_code == 200

    hash_exists, geo_member = asyncio.run(_redis_online_state(driver_id))
    assert hash_exists is False
    assert geo_member is False


def test_go_offline_rejected_when_already_offline(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_headers = _new_driver_with_profile(api_client, sms)

    response = api_client.post("/api/v1/drivers/me/offline", headers=driver_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DRIVER_NOT_ONLINE"


def test_go_offline_rejected_when_on_ride(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """ON_RIDE -> OFFLINE returns the same DRIVER_NOT_ONLINE as the
    already-offline case — see
    modules/driver/domain/errors.py::DriverNotOnlineError."""
    admin_headers = _login_admin(api_client, sms)
    driver_headers, _ = _new_eligible_driver_and_active_vehicle(
        api_client, sms, admin_headers
    )
    api_client.post("/api/v1/drivers/me/online", headers=driver_headers)
    db = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE driver.drivers SET operational_status = 'ON_RIDE' "
                "WHERE id = (SELECT id FROM driver.drivers ORDER BY created_at "
                "DESC LIMIT 1)"
            )
        )
        db.commit()
    finally:
        db.close()

    response = api_client.post("/api/v1/drivers/me/offline", headers=driver_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DRIVER_NOT_ONLINE"


def test_go_offline_rejected_without_driver_profile(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "DRIVER")
    headers = {"Authorization": f"Bearer {access_token}"}

    response = api_client.post("/api/v1/drivers/me/offline", headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_go_offline_unauthenticated_is_rejected(api_client: TestClient) -> None:
    response = api_client.post("/api/v1/drivers/me/offline")
    assert response.status_code == 401


# --- Concurrency -----------------------------------------------------------


def test_concurrent_go_offline_requests_never_double_process(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Concurrency must prevent two simultaneous Go Offline requests for
    the same driver from both succeeding or from corrupting
    operational_status. Fires two real HTTP requests from two threads, as
    close to simultaneously as possible — real row-locking
    (get_by_id_for_update) serializes them; the loser re-reads the
    now-current (OFFLINE) state and correctly returns DRIVER_NOT_ONLINE
    rather than double-applying the transition. Not testable against an
    in-memory fake — same reasoning as
    tests/test_vehicle_api.py::test_concurrent_activation_requests_never_leave_two_vehicles_active.
    """
    admin_headers = _login_admin(api_client, sms)
    driver_headers, _ = _new_eligible_driver_and_active_vehicle(
        api_client, sms, admin_headers
    )
    api_client.post("/api/v1/drivers/me/online", headers=driver_headers)

    results: list[int] = []

    def _go_offline() -> None:
        response = api_client.post("/api/v1/drivers/me/offline", headers=driver_headers)
        results.append(response.status_code)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(_go_offline) for _ in range(2)]
        for future in futures:
            future.result()

    assert sorted(results) == [200, 409]

    profile = api_client.get("/api/v1/drivers/me", headers=driver_headers).json()[
        "data"
    ]
    assert profile["operational_status"] == "OFFLINE"


# --- suspend_driver / reactivate_driver (Phase 03, ADR-0021) ----------------
#
# No HTTP endpoint exists (ADR-0021 Decision 2) — DriverService is called
# directly against a real DB session, same technique
# tests/test_wallet_api.py established for WalletService.debit() before
# any endpoint called it.


def _driver_id(api_client: TestClient, driver_headers: dict) -> uuid.UUID:
    driver_id = api_client.get("/api/v1/drivers/me", headers=driver_headers).json()[
        "data"
    ]["driver_id"]
    return uuid.UUID(driver_id)


def test_suspend_then_reactivate_lifecycle(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    driver_headers, _ = _new_eligible_driver_and_active_vehicle(
        api_client, sms, admin_headers
    )
    driver_id = _driver_id(api_client, driver_headers)

    db = SessionLocal()
    try:
        service = DriverService(drivers=SqlAlchemyDriverRepository(db))
        suspended = service.suspend_driver(
            driver_id=driver_id, reason="Safety complaint"
        )
        db.commit()
        assert suspended.operational_status.value == "SUSPENDED"
    finally:
        db.close()

    # A suspended driver cannot Go Online (ADR-0021 Decision 5 — the
    # existing generic "must be OFFLINE" guard already covers it).
    blocked = api_client.post("/api/v1/drivers/me/online", headers=driver_headers)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "INVALID_STATE_TRANSITION"

    db = SessionLocal()
    try:
        service = DriverService(drivers=SqlAlchemyDriverRepository(db))
        reactivated = service.reactivate_driver(driver_id=driver_id)
        db.commit()
        # ADR-0021 Decision 4: lands on OFFLINE, not ONLINE.
        assert reactivated.operational_status.value == "OFFLINE"
    finally:
        db.close()

    # Now the driver can Go Online again through the normal, already-
    # validated path.
    online = api_client.post("/api/v1/drivers/me/online", headers=driver_headers)
    assert online.status_code == 200
    assert online.json()["data"]["status"] == "ONLINE"


def _suspend(driver_id: uuid.UUID) -> str:
    """Runs in its own thread with its own DB session/connection.
    Returns "OK" or "ALREADY_SUSPENDED"."""
    db = SessionLocal()
    try:
        service = DriverService(drivers=SqlAlchemyDriverRepository(db))
        try:
            service.suspend_driver(driver_id=driver_id, reason="Safety complaint")
        except DriverAlreadySuspendedError:
            db.rollback()
            return "ALREADY_SUSPENDED"
        db.commit()
        return "OK"
    finally:
        db.close()


def test_concurrent_suspend_attempts_apply_exactly_once(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Same real-concurrency technique as
    test_concurrent_go_offline_requests_never_double_process — real
    row-locking (get_by_id_for_update) serializes two concurrent suspend
    attempts for the same driver; exactly one must succeed."""
    admin_headers = _login_admin(api_client, sms)
    driver_headers, _ = _new_eligible_driver_and_active_vehicle(
        api_client, sms, admin_headers
    )
    driver_id = _driver_id(api_client, driver_headers)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: _suspend(driver_id), range(2)))

    assert results.count("OK") == 1
    assert results.count("ALREADY_SUSPENDED") == 1

    profile = api_client.get("/api/v1/drivers/me", headers=driver_headers).json()[
        "data"
    ]
    assert profile["operational_status"] == "SUSPENDED"
