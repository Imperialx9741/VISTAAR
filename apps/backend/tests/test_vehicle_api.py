"""Integration tests: real HTTP layer (TestClient) + real Postgres,
exercising POST/GET /api/v1/drivers/me/vehicles and the activate/
deactivate endpoints end-to-end, authenticated via a real OTP login
through modules.identity and a real driver profile through
modules.driver — same layered pattern as tests/test_driver_api.py.

Skips (not fails) when Postgres is genuinely unreachable.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor

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


def _random_registration() -> str:
    return "BR01" + "".join(str(secrets.randbelow(10)) for _ in range(6))


def _new_driver_with_profile(
    api_client: TestClient, sms: CapturingSmsProvider
) -> dict[str, str]:
    """Logs in a brand-new DRIVER account and creates its driver profile
    (required by vehicle.vehicles.driver_id's foreign key), returning
    auth headers ready to use."""
    phone = _random_phone()
    request_response = api_client.post(
        "/api/v1/auth/otp/request",
        json={"phone": phone, "account_type": "DRIVER"},
    )
    challenge_id = request_response.json()["data"]["challenge_id"]
    otp = sms.sent[phone]
    tokens = api_client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "otp": otp},
    ).json()["data"]
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    api_client.patch(
        "/api/v1/drivers/me", json={"full_name": "Ravi Kumar"}, headers=headers
    )
    return headers


def _approve_vehicle(vehicle_id: str) -> None:
    """Simulates the not-yet-implemented ApproveVehicle admin command
    (out of scope for this task — see modules/vehicle/__init__.py) by
    writing directly to the database, so the documented "approved"
    branch of Activate Vehicle can be exercised end-to-end."""
    db = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE vehicle.vehicles SET verification_status = 'APPROVED' "
                "WHERE id = :id"
            ),
            {"id": vehicle_id},
        )
        db.commit()
    finally:
        db.close()


def test_list_vehicles_starts_empty(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers = _new_driver_with_profile(api_client, sms)

    response = api_client.get("/api/v1/drivers/me/vehicles", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["vehicles"] == []


def test_add_vehicle_succeeds_and_is_listed(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers = _new_driver_with_profile(api_client, sms)
    registration = _random_registration()

    add_response = api_client.post(
        "/api/v1/drivers/me/vehicles",
        json={
            "category": "CAB",
            "cab_tier": "ECO",
            "registration_number": registration,
            "make": "Maruti",
            "model": "Dzire",
        },
        headers=headers,
    )

    assert add_response.status_code == 201
    data = add_response.json()["data"]
    assert data["category"] == "CAB"
    assert data["registration_number"] == registration
    assert data["verification_status"] == "PENDING"
    assert data["operational_status"] == "INACTIVE"

    list_response = api_client.get("/api/v1/drivers/me/vehicles", headers=headers)
    assert len(list_response.json()["data"]["vehicles"]) == 1


def test_add_vehicle_without_driver_profile_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    phone = _random_phone()
    request_response = api_client.post(
        "/api/v1/auth/otp/request",
        json={"phone": phone, "account_type": "DRIVER"},
    )
    challenge_id = request_response.json()["data"]["challenge_id"]
    otp = sms.sent[phone]
    tokens = api_client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "otp": otp},
    ).json()["data"]
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    # No PATCH /api/v1/drivers/me call — no driver.drivers row exists.

    response = api_client.post(
        "/api/v1/drivers/me/vehicles",
        json={
            "category": "CAB",
            "cab_tier": "ECO",
            "registration_number": _random_registration(),
        },
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_duplicate_registration_number_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers = _new_driver_with_profile(api_client, sms)
    registration = _random_registration()
    api_client.post(
        "/api/v1/drivers/me/vehicles",
        json={
            "category": "CAB",
            "cab_tier": "ECO",
            "registration_number": registration,
        },
        headers=headers,
    )

    other_headers = _new_driver_with_profile(api_client, sms)
    response = api_client.post(
        "/api/v1/drivers/me/vehicles",
        json={"category": "BIKE", "registration_number": registration.lower()},
        headers=other_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_invalid_category_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers = _new_driver_with_profile(api_client, sms)

    response = api_client.post(
        "/api/v1/drivers/me/vehicles",
        json={"category": "TRUCK", "registration_number": _random_registration()},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_cab_without_a_tier_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """ADR-0020 Decision 1."""
    headers = _new_driver_with_profile(api_client, sms)

    response = api_client.post(
        "/api/v1/drivers/me/vehicles",
        json={"category": "CAB", "registration_number": _random_registration()},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_bike_with_a_tier_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """ADR-0020 Decision 1: cab_tier is CAB-only."""
    headers = _new_driver_with_profile(api_client, sms)

    response = api_client.post(
        "/api/v1/drivers/me/vehicles",
        json={
            "category": "BIKE",
            "cab_tier": "ECO",
            "registration_number": _random_registration(),
        },
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_activate_rejected_while_unapproved(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers = _new_driver_with_profile(api_client, sms)
    vehicle = api_client.post(
        "/api/v1/drivers/me/vehicles",
        json={
            "category": "CAB",
            "cab_tier": "ECO",
            "registration_number": _random_registration(),
        },
        headers=headers,
    ).json()["data"]

    response = api_client.post(
        f"/api/v1/drivers/me/vehicles/{vehicle['vehicle_id']}/activate",
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VEHICLE_NOT_ELIGIBLE"


def test_activate_and_deactivate_succeed_once_approved(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers = _new_driver_with_profile(api_client, sms)
    vehicle = api_client.post(
        "/api/v1/drivers/me/vehicles",
        json={
            "category": "CAB",
            "cab_tier": "ECO",
            "registration_number": _random_registration(),
        },
        headers=headers,
    ).json()["data"]
    _approve_vehicle(vehicle["vehicle_id"])

    activate_response = api_client.post(
        f"/api/v1/drivers/me/vehicles/{vehicle['vehicle_id']}/activate",
        headers=headers,
    )
    assert activate_response.status_code == 200
    assert activate_response.json()["data"]["operational_status"] == "ACTIVE"

    deactivate_response = api_client.post(
        f"/api/v1/drivers/me/vehicles/{vehicle['vehicle_id']}/deactivate",
        headers=headers,
    )
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["data"]["operational_status"] == "INACTIVE"


def test_another_driver_cannot_see_or_activate_this_vehicle(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers = _new_driver_with_profile(api_client, sms)
    vehicle = api_client.post(
        "/api/v1/drivers/me/vehicles",
        json={
            "category": "CAB",
            "cab_tier": "ECO",
            "registration_number": _random_registration(),
        },
        headers=headers,
    ).json()["data"]
    _approve_vehicle(vehicle["vehicle_id"])

    other_headers = _new_driver_with_profile(api_client, sms)

    list_response = api_client.get("/api/v1/drivers/me/vehicles", headers=other_headers)
    assert list_response.json()["data"]["vehicles"] == []

    activate_response = api_client.post(
        f"/api/v1/drivers/me/vehicles/{vehicle['vehicle_id']}/activate",
        headers=other_headers,
    )
    assert activate_response.status_code == 404
    assert activate_response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_unauthenticated_access_is_rejected(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/drivers/me/vehicles")
    assert response.status_code == 401


def test_customer_account_cannot_access_vehicle_endpoints(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
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

    response = api_client.get(
        "/api/v1/drivers/me/vehicles",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 403


def test_multiple_vehicles_per_driver_via_real_api(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers = _new_driver_with_profile(api_client, sms)

    for category in ("BIKE", "AUTO", "CAB"):
        body = {
            "category": category,
            "registration_number": _random_registration(),
        }
        if category == "CAB":
            body["cab_tier"] = "ECO"
        response = api_client.post(
            "/api/v1/drivers/me/vehicles", json=body, headers=headers
        )
        assert response.status_code == 201

    vehicles = api_client.get("/api/v1/drivers/me/vehicles", headers=headers).json()[
        "data"
    ]["vehicles"]
    assert len(vehicles) == 3


def test_data_persists_across_requests_via_postgres(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers = _new_driver_with_profile(api_client, sms)
    registration = _random_registration()
    api_client.post(
        "/api/v1/drivers/me/vehicles",
        json={
            "category": "CAB",
            "cab_tier": "ECO",
            "registration_number": registration,
        },
        headers=headers,
    )

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT registration_number FROM vehicle.vehicles "
                "WHERE registration_number = :r"
            ),
            {"r": registration},
        ).fetchone()
        assert row is not None
    finally:
        db.close()


def test_get_single_vehicle_returns_owned_vehicle(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers = _new_driver_with_profile(api_client, sms)
    vehicle = api_client.post(
        "/api/v1/drivers/me/vehicles",
        json={
            "category": "CAB",
            "cab_tier": "ECO",
            "registration_number": _random_registration(),
        },
        headers=headers,
    ).json()["data"]

    response = api_client.get(
        f"/api/v1/drivers/me/vehicles/{vehicle['vehicle_id']}", headers=headers
    )

    assert response.status_code == 200
    assert response.json()["data"]["vehicle_id"] == vehicle["vehicle_id"]


def test_get_single_vehicle_denies_another_driver(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers = _new_driver_with_profile(api_client, sms)
    vehicle = api_client.post(
        "/api/v1/drivers/me/vehicles",
        json={
            "category": "CAB",
            "cab_tier": "ECO",
            "registration_number": _random_registration(),
        },
        headers=headers,
    ).json()["data"]

    other_headers = _new_driver_with_profile(api_client, sms)
    response = api_client.get(
        f"/api/v1/drivers/me/vehicles/{vehicle['vehicle_id']}",
        headers=other_headers,
    )

    assert response.status_code == 404


def test_patch_updates_only_make_and_model(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers = _new_driver_with_profile(api_client, sms)
    vehicle = api_client.post(
        "/api/v1/drivers/me/vehicles",
        json={
            "category": "CAB",
            "cab_tier": "ECO",
            "registration_number": _random_registration(),
            "make": "Old Make",
            "model": "Old Model",
        },
        headers=headers,
    ).json()["data"]

    response = api_client.patch(
        f"/api/v1/drivers/me/vehicles/{vehicle['vehicle_id']}",
        json={"make": "New Make"},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["make"] == "New Make"
    assert data["model"] == "Old Model"  # untouched


def test_patch_cannot_modify_server_controlled_fields(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Fields not in UpdateVehicleBody (category, registration_number,
    verification_status, operational_status, driver_id, timestamps) are
    silently dropped by Pydantic rather than applied — verifies none of
    them changed."""
    headers = _new_driver_with_profile(api_client, sms)
    original_registration = _random_registration()
    vehicle = api_client.post(
        "/api/v1/drivers/me/vehicles",
        json={
            "category": "CAB",
            "cab_tier": "ECO",
            "registration_number": original_registration,
        },
        headers=headers,
    ).json()["data"]

    response = api_client.patch(
        f"/api/v1/drivers/me/vehicles/{vehicle['vehicle_id']}",
        json={
            "category": "BIKE",
            "registration_number": "HACKED1234",
            "verification_status": "APPROVED",
            "operational_status": "ACTIVE",
            "driver_id": str(uuid.uuid4()),
        },
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["category"] == "CAB"
    assert data["registration_number"] == original_registration
    assert data["verification_status"] == "PENDING"
    assert data["operational_status"] == "INACTIVE"


def test_activating_second_vehicle_deactivates_first_via_real_api(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers = _new_driver_with_profile(api_client, sms)
    first = api_client.post(
        "/api/v1/drivers/me/vehicles",
        json={
            "category": "CAB",
            "cab_tier": "ECO",
            "registration_number": _random_registration(),
        },
        headers=headers,
    ).json()["data"]
    second = api_client.post(
        "/api/v1/drivers/me/vehicles",
        json={"category": "AUTO", "registration_number": _random_registration()},
        headers=headers,
    ).json()["data"]
    _approve_vehicle(first["vehicle_id"])
    _approve_vehicle(second["vehicle_id"])

    api_client.post(
        f"/api/v1/drivers/me/vehicles/{first['vehicle_id']}/activate",
        headers=headers,
    )
    activate_second = api_client.post(
        f"/api/v1/drivers/me/vehicles/{second['vehicle_id']}/activate",
        headers=headers,
    )

    assert activate_second.status_code == 200
    assert activate_second.json()["data"]["operational_status"] == "ACTIVE"

    vehicles = {
        v["vehicle_id"]: v
        for v in api_client.get("/api/v1/drivers/me/vehicles", headers=headers).json()[
            "data"
        ]["vehicles"]
    }
    assert vehicles[first["vehicle_id"]]["operational_status"] == "INACTIVE"
    assert vehicles[second["vehicle_id"]]["operational_status"] == "ACTIVE"
    active_count = sum(
        1 for v in vehicles.values() if v["operational_status"] == "ACTIVE"
    )
    assert active_count == 1


def test_concurrent_activation_requests_never_leave_two_vehicles_active(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """9. Concurrency must prevent two simultaneous activation requests
    from leaving two vehicles ACTIVE for the same driver.

    Fires two real HTTP activation requests for two different vehicles
    belonging to the same driver, from two threads, as close to
    simultaneously as possible, then verifies — by querying PostgreSQL
    directly — that exactly one vehicle ended up ACTIVE. Relies on
    real row-locking (list_by_driver_for_update) plus the database's
    uq_vehicles_one_active_per_driver partial unique index as the
    backstop; this is not testable against an in-memory fake."""
    headers = _new_driver_with_profile(api_client, sms)
    first = api_client.post(
        "/api/v1/drivers/me/vehicles",
        json={
            "category": "CAB",
            "cab_tier": "ECO",
            "registration_number": _random_registration(),
        },
        headers=headers,
    ).json()["data"]
    second = api_client.post(
        "/api/v1/drivers/me/vehicles",
        json={"category": "AUTO", "registration_number": _random_registration()},
        headers=headers,
    ).json()["data"]
    _approve_vehicle(first["vehicle_id"])
    _approve_vehicle(second["vehicle_id"])

    results: list[int] = []

    def _activate(vehicle_id: str) -> None:
        response = api_client.post(
            f"/api/v1/drivers/me/vehicles/{vehicle_id}/activate", headers=headers
        )
        results.append(response.status_code)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_activate, first["vehicle_id"]),
            executor.submit(_activate, second["vehicle_id"]),
        ]
        for future in futures:
            future.result()

    # Both requests should complete successfully (row-locking serializes
    # them rather than rejecting either outright) — but see the DB-level
    # assertion below, which is what actually matters for BR-122.
    assert all(status == 200 for status in results)

    db = SessionLocal()
    try:
        active_rows = db.execute(
            text(
                "SELECT id FROM vehicle.vehicles WHERE driver_id = "
                "(SELECT driver_id FROM vehicle.vehicles WHERE id = :id) "
                "AND operational_status = 'ACTIVE'"
            ),
            {"id": first["vehicle_id"]},
        ).fetchall()
    finally:
        db.close()

    assert len(active_rows) == 1
