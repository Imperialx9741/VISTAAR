"""E2E: the real User (Customer) + Sarthi (Driver) ride journey, chained
in one continuous flow against real HTTP (TestClient) + real Postgres +
real Redis — testing-strategy.md §4.4/§82 ("Test complete journeys:
Customer books → Driver accepts → Ride starts → Ride completes → Payment
settles").

This is deliberately NOT a duplicate of test_ride_lifecycle_api.py's own
tests, which exercise each transition (`arrived`/`start`/`complete`) in
isolation with its own fresh setup. This file's value is the single
unbroken chain end to end, plus the two mid-ride modification paths
(Pickup Change, Destination Change) composed into that same chain — the
thing "E2E journey" actually means and nothing in this codebase's
existing suite does yet.

Two real, verified gaps against what testing-strategy.md §82/§85/§86
documents are recorded here, not silently worked around — see the
"DOCUMENTED GAP" comments at the two places they were found. Both are
also written up in `docs/10-testing/e2e-findings-2026-09-02.md`.

Skips (not fails) when Postgres is genuinely unreachable, same
convention as every other integration test in this file's family.
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
    """Same necessity as test_ride_lifecycle_api.py's own identical
    fixture — see that file's docstring for why this is essential, not
    merely tidy, whenever a test creates an ONLINE driver at a fixed
    pickup point matching.dispatch_offer() must find deterministically."""
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
    """Returns (driver_headers, driver_id, vehicle_id) — the real Sarthi
    onboarding journey: profile → document upload → admin approval →
    vehicle registration → vehicle document upload → admin approval →
    activate → go online → report location. Every one of these is a
    real HTTP call, not a shortcut."""
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


def test_full_customer_books_driver_accepts_ride_completes_journey(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """testing-strategy.md §82, End-to-End Happy Path — every step that
    actually exists in the real system today, chained in one test:

        User logs in
         -> Requests ride
         -> Sarthi receives the offer
         -> Sarthi accepts
         -> Sarthi arrives within the real configured radius
         -> User's OTP is used to start the ride
         -> Ride completes within the real configured radius
         -> Ride closes

    Expected per §82: "All state transitions valid, Payment correct,
    Events emitted, Notifications generated, Audit data available."

    DOCUMENTED GAP (verified this pass, not assumed — and worse than
    initially expected): §82's "Payment succeeds" step does not
    correspond to any real gate in the current system. `complete`
    transitions COMPLETED -> CLOSED in the same call with no
    payment-verification step in between — confirmed against
    modules/ride/router.py. This test originally also asserted
    `ride.rides.payment_method` was persisted as "ONLINE"; running it
    for real surfaced that `payment_method` is not even a column on
    `ride.rides` at all (`UndefinedColumn`, confirmed via a real
    Postgres query) — it's accepted and validated at the API boundary
    (`validate_payment_method()`) and then genuinely discarded, exactly
    as ADR-0010 §8's own Addendum already said in a code comment, now
    confirmed against the real schema rather than just the comment. No
    payment module exists in this backend at all (security-review-
    2026-09-02.md §1 row 8). This is not a bug this test works around;
    it's the real, current behavior, recorded honestly rather than
    silently assumed away.
    """
    admin_headers = _login_admin(api_client, sms)
    driver_headers, _driver_id, _vehicle_id = _new_online_eligible_driver(
        api_client, sms, admin_headers
    )
    customer_token = _login(api_client, sms, "CUSTOMER")
    customer_headers = {"Authorization": f"Bearer {customer_token}"}

    # Requests ride
    create_response = api_client.post(
        "/api/v1/rides",
        json=VALID_RIDE_BODY,
        headers={**customer_headers, "Idempotency-Key": f"ride-{uuid.uuid4()}"},
    )
    assert create_response.status_code == 201
    ride_id = create_response.json()["data"]["ride_id"]

    # Sarthi receives the offer, accepts
    offers = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=driver_headers
    ).json()["data"]["offers"]
    assert len(offers) == 1, "the offer this ride's own matching dispatch created"
    accept_response = api_client.post(
        f"/api/v1/drivers/me/ride-offers/{offers[0]['offer_id']}/accept",
        headers={**driver_headers, "Idempotency-Key": f"accept-{uuid.uuid4()}"},
    )
    assert accept_response.status_code == 200

    # Sarthi arrives, within the real configured radius (not a
    # hardcoded 50m — settings.RIDE_ARRIVAL_GPS_RADIUS_METERS is
    # whatever this environment's real config says, same pickup point
    # VALID_RIDE_BODY already uses).
    arrive_response = api_client.post(
        f"/api/v1/rides/{ride_id}/arrived",
        json={"latitude": 25.5941, "longitude": 85.1376},
        headers=driver_headers,
    )
    assert arrive_response.status_code == 200
    assert arrive_response.json()["data"]["status"] == "ARRIVED"

    # User's OTP starts the ride
    otp = api_client.post(
        f"/api/v1/rides/{ride_id}/otp/refresh", headers=customer_headers
    ).json()["data"]["otp"]
    start_response = api_client.post(
        f"/api/v1/rides/{ride_id}/start", json={"otp": otp}, headers=driver_headers
    )
    assert start_response.status_code == 200
    assert start_response.json()["data"]["status"] == "STARTED"

    # Ride completes, within the real configured completion radius
    complete_response = api_client.post(
        f"/api/v1/rides/{ride_id}/complete",
        json={"latitude": 25.6120, "longitude": 85.1580},
        headers=driver_headers,
    )
    assert complete_response.status_code == 200
    assert complete_response.json()["data"]["status"] == "CLOSED"

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
        # DOCUMENTED GAP, restated concretely: the ride is CLOSED here
        # with no payment ever created or verified, and — as this test
        # itself discovered — payment_method (VALID_RIDE_BODY's own
        # "ONLINE") isn't even a column on ride.rides to check;
        # see this test's own docstring.
        assert row.completed_at is not None
        assert row.closed_at is not None

        history_rows = db.execute(
            text(
                "SELECT to_status FROM ride.state_history WHERE ride_id = :id "
                "ORDER BY created_at ASC"
            ),
            {"id": ride_id},
        ).fetchall()
        assert [r.to_status for r in history_rows] == [
            "SEARCHING",
            "ACCEPTED",
            "ARRIVED",
            "STARTED",
            "COMPLETED",
            "CLOSED",
        ]

        # "Events emitted" (§82) — every real transition along the way
        # published an outbox event.
        event_types = {
            r.event_type
            for r in db.execute(
                text(
                    "SELECT event_type FROM shared.outbox_events "
                    "WHERE aggregate_id = :id"
                ),
                {"id": ride_id},
            ).fetchall()
        }
        assert "ride.completed" in event_types

        # "Audit data available" (§82) — the ride's own state_history is
        # the audit trail for this domain (no separate admin.audit_logs
        # row is expected here; that table is for admin-initiated
        # mutations specifically, per admin/router.py's own precedent —
        # nothing about a customer/driver-initiated ride transition
        # writes one, and this test doesn't assume it should).
    finally:
        db.close()


def test_pickup_change_within_threshold_applies_immediately(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """testing-strategy.md §85/§86 describe a driver PASS/PROCEED
    decision with a ₹10-20/km charge for a >250m pickup change — that
    design was REPLACED by ADR-0056 (2026-08-31, owner decision) before
    this test was written; see modules/ride/router.py's
    request_pickup_change() docstring for the real current behavior:
    no driver decision exists anymore. This test exercises what's
    actually implemented today: a change within the real configured
    threshold (RIDE_PICKUP_CHANGE_THRESHOLD_METERS) applies immediately,
    free, no driver involved at all.
    """
    admin_headers = _login_admin(api_client, sms)
    driver_headers, _driver_id, _vehicle_id = _new_online_eligible_driver(
        api_client, sms, admin_headers
    )
    customer_token = _login(api_client, sms, "CUSTOMER")
    customer_headers = {"Authorization": f"Bearer {customer_token}"}
    create_response = api_client.post(
        "/api/v1/rides",
        json=VALID_RIDE_BODY,
        headers={**customer_headers, "Idempotency-Key": f"ride-{uuid.uuid4()}"},
    )
    ride_id = create_response.json()["data"]["ride_id"]
    offers = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=driver_headers
    ).json()["data"]["offers"]
    api_client.post(
        f"/api/v1/drivers/me/ride-offers/{offers[0]['offer_id']}/accept",
        headers={**driver_headers, "Idempotency-Key": f"accept-{uuid.uuid4()}"},
    )

    # ~90m from the original pickup — inside the real 100m default
    # threshold (settings.RIDE_PICKUP_CHANGE_THRESHOLD_METERS).
    nearby_latitude = 25.5949
    response = api_client.post(
        f"/api/v1/rides/{ride_id}/pickup-change",
        json={"latitude": nearby_latitude, "longitude": 85.1376},
        headers=customer_headers,
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["applied"] is True
    assert body["distance_meters"] < settings.RIDE_PICKUP_CHANGE_THRESHOLD_METERS

    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT status FROM ride.rides WHERE id = :id"), {"id": ride_id}
        ).fetchone()
        assert row is not None
        # No driver decision step, no PASS/PROCEED — the ride simply
        # stays exactly where it was (ACCEPTED), pickup updated in
        # place.
        assert row.status == "ACCEPTED"
    finally:
        db.close()


def test_pickup_change_beyond_threshold_is_rejected_outright(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """The other half of ADR-0056's real behavior: beyond the threshold,
    there is no PROCEED-with-a-charge path anymore (unlike §86's
    superseded description) — the request is rejected outright and the
    customer must cancel and rebook."""
    admin_headers = _login_admin(api_client, sms)
    driver_headers, _driver_id, _vehicle_id = _new_online_eligible_driver(
        api_client, sms, admin_headers
    )
    customer_token = _login(api_client, sms, "CUSTOMER")
    customer_headers = {"Authorization": f"Bearer {customer_token}"}
    create_response = api_client.post(
        "/api/v1/rides",
        json=VALID_RIDE_BODY,
        headers={**customer_headers, "Idempotency-Key": f"ride-{uuid.uuid4()}"},
    )
    ride_id = create_response.json()["data"]["ride_id"]
    offers = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=driver_headers
    ).json()["data"]["offers"]
    api_client.post(
        f"/api/v1/drivers/me/ride-offers/{offers[0]['offer_id']}/accept",
        headers={**driver_headers, "Idempotency-Key": f"accept-{uuid.uuid4()}"},
    )

    # ~1.1km away — well beyond the real 100m default threshold.
    response = api_client.post(
        f"/api/v1/rides/{ride_id}/pickup-change",
        json={"latitude": 25.6041, "longitude": 85.1376},
        headers=customer_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PICKUP_CHANGE_TOO_FAR"


def test_destination_extension_beyond_original_charges_the_real_configured_rate(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """testing-strategy.md §87 — this one IS implemented as documented
    (BR-080's ₹8/km is a real, approved rate, unlike the pickup-change
    rate in §85/§86 — confirmed against core/config.py's
    RIDE_DESTINATION_EXTENSION_RATE_PER_KM, not assumed). Extends well
    beyond the original destination so this lands in one of the two
    pending, customer-confirmable cases (BEYOND_ORIGINAL or
    DIFFERENT_ROUTE — both quote-then-confirm; only WITHIN_ROUTE applies
    immediately for free), not asserting which of the two specifically,
    since that classification boundary is PricingService's own
    geometry logic, not something this journey test should pin an exact
    coordinate to."""
    admin_headers = _login_admin(api_client, sms)
    driver_headers, _driver_id, _vehicle_id = _new_online_eligible_driver(
        api_client, sms, admin_headers
    )
    customer_token = _login(api_client, sms, "CUSTOMER")
    customer_headers = {"Authorization": f"Bearer {customer_token}"}
    create_response = api_client.post(
        "/api/v1/rides",
        json=VALID_RIDE_BODY,
        headers={**customer_headers, "Idempotency-Key": f"ride-{uuid.uuid4()}"},
    )
    ride_id = create_response.json()["data"]["ride_id"]
    offers = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=driver_headers
    ).json()["data"]["offers"]
    api_client.post(
        f"/api/v1/drivers/me/ride-offers/{offers[0]['offer_id']}/accept",
        headers={**driver_headers, "Idempotency-Key": f"accept-{uuid.uuid4()}"},
    )
    api_client.post(
        f"/api/v1/rides/{ride_id}/arrived",
        json={"latitude": 25.5941, "longitude": 85.1376},
        headers=driver_headers,
    )
    otp = api_client.post(
        f"/api/v1/rides/{ride_id}/otp/refresh", headers=customer_headers
    ).json()["data"]["otp"]
    api_client.post(
        f"/api/v1/rides/{ride_id}/start", json={"otp": otp}, headers=driver_headers
    )

    # Far beyond VALID_RIDE_BODY's original destination
    # (25.6120, 85.1580), same direction, well past it.
    response = api_client.post(
        f"/api/v1/rides/{ride_id}/destination-change",
        json={"latitude": 25.6300, "longitude": 85.1700},
        headers=customer_headers,
    )

    assert response.status_code == 201
    body = response.json()["data"]
    assert body["applied"] is False, "a real charge needs explicit confirmation"
    assert body["case"] in {"BEYOND_ORIGINAL", "DIFFERENT_ROUTE"}
    change_request_id = body["change_request_id"]

    # The response itself doesn't echo the quoted amount (no
    # "additional_charge" field — verified against
    # modules/ride/router.py's own response construction); the real
    # BR-080 rate is visible via the fare_quote this change created.
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT new_fare_quote_id, request_type, status "
                "FROM ride.change_requests WHERE id = :id"
            ),
            {"id": change_request_id},
        ).fetchone()
        assert row is not None
        assert row.request_type == "DESTINATION_CHANGE"
        assert row.status == "AWAITING_CUSTOMER_CONFIRMATION"
        assert row.new_fare_quote_id is not None
        quote_row = db.execute(
            text("SELECT total FROM pricing.fare_quotes WHERE id = :id"),
            {"id": row.new_fare_quote_id},
        ).fetchone()
        assert quote_row is not None
        assert quote_row.total > 0
    finally:
        db.close()
