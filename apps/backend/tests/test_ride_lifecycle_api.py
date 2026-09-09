"""Integration tests: real HTTP layer (TestClient) + real Postgres,
exercising the Phase 06/07 ride-lifecycle endpoints end-to-end (ADR-0028):

    POST /api/v1/rides/{ride_id}/arrived
    POST /api/v1/rides/{ride_id}/otp/refresh
    POST /api/v1/rides/{ride_id}/start
    POST /api/v1/rides/{ride_id}/complete

Reuses the same driver/vehicle-approval setup helpers as
tests/test_get_ride_status_api.py (duplicated, not imported — same
per-file-duplication convention every other test_*_api.py in this
codebase already follows).

Skips (not fails) when Postgres is genuinely unreachable.
"""

from __future__ import annotations

import asyncio
import secrets
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
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
from modules.penalty.repositories import (
    SqlAlchemyPenaltyRepository,
    SqlAlchemyStrikeRepository,
)
from modules.penalty.service import PenaltyService
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
    """Task 2.7B test-isolation correction (same pattern as
    test_vehicle_document_integration.py/test_verification_integration.py):
    wipe the shared test database before every test in this file. Unlike
    those two files, this one is essential rather than merely tidy — every
    test here creates an ONLINE driver sitting at the exact same pickup
    coordinates every other test uses, and MatchingService.dispatch_offer()
    sends a ride's one offer to whichever eligible candidate its query
    returns first; without this cleanup, idle leftover drivers from
    earlier runs accumulate in the shared test database and can win that
    dispatch instead of the driver THIS test just created, making
    `_accept_first_offer()` observe zero offers non-deterministically."""
    truncate_integration_tables(engine)
    asyncio.run(_clean_matching_geo_index())


async def _clean_matching_geo_index() -> None:
    """shared/geo.py's `geo:drivers:{CATEGORY}` GEO sets and
    `driver:online:{driver_id}` hashes live in the SAME Redis instance
    dev and tests both use (unlike DATABASE_URL above, REDIS_URL is
    never redirected to a test-only instance/DB index). go_offline DOES
    now clean up its own caller's entry (modules/driver/router.py's
    go_offline endpoint composes shared/geo.py's
    remove_driver_location(), fixed 2026-08-28 — previously that
    function existed but nothing ever called it) — but this file's own
    tests never call POST .../me/offline for the drivers they create;
    each test ends right after its assertions, so its driver stays
    ONLINE in both Postgres and Redis. Left alone, driver_ids from every
    previous run of this file (and any other test that ever put a
    driver online and never took it back offline) accumulate forever at
    the exact same test coordinates every test here reuses — with
    enough accumulated entries, MatchingService.dispatch_offer()'s
    candidate_limit-bounded GEOSEARCH can return 20 stale, no-longer-
    eligible candidates before ever reaching the one real driver THIS
    test just created, so dispatch silently finds no offer to send
    (confirmed by direct reproduction: identical setup, same behavior,
    independent of every line this test file's own feature touches).
    This explicit cleanup therefore stays necessary regardless of the
    go_offline fix — it isn't a workaround for a bug, it's covering for
    these tests' own drivers never going offline."""
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

# ~1.1km from VALID_RIDE_BODY's own pickup point above — well outside
# the 50m arrival / 100m completion radii (core.config.Settings'
# defaults, unchanged in tests).
FAR_LATITUDE = 25.6041
FAR_LONGITUDE = 85.1376


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


def _arrived_ride(
    api_client: TestClient, sms: CapturingSmsProvider, admin_headers: dict
) -> tuple[str, dict, dict]:
    ride_id, customer_headers, driver_headers = _accepted_ride(
        api_client, sms, admin_headers
    )
    response = api_client.post(
        f"/api/v1/rides/{ride_id}/arrived",
        json={"latitude": 25.5941, "longitude": 85.1376},
        headers=driver_headers,
    )
    assert response.status_code == 200
    return ride_id, customer_headers, driver_headers


def _started_ride(
    api_client: TestClient, sms: CapturingSmsProvider, admin_headers: dict
) -> tuple[str, dict, dict]:
    ride_id, customer_headers, driver_headers = _arrived_ride(
        api_client, sms, admin_headers
    )
    otp = api_client.post(
        f"/api/v1/rides/{ride_id}/otp/refresh", headers=customer_headers
    ).json()["data"]["otp"]
    response = api_client.post(
        f"/api/v1/rides/{ride_id}/start", json={"otp": otp}, headers=driver_headers
    )
    assert response.status_code == 200
    return ride_id, customer_headers, driver_headers


# --- Driver Arrival (§17) ----------------------------------------------------


def test_driver_arrival_within_radius_transitions_to_arrived(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, _customer_headers, driver_headers = _accepted_ride(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/arrived",
        json={"latitude": 25.5941, "longitude": 85.1376},
        headers=driver_headers,
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "ARRIVED"
    assert body["waiting_started_at"] is not None

    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT status, arrived_at FROM ride.rides WHERE id = :id"),
            {"id": ride_id},
        ).fetchone()
        assert row is not None
        assert row.status == "ARRIVED"
        assert row.arrived_at is not None

        gps_row = db.execute(
            text(
                "SELECT verification_type, result FROM ride.gps_verifications "
                "WHERE ride_id = :id"
            ),
            {"id": ride_id},
        ).fetchone()
        assert gps_row is not None
        assert gps_row.verification_type == "ARRIVAL"
        assert gps_row.result == "PASS"

        otp_row = db.execute(
            text(
                "SELECT status FROM ride.ride_otps WHERE ride_id = :id "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"id": ride_id},
        ).fetchone()
        assert otp_row is not None
        assert otp_row.status == "ACTIVE"

        outbox_row = db.execute(
            text(
                "SELECT payload FROM shared.outbox_events "
                "WHERE aggregate_id = :id AND event_type = 'ride.arrived'"
            ),
            {"id": ride_id},
        ).fetchone()
        assert outbox_row is not None
        assert outbox_row.payload["data"]["gps_verified"] is True

        # ADR-0034 — the customer gets a best-effort IN_APP notification
        # once arrival is durable.
        notification = db.execute(
            text(
                "SELECT d.channel, d.template_key, d.status FROM "
                "notification.deliveries d JOIN ride.rides r "
                "ON r.customer_id = d.user_id "
                "WHERE r.id = :ride_id AND d.template_key = 'RIDE_ARRIVED'"
            ),
            {"ride_id": ride_id},
        ).fetchone()
        assert notification is not None
        assert notification.channel == "IN_APP"
        assert notification.status == "SENT"
    finally:
        db.close()


def test_driver_arrival_outside_radius_is_rejected_and_ride_stays_accepted(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, _customer_headers, driver_headers = _accepted_ride(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/arrived",
        json={"latitude": FAR_LATITUDE, "longitude": FAR_LONGITUDE},
        headers=driver_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOT_WITHIN_PICKUP_RADIUS"

    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT status FROM ride.rides WHERE id = :id"), {"id": ride_id}
        ).fetchone()
        assert row is not None
        assert row.status == "ACCEPTED"

        # The failed attempt is still recorded — audit-trail-first design
        # (ADR-0028 §3) — even though the ride transition was rejected.
        gps_row = db.execute(
            text("SELECT result FROM ride.gps_verifications WHERE ride_id = :id"),
            {"id": ride_id},
        ).fetchone()
        assert gps_row is not None
        assert gps_row.result == "FAIL"
    finally:
        db.close()


def test_driver_arrival_becomes_manual_review_after_three_failures(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, _customer_headers, driver_headers = _accepted_ride(
        api_client, sms, admin_headers
    )

    for _ in range(3):
        response = api_client.post(
            f"/api/v1/rides/{ride_id}/arrived",
            json={"latitude": FAR_LATITUDE, "longitude": FAR_LONGITUDE},
            headers=driver_headers,
        )
        assert response.json()["error"]["code"] == "NOT_WITHIN_PICKUP_RADIUS"

    fourth = api_client.post(
        f"/api/v1/rides/{ride_id}/arrived",
        json={"latitude": FAR_LATITUDE, "longitude": FAR_LONGITUDE},
        headers=driver_headers,
    )
    assert fourth.status_code == 409
    assert fourth.json()["error"]["code"] == "GPS_VERIFICATION_FAILED"


def test_customer_cannot_mark_arrived(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, _driver_headers = _accepted_ride(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/arrived",
        json={"latitude": 25.5941, "longitude": 85.1376},
        headers=customer_headers,
    )

    assert response.status_code == 403


def test_unassigned_driver_cannot_mark_arrived(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, _customer_headers, _driver_headers = _accepted_ride(
        api_client, sms, admin_headers
    )
    other_driver_headers, _did, _vid = _new_online_eligible_driver(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/arrived",
        json={"latitude": 25.5941, "longitude": 85.1376},
        headers=other_driver_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RIDE_NOT_FOUND"


# --- Generate/Refresh OTP (§18) ----------------------------------------------


def test_customer_can_refresh_otp_after_arrival(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, _driver_headers = _arrived_ride(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/otp/refresh", headers=customer_headers
    )

    assert response.status_code == 200
    otp = response.json()["data"]["otp"]
    assert isinstance(otp, str)
    assert len(otp) == 6
    assert otp.isdigit()


def test_refresh_otp_invalidates_the_previous_one(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, driver_headers = _arrived_ride(
        api_client, sms, admin_headers
    )

    first_otp = api_client.post(
        f"/api/v1/rides/{ride_id}/otp/refresh", headers=customer_headers
    ).json()["data"]["otp"]
    api_client.post(f"/api/v1/rides/{ride_id}/otp/refresh", headers=customer_headers)

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/start",
        json={"otp": first_otp},
        headers=driver_headers,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "OTP_INVALID"


def test_driver_cannot_refresh_otp(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, _customer_headers, driver_headers = _arrived_ride(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/otp/refresh", headers=driver_headers
    )

    assert response.status_code == 403


def test_refresh_otp_before_arrival_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, _driver_headers = _accepted_ride(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/otp/refresh", headers=customer_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


# --- Start Ride (§18) --------------------------------------------------------


def test_start_ride_with_correct_otp_transitions_to_started(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, driver_headers = _arrived_ride(
        api_client, sms, admin_headers
    )
    otp = api_client.post(
        f"/api/v1/rides/{ride_id}/otp/refresh", headers=customer_headers
    ).json()["data"]["otp"]

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/start", json={"otp": otp}, headers=driver_headers
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "STARTED"

    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT status, started_at FROM ride.rides WHERE id = :id"),
            {"id": ride_id},
        ).fetchone()
        assert row is not None
        assert row.status == "STARTED"
        assert row.started_at is not None

        otp_row = db.execute(
            text(
                "SELECT status FROM ride.ride_otps WHERE ride_id = :id "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"id": ride_id},
        ).fetchone()
        assert otp_row is not None
        assert otp_row.status == "USED"

        outbox_row = db.execute(
            text(
                "SELECT payload FROM shared.outbox_events "
                "WHERE aggregate_id = :id AND event_type = 'ride.started'"
            ),
            {"id": ride_id},
        ).fetchone()
        assert outbox_row is not None
    finally:
        db.close()


def test_start_ride_with_wrong_otp_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, driver_headers = _arrived_ride(
        api_client, sms, admin_headers
    )
    real_otp = api_client.post(
        f"/api/v1/rides/{ride_id}/otp/refresh", headers=customer_headers
    ).json()["data"]["otp"]
    wrong_otp = "000000" if real_otp != "000000" else "111111"

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/start",
        json={"otp": wrong_otp},
        headers=driver_headers,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "OTP_INVALID"


def test_customer_cannot_start_ride(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, _driver_headers = _arrived_ride(
        api_client, sms, admin_headers
    )
    otp = api_client.post(
        f"/api/v1/rides/{ride_id}/otp/refresh", headers=customer_headers
    ).json()["data"]["otp"]

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/start", json={"otp": otp}, headers=customer_headers
    )

    assert response.status_code == 403


# --- Ride Completion (§28) ---------------------------------------------------


def test_ride_completion_within_radius_transitions_straight_to_closed(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, _customer_headers, driver_headers = _started_ride(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/complete",
        json={"latitude": 25.6120, "longitude": 85.1580},
        headers=driver_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "CLOSED"

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT status, completed_at, closed_at FROM ride.rides WHERE id = :id"
            ),
            {"id": ride_id},
        ).fetchone()
        assert row is not None
        assert row.status == "CLOSED"
        assert row.completed_at is not None
        assert row.closed_at is not None

        history_rows = db.execute(
            text(
                "SELECT to_status FROM ride.state_history WHERE ride_id = :id "
                "ORDER BY created_at ASC"
            ),
            {"id": ride_id},
        ).fetchall()
        assert [r.to_status for r in history_rows][-2:] == ["COMPLETED", "CLOSED"]

        outbox_row = db.execute(
            text(
                "SELECT payload FROM shared.outbox_events "
                "WHERE aggregate_id = :id AND event_type = 'ride.completed'"
            ),
            {"id": ride_id},
        ).fetchone()
        assert outbox_row is not None
        assert outbox_row.payload["data"]["gps_verified"] is True
    finally:
        db.close()


def test_ride_completion_settles_carried_forward_penalty_and_debits_wallet(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Customer Outstanding Penalty Settlement (ADR-0066, owner decision
    2026-09-03) end-to-end: a customer with a real ₹15 OUTSTANDING
    penalty books a ride (attached, per ADR-0026's existing display),
    the ride runs its full real lifecycle through HTTP, and completing
    it settles the penalty AND debits the driver's wallet by ₹15
    (CASH_SETTLEMENT) — "the User pays the Sarthi directly... Apply the
    corresponding Sarthi wallet/platform accounting"."""
    admin_headers = _login_admin(api_client, sms)
    customer_token = _login(api_client, sms, "CUSTOMER")
    customer_headers = {"Authorization": f"Bearer {customer_token}"}
    customer_id = _account_id_from_token(customer_token)

    # BR-047/048: the first qualifying cancellation is free (₹0,
    # auto-SETTLED); the second produces a real ₹15 OUTSTANDING penalty
    # — seeded directly via the domain service, the same shortcut
    # tests/test_ride_api.py's own outstanding-penalty tests already
    # use. penalty.penalties.ride_id has a real FK to ride.rides, so
    # these must be two real (throwaway) rides, not arbitrary UUIDs.
    # Created before any driver goes ONLINE below, deliberately — no
    # eligible driver exists yet, so matching dispatches no offer for
    # either throwaway ride, and _accept_first_offer()'s own "exactly
    # one offer" assertion further down stays true for the real ride.
    throwaway_ride_id_1 = _create_ride(api_client, customer_headers)
    throwaway_ride_id_2 = _create_ride(api_client, customer_headers)
    db = SessionLocal()
    try:
        penalty_service = PenaltyService(
            penalties=SqlAlchemyPenaltyRepository(db),
            strikes=SqlAlchemyStrikeRepository(db),
        )
        penalty_service.record_customer_cancellation(
            customer_id=customer_id,
            ride_id=uuid.UUID(throwaway_ride_id_1),
            now=datetime.now(UTC),
        )
        penalty_service.record_customer_cancellation(
            customer_id=customer_id,
            ride_id=uuid.UUID(throwaway_ride_id_2),
            now=datetime.now(UTC),
        )
        db.commit()
    finally:
        db.close()

    driver_headers, driver_id, _vehicle_id = _new_online_eligible_driver(
        api_client, sms, admin_headers
    )

    # Create Ride durably attaches the ₹15 OUTSTANDING penalty to this
    # new ride (ADR-0066) — the response shape itself is unchanged from
    # ADR-0026/ADR-0059, confirmed the same way tests/test_ride_api.py's
    # existing outstanding-penalty tests already do.
    create_response = api_client.post(
        "/api/v1/rides",
        json=VALID_RIDE_BODY,
        headers={**customer_headers, "Idempotency-Key": f"ride-{uuid.uuid4()}"},
    )
    assert create_response.status_code == 201
    assert create_response.json()["data"]["outstanding_penalty"] == {
        "amount": 15.0,
        "currency": "INR",
    }
    ride_id = create_response.json()["data"]["ride_id"]

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

    wallet_before = api_client.get(
        "/api/v1/drivers/me/wallet", headers=driver_headers
    ).json()["data"]["balance"]

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/complete",
        json={"latitude": 25.6120, "longitude": 85.1580},
        headers=driver_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "CLOSED"
    assert data["customer_penalty_settled"] == 15.0

    wallet_after = api_client.get(
        "/api/v1/drivers/me/wallet", headers=driver_headers
    ).json()["data"]["balance"]
    assert wallet_after == pytest.approx(wallet_before - 15.0)

    db = SessionLocal()
    try:
        # Scoped by settlement_ride_id specifically, not just
        # status = 'SETTLED' — this customer has two SETTLED rows (the
        # free ₹0 first cancellation is auto-SETTLED at creation too,
        # with no settlement_ride_id of its own), so an unscoped query
        # would nondeterministically match either one.
        penalty_row = db.execute(
            text(
                "SELECT status, settled_at, amount FROM penalty.penalties "
                "WHERE settlement_ride_id = :ride_id"
            ),
            {"ride_id": ride_id},
        ).fetchone()
        assert penalty_row is not None
        assert penalty_row.status == "SETTLED"
        assert penalty_row.settled_at is not None
        assert float(penalty_row.amount) == 15.0

        transaction_row = db.execute(
            text(
                "SELECT amount, direction FROM wallet.transactions "
                "WHERE driver_id = :driver_id AND transaction_type = 'CASH_SETTLEMENT'"
            ),
            {"driver_id": driver_id},
        ).fetchone()
        assert transaction_row is not None
        assert float(transaction_row.amount) == 15.0
        assert transaction_row.direction == "DEBIT"
    finally:
        db.close()


def test_ride_completion_with_no_outstanding_penalty_omits_the_settlement_field(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """The overwhelming common case: no penalty attached, no wallet
    side-effect, `customer_penalty_settled` stays null."""
    admin_headers = _login_admin(api_client, sms)
    ride_id, _customer_headers, driver_headers = _started_ride(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/complete",
        json={"latitude": 25.6120, "longitude": 85.1580},
        headers=driver_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["customer_penalty_settled"] is None


def test_ride_completion_outside_radius_is_rejected_and_ride_stays_started(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, _customer_headers, driver_headers = _started_ride(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/complete",
        json={"latitude": FAR_LATITUDE, "longitude": FAR_LONGITUDE},
        headers=driver_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOT_WITHIN_DESTINATION_RADIUS"

    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT status FROM ride.rides WHERE id = :id"), {"id": ride_id}
        ).fetchone()
        assert row is not None
        assert row.status == "STARTED"
    finally:
        db.close()


def test_ride_completion_before_start_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, _customer_headers, driver_headers = _arrived_ride(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/complete",
        json={"latitude": 25.6120, "longitude": 85.1580},
        headers=driver_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RIDE_NOT_COMPLETABLE"


def test_customer_cannot_complete_ride(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, _driver_headers = _started_ride(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/complete",
        json={"latitude": 25.6120, "longitude": 85.1580},
        headers=customer_headers,
    )

    assert response.status_code == 403


# --- Promotion Consume/Restore Integration (ADR-0070, Phase 12) -------------
#
# ADR-0019 Item 6 left ConsumePromotion/RestorePromotion uncomposed into the
# ride lifecycle ("proven instead by real-Postgres integration tests
# exercising the full lifecycle directly"). ReservePromotion was, at some
# point after ADR-0019, actually wired into Create Ride (Pricing now exists
# — see ride/router.py's create_ride()) without that composition, or the
# other two, ever being recorded anywhere. These three tests are the real,
# end-to-end proof (through the actual HTTP endpoints, not PromotionService
# called directly) that ADR-0070 closes the remaining gap: consume on
# completion, restore on both cancellation paths.


def test_ride_completion_consumes_reserved_promotion_and_writes_usage(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """A fresh customer's auto-granted WELCOME entitlement (BR-058) is
    the only ACTIVE entitlement they have, so Create Ride reserves
    against it automatically. Completing the ride must consume that
    exact reservation, with discount_amount matching what Create Ride's
    own response already reported (`quote.promotion_discount` — the same
    amount, not re-derived), and must leave remaining_uses exactly where
    reserve_entitlement() already decremented it to (2) — consume never
    touches remaining_uses again (BR-065/066)."""
    admin_headers = _login_admin(api_client, sms)
    driver_headers, _driver_id, _vehicle_id = _new_online_eligible_driver(
        api_client, sms, admin_headers
    )
    customer_token = _login(api_client, sms, "CUSTOMER")
    customer_headers = {"Authorization": f"Bearer {customer_token}"}
    # GET /me is the composition point that grants the WELCOME
    # entitlement (BR-058, ADR-0019 Decision 4) — without this call,
    # Create Ride below has no ACTIVE entitlement to reserve against.
    api_client.get("/api/v1/customers/me", headers=customer_headers)

    create_response = api_client.post(
        "/api/v1/rides",
        json=VALID_RIDE_BODY,
        headers={**customer_headers, "Idempotency-Key": f"ride-{uuid.uuid4()}"},
    )
    assert create_response.status_code == 201
    create_data = create_response.json()["data"]
    ride_id = create_data["ride_id"]
    discount_applied = create_data["fare"]["discount"]
    assert discount_applied > 0  # WELCOME reserved — a real discount was quoted

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

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/complete",
        json={"latitude": 25.6120, "longitude": 85.1580},
        headers=driver_headers,
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "CLOSED"

    db = SessionLocal()
    try:
        reservation_row = db.execute(
            text(
                "SELECT id, entitlement_id, status FROM promotion.reservations "
                "WHERE ride_id = :ride_id"
            ),
            {"ride_id": ride_id},
        ).fetchone()
        assert reservation_row is not None
        assert reservation_row.status == "CONSUMED"

        usage_row = db.execute(
            text(
                "SELECT status, discount_amount FROM promotion.usage "
                "WHERE entitlement_id = :entitlement_id AND ride_id = :ride_id"
            ),
            {
                "entitlement_id": reservation_row.entitlement_id,
                "ride_id": ride_id,
            },
        ).fetchone()
        assert usage_row is not None
        assert usage_row.status == "CONSUMED"
        assert float(usage_row.discount_amount) == pytest.approx(discount_applied)

        remaining = db.execute(
            text("SELECT remaining_uses FROM promotion.entitlements WHERE id = :id"),
            {"id": reservation_row.entitlement_id},
        ).scalar()
        assert remaining == 2  # decremented at reserve time only, unchanged here

        outbox_row = db.execute(
            text(
                "SELECT payload FROM shared.outbox_events "
                "WHERE aggregate_id = :id AND event_type = 'promotion.consumed'"
            ),
            {"id": reservation_row.entitlement_id},
        ).fetchone()
        assert outbox_row is not None
        assert outbox_row.payload["data"]["ride_id"] == ride_id
        assert float(outbox_row.payload["data"]["discount_amount"]) == pytest.approx(
            discount_applied
        )
    finally:
        db.close()


def test_ride_completion_with_no_promotion_reservation_is_a_silent_no_op(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """The genuine no-reservation case: a customer whose WELCOME
    entitlement is already EXHAUSTED (seeded directly — cheaper than
    three real prior rides) has no ACTIVE entitlement for Create Ride to
    reserve against, so this ride carries no reservation at all.
    Completion must still succeed, and must write no Usage row and
    fire no promotion.consumed event."""
    admin_headers = _login_admin(api_client, sms)
    driver_headers, _driver_id, _vehicle_id = _new_online_eligible_driver(
        api_client, sms, admin_headers
    )
    customer_token = _login(api_client, sms, "CUSTOMER")
    customer_headers = {"Authorization": f"Bearer {customer_token}"}
    customer_id = _account_id_from_token(customer_token)
    # GET /me is the composition point that grants the WELCOME
    # entitlement (BR-058) — same trigger test_promotion_api.py's own
    # helpers rely on.
    api_client.get("/api/v1/customers/me", headers=customer_headers)

    db = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE promotion.entitlements SET remaining_uses = 0, "
                "status = 'EXHAUSTED' WHERE customer_id = :id"
            ),
            {"id": str(customer_id)},
        )
        db.commit()
    finally:
        db.close()

    create_response = api_client.post(
        "/api/v1/rides",
        json=VALID_RIDE_BODY,
        headers={**customer_headers, "Idempotency-Key": f"ride-{uuid.uuid4()}"},
    )
    assert create_response.status_code == 201
    ride_id = create_response.json()["data"]["ride_id"]
    assert create_response.json()["data"]["fare"]["discount"] == 0

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

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/complete",
        json={"latitude": 25.6120, "longitude": 85.1580},
        headers=driver_headers,
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "CLOSED"

    db = SessionLocal()
    try:
        reservation_count = db.execute(
            text("SELECT COUNT(*) FROM promotion.reservations WHERE ride_id = :id"),
            {"id": ride_id},
        ).scalar()
        assert reservation_count == 0

        usage_count = db.execute(
            text("SELECT COUNT(*) FROM promotion.usage WHERE ride_id = :id"),
            {"id": ride_id},
        ).scalar()
        assert usage_count == 0

        outbox_row = db.execute(
            text(
                "SELECT id FROM shared.outbox_events "
                "WHERE event_type = 'promotion.consumed' "
                "AND payload->'data'->>'ride_id' = :ride_id"
            ),
            {"ride_id": ride_id},
        ).fetchone()
        assert outbox_row is None
    finally:
        db.close()


def test_cancelling_an_accepted_ride_restores_its_reserved_promotion(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """BR-065: cancelling a ride that reserved a promotion gives the use
    back. Real HTTP: Create Ride (auto-reserves WELCOME, 3 -> 2) -> accept
    -> customer cancel (grace period) -> remaining_uses is back to 3 and
    the reservation is RESTORED, not left dangling forever."""
    admin_headers = _login_admin(api_client, sms)
    driver_headers, _driver_id, _vehicle_id = _new_online_eligible_driver(
        api_client, sms, admin_headers
    )
    customer_token = _login(api_client, sms, "CUSTOMER")
    customer_headers = {"Authorization": f"Bearer {customer_token}"}
    # GET /me is the composition point that grants the WELCOME
    # entitlement (BR-058, ADR-0019 Decision 4) — without this call,
    # Create Ride below has no ACTIVE entitlement to reserve against.
    api_client.get("/api/v1/customers/me", headers=customer_headers)

    create_response = api_client.post(
        "/api/v1/rides",
        json=VALID_RIDE_BODY,
        headers={**customer_headers, "Idempotency-Key": f"ride-{uuid.uuid4()}"},
    )
    assert create_response.status_code == 201
    ride_id = create_response.json()["data"]["ride_id"]
    assert create_response.json()["data"]["fare"]["discount"] > 0

    _accept_first_offer(api_client, driver_headers)

    cancel_response = api_client.post(
        f"/api/v1/rides/{ride_id}/cancel",
        json={"reason": "CHANGED_MY_MIND"},
        headers=customer_headers,
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["data"]["ride_status"] == "CANCELLED"

    db = SessionLocal()
    try:
        reservation_row = db.execute(
            text(
                "SELECT entitlement_id, status FROM promotion.reservations "
                "WHERE ride_id = :ride_id"
            ),
            {"ride_id": ride_id},
        ).fetchone()
        assert reservation_row is not None
        assert reservation_row.status == "RESTORED"

        remaining = db.execute(
            text(
                "SELECT remaining_uses, status FROM promotion.entitlements "
                "WHERE id = :id"
            ),
            {"id": reservation_row.entitlement_id},
        ).fetchone()
        assert remaining is not None
        assert remaining.remaining_uses == 3  # given back
        assert remaining.status == "ACTIVE"

        outbox_row = db.execute(
            text(
                "SELECT payload FROM shared.outbox_events "
                "WHERE aggregate_id = :id AND event_type = 'promotion.restored'"
            ),
            {"id": reservation_row.entitlement_id},
        ).fetchone()
        assert outbox_row is not None
        assert outbox_row.payload["data"]["ride_id"] == ride_id
    finally:
        db.close()


def test_driver_cancelling_a_ride_restores_its_reserved_promotion(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Same as the customer-cancel case above, but via driver-cancel
    (ADR-0016) — the other real path a ride carrying a reservation can
    be cancelled through. Deliberately not built on the shared
    _accepted_ride() helper — that helper's customer never calls GET
    /me, so it never has a WELCOME entitlement to reserve in the first
    place."""
    admin_headers = _login_admin(api_client, sms)
    driver_headers, _driver_id, _vehicle_id = _new_online_eligible_driver(
        api_client, sms, admin_headers
    )
    customer_token = _login(api_client, sms, "CUSTOMER")
    customer_headers = {"Authorization": f"Bearer {customer_token}"}
    api_client.get("/api/v1/customers/me", headers=customer_headers)

    create_response = api_client.post(
        "/api/v1/rides",
        json=VALID_RIDE_BODY,
        headers={**customer_headers, "Idempotency-Key": f"ride-{uuid.uuid4()}"},
    )
    assert create_response.status_code == 201
    ride_id = create_response.json()["data"]["ride_id"]
    assert create_response.json()["data"]["fare"]["discount"] > 0
    _accept_first_offer(api_client, driver_headers)

    db = SessionLocal()
    try:
        reservation_before = db.execute(
            text(
                "SELECT entitlement_id, status FROM promotion.reservations "
                "WHERE ride_id = :ride_id"
            ),
            {"ride_id": ride_id},
        ).fetchone()
    finally:
        db.close()
    assert reservation_before is not None
    assert reservation_before.status == "RESERVED"

    cancel_response = api_client.post(
        f"/api/v1/rides/{ride_id}/driver-cancel",
        json={"reason": "UNWILLING_TO_PROCEED"},
        headers=driver_headers,
    )
    assert cancel_response.status_code == 200

    db = SessionLocal()
    try:
        reservation_after = db.execute(
            text("SELECT status FROM promotion.reservations WHERE ride_id = :id"),
            {"id": ride_id},
        ).fetchone()
        assert reservation_after is not None
        assert reservation_after.status == "RESTORED"

        remaining = db.execute(
            text("SELECT remaining_uses FROM promotion.entitlements WHERE id = :id"),
            {"id": reservation_before.entitlement_id},
        ).scalar()
        assert remaining == 3  # given back
    finally:
        db.close()


# --- Book for Someone Else: OTP delivered to the linked contact (ADR-0057) --


def _arrived_ride_with_linked_contact(
    api_client: TestClient, sms: CapturingSmsProvider, admin_headers: dict
) -> tuple[str, dict, str]:
    """Same shape as _arrived_ride() above, but the ride is created with
    a linked_contact — returns (ride_id, customer_headers,
    linked_contact_phone) instead of also returning driver_headers
    (unused by the one test that needs this)."""
    driver_headers, _driver_id, _vehicle_id = _new_online_eligible_driver(
        api_client, sms, admin_headers
    )
    customer_token = _login(api_client, sms, "CUSTOMER")
    customer_headers = {"Authorization": f"Bearer {customer_token}"}
    linked_contact_phone = "+91" + "".join(
        str(secrets.randbelow(10)) for _ in range(10)
    )
    response = api_client.post(
        "/api/v1/rides",
        json={
            **VALID_RIDE_BODY,
            "linked_contact": {
                "name": "Priya Singh",
                "phone": linked_contact_phone,
            },
        },
        headers={**customer_headers, "Idempotency-Key": f"ride-{uuid.uuid4()}"},
    )
    assert response.status_code == 201
    ride_id = response.json()["data"]["ride_id"]
    _accept_first_offer(api_client, driver_headers)
    arrived = api_client.post(
        f"/api/v1/rides/{ride_id}/arrived",
        json={"latitude": 25.5941, "longitude": 85.1376},
        headers=driver_headers,
    )
    assert arrived.status_code == 200
    return ride_id, customer_headers, linked_contact_phone


def test_refresh_otp_also_sends_it_by_sms_to_the_linked_contact(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, linked_contact_phone = _arrived_ride_with_linked_contact(
        api_client, sms, admin_headers
    )

    response = api_client.post(
        f"/api/v1/rides/{ride_id}/otp/refresh", headers=customer_headers
    )

    assert response.status_code == 200
    otp = response.json()["data"]["otp"]
    assert sms.sent[linked_contact_phone] == otp


def test_refresh_otp_without_a_linked_contact_sends_no_extra_sms(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """An ordinary (not Book for Someone Else) ride — the booker's own
    login-OTP phone is the only key CapturingSmsProvider.sent ever
    gains; refresh_ride_otp() itself must not add a second entry."""
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_headers, _driver_headers = _arrived_ride(
        api_client, sms, admin_headers
    )
    sent_before = dict(sms.sent)

    api_client.post(f"/api/v1/rides/{ride_id}/otp/refresh", headers=customer_headers)

    assert sms.sent == sent_before
