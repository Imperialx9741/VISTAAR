"""Integration tests: real HTTP layer (TestClient) + real Postgres,
exercising Phase 16's Admin monitoring/review additions end-to-end
(ADR-0023): Search Rides, Get Ride (admin), Admin Wallet View, Search
Penalties, Resolve Penalty.

Penalties are seeded directly via SQLAlchemy (no HTTP endpoint creates
one — PenaltyService.record_customer_cancellation() is only ever called
from modules/ride/router.py's cancellation composition) — same "reach a
state no endpoint produces yet" pattern tests/test_admin_api.py already
uses for admin.users/APPROVED documents.

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


def _idempotency_key() -> str:
    return f"test-{uuid.uuid4()}"


VALID_RIDE_BODY = {
    "pickup": {"latitude": 25.5941, "longitude": 85.1376},
    "destination": {"latitude": 25.6120, "longitude": 85.1580},
    "vehicle_category": "CAB",
    "cab_tier": "ECO",
    "payment_method": "ONLINE",
}


def _create_ride(api_client: TestClient, sms: CapturingSmsProvider) -> tuple[str, dict]:
    access_token = _login(api_client, sms, "CUSTOMER")
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Idempotency-Key": _idempotency_key(),
    }
    response = api_client.post("/api/v1/rides", json=VALID_RIDE_BODY, headers=headers)
    ride_id: str = response.json()["data"]["ride_id"]
    return ride_id, headers


def _new_driver_with_profile(api_client: TestClient, sms: CapturingSmsProvider) -> str:
    access_token = _login(api_client, sms, "DRIVER")
    headers = {"Authorization": f"Bearer {access_token}"}
    response = api_client.patch(
        "/api/v1/drivers/me", json={"full_name": "Ravi Kumar"}, headers=headers
    )
    driver_id: str = response.json()["data"]["driver_id"]
    return driver_id


def _seed_outstanding_penalty(
    *, user_id: uuid.UUID, ride_id: uuid.UUID | None, amount: Decimal = Decimal("15.00")
) -> str:
    db = SessionLocal()
    try:
        penalty_id = uuid.uuid4()
        now = datetime.now(UTC)
        db.execute(
            text(
                "INSERT INTO penalty.penalties "
                "(id, user_id, ride_id, penalty_type, amount, status, "
                " issued_at) "
                "VALUES (:id, :user_id, :ride_id, :penalty_type, :amount, "
                " :status, :issued_at)"
            ),
            {
                "id": penalty_id,
                "user_id": user_id,
                "ride_id": ride_id,
                "penalty_type": "CUSTOMER_CANCELLATION",
                "amount": amount,
                "status": "OUTSTANDING",
                "issued_at": now,
            },
        )
        db.commit()
        return str(penalty_id)
    finally:
        db.close()


# --- Search Rides / Get Ride --------------------------------------------


def test_search_rides_requires_admin(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, ride_headers = _create_ride(api_client, sms)
    response = api_client.get("/api/v1/admin/rides", headers=ride_headers)
    assert response.status_code == 403


def test_unauthenticated_search_rides_is_rejected(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/admin/rides")
    assert response.status_code == 401


def test_search_rides_returns_created_ride(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    ride_id, _ = _create_ride(api_client, sms)
    admin_headers = _login_admin(api_client, sms)

    response = api_client.get(
        "/api/v1/admin/rides", params={"status": "SEARCHING"}, headers=admin_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    items = body["data"]["items"]
    assert any(item["ride_id"] == ride_id for item in items)
    match = next(item for item in items if item["ride_id"] == ride_id)
    assert match["status"] == "SEARCHING"
    assert match["fare"]["total"] == 89.25  # matches test_ride_api.py's own math
    pagination = body["data"]["pagination"]
    assert pagination["page"] == 1
    assert pagination["page_size"] == 20
    assert pagination["total"] >= 1


def test_search_rides_filters_by_customer_id(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    ride_id, ride_headers = _create_ride(api_client, sms)
    other_ride_id, _ = _create_ride(api_client, sms)
    customer_id = str(_account_id_from_token(ride_headers["Authorization"].split()[1]))
    admin_headers = _login_admin(api_client, sms)

    response = api_client.get(
        "/api/v1/admin/rides",
        params={"customer_id": customer_id},
        headers=admin_headers,
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    ride_ids = {item["ride_id"] for item in items}
    assert ride_id in ride_ids
    assert other_ride_id not in ride_ids


def test_search_rides_rejects_unknown_status(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    response = api_client.get(
        "/api/v1/admin/rides", params={"status": "NOT_A_STATUS"}, headers=admin_headers
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_search_rides_page_size_is_capped_at_server_configured_max(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    response = api_client.get(
        "/api/v1/admin/rides", params={"page_size": 999999}, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["data"]["pagination"]["page_size"] <= 100


def test_get_ride_returns_full_ride_data(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    ride_id, ride_headers = _create_ride(api_client, sms)
    customer_id = str(_account_id_from_token(ride_headers["Authorization"].split()[1]))
    admin_headers = _login_admin(api_client, sms)

    response = api_client.get(f"/api/v1/admin/rides/{ride_id}", headers=admin_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["ride_id"] == ride_id
    assert data["customer_id"] == customer_id
    assert data["status"] == "SEARCHING"
    assert data["requested_vehicle_category"] == "CAB"
    assert data["requested_cab_tier"] == "ECO"
    assert data["fare"]["total"] == 89.25
    assert data["pickup"]["latitude"] == pytest.approx(25.5941)


def test_get_unknown_ride_returns_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    response = api_client.get(
        f"/api/v1/admin/rides/{uuid.uuid4()}", headers=admin_headers
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RIDE_NOT_FOUND"


# --- Admin Wallet View ----------------------------------------------------


def test_get_driver_wallet_returns_zero_balance_for_new_driver(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_id = _new_driver_with_profile(api_client, sms)
    admin_headers = _login_admin(api_client, sms)

    response = api_client.get(
        f"/api/v1/admin/wallets/{driver_id}", headers=admin_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["balance"] == 0.0
    assert data["currency"] == "INR"
    assert data["outstanding_settlement"] == 0


def test_get_wallet_for_nonexistent_driver_returns_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    response = api_client.get(
        f"/api/v1/admin/wallets/{uuid.uuid4()}", headers=admin_headers
    )
    assert response.status_code == 404


def test_get_driver_wallet_requires_admin(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_id = _new_driver_with_profile(api_client, sms)
    access_token = _login(api_client, sms, "CUSTOMER")
    response = api_client.get(
        f"/api/v1/admin/wallets/{driver_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 403


# --- Search Penalties / Resolve Penalty ------------------------------------


def test_search_penalties_filters_by_status_and_user_id(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    ride_id, ride_headers = _create_ride(api_client, sms)
    customer_id = _account_id_from_token(ride_headers["Authorization"].split()[1])
    penalty_id = _seed_outstanding_penalty(
        user_id=customer_id, ride_id=uuid.UUID(ride_id)
    )
    admin_headers = _login_admin(api_client, sms)

    response = api_client.get(
        "/api/v1/admin/penalties",
        params={"status": "OUTSTANDING", "user_id": str(customer_id)},
        headers=admin_headers,
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert any(item["penalty_id"] == penalty_id for item in items)
    match = next(item for item in items if item["penalty_id"] == penalty_id)
    assert match["status"] == "OUTSTANDING"
    assert match["amount"] == 15.0
    assert match["user_id"] == str(customer_id)


def test_search_penalties_rejects_unknown_status(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    response = api_client.get(
        "/api/v1/admin/penalties",
        params={"status": "NOT_A_STATUS"},
        headers=admin_headers,
    )
    assert response.status_code == 422


def test_resolve_penalty_waives_an_outstanding_penalty(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    ride_id, ride_headers = _create_ride(api_client, sms)
    customer_id = _account_id_from_token(ride_headers["Authorization"].split()[1])
    penalty_id = _seed_outstanding_penalty(
        user_id=customer_id, ride_id=uuid.UUID(ride_id)
    )
    admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        f"/api/v1/admin/penalties/{penalty_id}/resolve",
        json={"action": "WAIVE", "reason": "Verified system error"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "WAIVED"
    assert data["amount"] == 15.0  # api-contracts.md §48: original amount immutable
    assert data["settled_at"] is None  # ADR-0023 Decision 4: WAIVED != settled


def test_resolve_penalty_writes_an_audit_log(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    ride_id, ride_headers = _create_ride(api_client, sms)
    customer_id = _account_id_from_token(ride_headers["Authorization"].split()[1])
    penalty_id = _seed_outstanding_penalty(
        user_id=customer_id, ride_id=uuid.UUID(ride_id)
    )
    admin_headers = _login_admin(api_client, sms)

    api_client.post(
        f"/api/v1/admin/penalties/{penalty_id}/resolve",
        json={"action": "WAIVE", "reason": "Verified system error"},
        headers=admin_headers,
    )

    db = SessionLocal()
    try:
        row = (
            db.execute(
                text(
                    "SELECT action, reason, before_state, after_state "
                    "FROM admin.audit_logs WHERE target_id = :target_id "
                    "AND action = 'RESOLVE_PENALTY'"
                ),
                {"target_id": penalty_id},
            )
            .mappings()
            .one()
        )
    finally:
        db.close()
    assert row["reason"] == "Verified system error"
    assert row["before_state"] == {"status": "OUTSTANDING"}
    assert row["after_state"] == {"status": "WAIVED"}


def test_resolve_penalty_twice_returns_invalid_state_transition(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    ride_id, ride_headers = _create_ride(api_client, sms)
    customer_id = _account_id_from_token(ride_headers["Authorization"].split()[1])
    penalty_id = _seed_outstanding_penalty(
        user_id=customer_id, ride_id=uuid.UUID(ride_id)
    )
    admin_headers = _login_admin(api_client, sms)
    api_client.post(
        f"/api/v1/admin/penalties/{penalty_id}/resolve",
        json={"action": "WAIVE"},
        headers=admin_headers,
    )

    response = api_client.post(
        f"/api/v1/admin/penalties/{penalty_id}/resolve",
        json={"action": "WAIVE"},
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_resolve_penalty_rejects_unsupported_action(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    ride_id, ride_headers = _create_ride(api_client, sms)
    customer_id = _account_id_from_token(ride_headers["Authorization"].split()[1])
    penalty_id = _seed_outstanding_penalty(
        user_id=customer_id, ride_id=uuid.UUID(ride_id)
    )
    admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        f"/api/v1/admin/penalties/{penalty_id}/resolve",
        json={"action": "REFUND"},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_resolve_unknown_penalty_returns_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    response = api_client.post(
        f"/api/v1/admin/penalties/{uuid.uuid4()}/resolve",
        json={"action": "WAIVE"},
        headers=admin_headers,
    )
    assert response.status_code == 404


def test_resolve_penalty_requires_admin(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    ride_id, ride_headers = _create_ride(api_client, sms)
    customer_id = _account_id_from_token(ride_headers["Authorization"].split()[1])
    penalty_id = _seed_outstanding_penalty(
        user_id=customer_id, ride_id=uuid.UUID(ride_id)
    )

    response = api_client.post(
        f"/api/v1/admin/penalties/{penalty_id}/resolve",
        json={"action": "WAIVE"},
        headers=ride_headers,
    )

    assert response.status_code == 403


def test_concurrent_resolve_requests_never_double_waive(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Two simultaneous Resolve Penalty requests for the same penalty
    must not both succeed. Real row-locking (get_by_id_for_update())
    serializes them; the loser re-reads the now-WAIVED state and
    correctly returns INVALID_STATE_TRANSITION rather than
    double-processing — same reasoning as
    tests/test_driver_availability_api.py::
    test_concurrent_go_offline_requests_never_double_process."""
    ride_id, ride_headers = _create_ride(api_client, sms)
    customer_id = _account_id_from_token(ride_headers["Authorization"].split()[1])
    penalty_id = _seed_outstanding_penalty(
        user_id=customer_id, ride_id=uuid.UUID(ride_id)
    )
    admin_headers = _login_admin(api_client, sms)

    results: list[int] = []

    def _resolve() -> None:
        response = api_client.post(
            f"/api/v1/admin/penalties/{penalty_id}/resolve",
            json={"action": "WAIVE"},
            headers=admin_headers,
        )
        results.append(response.status_code)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(_resolve) for _ in range(2)]
        for future in futures:
            future.result()

    assert sorted(results) == [200, 409]
