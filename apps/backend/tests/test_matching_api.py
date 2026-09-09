"""Integration tests: real HTTP layer (TestClient) + real Postgres +
real Redis, exercising POST /api/v1/drivers/me/location,
GET /api/v1/drivers/me/ride-offers, and
POST /api/v1/drivers/me/ride-offers/{offer_id}/reject end-to-end,
including the matching dispatch triggered by POST /api/v1/rides.

Setup helpers (login, driver eligibility) are copied from
tests/test_driver_availability_api.py — same "no shared test-helper
module" convention already used across this codebase's integration
tests.

Each test uses its own randomized base coordinate (see _random_point())
well outside any other test's search radius, so drivers/rides created by
earlier test runs (Redis GEO entries and ONLINE driver rows are never
cleaned up by this file — see modules/matching/__init__.py) can never be
mistaken for this test's own nearest-driver candidates.

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
from httpx import Response
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from core.config import settings
from core.database import SessionLocal
from main import app
from modules.admin.models import AdminUserORM
from modules.identity.dependencies import get_sms_provider_dependency
from modules.identity.security import decode_access_token
from modules.vehicle.repositories import SqlAlchemyVehicleDocumentRepository
from modules.vehicle.service import VehicleDocumentService
from modules.wallet.repositories import SqlAlchemyWalletRepository
from modules.wallet.service import WalletService


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
    """A base coordinate randomized well outside any other test's search
    radius (default 5km — a 0.2 degree jitter is roughly 20km) — see
    this module's docstring."""
    lat = 20.0 + secrets.randbelow(1000) / 100.0  # 20.00-29.99
    lng = 75.0 + secrets.randbelow(1000) / 100.0  # 75.00-84.99
    return lat, lng


def _nearby(point: tuple[float, float], *, offset: float = 0.001) -> dict[str, float]:
    """~100m away from `point` — well within the default 5km search
    radius."""
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


def _provision_admin(account_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        db.add(AdminUserORM(id=account_id, role="SUPER_ADMIN", status="ACTIVE"))
        db.commit()
    finally:
        db.close()


def _login_admin(api_client: TestClient, sms: CapturingSmsProvider) -> dict[str, str]:
    access_token = _login(api_client, sms, "ADMIN")
    account_id = _account_id_from_token(access_token)
    _provision_admin(account_id)
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
    api_client: TestClient, driver_headers: dict[str, str], document_type: str
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


def _make_driver_documents_valid(
    api_client: TestClient, driver_headers: dict[str, str]
) -> None:
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
    api_client: TestClient, admin_headers: dict[str, str], driver_id: str
) -> None:
    response = api_client.post(
        f"/api/v1/admin/drivers/{driver_id}/approve", headers=admin_headers
    )
    assert response.status_code == 200


def _approve_vehicle(
    api_client: TestClient, admin_headers: dict[str, str], vehicle_id: str
) -> None:
    response = api_client.post(
        f"/api/v1/admin/vehicles/{vehicle_id}/approve", headers=admin_headers
    )
    assert response.status_code == 200


def _new_online_eligible_driver(
    api_client: TestClient,
    sms: CapturingSmsProvider,
    admin_headers: dict[str, str],
    *,
    category: str = "CAB",
    cab_tier: str | None = None,
    location: dict[str, float],
) -> dict[str, str]:
    """Builds a driver that is fully eligible, ONLINE, with an ACTIVE
    vehicle of `category`, and a fresh location write — ready to receive
    a matching offer. Returns driver_headers. `cab_tier` defaults to
    "ECO" when category is CAB (ADR-0020 Decision 1) — pass it
    explicitly to test a specific tier."""
    if category == "CAB" and cab_tier is None:
        cab_tier = "ECO"
    driver_headers = _new_driver_with_profile(api_client, sms)
    driver_id = api_client.get("/api/v1/drivers/me", headers=driver_headers).json()[
        "data"
    ]["driver_id"]
    _make_driver_documents_valid(api_client, driver_headers)
    _approve_driver(api_client, admin_headers, driver_id)

    vehicle_body = {"category": category, "registration_number": _random_registration()}
    if cab_tier is not None:
        vehicle_body["cab_tier"] = cab_tier
    vehicle = api_client.post(
        "/api/v1/drivers/me/vehicles",
        json=vehicle_body,
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

    location_response = api_client.post(
        "/api/v1/drivers/me/location", json=location, headers=driver_headers
    )
    assert location_response.status_code == 200

    return driver_headers


def _get_driver_id(api_client: TestClient, driver_headers: dict[str, str]) -> str:
    response = api_client.get("/api/v1/drivers/me", headers=driver_headers)
    driver_id: str = response.json()["data"]["driver_id"]
    return driver_id


def _seed_wallet_balance(driver_id: str, amount: Decimal) -> None:
    """Same pattern tests/test_wallet_api.py already uses — no recharge
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


def _login_as_new_customer(api_client: TestClient, sms: CapturingSmsProvider) -> str:
    access_token = _login(api_client, sms, "CUSTOMER")
    return access_token


def _create_ride(
    api_client: TestClient,
    customer_headers: dict[str, str],
    *,
    pickup: dict[str, float],
    destination: dict[str, float],
    category: str = "CAB",
    cab_tier: str | None = None,
) -> dict[str, object]:
    """`cab_tier` defaults to "ECO" when category is CAB (ADR-0020
    Decision 1) — pass it explicitly to test a specific tier."""
    if category == "CAB" and cab_tier is None:
        cab_tier = "ECO"
    response = api_client.post(
        "/api/v1/rides",
        json={
            "pickup": pickup,
            "destination": destination,
            "vehicle_category": category,
            "cab_tier": cab_tier,
            "payment_method": "ONLINE",
        },
        headers={**customer_headers, "Idempotency-Key": f"ride-{uuid.uuid4()}"},
    )
    assert response.status_code == 201
    data: dict[str, object] = response.json()["data"]
    return data


# --- Driver Location Update ------------------------------------------------


def test_update_location_succeeds_when_online_with_active_vehicle(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    driver_headers = _new_online_eligible_driver(
        api_client, sms, admin_headers, location=_nearby(point)
    )

    response = api_client.post(
        "/api/v1/drivers/me/location",
        json=_nearby(point, offset=0.002),
        headers=driver_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "OK"


def test_update_location_rejected_when_not_online(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_headers = _new_driver_with_profile(api_client, sms)
    point = _random_point()

    response = api_client.post(
        "/api/v1/drivers/me/location", json=_nearby(point), headers=driver_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DRIVER_NOT_ONLINE"


def test_update_location_rejected_invalid_coordinates(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_headers = _new_driver_with_profile(api_client, sms)

    response = api_client.post(
        "/api/v1/drivers/me/location",
        json={"latitude": 999.0, "longitude": 85.1376},
        headers=driver_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_update_location_unauthenticated_is_rejected(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/drivers/me/location", json={"latitude": 25.59, "longitude": 85.13}
    )
    assert response.status_code == 401


# --- Ride Creation -> Matching Dispatch ------------------------------------


def test_ride_creation_dispatches_offer_to_the_online_eligible_driver(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    driver_headers = _new_online_eligible_driver(
        api_client, sms, admin_headers, location=_nearby(point)
    )

    customer_token = _login_as_new_customer(api_client, sms)
    ride = _create_ride(
        api_client,
        {"Authorization": f"Bearer {customer_token}"},
        pickup=_nearby(point, offset=0.0005),
        destination=_nearby(point, offset=0.02),
    )
    assert ride["status"] == "SEARCHING"

    offers = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=driver_headers
    ).json()["data"]["offers"]

    assert len(offers) == 1
    assert offers[0]["ride_id"] == ride["ride_id"]
    assert offers[0]["status"] == "PENDING"
    assert offers[0]["pickup"] is not None


def test_ride_creation_with_no_eligible_driver_leaves_ride_searching(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    point = _random_point()
    customer_token = _login_as_new_customer(api_client, sms)

    ride = _create_ride(
        api_client,
        {"Authorization": f"Bearer {customer_token}"},
        pickup=_nearby(point),
        destination=_nearby(point, offset=0.02),
    )

    assert ride["status"] == "SEARCHING"


def test_ride_creation_only_offers_drivers_of_the_matching_category(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    # Only a BIKE driver is online; the ride requests CAB.
    _new_online_eligible_driver(
        api_client, sms, admin_headers, category="BIKE", location=_nearby(point)
    )

    customer_token = _login_as_new_customer(api_client, sms)
    ride = _create_ride(
        api_client,
        {"Authorization": f"Bearer {customer_token}"},
        pickup=_nearby(point),
        destination=_nearby(point, offset=0.02),
        category="CAB",
    )

    assert ride["status"] == "SEARCHING"


def test_ride_creation_only_offers_drivers_of_the_matching_cab_tier(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """ADR-0020 Decision 1: a customer requesting PREMIUM must not be
    offered an ECO-tier driver, even though both are CAB."""
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    eco_driver_headers = _new_online_eligible_driver(
        api_client, sms, admin_headers, cab_tier="ECO", location=_nearby(point)
    )

    customer_token = _login_as_new_customer(api_client, sms)
    _create_ride(
        api_client,
        {"Authorization": f"Bearer {customer_token}"},
        pickup=_nearby(point),
        destination=_nearby(point, offset=0.02),
        cab_tier="PREMIUM",
    )

    offers = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=eco_driver_headers
    ).json()["data"]["offers"]
    assert offers == []


def test_ride_creation_offers_a_driver_of_the_matching_cab_tier(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    premium_driver_headers = _new_online_eligible_driver(
        api_client, sms, admin_headers, cab_tier="PREMIUM", location=_nearby(point)
    )

    customer_token = _login_as_new_customer(api_client, sms)
    _create_ride(
        api_client,
        {"Authorization": f"Bearer {customer_token}"},
        pickup=_nearby(point),
        destination=_nearby(point, offset=0.02),
        cab_tier="PREMIUM",
    )

    offers = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=premium_driver_headers
    ).json()["data"]["offers"]
    assert len(offers) == 1


# --- Get Current Offers / Reject --------------------------------------------


def test_get_offers_unauthenticated_is_rejected(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/drivers/me/ride-offers")
    assert response.status_code == 401


def test_customer_cannot_access_driver_offer_endpoints(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    customer_token = _login_as_new_customer(api_client, sms)
    response = api_client.get(
        "/api/v1/drivers/me/ride-offers",
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert response.status_code == 403


def test_reject_offer_dispatches_to_the_next_eligible_driver(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    first_driver = _new_online_eligible_driver(
        api_client, sms, admin_headers, location=_nearby(point, offset=0.0005)
    )
    second_driver = _new_online_eligible_driver(
        api_client, sms, admin_headers, location=_nearby(point, offset=0.0006)
    )

    customer_token = _login_as_new_customer(api_client, sms)
    ride = _create_ride(
        api_client,
        {"Authorization": f"Bearer {customer_token}"},
        pickup=_nearby(point),
        destination=_nearby(point, offset=0.02),
    )

    first_offers = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=first_driver
    ).json()["data"]["offers"]
    second_offers_before = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=second_driver
    ).json()["data"]["offers"]
    # Exactly one of the two drivers received the initial offer.
    assert len(first_offers) + len(second_offers_before) == 1

    offered_driver, other_driver = (
        (first_driver, second_driver) if first_offers else (second_driver, first_driver)
    )
    offer_id = (first_offers or second_offers_before)[0]["offer_id"]

    reject_response = api_client.post(
        f"/api/v1/drivers/me/ride-offers/{offer_id}/reject", headers=offered_driver
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["data"]["status"] == "REJECTED"

    other_offers = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=other_driver
    ).json()["data"]["offers"]
    assert len(other_offers) == 1
    assert other_offers[0]["ride_id"] == ride["ride_id"]


def test_reject_offer_not_found_for_another_drivers_offer(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    offered_driver = _new_online_eligible_driver(
        api_client, sms, admin_headers, location=_nearby(point)
    )
    other_driver = _new_online_eligible_driver(
        api_client, sms, admin_headers, location=_nearby(point, offset=0.05)
    )
    customer_token = _login_as_new_customer(api_client, sms)
    _create_ride(
        api_client,
        {"Authorization": f"Bearer {customer_token}"},
        pickup=_nearby(point),
        destination=_nearby(point, offset=0.02),
    )

    offers = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=offered_driver
    ).json()["data"]["offers"]
    assert len(offers) == 1

    response = api_client.post(
        f"/api/v1/drivers/me/ride-offers/{offers[0]['offer_id']}/reject",
        headers=other_driver,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_reject_unknown_offer_returns_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_headers = _new_driver_with_profile(api_client, sms)
    response = api_client.post(
        f"/api/v1/drivers/me/ride-offers/{uuid.uuid4()}/reject", headers=driver_headers
    )
    assert response.status_code == 404


def test_reject_already_rejected_offer_returns_offer_already_responded(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    driver_headers = _new_online_eligible_driver(
        api_client, sms, admin_headers, location=_nearby(point)
    )
    customer_token = _login_as_new_customer(api_client, sms)
    _create_ride(
        api_client,
        {"Authorization": f"Bearer {customer_token}"},
        pickup=_nearby(point),
        destination=_nearby(point, offset=0.02),
    )
    offers = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=driver_headers
    ).json()["data"]["offers"]
    offer_id = offers[0]["offer_id"]
    first = api_client.post(
        f"/api/v1/drivers/me/ride-offers/{offer_id}/reject", headers=driver_headers
    )
    assert first.status_code == 200

    second = api_client.post(
        f"/api/v1/drivers/me/ride-offers/{offer_id}/reject", headers=driver_headers
    )

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "OFFER_ALREADY_RESPONDED"


def test_expired_offer_is_removed_from_get_offers_and_rematched(
    api_client: TestClient, sms: CapturingSmsProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-0011 Decision 2 (lazy expiry). Uses a negative TTL so the
    offer is already expired the moment it's created — no real sleep
    needed."""
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    first_driver = _new_online_eligible_driver(
        api_client, sms, admin_headers, location=_nearby(point, offset=0.0005)
    )
    second_driver = _new_online_eligible_driver(
        api_client, sms, admin_headers, location=_nearby(point, offset=0.0006)
    )

    monkeypatch.setattr(settings, "MATCHING_OFFER_TTL_SECONDS", -1)
    customer_token = _login_as_new_customer(api_client, sms)
    ride = _create_ride(
        api_client,
        {"Authorization": f"Bearer {customer_token}"},
        pickup=_nearby(point),
        destination=_nearby(point, offset=0.02),
    )
    monkeypatch.undo()

    # First pass: whichever driver actually held the (already-expired)
    # initial offer has it lazily expired here, and a rematch is
    # dispatched to the *other* driver — which that other driver's own
    # GET call in this same pass cannot see yet (the rematch happens
    # after that driver's still_pending snapshot is already computed —
    # see modules/matching/router.py::list_my_offers). A second,
    # settling pass picks it up.
    api_client.get("/api/v1/drivers/me/ride-offers", headers=first_driver)
    api_client.get("/api/v1/drivers/me/ride-offers", headers=second_driver)

    first_offers = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=first_driver
    ).json()["data"]["offers"]
    second_offers = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=second_driver
    ).json()["data"]["offers"]

    total_pending = len(first_offers) + len(second_offers)
    assert total_pending == 1
    if second_offers:
        assert second_offers[0]["ride_id"] == ride["ride_id"]
    else:
        assert first_offers[0]["ride_id"] == ride["ride_id"]


# --- Ride Cancellation cancels outstanding offers (Phase 3 / Task 3.3) -----


def test_cancelling_a_ride_cancels_its_outstanding_pending_offer(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    driver_headers = _new_online_eligible_driver(
        api_client, sms, admin_headers, location=_nearby(point)
    )
    customer_token = _login_as_new_customer(api_client, sms)
    ride = _create_ride(
        api_client,
        {"Authorization": f"Bearer {customer_token}"},
        pickup=_nearby(point),
        destination=_nearby(point, offset=0.02),
    )
    offers_before = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=driver_headers
    ).json()["data"]["offers"]
    assert len(offers_before) == 1
    offer_id = offers_before[0]["offer_id"]

    cancel_response = api_client.post(
        f"/api/v1/rides/{ride['ride_id']}/cancel",
        json={"reason": "CUSTOMER_CHANGED_PLANS"},
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert cancel_response.status_code == 200

    offers_after = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=driver_headers
    ).json()["data"]["offers"]
    assert offers_after == []

    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT status FROM matching.ride_offers WHERE id = :id"),
            {"id": offer_id},
        ).fetchone()
        assert row is not None
        assert row.status == "CANCELLED"
    finally:
        db.close()


# --- Accept Offer (Phase 3 / Task 3.4, ADR-0014) ----------------------------


def _accept_offer(
    api_client: TestClient,
    offer_id: str,
    driver_headers: dict[str, str],
    *,
    idempotency_key: str | None = None,
) -> Response:
    return api_client.post(
        f"/api/v1/drivers/me/ride-offers/{offer_id}/accept",
        headers={
            **driver_headers,
            "Idempotency-Key": idempotency_key or f"accept-{uuid.uuid4()}",
        },
    )


def _create_ride_with_one_offer(
    api_client: TestClient,
    sms: CapturingSmsProvider,
    admin_headers: dict[str, str],
    *,
    point: tuple[float, float],
) -> tuple[dict[str, object], dict[str, str], dict[str, object]]:
    """Returns (ride, driver_headers, offer) for a ride with exactly one
    online eligible driver already holding the PENDING offer."""
    driver_headers = _new_online_eligible_driver(
        api_client, sms, admin_headers, location=_nearby(point)
    )
    customer_token = _login_as_new_customer(api_client, sms)
    ride = _create_ride(
        api_client,
        {"Authorization": f"Bearer {customer_token}"},
        pickup=_nearby(point),
        destination=_nearby(point, offset=0.02),
    )
    offers = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=driver_headers
    ).json()["data"]["offers"]
    assert len(offers) == 1
    return ride, driver_headers, offers[0]


def test_accept_offer_debits_fee_and_assigns_driver_to_the_ride(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    ride, driver_headers, offer = _create_ride_with_one_offer(
        api_client, sms, admin_headers, point=point
    )
    driver_id = _get_driver_id(api_client, driver_headers)
    _seed_wallet_balance(driver_id, Decimal("100.00"))  # CAB fee = ₹10 (ADR-0020)

    response = _accept_offer(api_client, str(offer["offer_id"]), driver_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["offer_id"] == offer["offer_id"]
    assert data["ride_id"] == ride["ride_id"]
    assert data["status"] == "ACCEPTED"
    assert data["wallet_balance"] == 90.0

    db = SessionLocal()
    try:
        ride_row = db.execute(
            text(
                "SELECT status, driver_id, vehicle_id, accepted_at "
                "FROM ride.rides WHERE id = :id"
            ),
            {"id": ride["ride_id"]},
        ).fetchone()
        assert ride_row is not None
        assert ride_row.status == "ACCEPTED"
        assert str(ride_row.driver_id) == driver_id
        assert ride_row.vehicle_id is not None
        assert ride_row.accepted_at is not None

        offer_row = db.execute(
            text("SELECT status FROM matching.ride_offers WHERE id = :id"),
            {"id": offer["offer_id"]},
        ).fetchone()
        assert offer_row is not None
        assert offer_row.status == "ACCEPTED"

        history_rows = db.execute(
            text(
                "SELECT from_status, to_status FROM ride.state_history "
                "WHERE ride_id = :id AND to_status = 'ACCEPTED'"
            ),
            {"id": ride["ride_id"]},
        ).fetchall()
        assert len(history_rows) == 1
        assert history_rows[0].from_status == "SEARCHING"

        ledger_row = db.execute(
            text(
                "SELECT transaction_type, direction, amount, ride_id "
                "FROM wallet.transactions WHERE driver_id = :driver_id"
            ),
            {"driver_id": driver_id},
        ).fetchone()
        assert ledger_row is not None
        assert ledger_row.transaction_type == "PLATFORM_FEE"
        assert ledger_row.direction == "DEBIT"
        assert ledger_row.amount == Decimal("10.00")
        assert str(ledger_row.ride_id) == ride["ride_id"]
    finally:
        db.close()


def test_accept_offer_uses_the_published_platform_fee_rule(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """ADR-0045: Accept Offer reads the live-published platform fee
    rule instead of the hardcoded constant. Publishing a rule here
    replaces the globally-active CAB fee (there is only ever one; no
    collision-free test-only vehicle_category exists), so the test
    restores the seeded ₹10 baseline in a `finally` — the sibling test
    above (and any future run) depends on that being the active fee."""
    admin_headers = _login_admin(api_client, sms)

    def _publish_cab_fee(fee_amount: int) -> None:
        rule_id = api_client.post(
            "/api/v1/admin/platform-fee-rules",
            json={"vehicle_category": "CAB", "fee_amount": fee_amount},
            headers=admin_headers,
        ).json()["data"]["rule_id"]
        api_client.post(
            f"/api/v1/admin/platform-fee-rules/{rule_id}/publish",
            json={},
            headers=admin_headers,
        )

    _publish_cab_fee(25)
    try:
        point = _random_point()
        ride, driver_headers, offer = _create_ride_with_one_offer(
            api_client, sms, admin_headers, point=point
        )
        driver_id = _get_driver_id(api_client, driver_headers)
        _seed_wallet_balance(driver_id, Decimal("100.00"))

        response = _accept_offer(api_client, str(offer["offer_id"]), driver_headers)

        assert response.status_code == 200
        assert response.json()["data"]["wallet_balance"] == 75.0

        db = SessionLocal()
        try:
            ledger_row = db.execute(
                text(
                    "SELECT amount FROM wallet.transactions "
                    "WHERE driver_id = :driver_id AND transaction_type = "
                    "'PLATFORM_FEE'"
                ),
                {"driver_id": driver_id},
            ).fetchone()
            assert ledger_row is not None
            assert ledger_row.amount == Decimal("25.00")
        finally:
            db.close()
    finally:
        _publish_cab_fee(10)


def test_accept_offer_writes_ride_accepted_and_wallet_debited_outbox_events(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Phase 3 / Event & Outbox Foundation (ADR-0017)."""
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    ride, driver_headers, offer = _create_ride_with_one_offer(
        api_client, sms, admin_headers, point=point
    )
    driver_id = _get_driver_id(api_client, driver_headers)
    _seed_wallet_balance(driver_id, Decimal("100.00"))

    response = _accept_offer(api_client, str(offer["offer_id"]), driver_headers)
    assert response.status_code == 200

    db = SessionLocal()
    try:
        ride_accepted = db.execute(
            text(
                "SELECT payload FROM shared.outbox_events "
                "WHERE aggregate_id = :id AND event_type = 'ride.accepted'"
            ),
            {"id": ride["ride_id"]},
        ).fetchone()
        assert ride_accepted is not None
        assert ride_accepted.payload["data"]["driver_id"] == driver_id
        assert ride_accepted.payload["aggregate_type"] == "ride"

        wallet_debited = db.execute(
            text(
                "SELECT payload FROM shared.outbox_events "
                "WHERE aggregate_id = :id AND event_type = 'wallet.debited'"
            ),
            {"id": driver_id},
        ).fetchone()
        assert wallet_debited is not None
        assert wallet_debited.payload["data"]["amount"] == 10.0
        assert wallet_debited.payload["data"]["transaction_type"] == "PLATFORM_FEE"

        # ADR-0034 — the customer gets a best-effort IN_APP notification
        # once acceptance is durable.
        notification = db.execute(
            text(
                "SELECT d.channel, d.template_key, d.status FROM "
                "notification.deliveries d JOIN ride.rides r "
                "ON r.customer_id = d.user_id "
                "WHERE r.id = :ride_id AND d.template_key = 'RIDE_ACCEPTED'"
            ),
            {"ride_id": ride["ride_id"]},
        ).fetchone()
        assert notification is not None
        assert notification.channel == "IN_APP"
        assert notification.status == "SENT"
    finally:
        db.close()


def test_accept_offer_insufficient_balance_leaves_ride_and_offer_untouched(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    ride, driver_headers, offer = _create_ride_with_one_offer(
        api_client, sms, admin_headers, point=point
    )
    driver_id = _get_driver_id(api_client, driver_headers)
    _seed_wallet_balance(driver_id, Decimal("5.00"))  # CAB fee = ₹10 (ADR-0020)

    response = _accept_offer(api_client, str(offer["offer_id"]), driver_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INSUFFICIENT_WALLET_BALANCE"

    db = SessionLocal()
    try:
        ride_row = db.execute(
            text("SELECT status FROM ride.rides WHERE id = :id"),
            {"id": ride["ride_id"]},
        ).fetchone()
        assert ride_row is not None
        assert ride_row.status == "SEARCHING"

        offer_row = db.execute(
            text("SELECT status FROM matching.ride_offers WHERE id = :id"),
            {"id": offer["offer_id"]},
        ).fetchone()
        assert offer_row is not None
        assert offer_row.status == "PENDING"

        balance = db.execute(
            text("SELECT balance FROM wallet.wallets WHERE driver_id = :id"),
            {"id": driver_id},
        ).scalar()
        assert balance == Decimal("5.00")  # untouched — no partial debit
    finally:
        db.close()


def test_accept_unknown_offer_returns_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_headers = _new_driver_with_profile(api_client, sms)
    response = _accept_offer(api_client, str(uuid.uuid4()), driver_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_accept_another_drivers_offer_returns_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    _, offered_driver, offer = _create_ride_with_one_offer(
        api_client, sms, admin_headers, point=point
    )
    other_driver = _new_driver_with_profile(api_client, sms)

    response = _accept_offer(api_client, str(offer["offer_id"]), other_driver)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_accept_already_accepted_offer_returns_offer_already_responded(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    _, driver_headers, offer = _create_ride_with_one_offer(
        api_client, sms, admin_headers, point=point
    )
    driver_id = _get_driver_id(api_client, driver_headers)
    _seed_wallet_balance(driver_id, Decimal("100.00"))
    first = _accept_offer(api_client, str(offer["offer_id"]), driver_headers)
    assert first.status_code == 200

    second = _accept_offer(api_client, str(offer["offer_id"]), driver_headers)

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "OFFER_ALREADY_RESPONDED"


def test_accept_expired_offer_returns_offer_expired(
    api_client: TestClient, sms: CapturingSmsProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same negative-TTL technique as the lazy-expiry GET test above."""
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    driver_headers = _new_online_eligible_driver(
        api_client, sms, admin_headers, location=_nearby(point)
    )
    driver_id = _get_driver_id(api_client, driver_headers)
    _seed_wallet_balance(driver_id, Decimal("100.00"))
    customer_token = _login_as_new_customer(api_client, sms)

    monkeypatch.setattr(settings, "MATCHING_OFFER_TTL_SECONDS", -1)
    ride = _create_ride(
        api_client,
        {"Authorization": f"Bearer {customer_token}"},
        pickup=_nearby(point),
        destination=_nearby(point, offset=0.02),
    )
    monkeypatch.undo()

    db = SessionLocal()
    try:
        offer_id = db.execute(
            text("SELECT id FROM matching.ride_offers WHERE ride_id = :ride_id"),
            {"ride_id": ride["ride_id"]},
        ).scalar()
    finally:
        db.close()
    assert offer_id is not None

    response = _accept_offer(api_client, str(offer_id), driver_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "OFFER_EXPIRED"

    db = SessionLocal()
    try:
        offer_row = db.execute(
            text("SELECT status FROM matching.ride_offers WHERE id = :id"),
            {"id": str(offer_id)},
        ).fetchone()
        assert offer_row is not None
        assert offer_row.status == "EXPIRED"
    finally:
        db.close()


def test_accept_offer_idempotency_key_replay_does_not_debit_twice(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    _, driver_headers, offer = _create_ride_with_one_offer(
        api_client, sms, admin_headers, point=point
    )
    driver_id = _get_driver_id(api_client, driver_headers)
    _seed_wallet_balance(driver_id, Decimal("100.00"))
    key = f"accept-{uuid.uuid4()}"

    first = _accept_offer(
        api_client, str(offer["offer_id"]), driver_headers, idempotency_key=key
    )
    second = _accept_offer(
        api_client, str(offer["offer_id"]), driver_headers, idempotency_key=key
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"] == second.json()["data"]

    db = SessionLocal()
    try:
        balance = db.execute(
            text("SELECT balance FROM wallet.wallets WHERE driver_id = :id"),
            {"id": driver_id},
        ).scalar()
        assert balance == Decimal("90.00")  # debited exactly once, not twice
    finally:
        db.close()


def test_accept_offer_reusing_an_idempotency_key_for_a_different_offer_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Targeted negative-idempotency test (security review, 2026-09-03)
    — the sibling test above only proves the *same*-body replay case
    (same offer_id, same key -> cached response, no double-debit); this
    proves the request_hash mismatch path actually rejects a *reused*
    key against a *different* offer_id, rather than silently accepting
    the second offer or replaying the first offer's cached result
    against it. `IdempotencyStore.reserve()`'s own hash comparison is
    what this exercises for real, through the actual HTTP endpoint."""
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    _ride1, driver_headers, offer1 = _create_ride_with_one_offer(
        api_client, sms, admin_headers, point=point
    )
    driver_id = _get_driver_id(api_client, driver_headers)
    _seed_wallet_balance(driver_id, Decimal("100.00"))
    shared_key = f"accept-{uuid.uuid4()}"

    first = _accept_offer(
        api_client, str(offer1["offer_id"]), driver_headers, idempotency_key=shared_key
    )
    assert first.status_code == 200

    # Still online (accepting a ride doesn't take a driver offline —
    # confirmed against modules/matching's own geo index behavior), so
    # a second, independently-created ride at the same point dispatches
    # its offer to this same driver.
    customer_token = _login_as_new_customer(api_client, sms)
    ride2 = _create_ride(
        api_client,
        {"Authorization": f"Bearer {customer_token}"},
        pickup=_nearby(point),
        destination=_nearby(point, offset=0.02),
    )
    offers = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=driver_headers
    ).json()["data"]["offers"]
    offer2 = next(o for o in offers if o["ride_id"] == ride2["ride_id"])

    second = _accept_offer(
        api_client, str(offer2["offer_id"]), driver_headers, idempotency_key=shared_key
    )

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSE"

    db = SessionLocal()
    try:
        # offer2/ride2 must be completely untouched — the reused key was
        # rejected before any state change, not silently applied to it.
        ride2_row = db.execute(
            text("SELECT status FROM ride.rides WHERE id = :id"),
            {"id": ride2["ride_id"]},
        ).fetchone()
        assert ride2_row is not None
        assert ride2_row.status == "SEARCHING"

        offer2_row = db.execute(
            text("SELECT status FROM matching.ride_offers WHERE id = :id"),
            {"id": offer2["offer_id"]},
        ).fetchone()
        assert offer2_row is not None
        assert offer2_row.status == "PENDING"

        # Only the first accept's debit ever happened.
        balance = db.execute(
            text("SELECT balance FROM wallet.wallets WHERE driver_id = :id"),
            {"id": driver_id},
        ).scalar()
        assert balance == Decimal("90.00")
    finally:
        db.close()


def test_concurrent_accept_attempts_on_the_same_offer_debit_exactly_once(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """BR-013: prevent duplicate ride acceptance / double deduction.
    Fires two real HTTP accept requests for the SAME offer (different
    Idempotency-Key values, simulating two independent double-taps) from
    two threads as close to simultaneously as possible — same technique
    as tests/test_vehicle_api.py's BR-122 concurrent-activation test and
    tests/test_wallet_api.py's concurrent-debit tests. Exactly one must
    succeed; the wallet row lock (acquired first, before either request
    re-validates offer/ride status) is what serializes them — see
    modules/matching/router.py's module docstring."""
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    ride, driver_headers, offer = _create_ride_with_one_offer(
        api_client, sms, admin_headers, point=point
    )
    driver_id = _get_driver_id(api_client, driver_headers)
    _seed_wallet_balance(driver_id, Decimal("100.00"))

    results: list[int] = []

    def _attempt() -> None:
        response = _accept_offer(api_client, str(offer["offer_id"]), driver_headers)
        results.append(response.status_code)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(_attempt) for _ in range(2)]
        for future in futures:
            future.result()

    assert sorted(results) == [200, 409]

    db = SessionLocal()
    try:
        balance = db.execute(
            text("SELECT balance FROM wallet.wallets WHERE driver_id = :id"),
            {"id": driver_id},
        ).scalar()
        assert balance == Decimal("90.00")  # debited exactly once

        ledger_count = db.execute(
            text(
                "SELECT COUNT(*) FROM wallet.transactions "
                "WHERE driver_id = :id AND transaction_type = 'PLATFORM_FEE'"
            ),
            {"id": driver_id},
        ).scalar()
        assert ledger_count == 1

        history_count = db.execute(
            text(
                "SELECT COUNT(*) FROM ride.state_history "
                "WHERE ride_id = :id AND to_status = 'ACCEPTED'"
            ),
            {"id": ride["ride_id"]},
        ).scalar()
        assert history_count == 1  # no duplicate acceptance record
    finally:
        db.close()


# --- Post-acceptance cancellation (Phase 3 / Task 3.5-3.6, ADR-0015/16) -----
#
# Setup needs a full ride -> offer -> accept flow, which this file already
# has all the machinery for (unlike tests/test_ride_api.py, which only
# exercises SEARCHING-state behavior) — reused here rather than duplicated,
# same "no shared test-helper module, but reuse within a file" convention.


def _accepted_ride_with_customer_and_driver(
    api_client: TestClient,
    sms: CapturingSmsProvider,
    admin_headers: dict[str, str],
    *,
    point: tuple[float, float],
) -> tuple[dict[str, object], dict[str, str], dict[str, str], str]:
    """Returns (ride, customer_headers, driver_headers, driver_id) for a
    ride already accepted by an eligible driver with a seeded ₹100
    wallet balance (CAB fee = ₹10, ADR-0020, leaving ₹90)."""
    driver_headers = _new_online_eligible_driver(
        api_client, sms, admin_headers, location=_nearby(point)
    )
    customer_token = _login_as_new_customer(api_client, sms)
    customer_headers = {"Authorization": f"Bearer {customer_token}"}
    ride = _create_ride(
        api_client,
        customer_headers,
        pickup=_nearby(point),
        destination=_nearby(point, offset=0.02),
    )
    offers = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=driver_headers
    ).json()["data"]["offers"]
    assert len(offers) == 1
    driver_id = _get_driver_id(api_client, driver_headers)
    _seed_wallet_balance(driver_id, Decimal("100.00"))
    accept_response = _accept_offer(
        api_client, str(offers[0]["offer_id"]), driver_headers
    )
    assert accept_response.status_code == 200
    return ride, customer_headers, driver_headers, driver_id


def _backdate_accepted_at(ride_id: str, *, minutes_ago: int) -> None:
    """Simulates time having passed since acceptance (BR-046's 2-minute
    grace period) — same "seed state no endpoint produces yet" pattern
    used throughout this codebase (e.g. _mark_driver_document_approved)."""
    db = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE ride.rides SET accepted_at = accepted_at - "
                "(:minutes || ' minutes')::interval WHERE id = :id"
            ),
            {"minutes": minutes_ago, "id": ride_id},
        )
        db.commit()
    finally:
        db.close()


def _wallet_balance(driver_id: str) -> Decimal:
    db = SessionLocal()
    try:
        balance = db.execute(
            text("SELECT balance FROM wallet.wallets WHERE driver_id = :id"),
            {"id": driver_id},
        ).scalar()
        assert balance is not None
        return balance
    finally:
        db.close()


def test_cancel_accepted_ride_within_grace_period_is_free_and_refunds_driver(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    ride, customer_headers, _, driver_id = _accepted_ride_with_customer_and_driver(
        api_client, sms, admin_headers, point=point
    )
    assert _wallet_balance(driver_id) == Decimal("90.00")  # ₹10 CAB fee debited

    response = api_client.post(
        f"/api/v1/rides/{ride['ride_id']}/cancel",
        json={"reason": "CHANGED_MY_MIND"},
        headers=customer_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["ride_status"] == "CANCELLED"
    assert data["charge"] == {"amount": 0, "currency": "INR"}
    assert _wallet_balance(driver_id) == Decimal("100.00")  # fee refunded

    db = SessionLocal()
    try:
        penalty_count = db.execute(
            text("SELECT COUNT(*) FROM penalty.penalties WHERE ride_id = :id"),
            {"id": ride["ride_id"]},
        ).scalar()
        assert penalty_count == 0  # grace period — no penalty record at all
    finally:
        db.close()


def test_cancel_accepted_ride_outside_grace_first_qualifying_is_free_but_recorded(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    ride, customer_headers, _, driver_id = _accepted_ride_with_customer_and_driver(
        api_client, sms, admin_headers, point=point
    )
    _backdate_accepted_at(str(ride["ride_id"]), minutes_ago=10)

    response = api_client.post(
        f"/api/v1/rides/{ride['ride_id']}/cancel",
        json={"reason": "CHANGED_MY_MIND"},
        headers=customer_headers,
    )

    assert response.status_code == 200
    charge = response.json()["data"]["charge"]
    assert charge is not None
    assert charge["amount"] == 0
    assert "expires_at" not in charge  # BR-049 (ADR-0069): never expires
    assert _wallet_balance(driver_id) == Decimal("100.00")  # still refunded

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT id, amount, status FROM penalty.penalties WHERE ride_id = :id"
            ),
            {"id": ride["ride_id"]},
        ).fetchone()
        assert row is not None
        assert row.amount == Decimal("0.00")
        assert row.status == "SETTLED"
        # ADR-0029 Decision 3 — present even for the ₹0 first-qualifying
        # case, since a real penalty.penalties row still exists for it.
        assert charge["penalty_id"] == str(row.id)

        # ride.cancelled and wallet.credited are always written; per
        # state-machines.md §12/ADR-0015 §3, penalty.applied is NOT —
        # ₹0 is not "a penalty [that] actually exists" from an outside
        # observer's perspective, even though the row above still is.
        ride_cancelled = db.execute(
            text(
                "SELECT payload FROM shared.outbox_events "
                "WHERE aggregate_id = :id AND event_type = 'ride.cancelled'"
            ),
            {"id": ride["ride_id"]},
        ).fetchone()
        assert ride_cancelled is not None
        assert ride_cancelled.payload["data"]["cancelled_by"] == "CUSTOMER"

        wallet_credited_count = db.execute(
            text(
                "SELECT COUNT(*) FROM shared.outbox_events "
                "WHERE aggregate_id = :id AND event_type = 'wallet.credited'"
            ),
            {"id": driver_id},
        ).scalar()
        assert wallet_credited_count == 1

        penalty_applied_count = db.execute(
            text(
                "SELECT COUNT(*) FROM shared.outbox_events "
                "WHERE aggregate_type = 'penalty' AND event_type = 'penalty.applied' "
                "AND payload->'data'->>'ride_id' = :ride_id"
            ),
            {"ride_id": ride["ride_id"]},
        ).scalar()
        assert penalty_applied_count == 0
    finally:
        db.close()


def test_cancel_accepted_ride_second_qualifying_charges_fifteen(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)

    # First qualifying cancellation, for the SAME customer — do it by
    # logging in that customer once and reusing their token across two
    # separate ride+driver setups.
    point_a = _random_point()
    driver_headers_a = _new_online_eligible_driver(
        api_client, sms, admin_headers, location=_nearby(point_a)
    )
    customer_token = _login_as_new_customer(api_client, sms)
    customer_headers = {"Authorization": f"Bearer {customer_token}"}
    ride_a = _create_ride(
        api_client,
        customer_headers,
        pickup=_nearby(point_a),
        destination=_nearby(point_a, offset=0.02),
    )
    offers_a = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=driver_headers_a
    ).json()["data"]["offers"]
    driver_id_a = _get_driver_id(api_client, driver_headers_a)
    _seed_wallet_balance(driver_id_a, Decimal("100.00"))
    assert (
        _accept_offer(
            api_client, str(offers_a[0]["offer_id"]), driver_headers_a
        ).status_code
        == 200
    )
    _backdate_accepted_at(str(ride_a["ride_id"]), minutes_ago=10)
    first = api_client.post(
        f"/api/v1/rides/{ride_a['ride_id']}/cancel",
        json={"reason": "x"},
        headers=customer_headers,
    )
    assert first.status_code == 200
    assert first.json()["data"]["charge"]["amount"] == 0

    # Second qualifying cancellation, same customer, a new ride/driver.
    point_b = _random_point()
    driver_headers_b = _new_online_eligible_driver(
        api_client, sms, admin_headers, location=_nearby(point_b)
    )
    ride_b = _create_ride(
        api_client,
        customer_headers,
        pickup=_nearby(point_b),
        destination=_nearby(point_b, offset=0.02),
    )
    offers_b = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=driver_headers_b
    ).json()["data"]["offers"]
    driver_id_b = _get_driver_id(api_client, driver_headers_b)
    _seed_wallet_balance(driver_id_b, Decimal("100.00"))
    assert (
        _accept_offer(
            api_client, str(offers_b[0]["offer_id"]), driver_headers_b
        ).status_code
        == 200
    )
    _backdate_accepted_at(str(ride_b["ride_id"]), minutes_ago=10)

    second = api_client.post(
        f"/api/v1/rides/{ride_b['ride_id']}/cancel",
        json={"reason": "x"},
        headers=customer_headers,
    )

    assert second.status_code == 200
    charge = second.json()["data"]["charge"]
    assert charge["amount"] == 15.0
    assert _wallet_balance(driver_id_b) == Decimal("100.00")  # still refunded

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT id, amount, status FROM penalty.penalties WHERE ride_id = :id"
            ),
            {"id": ride_b["ride_id"]},
        ).fetchone()
        assert row is not None
        assert row.amount == Decimal("15.00")
        assert row.status == "OUTSTANDING"
        # ADR-0029 Decision 3 — the customer's own reference for later
        # disputing this specific penalty via POST /api/v1/support/cases.
        assert charge["penalty_id"] == str(row.id)

        # Unlike the ₹0 first-qualifying case, a real ₹15 charge DOES
        # publish penalty.applied (state-machines.md §12/ADR-0015 §3).
        penalty_applied = db.execute(
            text(
                "SELECT payload FROM shared.outbox_events "
                "WHERE aggregate_type = 'penalty' AND event_type = 'penalty.applied' "
                "AND payload->'data'->>'ride_id' = :ride_id"
            ),
            {"ride_id": ride_b["ride_id"]},
        ).fetchone()
        assert penalty_applied is not None
        assert penalty_applied.payload["data"]["amount"] == 15.0
    finally:
        db.close()


def test_customer_disputes_a_penalty_and_admin_waives_it(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Phase 13 (Dispute-as-Support, ADR-0029) end-to-end: a customer
    files domain-design.md §17.3's DisputePenalty as an ordinary Support
    Case referencing `charge.penalty_id` (ADR-0029 Decision 3), and an
    admin decides it via the already-existing Resolve Penalty endpoint
    (ADR-0029 Decision 2) — no dispute-specific endpoint exists for
    either step."""
    admin_headers = _login_admin(api_client, sms)

    # Same two-ride dance as the "second qualifying" test above — a real
    # ₹15 OUTSTANDING penalty is needed to have something worth disputing.
    point_a = _random_point()
    driver_headers_a = _new_online_eligible_driver(
        api_client, sms, admin_headers, location=_nearby(point_a)
    )
    customer_token = _login_as_new_customer(api_client, sms)
    customer_headers = {"Authorization": f"Bearer {customer_token}"}
    ride_a = _create_ride(
        api_client,
        customer_headers,
        pickup=_nearby(point_a),
        destination=_nearby(point_a, offset=0.02),
    )
    offers_a = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=driver_headers_a
    ).json()["data"]["offers"]
    driver_id_a = _get_driver_id(api_client, driver_headers_a)
    _seed_wallet_balance(driver_id_a, Decimal("100.00"))
    assert (
        _accept_offer(
            api_client, str(offers_a[0]["offer_id"]), driver_headers_a
        ).status_code
        == 200
    )
    _backdate_accepted_at(str(ride_a["ride_id"]), minutes_ago=10)
    api_client.post(
        f"/api/v1/rides/{ride_a['ride_id']}/cancel",
        json={"reason": "x"},
        headers=customer_headers,
    )

    point_b = _random_point()
    driver_headers_b = _new_online_eligible_driver(
        api_client, sms, admin_headers, location=_nearby(point_b)
    )
    ride_b = _create_ride(
        api_client,
        customer_headers,
        pickup=_nearby(point_b),
        destination=_nearby(point_b, offset=0.02),
    )
    offers_b = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=driver_headers_b
    ).json()["data"]["offers"]
    driver_id_b = _get_driver_id(api_client, driver_headers_b)
    _seed_wallet_balance(driver_id_b, Decimal("100.00"))
    assert (
        _accept_offer(
            api_client, str(offers_b[0]["offer_id"]), driver_headers_b
        ).status_code
        == 200
    )
    _backdate_accepted_at(str(ride_b["ride_id"]), minutes_ago=10)

    cancel_response = api_client.post(
        f"/api/v1/rides/{ride_b['ride_id']}/cancel",
        json={"reason": "x"},
        headers=customer_headers,
    )
    charge = cancel_response.json()["data"]["charge"]
    assert charge["amount"] == 15.0
    penalty_id = charge["penalty_id"]

    # Step 1: the customer files the dispute as a Support Case.
    dispute_response = api_client.post(
        "/api/v1/support/cases",
        json={
            "category": "PENALTY_DISPUTE",
            "ride_id": ride_b["ride_id"],
            "message": f"I dispute penalty {penalty_id} — driver was late.",
        },
        headers=customer_headers,
    )
    assert dispute_response.status_code == 201
    case = dispute_response.json()["data"]
    assert case["category"] == "PENALTY_DISPUTE"
    assert case["status"] == "OPEN"
    case_id = case["case_id"]

    # Step 2: an admin reviews the case (already-built Get Support Case)...
    admin_view = api_client.get(
        f"/api/v1/support/cases/{case_id}", headers=admin_headers
    )
    assert admin_view.status_code == 200
    assert admin_view.json()["data"]["ride_id"] == ride_b["ride_id"]
    assert penalty_id in admin_view.json()["data"]["messages"][0]["message"]

    # ...and decides the dispute via the already-built Resolve Penalty
    # endpoint — no dispute-specific action or endpoint exists.
    resolve_response = api_client.post(
        f"/api/v1/admin/penalties/{penalty_id}/resolve",
        json={"action": "WAIVE", "reason": "Driver confirmed late arrival"},
        headers=admin_headers,
    )
    assert resolve_response.status_code == 200
    assert resolve_response.json()["data"]["status"] == "WAIVED"

    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT status FROM penalty.penalties WHERE id = :id"),
            {"id": penalty_id},
        ).fetchone()
        assert row is not None
        assert row.status == "WAIVED"
    finally:
        db.close()


def test_cancel_arrived_ride_also_refunds_the_driver(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """No endpoint reaches ARRIVED yet (Phase 06 — GPS radius TBD), so
    this test seeds it directly via SQL, same established pattern."""
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    ride, customer_headers, _, driver_id = _accepted_ride_with_customer_and_driver(
        api_client, sms, admin_headers, point=point
    )
    db = SessionLocal()
    try:
        db.execute(
            text("UPDATE ride.rides SET status = 'ARRIVED' WHERE id = :id"),
            {"id": ride["ride_id"]},
        )
        db.commit()
    finally:
        db.close()

    response = api_client.post(
        f"/api/v1/rides/{ride['ride_id']}/cancel",
        json={"reason": "x"},
        headers=customer_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["ride_status"] == "CANCELLED"
    assert _wallet_balance(driver_id) == Decimal("100.00")


def test_cancel_already_accepted_ride_twice_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    ride, customer_headers, _, _ = _accepted_ride_with_customer_and_driver(
        api_client, sms, admin_headers, point=point
    )
    first = api_client.post(
        f"/api/v1/rides/{ride['ride_id']}/cancel",
        json={"reason": "x"},
        headers=customer_headers,
    )
    assert first.status_code == 200

    second = api_client.post(
        f"/api/v1/rides/{ride['ride_id']}/cancel",
        json={"reason": "x"},
        headers=customer_headers,
    )

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "RIDE_NOT_CANCELLABLE"


def test_concurrent_cancel_attempts_on_the_same_accepted_ride_refund_exactly_once(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """BR-013-style atomicity: two real HTTP cancel requests for the
    SAME accepted ride, fired as close to simultaneously as possible —
    same ThreadPoolExecutor technique as every other concurrency test in
    this codebase. Exactly one must succeed; the ride row lock
    (RideService.cancel_ride()'s get_by_id_for_update(), ADR-0015) is
    what serializes them."""
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    ride, customer_headers, _, driver_id = _accepted_ride_with_customer_and_driver(
        api_client, sms, admin_headers, point=point
    )

    results: list[int] = []

    def _attempt() -> None:
        response = api_client.post(
            f"/api/v1/rides/{ride['ride_id']}/cancel",
            json={"reason": "x"},
            headers=customer_headers,
        )
        results.append(response.status_code)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(_attempt) for _ in range(2)]
        for future in futures:
            future.result()

    assert sorted(results) == [200, 409]
    assert _wallet_balance(driver_id) == Decimal("100.00")  # refunded exactly once

    db = SessionLocal()
    try:
        ledger_count = db.execute(
            text(
                "SELECT COUNT(*) FROM wallet.transactions "
                "WHERE driver_id = :id AND transaction_type = 'FEE_REVERSAL'"
            ),
            {"id": driver_id},
        ).scalar()
        assert ledger_count == 1
    finally:
        db.close()


# --- Driver Cancellation (Phase 3 / Task 3.6, ADR-0016) ---------------------


def test_driver_cancel_accepted_ride_charges_thirty_and_records_strike(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    ride, _, driver_headers, driver_id = _accepted_ride_with_customer_and_driver(
        api_client, sms, admin_headers, point=point
    )
    assert _wallet_balance(driver_id) == Decimal("90.00")

    response = api_client.post(
        f"/api/v1/rides/{ride['ride_id']}/driver-cancel",
        json={"reason": "UNWILLING_TO_PROCEED"},
        headers=driver_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["ride_status"] == "CANCELLED"
    assert _wallet_balance(driver_id) == Decimal("60.00")  # 90 - 30 penalty

    db = SessionLocal()
    try:
        strike = db.execute(
            text("SELECT reason FROM penalty.strikes WHERE driver_id = :id"),
            {"id": driver_id},
        ).fetchone()
        assert strike is not None
        assert strike.reason == "UNWILLING_TO_PROCEED"

        ledger_row = db.execute(
            text(
                "SELECT amount, direction FROM wallet.transactions "
                "WHERE driver_id = :id AND transaction_type = 'DRIVER_PENALTY'"
            ),
            {"id": driver_id},
        ).fetchone()
        assert ledger_row is not None
        assert ledger_row.amount == Decimal("30.00")
        assert ledger_row.direction == "DEBIT"

        # Phase 3 / Event & Outbox Foundation (ADR-0017).
        ride_cancelled = db.execute(
            text(
                "SELECT payload FROM shared.outbox_events "
                "WHERE aggregate_id = :id AND event_type = 'ride.cancelled'"
            ),
            {"id": ride["ride_id"]},
        ).fetchone()
        assert ride_cancelled is not None
        assert ride_cancelled.payload["data"]["cancelled_by"] == "DRIVER"

        strike_recorded = db.execute(
            text(
                "SELECT payload FROM shared.outbox_events "
                "WHERE aggregate_type = 'strike' "
                "AND event_type = 'penalty.strike_recorded' "
                "AND payload->'data'->>'driver_id' = :driver_id"
            ),
            {"driver_id": driver_id},
        ).fetchone()
        assert strike_recorded is not None
        assert strike_recorded.payload["data"]["reason"] == "UNWILLING_TO_PROCEED"
    finally:
        db.close()


def test_driver_cancel_with_changed_pickup_pass_reason_has_no_penalty_or_strike(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    ride, _, driver_headers, driver_id = _accepted_ride_with_customer_and_driver(
        api_client, sms, admin_headers, point=point
    )

    response = api_client.post(
        f"/api/v1/rides/{ride['ride_id']}/driver-cancel",
        json={"reason": "CHANGED_PICKUP_OVER_250M"},
        headers=driver_headers,
    )

    assert response.status_code == 200
    assert _wallet_balance(driver_id) == Decimal("90.00")  # unchanged — no penalty

    db = SessionLocal()
    try:
        strike_count = db.execute(
            text("SELECT COUNT(*) FROM penalty.strikes WHERE driver_id = :id"),
            {"id": driver_id},
        ).scalar()
        assert strike_count == 0

        # ride.cancelled is still written; the DRIVER_PENALTY-flavored
        # wallet.debited and penalty.strike_recorded are not, matching
        # BR-071's exemption.
        ride_cancelled_count = db.execute(
            text(
                "SELECT COUNT(*) FROM shared.outbox_events "
                "WHERE aggregate_id = :id AND event_type = 'ride.cancelled'"
            ),
            {"id": ride["ride_id"]},
        ).scalar()
        assert ride_cancelled_count == 1

        strike_event_count = db.execute(
            text(
                "SELECT COUNT(*) FROM shared.outbox_events "
                "WHERE event_type = 'penalty.strike_recorded' "
                "AND payload->'data'->>'driver_id' = :driver_id"
            ),
            {"driver_id": driver_id},
        ).scalar()
        assert strike_event_count == 0
    finally:
        db.close()


def test_driver_cancel_insufficient_balance_records_debt_and_still_cancels(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """RESOLVED (ADR-0062, 2026-09-03, owner decision) — this test used
    to assert the opposite (409, ride stuck ACCEPTED) on purpose. The
    owner's decision: cancellation must never be blocked by an
    insufficient balance; the unpaid penalty becomes a tracked
    wallet.outstanding_debt instead, recovered from a future recharge.
    See tests/test_e2e_wallet_penalty_journey.py for the full
    cancel-then-recharge journey."""
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    ride, _, driver_headers, driver_id = _accepted_ride_with_customer_and_driver(
        api_client, sms, admin_headers, point=point
    )
    _seed_wallet_balance(driver_id, Decimal("5.00"))  # can't afford ₹30 penalty

    response = api_client.post(
        f"/api/v1/rides/{ride['ride_id']}/driver-cancel",
        json={"reason": "UNWILLING_TO_PROCEED"},
        headers=driver_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["ride_status"] == "CANCELLED"

    db = SessionLocal()
    try:
        ride_row = db.execute(
            text("SELECT status FROM ride.rides WHERE id = :id"),
            {"id": ride["ride_id"]},
        ).fetchone()
        assert ride_row is not None
        assert ride_row.status == "CANCELLED"

        wallet_row = db.execute(
            text(
                "SELECT balance, outstanding_debt FROM wallet.wallets "
                "WHERE driver_id = :id"
            ),
            {"id": driver_id},
        ).fetchone()
        assert wallet_row is not None
        assert wallet_row.balance == Decimal("5.00")  # untouched
        assert wallet_row.outstanding_debt == Decimal("30.00")
    finally:
        db.close()


def test_driver_cancel_another_drivers_ride_is_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    ride, _, _, _ = _accepted_ride_with_customer_and_driver(
        api_client, sms, admin_headers, point=point
    )
    other_driver_headers = _new_driver_with_profile(api_client, sms)

    response = api_client.post(
        f"/api/v1/rides/{ride['ride_id']}/driver-cancel",
        json={"reason": "x"},
        headers=other_driver_headers,
    )

    assert response.status_code == 404
    # RideNotFoundError uses the ride-specific RIDE_NOT_FOUND code
    # (ride/domain/errors.py), unlike matching's OfferNotFoundError.
    assert response.json()["error"]["code"] == "RIDE_NOT_FOUND"


def test_customer_cannot_driver_cancel(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    ride, customer_headers, _, _ = _accepted_ride_with_customer_and_driver(
        api_client, sms, admin_headers, point=point
    )

    response = api_client.post(
        f"/api/v1/rides/{ride['ride_id']}/driver-cancel",
        json={"reason": "x"},
        headers=customer_headers,
    )

    assert response.status_code == 403


def test_concurrent_driver_cancel_attempts_charge_the_penalty_exactly_once(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    ride, _, driver_headers, driver_id = _accepted_ride_with_customer_and_driver(
        api_client, sms, admin_headers, point=point
    )

    results: list[int] = []

    def _attempt() -> None:
        response = api_client.post(
            f"/api/v1/rides/{ride['ride_id']}/driver-cancel",
            json={"reason": "UNWILLING_TO_PROCEED"},
            headers=driver_headers,
        )
        results.append(response.status_code)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(_attempt) for _ in range(2)]
        for future in futures:
            future.result()

    assert sorted(results) == [200, 409]
    assert _wallet_balance(driver_id) == Decimal("60.00")  # penalized exactly once

    db = SessionLocal()
    try:
        strike_count = db.execute(
            text("SELECT COUNT(*) FROM penalty.strikes WHERE driver_id = :id"),
            {"id": driver_id},
        ).scalar()
        assert strike_count == 1
    finally:
        db.close()


# --- Sarthi Wallet Low-Balance Rule (ADR-0058, 2026-09-02) -----------------


def _wallet_grace_used(driver_id: str) -> bool:
    db = SessionLocal()
    try:
        value = db.execute(
            text(
                "SELECT low_balance_grace_ride_used FROM wallet.wallets "
                "WHERE driver_id = :id"
            ),
            {"id": driver_id},
        ).scalar()
        return bool(value)
    finally:
        db.close()


def test_accept_offer_at_low_balance_succeeds_and_consumes_the_grace_ride(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Balance at or below ₹20 (but still enough for the CAB fee): the
    accept still succeeds — this IS the driver's one grace ride — and
    the grace flag is now recorded as used."""
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    _ride, driver_headers, offer = _create_ride_with_one_offer(
        api_client, sms, admin_headers, point=point
    )
    driver_id = _get_driver_id(api_client, driver_headers)
    _seed_wallet_balance(driver_id, Decimal("15.00"))

    response = _accept_offer(api_client, str(offer["offer_id"]), driver_headers)

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ACCEPTED"
    assert response.json()["data"]["wallet_balance"] == 5.0
    assert _wallet_grace_used(driver_id) is True


def test_accept_offer_blocked_once_grace_already_used_even_with_sufficient_balance(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """The core rule: after the one grace ride, a second acceptance is
    blocked outright — even when the balance would otherwise comfortably
    cover the platform fee — until a real recharge crosses back above
    the threshold. Distinguishes this from plain
    INSUFFICIENT_WALLET_BALANCE by using a balance well above the CAB
    fee (₹18 > ₹10) for the second attempt."""
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    _ride1, driver_headers, offer1 = _create_ride_with_one_offer(
        api_client, sms, admin_headers, point=point
    )
    driver_id = _get_driver_id(api_client, driver_headers)
    _seed_wallet_balance(driver_id, Decimal("15.00"))

    first = _accept_offer(api_client, str(offer1["offer_id"]), driver_headers)
    assert first.status_code == 200
    assert _wallet_grace_used(driver_id) is True

    # Still online (accepting a ride doesn't take a driver offline —
    # confirmed against modules/matching's own geo index behavior), so
    # a second, independently-created ride at the same point dispatches
    # its offer to this same driver.
    _seed_wallet_balance(driver_id, Decimal("18.00"))  # comfortably covers ₹10 CAB fee
    customer_token = _login_as_new_customer(api_client, sms)
    ride2 = _create_ride(
        api_client,
        {"Authorization": f"Bearer {customer_token}"},
        pickup=_nearby(point),
        destination=_nearby(point, offset=0.02),
    )
    offers = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=driver_headers
    ).json()["data"]["offers"]
    offer2 = next(o for o in offers if o["ride_id"] == ride2["ride_id"])

    second = _accept_offer(api_client, str(offer2["offer_id"]), driver_headers)

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "WALLET_RECHARGE_REQUIRED"

    db = SessionLocal()
    try:
        ride2_row = db.execute(
            text("SELECT status FROM ride.rides WHERE id = :id"),
            {"id": ride2["ride_id"]},
        ).fetchone()
        assert ride2_row is not None
        assert ride2_row.status == "SEARCHING"

        offer2_row = db.execute(
            text("SELECT status FROM matching.ride_offers WHERE id = :id"),
            {"id": offer2["offer_id"]},
        ).fetchone()
        assert offer2_row is not None
        assert offer2_row.status == "PENDING"

        balance = db.execute(
            text("SELECT balance FROM wallet.wallets WHERE driver_id = :id"),
            {"id": driver_id},
        ).scalar()
        assert balance == Decimal("18.00")  # untouched — no partial debit
    finally:
        db.close()


def test_wallet_low_balance_notification_sent_when_crossing_the_threshold(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    _ride, driver_headers, offer = _create_ride_with_one_offer(
        api_client, sms, admin_headers, point=point
    )
    driver_id = _get_driver_id(api_client, driver_headers)
    # ₹25 -> (₹10 CAB fee) -> ₹15: crosses from above the ₹20 threshold
    # to at/below it in this exact debit.
    _seed_wallet_balance(driver_id, Decimal("25.00"))

    response = _accept_offer(api_client, str(offer["offer_id"]), driver_headers)
    assert response.status_code == 200

    db = SessionLocal()
    try:
        delivery = db.execute(
            text(
                "SELECT channel, status FROM notification.deliveries "
                "WHERE user_id = :driver_id AND template_key = "
                "'WALLET_LOW_BALANCE'"
            ),
            {"driver_id": driver_id},
        ).fetchone()
        assert delivery is not None
        assert delivery.channel == "IN_APP"
    finally:
        db.close()


def test_wallet_low_balance_notification_not_sent_when_already_low(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """No repeat notification on a debit that doesn't newly cross the
    threshold — the driver was already at/below it beforehand."""
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    _ride, driver_headers, offer = _create_ride_with_one_offer(
        api_client, sms, admin_headers, point=point
    )
    driver_id = _get_driver_id(api_client, driver_headers)
    _seed_wallet_balance(driver_id, Decimal("15.00"))  # already <= ₹20

    response = _accept_offer(api_client, str(offer["offer_id"]), driver_headers)
    assert response.status_code == 200

    db = SessionLocal()
    try:
        delivery = db.execute(
            text(
                "SELECT id FROM notification.deliveries "
                "WHERE user_id = :driver_id AND template_key = "
                "'WALLET_LOW_BALANCE'"
            ),
            {"driver_id": driver_id},
        ).fetchone()
        assert delivery is None
    finally:
        db.close()


def test_recharging_above_threshold_resets_grace_and_allows_another_accept(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """A real credit crossing back above ₹20 (WalletService.credit(),
    the same primitive the eventual Razorpay recharge endpoint will
    call) resets the grace flag, so the next accept is evaluated fresh."""
    admin_headers = _login_admin(api_client, sms)
    point = _random_point()
    _ride1, driver_headers, offer1 = _create_ride_with_one_offer(
        api_client, sms, admin_headers, point=point
    )
    driver_id = _get_driver_id(api_client, driver_headers)
    _seed_wallet_balance(driver_id, Decimal("15.00"))

    first = _accept_offer(api_client, str(offer1["offer_id"]), driver_headers)
    assert first.status_code == 200
    assert _wallet_grace_used(driver_id) is True

    db = SessionLocal()
    try:
        WalletService(wallets=SqlAlchemyWalletRepository(db)).credit(
            driver_id=uuid.UUID(driver_id),
            amount=Decimal("200.00"),
            transaction_type="WALLET_RECHARGE",
            ride_id=None,
            idempotency_key=f"recharge-{uuid.uuid4()}",
            now=datetime.now(UTC),
        )
        db.commit()
    finally:
        db.close()

    assert _wallet_grace_used(driver_id) is False

    customer_token = _login_as_new_customer(api_client, sms)
    ride2 = _create_ride(
        api_client,
        {"Authorization": f"Bearer {customer_token}"},
        pickup=_nearby(point),
        destination=_nearby(point, offset=0.02),
    )
    offers = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=driver_headers
    ).json()["data"]["offers"]
    offer2 = next(o for o in offers if o["ride_id"] == ride2["ride_id"])

    second = _accept_offer(api_client, str(offer2["offer_id"]), driver_headers)

    assert second.status_code == 200
    assert second.json()["data"]["status"] == "ACCEPTED"
