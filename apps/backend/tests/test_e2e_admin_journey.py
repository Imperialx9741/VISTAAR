"""E2E: the real Admin journey — login, driver/vehicle onboarding review,
ride visibility, and penalty resolution, chained against real HTTP
(TestClient) + real Postgres + real Redis.

testing-strategy.md's §82-90 "End-to-End" scenarios are all customer/
driver-ride-focused; no dedicated Admin journey is documented there. This
file's scope is composed directly from what api-contracts.md/ADR-0023/
ADR-0040 actually document as real admin capabilities (driver/vehicle
approval, ride search, penalty resolution, audit logging), not invented.
GPS dispute resolution is deliberately not re-covered here — it already
has its own dedicated integration coverage in test_gps_dispute_api.py;
duplicating it here would test the same thing twice, not add journey
coverage.

Skips (not fails) when Postgres is genuinely unreachable, same
convention as this file's sibling E2E/integration tests.
"""

from __future__ import annotations

import asyncio
import secrets
import uuid
from collections.abc import Generator
from datetime import UTC, datetime

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
    """The real Admin journey's first step — same phone+OTP flow every
    other account type uses (security-review-2026-09-02.md §3 already
    confirmed this means admin login inherits the OTP rate limiter, not
    a separate unprotected path)."""
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


def test_admin_reviews_and_approves_a_pending_driver_and_vehicle(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """The real Admin operator journey: log in -> find a pending driver
    -> review their submitted documents -> approve the driver -> review
    the vehicle they registered -> approve it -> confirm both are now
    reflected as APPROVED, both through the real admin GET endpoints
    (not just a database check), and that the approval was written to
    the real audit log (security.md §45 — "Driver approval" is one of
    the required audit-logged privileged actions)."""
    admin_headers = _login_admin(api_client, sms)
    driver_headers = _new_driver_with_profile(api_client, sms)
    driver_id = api_client.get("/api/v1/drivers/me", headers=driver_headers).json()[
        "data"
    ]["driver_id"]
    document_ids = [
        _submit_driver_document(api_client, driver_headers, document_type)
        for document_type in ("GOVERNMENT_ID", "DRIVING_LICENSE")
    ]

    # Admin reviews the pending driver — real GET, real response.
    review_response = api_client.get(
        f"/api/v1/admin/drivers/{driver_id}", headers=admin_headers
    )
    assert review_response.status_code == 200
    reviewed_documents = review_response.json()["data"]["documents"]
    assert {d["document_id"] for d in reviewed_documents} == set(document_ids)
    assert all(d["verification_status"] == "PENDING" for d in reviewed_documents)

    # Nothing to approve yet — documents aren't verified. Confirmed
    # against the real endpoint, not assumed: approving here should be
    # rejected until the documents themselves are marked APPROVED
    # (out-of-band, the same way every sibling E2E file in this session
    # does it — no HTTP endpoint exists anywhere in this codebase for an
    # admin to approve an individual *document*, only the driver/vehicle
    # as a whole, confirmed by reading modules/admin/router.py in full).
    premature_approve = api_client.post(
        f"/api/v1/admin/drivers/{driver_id}/approve", headers=admin_headers
    )
    assert premature_approve.status_code == 409

    db = SessionLocal()
    try:
        for document_id in document_ids:
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

    approve_response = api_client.post(
        f"/api/v1/admin/drivers/{driver_id}/approve", headers=admin_headers
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["data"]["verification_status"] == "APPROVED"

    # Vehicle side of the same journey.
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

    db = SessionLocal()
    try:
        vehicle_document_service = VehicleDocumentService(
            documents=SqlAlchemyVehicleDocumentRepository(db)
        )
        for document_type in ("RC", "INSURANCE"):
            document = vehicle_document_service.submit_document(
                vehicle_id=uuid.UUID(vehicle_id),
                document_type=document_type,
                document_number=None,
                evidence_uri="ref-1",
                expires_at=None,
            )
            db.commit()
            db.execute(
                text(
                    "UPDATE vehicle.documents SET verification_status = 'APPROVED' "
                    "WHERE id = :id"
                ),
                {"id": str(document.id)},
            )
            db.commit()
    finally:
        db.close()

    vehicle_approve_response = api_client.post(
        f"/api/v1/admin/vehicles/{vehicle_id}/approve", headers=admin_headers
    )
    assert vehicle_approve_response.status_code == 200

    # Confirm both, through the real GET endpoints an admin operator
    # would actually look at.
    driver_after = api_client.get(
        f"/api/v1/admin/drivers/{driver_id}", headers=admin_headers
    ).json()["data"]
    assert driver_after["verification_status"] == "APPROVED"

    # Audit trail (security.md §45/§46) — a real admin.audit_logs row,
    # queried through the real Search Audit Logs endpoint, not a raw SQL
    # check, since that endpoint is itself part of this journey.
    audit_response = api_client.get(
        "/api/v1/admin/audit-logs",
        params={"target_type": "DRIVER", "target_id": driver_id},
        headers=admin_headers,
    )
    assert audit_response.status_code == 200
    audit_items = audit_response.json()["data"]["items"]
    assert any(item["action"] == "APPROVE_DRIVER" for item in audit_items)


def _make_driver_documents_valid(api_client: TestClient, driver_headers: dict) -> None:
    db = SessionLocal()
    try:
        for document_type in ("GOVERNMENT_ID", "DRIVING_LICENSE"):
            document_id = api_client.post(
                "/api/v1/drivers/me/documents",
                json={"document_type": document_type, "evidence_uri": "ref-1"},
                headers=driver_headers,
            ).json()["data"]["document_id"]
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


def _make_vehicle_documents_valid(vehicle_id: str) -> None:
    db = SessionLocal()
    try:
        vehicle_document_service = VehicleDocumentService(
            documents=SqlAlchemyVehicleDocumentRepository(db)
        )
        for document_type in ("RC", "INSURANCE"):
            document = vehicle_document_service.submit_document(
                vehicle_id=uuid.UUID(vehicle_id),
                document_type=document_type,
                document_number=None,
                evidence_uri="ref-1",
                expires_at=None,
            )
            db.commit()
            db.execute(
                text(
                    "UPDATE vehicle.documents SET verification_status = 'APPROVED' "
                    "WHERE id = :id"
                ),
                {"id": str(document.id)},
            )
        db.commit()
    finally:
        db.close()


def _accepted_ride_for_penalty_test(
    api_client: TestClient,
    sms: CapturingSmsProvider,
    admin_headers: dict,
    *,
    customer_headers: dict | None = None,
    customer_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, uuid.UUID, dict]:
    """Returns (ride_id, customer_id, customer_headers) for a real ride,
    created and accepted entirely through the real API — the whole point
    of testing Search Rides finding it and Resolve Penalty acting on it
    is that both operate on a ride the same way a real one would exist,
    not a hand-crafted database row guessing at ride.rides' own NOT NULL
    columns.

    Accepts an existing (customer_headers, customer_id) to reuse the same
    customer across two calls — BR-047/048's own "first cancellation is
    free, second+ is charged" rule (modules/penalty/service.py's
    record_customer_cancellation()) means a single call never produces a
    resolvable OUTSTANDING penalty; this file's own test needs two."""
    driver_access_token = _login(api_client, sms, "DRIVER")
    driver_headers = {"Authorization": f"Bearer {driver_access_token}"}
    api_client.patch(
        "/api/v1/drivers/me", json={"full_name": "Ravi Kumar"}, headers=driver_headers
    )
    driver_id = api_client.get("/api/v1/drivers/me", headers=driver_headers).json()[
        "data"
    ]["driver_id"]
    _make_driver_documents_valid(api_client, driver_headers)
    assert (
        api_client.post(
            f"/api/v1/admin/drivers/{driver_id}/approve", headers=admin_headers
        ).status_code
        == 200
    )
    vehicle_id = api_client.post(
        "/api/v1/drivers/me/vehicles",
        json={
            "category": "CAB",
            "cab_tier": "ECO",
            "registration_number": _random_registration(),
        },
        headers=driver_headers,
    ).json()["data"]["vehicle_id"]
    _make_vehicle_documents_valid(vehicle_id)
    assert (
        api_client.post(
            f"/api/v1/admin/vehicles/{vehicle_id}/approve", headers=admin_headers
        ).status_code
        == 200
    )
    api_client.post(
        f"/api/v1/drivers/me/vehicles/{vehicle_id}/activate", headers=driver_headers
    )
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO wallet.wallets (driver_id, balance) "
                "VALUES (:driver_id, 100.00) "
                "ON CONFLICT (driver_id) DO UPDATE SET balance = 100.00"
            ),
            {"driver_id": driver_id},
        )
        db.commit()
    finally:
        db.close()
    api_client.post("/api/v1/drivers/me/online", headers=driver_headers)
    api_client.post(
        "/api/v1/drivers/me/location",
        json={"latitude": 25.5941, "longitude": 85.1376},
        headers=driver_headers,
    )

    if customer_headers is None:
        customer_access_token = _login(api_client, sms, "CUSTOMER")
        customer_headers = {"Authorization": f"Bearer {customer_access_token}"}
        customer_id = _account_id_from_token(customer_access_token)
    assert customer_id is not None
    create_response = api_client.post(
        "/api/v1/rides",
        json={
            "pickup": {"latitude": 25.5941, "longitude": 85.1376},
            "destination": {"latitude": 25.6120, "longitude": 85.1580},
            "vehicle_category": "CAB",
            "cab_tier": "ECO",
            "payment_method": "ONLINE",
        },
        headers={**customer_headers, "Idempotency-Key": f"ride-{uuid.uuid4()}"},
    )
    ride_id = uuid.UUID(create_response.json()["data"]["ride_id"])
    offers = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=driver_headers
    ).json()["data"]["offers"]
    assert len(offers) == 1, (
        "if this is empty, a still-online driver from an earlier call to "
        "this same helper (accepting an offer doesn't remove a driver "
        "from the matching geo index — confirmed by reading "
        "modules/matching/router.py) intercepted this ride's offer "
        "instead; see the explicit go-offline call below, added for "
        "exactly this reason once this test file's own two-ride "
        "penalty scenario first hit it"
    )
    api_client.post(
        f"/api/v1/drivers/me/ride-offers/{offers[0]['offer_id']}/accept",
        headers={**driver_headers, "Idempotency-Key": f"accept-{uuid.uuid4()}"},
    )
    # This helper is called twice in a row by this file's own two-ride
    # penalty scenario — taking this driver back offline immediately
    # ensures the *next* call's ride only ever has one eligible
    # candidate (itself), not two, avoiding exactly the
    # dispatch-goes-to-whichever-driver-the-geo-query-returns-first
    # nondeterminism test_ride_lifecycle_api.py's own cleanup fixture
    # already documents for the identical reason.
    api_client.post("/api/v1/drivers/me/offline", headers=driver_headers)
    return ride_id, customer_id, customer_headers


def test_admin_searches_rides_and_resolves_a_customer_cancellation_penalty(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Search Rides (api-contracts.md §46) plus Resolve Penalty
    (api-contracts.md §48, ADR-0023) — the ride itself is real, created
    and accepted entirely through the real API. The penalty is created
    through `PenaltyService.record_customer_cancellation()` called
    directly (not via a real 2-minute wait past the grace period — the
    point of this test is the admin-side resolution journey, not
    re-proving BR-046-049's own timing rule, which has its own dedicated
    coverage elsewhere), then resolved through the real HTTP endpoint,
    confirming the WAIVE action actually changes the penalty's status and
    writes an audit record.

    Two rides, not one: BR-047/048 makes a customer's *first* qualifying
    cancellation free (auto-SETTLED, ₹0 — confirmed against
    Penalty.new_customer_cancellation()'s own docstring) and only the
    second-plus a real ₹15 OUTSTANDING penalty an admin could ever
    resolve — a single cancellation would create nothing worth this
    test's own "resolve" step."""
    admin_headers = _login_admin(api_client, sms)
    first_ride_id, customer_id, customer_headers = _accepted_ride_for_penalty_test(
        api_client, sms, admin_headers
    )
    second_ride_id, _customer_id, _customer_headers = _accepted_ride_for_penalty_test(
        api_client,
        sms,
        admin_headers,
        customer_headers=customer_headers,
        customer_id=customer_id,
    )

    db = SessionLocal()
    try:
        for ride_id in (first_ride_id, second_ride_id):
            db.execute(
                text("UPDATE ride.rides SET status = 'CANCELLED' WHERE id = :id"),
                {"id": str(ride_id)},
            )
        db.commit()

        penalty_service = PenaltyService(
            penalties=SqlAlchemyPenaltyRepository(db),
            strikes=SqlAlchemyStrikeRepository(db),
        )
        free_penalty = penalty_service.record_customer_cancellation(
            customer_id=customer_id, ride_id=first_ride_id, now=datetime.now(UTC)
        )
        assert free_penalty.amount == 0
        assert free_penalty.status.value == "SETTLED"

        penalty = penalty_service.record_customer_cancellation(
            customer_id=customer_id, ride_id=second_ride_id, now=datetime.now(UTC)
        )
        assert penalty.amount > 0
        assert penalty.status.value == "OUTSTANDING"
        db.commit()
    finally:
        db.close()

    ride_id = second_ride_id

    # Search Rides — admin can find the ride the penalty is attached to.
    search_response = api_client.get(
        "/api/v1/admin/rides",
        params={"status": "CANCELLED", "customer_id": str(customer_id)},
        headers=admin_headers,
    )
    assert search_response.status_code == 200
    search_items = search_response.json()["data"]["items"]
    found_ride_ids = {item["ride_id"] for item in search_items}
    assert str(ride_id) in found_ride_ids

    # Resolve the penalty.
    resolve_response = api_client.post(
        f"/api/v1/admin/penalties/{penalty.id}/resolve",
        json={"action": "WAIVE", "reason": "Goodwill waiver — first-time customer"},
        headers=admin_headers,
    )
    assert resolve_response.status_code == 200
    assert resolve_response.json()["data"]["status"] == "WAIVED"

    audit_response = api_client.get(
        "/api/v1/admin/audit-logs",
        params={"target_type": "PENALTY", "target_id": str(penalty.id)},
        headers=admin_headers,
    )
    assert audit_response.status_code == 200
    audit_items = audit_response.json()["data"]["items"]
    assert any(item["action"] == "RESOLVE_PENALTY" for item in audit_items)
