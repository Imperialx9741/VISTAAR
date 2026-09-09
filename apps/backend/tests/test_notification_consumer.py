"""Integration tests for modules.notification.consumer.handle_event()
(ADR-0038) against a real Postgres test database — needed because,
unlike test_notification_service.py's pure-fake-repository unit tests,
handle_event() builds its own SqlAlchemy-backed NotificationService
internally (mirroring OutboxPublisher.publish_pending()'s own per-call
SessionLocal() pattern) and two of its handlers look up a real
ride.rides row.

Async handle_event() calls are driven via asyncio.run() from ordinary
sync test functions — no pytest-asyncio plugin is configured in this
codebase (see tests/test_identity_sms.py's own established pattern).

Skips (not fails) when Postgres is genuinely unreachable.
"""

from __future__ import annotations

import asyncio
import secrets
import uuid
from collections.abc import Generator
from decimal import Decimal
from typing import Any

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
from modules.notification.consumer import (
    TEMPLATE_PENALTY_APPLIED,
    TEMPLATE_RIDE_CANCELLED,
    TEMPLATE_RIDE_COMPLETED,
    TEMPLATE_RIDE_STARTED,
    TEMPLATE_SOS_TRIGGERED,
    handle_event,
)
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


def _login_admin(api_client: TestClient, sms: CapturingSmsProvider) -> dict:
    access_token = _login(api_client, sms, "ADMIN")
    account_id = uuid.UUID(decode_access_token(access_token)["sub"])
    db = SessionLocal()
    try:
        db.add(AdminUserORM(id=account_id, role="SUPER_ADMIN", status="ACTIVE"))
        db.commit()
    finally:
        db.close()
    return {"Authorization": f"Bearer {access_token}"}


def _new_driver_with_profile(api_client: TestClient, sms: CapturingSmsProvider) -> dict:
    access_token = _login(api_client, sms, "DRIVER")
    headers = {"Authorization": f"Bearer {access_token}"}
    api_client.patch(
        "/api/v1/drivers/me", json={"full_name": "Ravi Kumar"}, headers=headers
    )
    return headers


def _make_driver_documents_valid(api_client: TestClient, driver_headers: dict) -> None:
    db = SessionLocal()
    try:
        for document_type in ("GOVERNMENT_ID", "DRIVING_LICENSE"):
            response = api_client.post(
                "/api/v1/drivers/me/documents",
                json={"document_type": document_type, "evidence_uri": "ref-1"},
                headers=driver_headers,
            )
            document_id = response.json()["data"]["document_id"]
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
        service = VehicleDocumentService(
            documents=SqlAlchemyVehicleDocumentRepository(db)
        )
        for document_type in ("RC", "INSURANCE"):
            document = service.submit_document(
                vehicle_id=uuid.UUID(vehicle_id),
                document_type=document_type,
                document_number=None,
                evidence_uri="ref-1",
                expires_at=None,
            )
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


def _accepted_ride(
    api_client: TestClient, sms: CapturingSmsProvider, admin_headers: dict
) -> tuple[str, str, str]:
    """Returns (ride_id, customer_id, driver_id) for a real ACCEPTED
    ride — the minimal real state both ride.started's and
    ride.cancelled's handlers need to look up."""
    driver_headers = _new_driver_with_profile(api_client, sms)
    driver_id = api_client.get("/api/v1/drivers/me", headers=driver_headers).json()[
        "data"
    ]["driver_id"]
    _make_driver_documents_valid(api_client, driver_headers)
    api_client.post(f"/api/v1/admin/drivers/{driver_id}/approve", headers=admin_headers)

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
    api_client.post(
        f"/api/v1/admin/vehicles/{vehicle_id}/approve", headers=admin_headers
    )
    api_client.post(
        f"/api/v1/drivers/me/vehicles/{vehicle_id}/activate", headers=driver_headers
    )
    _seed_wallet_balance(driver_id, Decimal("100.00"))
    api_client.post("/api/v1/drivers/me/online", headers=driver_headers)
    api_client.post(
        "/api/v1/drivers/me/location",
        json={"latitude": 25.5941, "longitude": 85.1376},
        headers=driver_headers,
    )

    customer_token = _login(api_client, sms, "CUSTOMER")
    customer_headers = {"Authorization": f"Bearer {customer_token}"}
    ride = api_client.post(
        "/api/v1/rides",
        json={
            "pickup": {"latitude": 25.5941, "longitude": 85.1376},
            "destination": {"latitude": 25.6120, "longitude": 85.1580},
            "vehicle_category": "CAB",
            "cab_tier": "ECO",
            "payment_method": "ONLINE",
        },
        headers={**customer_headers, "Idempotency-Key": f"ride-{uuid.uuid4()}"},
    ).json()["data"]
    ride_id = ride["ride_id"]
    customer_id = uuid.UUID(decode_access_token(customer_token)["sub"])

    offers = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=driver_headers
    ).json()["data"]["offers"]
    api_client.post(
        f"/api/v1/drivers/me/ride-offers/{offers[0]['offer_id']}/accept",
        headers={**driver_headers, "Idempotency-Key": f"accept-{uuid.uuid4()}"},
    )

    return ride_id, str(customer_id), driver_id


def _delivery_rows(user_id: str, *, template_key: str | None = None) -> list[Any]:
    """Filterable by template_key — `_accepted_ride()` itself already
    triggers a real RIDE_ACCEPTED delivery for the customer (ADR-0034's
    existing synchronous dispatch, untouched by ADR-0038 Decision 4), so
    an unfiltered count would conflate that with whatever this test is
    actually asserting."""
    query = (
        "SELECT channel, template_key, status FROM notification.deliveries "
        "WHERE user_id = :user_id"
    )
    params: dict[str, str] = {"user_id": user_id}
    if template_key is not None:
        query += " AND template_key = :template_key"
        params["template_key"] = template_key

    db = SessionLocal()
    try:
        return list(db.execute(text(query), params).fetchall())
    finally:
        db.close()


def test_ride_started_notifies_the_customer(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_id, driver_id = _accepted_ride(api_client, sms, admin_headers)
    envelope = {
        "event_id": str(uuid.uuid4()),
        "event_type": "ride.started",
        "data": {
            "ride_id": ride_id,
            "driver_id": driver_id,
            "started_at": "2026-08-26T10:00:00Z",
        },
    }

    db = SessionLocal()
    try:
        asyncio.run(handle_event(envelope, db=db))
    finally:
        db.close()

    rows = _delivery_rows(customer_id, template_key=TEMPLATE_RIDE_STARTED)
    assert len(rows) == 1
    assert rows[0].channel == "IN_APP"
    assert rows[0].status == "SENT"


def test_ride_started_for_unknown_ride_is_skipped(api_client: TestClient) -> None:
    envelope = {
        "event_id": str(uuid.uuid4()),
        "event_type": "ride.started",
        "data": {
            "ride_id": str(uuid.uuid4()),
            "driver_id": str(uuid.uuid4()),
            "started_at": "2026-08-26T10:00:00Z",
        },
    }

    db = SessionLocal()
    try:
        asyncio.run(handle_event(envelope, db=db))  # must not raise
    finally:
        db.close()


def test_ride_completed_notifies_the_customer(api_client: TestClient) -> None:
    customer_id = str(uuid.uuid4())
    envelope = {
        "event_id": str(uuid.uuid4()),
        "event_type": "ride.completed",
        "data": {
            "ride_id": str(uuid.uuid4()),
            "customer_id": customer_id,
            "driver_id": str(uuid.uuid4()),
        },
    }

    db = SessionLocal()
    try:
        asyncio.run(handle_event(envelope, db=db))
    finally:
        db.close()

    rows = _delivery_rows(customer_id)
    assert len(rows) == 1
    assert rows[0].template_key == TEMPLATE_RIDE_COMPLETED
    assert rows[0].status == "SENT"


def test_ride_cancelled_by_customer_notifies_the_driver(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_id, driver_id = _accepted_ride(api_client, sms, admin_headers)
    envelope = {
        "event_id": str(uuid.uuid4()),
        "event_type": "ride.cancelled",
        "data": {
            "ride_id": ride_id,
            "cancelled_by": "CUSTOMER",
            "reason": "CUSTOMER_CHANGED_PLANS",
        },
    }

    db = SessionLocal()
    try:
        asyncio.run(handle_event(envelope, db=db))
    finally:
        db.close()

    assert len(_delivery_rows(driver_id, template_key=TEMPLATE_RIDE_CANCELLED)) == 1
    assert _delivery_rows(customer_id, template_key=TEMPLATE_RIDE_CANCELLED) == []


def test_ride_cancelled_by_driver_notifies_the_customer(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    ride_id, customer_id, driver_id = _accepted_ride(api_client, sms, admin_headers)
    envelope = {
        "event_id": str(uuid.uuid4()),
        "event_type": "ride.cancelled",
        "data": {
            "ride_id": ride_id,
            "cancelled_by": "DRIVER",
            "reason": "VEHICLE_ISSUE",
        },
    }

    db = SessionLocal()
    try:
        asyncio.run(handle_event(envelope, db=db))
    finally:
        db.close()

    assert len(_delivery_rows(customer_id, template_key=TEMPLATE_RIDE_CANCELLED)) == 1
    assert _delivery_rows(driver_id, template_key=TEMPLATE_RIDE_CANCELLED) == []


def test_ride_cancelled_with_no_driver_assigned_is_skipped(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """A customer may cancel while the ride is still SEARCHING — there
    is no driver yet to notify."""
    customer_token = _login(api_client, sms, "CUSTOMER")
    customer_headers = {"Authorization": f"Bearer {customer_token}"}
    ride = api_client.post(
        "/api/v1/rides",
        json={
            "pickup": {"latitude": 25.5941, "longitude": 85.1376},
            "destination": {"latitude": 25.6120, "longitude": 85.1580},
            "vehicle_category": "CAB",
            "cab_tier": "ECO",
            "payment_method": "ONLINE",
        },
        headers={**customer_headers, "Idempotency-Key": f"ride-{uuid.uuid4()}"},
    ).json()["data"]
    ride_id = ride["ride_id"]

    envelope = {
        "event_id": str(uuid.uuid4()),
        "event_type": "ride.cancelled",
        "data": {
            "ride_id": ride_id,
            "cancelled_by": "CUSTOMER",
            "reason": "CUSTOMER_CHANGED_PLANS",
        },
    }

    db = SessionLocal()
    try:
        asyncio.run(handle_event(envelope, db=db))  # must not raise
    finally:
        db.close()


def test_penalty_applied_notifies_the_penalized_user(api_client: TestClient) -> None:
    user_id = str(uuid.uuid4())
    envelope = {
        "event_id": str(uuid.uuid4()),
        "event_type": "penalty.applied",
        "data": {
            "penalty_id": str(uuid.uuid4()),
            "user_id": user_id,
            "ride_id": str(uuid.uuid4()),
            "amount": 30.0,
            "penalty_type": "NO_SHOW",
        },
    }

    db = SessionLocal()
    try:
        asyncio.run(handle_event(envelope, db=db))
    finally:
        db.close()

    rows = _delivery_rows(user_id)
    assert len(rows) == 1
    assert rows[0].template_key == TEMPLATE_PENALTY_APPLIED
    assert rows[0].status == "SENT"


def test_sos_triggered_notifies_the_safety_team(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """ADR-0050 — a Super Admin counts as the internal safety/call-center
    team (implicit full access, ADR-0040), so provisioning one via
    _login_admin() is enough setup; no separate SAFETY-MANAGE employee
    admin is needed to prove the recipient lookup works."""
    admin_headers = _login_admin(api_client, sms)
    admin_account_id = str(
        decode_access_token(admin_headers["Authorization"].removeprefix("Bearer "))[
            "sub"
        ]
    )
    envelope = {
        "event_id": str(uuid.uuid4()),
        "event_type": "safety.sos_triggered",
        "data": {
            "incident_id": str(uuid.uuid4()),
            "ride_id": str(uuid.uuid4()),
            "reporter_id": str(uuid.uuid4()),
            "location": {"latitude": 25.5941, "longitude": 85.1376},
            "triggered_at": "2026-08-28T10:00:00+00:00",
        },
    }

    db = SessionLocal()
    try:
        asyncio.run(handle_event(envelope, db=db))
    finally:
        db.close()

    rows = _delivery_rows(admin_account_id, template_key=TEMPLATE_SOS_TRIGGERED)
    channels = {row.channel for row in rows}
    assert channels == {"IN_APP", "SMS"}
    assert all(row.status == "SENT" for row in rows)


def test_sos_triggered_with_no_safety_team_is_skipped(api_client: TestClient) -> None:
    """No admin exists at all in this test's own isolated slice of the
    shared test database (truncate_integration_tables clears admin.users
    every test, same autouse fixture as every test above) — must not
    raise."""
    envelope = {
        "event_id": str(uuid.uuid4()),
        "event_type": "safety.sos_triggered",
        "data": {
            "incident_id": str(uuid.uuid4()),
            "ride_id": str(uuid.uuid4()),
            "reporter_id": str(uuid.uuid4()),
            "location": {"latitude": 25.5941, "longitude": 85.1376},
            "triggered_at": "2026-08-28T10:00:00+00:00",
        },
    }

    db = SessionLocal()
    try:
        asyncio.run(handle_event(envelope, db=db))  # must not raise
    finally:
        db.close()


def test_unrecognized_event_type_is_ignored(api_client: TestClient) -> None:
    """Every other event_type on the subscribed topics (e.g.
    ride.accepted, still dispatched synchronously per ADR-0038 Decision
    4) is silently ignored here, not an error."""
    envelope = {
        "event_id": str(uuid.uuid4()),
        "event_type": "ride.accepted",
        "data": {"ride_id": str(uuid.uuid4()), "driver_id": str(uuid.uuid4())},
    }

    db = SessionLocal()
    try:
        asyncio.run(handle_event(envelope, db=db))  # must not raise
    finally:
        db.close()


def test_handle_event_is_idempotent_on_redelivery(api_client: TestClient) -> None:
    """At-least-once Kafka delivery: processing the identical envelope
    twice must not create a second Delivery row (ADR-0038 Decision 2 —
    relies on NotificationService.send()'s own dedup, ADR-0034)."""
    user_id = str(uuid.uuid4())
    envelope = {
        "event_id": str(uuid.uuid4()),
        "event_type": "penalty.applied",
        "data": {
            "penalty_id": str(uuid.uuid4()),
            "user_id": user_id,
            "ride_id": str(uuid.uuid4()),
            "amount": 30.0,
            "penalty_type": "NO_SHOW",
        },
    }

    async def _handle_twice() -> None:
        db = SessionLocal()
        try:
            await handle_event(envelope, db=db)
            await handle_event(envelope, db=db)
        finally:
            db.close()

    asyncio.run(_handle_twice())

    assert len(_delivery_rows(user_id)) == 1


# --- Consumer Idempotency: shared.processed_events (ADR-0071, 2026-09-04) --


def _processed_events_row(event_id: str) -> Any:
    db = SessionLocal()
    try:
        return db.execute(
            text(
                "SELECT consumer_name, processed_at FROM shared.processed_events "
                "WHERE event_id = :event_id"
            ),
            {"event_id": event_id},
        ).fetchone()
    finally:
        db.close()


def test_handle_event_records_a_processed_events_row(api_client: TestClient) -> None:
    """event-contracts.md §29: after a handler successfully applies its
    effect, the (consumer_name, event_id) pair is durably recorded."""
    event_id = str(uuid.uuid4())
    envelope = {
        "event_id": event_id,
        "event_type": "penalty.applied",
        "data": {
            "penalty_id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
            "ride_id": str(uuid.uuid4()),
            "amount": 30.0,
            "penalty_type": "NO_SHOW",
        },
    }

    db = SessionLocal()
    try:
        asyncio.run(handle_event(envelope, db=db))
    finally:
        db.close()

    row = _processed_events_row(event_id)
    assert row is not None
    assert row.consumer_name == "notification-consumer"
    assert row.processed_at is not None


def test_handle_event_skips_the_handler_entirely_once_already_processed(
    api_client: TestClient,
) -> None:
    """Stronger than test_handle_event_is_idempotent_on_redelivery above:
    proves the handler is never even invoked a second time (not merely
    that its own side effect happens to dedupe), by pre-marking the
    event processed via a direct insert and confirming zero Delivery
    rows are created — if the handler had run, `penalty.applied`'s
    handler always creates exactly one."""
    user_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    envelope = {
        "event_id": event_id,
        "event_type": "penalty.applied",
        "data": {
            "penalty_id": str(uuid.uuid4()),
            "user_id": user_id,
            "ride_id": str(uuid.uuid4()),
            "amount": 30.0,
            "penalty_type": "NO_SHOW",
        },
    }

    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO shared.processed_events (consumer_name, event_id) "
                "VALUES ('notification-consumer', :event_id)"
            ),
            {"event_id": event_id},
        )
        db.commit()
        asyncio.run(handle_event(envelope, db=db))
    finally:
        db.close()

    assert _delivery_rows(user_id) == []


def test_processed_events_is_scoped_per_consumer_name(api_client: TestClient) -> None:
    """A processed_events row recorded under a *different* consumer_name
    must not suppress this consumer's own handling — the primary key is
    (consumer_name, event_id), not event_id alone (event-contracts.md
    §29's own documented schema)."""
    user_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    envelope = {
        "event_id": event_id,
        "event_type": "penalty.applied",
        "data": {
            "penalty_id": str(uuid.uuid4()),
            "user_id": user_id,
            "ride_id": str(uuid.uuid4()),
            "amount": 30.0,
            "penalty_type": "NO_SHOW",
        },
    }

    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO shared.processed_events (consumer_name, event_id) "
                "VALUES ('some-other-consumer', :event_id)"
            ),
            {"event_id": event_id},
        )
        db.commit()
        asyncio.run(handle_event(envelope, db=db))
    finally:
        db.close()

    assert len(_delivery_rows(user_id)) == 1
