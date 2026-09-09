"""Integration tests: real HTTP layer (TestClient) + real Postgres,
exercising GET /api/v1/drivers/me/strikes end-to-end, authenticated via
a real OTP login through modules.identity — same pattern
tests/test_driver_document_api.py already uses.

Added by ADR-0073 (2026-09-04), closing the same shape of gap ADR-0072
closed for driver/vehicle documents: the service/repository layer
(`PenaltyService.list_strikes_for_driver()`) and an admin-only HTTP
route (`GET /api/v1/admin/drivers/{driver_id}/strikes`,
tests/test_admin_api.py) already existed; this is the caller's-own-data
equivalent. No HTTP endpoint creates a strike on demand (BR-068 records
one as a side effect of a real ride-cancellation flow) — strikes here
are seeded directly at the service layer, the same technique
test_admin_api.py's own `_record_driver_strike_directly()` uses.

Skips (not fails) when Postgres is genuinely unreachable.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from core.database import SessionLocal
from main import app
from modules.identity.dependencies import get_sms_provider_dependency
from modules.penalty.repositories import (
    SqlAlchemyPenaltyRepository,
    SqlAlchemyStrikeRepository,
)
from modules.penalty.service import PenaltyService


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


def _create_driver_profile(api_client: TestClient, headers: dict[str, str]) -> str:
    data = api_client.patch(
        "/api/v1/drivers/me", json={"full_name": "Ravi Kumar"}, headers=headers
    ).json()["data"]
    driver_id: str = data["driver_id"]
    return driver_id


def _create_ride(api_client: TestClient, customer_headers: dict[str, str]) -> str:
    response = api_client.post(
        "/api/v1/rides",
        json={
            "pickup": {"latitude": 25.5941, "longitude": 85.1376},
            "destination": {"latitude": 25.6120, "longitude": 85.1580},
            "vehicle_category": "BIKE",
        },
        headers={**customer_headers, "Idempotency-Key": f"test-{uuid.uuid4()}"},
    )
    ride_id: str = response.json()["data"]["ride_id"]
    return ride_id


def _record_driver_strike_directly(
    driver_id: uuid.UUID, *, ride_id: uuid.UUID, reason: str
) -> None:
    """Direct-service-layer seed — see this module's docstring."""
    db = SessionLocal()
    try:
        service = PenaltyService(
            penalties=SqlAlchemyPenaltyRepository(db),
            strikes=SqlAlchemyStrikeRepository(db),
        )
        service.record_driver_strike(
            driver_id=driver_id, ride_id=ride_id, reason=reason, now=datetime.now(UTC)
        )
        db.commit()
    finally:
        db.close()


def test_list_strikes_before_profile_exists_returns_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "DRIVER")

    response = api_client.get(
        "/api/v1/drivers/me/strikes",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_list_strikes_is_empty_for_a_driver_with_none(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "DRIVER")
    headers = {"Authorization": f"Bearer {access_token}"}
    _create_driver_profile(api_client, headers)

    response = api_client.get("/api/v1/drivers/me/strikes", headers=headers)

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["items"] == []
    assert body["pagination"]["total"] == 0


def test_list_strikes_returns_the_seeded_strike_matching_the_documented_shape(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_token = _login(api_client, sms, "DRIVER")
    driver_headers = {"Authorization": f"Bearer {driver_token}"}
    driver_id = _create_driver_profile(api_client, driver_headers)

    customer_token = _login(api_client, sms, "CUSTOMER")
    customer_headers = {"Authorization": f"Bearer {customer_token}"}
    ride_id = _create_ride(api_client, customer_headers)

    _record_driver_strike_directly(
        uuid.UUID(driver_id), ride_id=uuid.UUID(ride_id), reason="UNWILLING_TO_PROCEED"
    )

    response = api_client.get("/api/v1/drivers/me/strikes", headers=driver_headers)

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["driver_id"] == driver_id
    assert items[0]["ride_id"] == ride_id
    assert items[0]["reason"] == "UNWILLING_TO_PROCEED"
    assert "strike_id" in items[0]
    assert "created_at" in items[0]


def test_list_strikes_only_returns_the_callers_own(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_a_token = _login(api_client, sms, "DRIVER")
    driver_a_headers = {"Authorization": f"Bearer {driver_a_token}"}
    driver_a_id = _create_driver_profile(api_client, driver_a_headers)

    driver_b_token = _login(api_client, sms, "DRIVER")
    driver_b_headers = {"Authorization": f"Bearer {driver_b_token}"}
    _create_driver_profile(api_client, driver_b_headers)

    customer_token = _login(api_client, sms, "CUSTOMER")
    customer_headers = {"Authorization": f"Bearer {customer_token}"}
    ride_id = _create_ride(api_client, customer_headers)

    _record_driver_strike_directly(
        uuid.UUID(driver_a_id), ride_id=uuid.UUID(ride_id), reason="DRIVER_CANCELLATION"
    )

    response = api_client.get("/api/v1/drivers/me/strikes", headers=driver_b_headers)

    assert response.status_code == 200
    assert response.json()["data"]["items"] == []


def test_list_strikes_unauthenticated_is_rejected(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/drivers/me/strikes")
    assert response.status_code == 401


def test_list_strikes_customer_account_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "CUSTOMER")

    response = api_client.get(
        "/api/v1/drivers/me/strikes",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 403
