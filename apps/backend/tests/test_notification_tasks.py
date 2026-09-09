"""Integration tests for modules.notification.tasks (ADR-0039) against a
real Postgres test database — same rationale as
test_notification_consumer.py: these functions build their own
SqlAlchemy-backed NotificationService internally, and both look up real
rows (promotion.entitlements; driver.documents/vehicle.documents).

Async calls are driven via asyncio.run() from ordinary sync test
functions — no pytest-asyncio plugin is configured in this codebase.

Skips (not fails) when Postgres is genuinely unreachable.
"""

from __future__ import annotations

import asyncio
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from _integration_db import truncate_integration_tables
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from core.config import settings
from core.database import SessionLocal, engine
from main import app
from modules.admin.models import AdminUserORM
from modules.identity.dependencies import get_sms_provider_dependency
from modules.identity.security import decode_access_token
from modules.notification.domain.entities import AudienceType, Channel
from modules.notification.repositories import (
    SqlAlchemyBroadcastRepository,
    SqlAlchemyDeliveryRepository,
    SqlAlchemyPreferencesRepository,
    SqlAlchemyTemplateRepository,
)
from modules.notification.service import NotificationService
from modules.notification.tasks import (
    TEMPLATE_DOCUMENT_EXPIRING,
    TEMPLATE_PROMOTION_EXPIRING,
    check_expiring_documents,
    check_expiring_promotions,
    retry_failed_notifications,
    send_scheduled_broadcasts,
)


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


@pytest.fixture
def sms() -> CapturingSmsProvider:
    return CapturingSmsProvider()


@pytest.fixture
def api_client(sms: CapturingSmsProvider):
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


def _new_customer(api_client: TestClient, sms: CapturingSmsProvider) -> str:
    """Returns the customer's id — GET /me auto-provisions on first
    access (same pattern driver profiles use)."""
    access_token = _login(api_client, sms, "CUSTOMER")
    headers = {"Authorization": f"Bearer {access_token}"}
    customer_id: str = api_client.get("/api/v1/customers/me", headers=headers).json()[
        "data"
    ]["customer_id"]
    return customer_id


def _new_driver(api_client: TestClient, sms: CapturingSmsProvider) -> str:
    """Unlike GET /customers/me, GET /drivers/me does not auto-provision
    — a PATCH first creates the profile (same pattern every other test
    file needing a driver already establishes)."""
    access_token = _login(api_client, sms, "DRIVER")
    headers = {"Authorization": f"Bearer {access_token}"}
    api_client.patch(
        "/api/v1/drivers/me", json={"full_name": "Ravi Kumar"}, headers=headers
    )
    driver_id: str = api_client.get("/api/v1/drivers/me", headers=headers).json()[
        "data"
    ]["driver_id"]
    return driver_id


def _insert_entitlement(
    customer_id: str, *, expires_at: datetime, status: str = "ACTIVE"
) -> uuid.UUID:
    entitlement_id = uuid.uuid4()
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO promotion.entitlements "
                "(id, customer_id, promotion_type, total_uses, remaining_uses, "
                "discount_percent, activated_at, expires_at, status) "
                "VALUES (:id, :customer_id, 'WELCOME', 1, 1, 10.00, :now, "
                ":expires_at, :status)"
            ),
            {
                "id": str(entitlement_id),
                "customer_id": customer_id,
                "now": datetime.now(UTC),
                "expires_at": expires_at,
                "status": status,
            },
        )
        db.commit()
    finally:
        db.close()
    return entitlement_id


def _update_entitlement_expiry(entitlement_id: uuid.UUID, expires_at: datetime) -> None:
    db = SessionLocal()
    try:
        db.execute(
            text("UPDATE promotion.entitlements SET expires_at = :e WHERE id = :id"),
            {"e": expires_at, "id": str(entitlement_id)},
        )
        db.commit()
    finally:
        db.close()


def _provision_admin_id(api_client: TestClient, sms: CapturingSmsProvider) -> uuid.UUID:
    """A real admin.users row (FK target for notification.broadcasts.
    created_by) — same direct-insert technique as test_admin_api.py's
    own _provision_admin(), reached via a real ADMIN login first so the
    identity.accounts row it references already exists."""
    access_token = _login(api_client, sms, "ADMIN")
    account_id = uuid.UUID(decode_access_token(access_token)["sub"])
    db = SessionLocal()
    try:
        db.add(AdminUserORM(id=account_id, role="SUPER_ADMIN", status="ACTIVE"))
        db.commit()
    finally:
        db.close()
    return account_id


def _deliveries(user_id: str, template_key: str) -> list:
    db = SessionLocal()
    try:
        return list(
            db.execute(
                text(
                    "SELECT event_id, status FROM notification.deliveries "
                    "WHERE user_id = :user_id AND template_key = :template_key"
                ),
                {"user_id": user_id, "template_key": template_key},
            ).fetchall()
        )
    finally:
        db.close()


def test_promotion_expiring_within_window_notifies_the_customer(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    customer_id = _new_customer(api_client, sms)
    now = datetime.now(UTC)
    _insert_entitlement(
        customer_id,
        expires_at=now + timedelta(days=settings.PROMOTION_EXPIRY_WARNING_DAYS - 1),
    )

    db = SessionLocal()
    try:
        sent = asyncio.run(check_expiring_promotions(db=db, now=now))
    finally:
        db.close()

    assert sent == 1
    rows = _deliveries(customer_id, TEMPLATE_PROMOTION_EXPIRING)
    assert len(rows) == 1
    assert rows[0].status == "SENT"


def test_promotion_expiring_outside_window_is_not_notified(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    customer_id = _new_customer(api_client, sms)
    now = datetime.now(UTC)
    _insert_entitlement(
        customer_id,
        expires_at=now + timedelta(days=settings.PROMOTION_EXPIRY_WARNING_DAYS + 10),
    )

    db = SessionLocal()
    try:
        sent = asyncio.run(check_expiring_promotions(db=db, now=now))
    finally:
        db.close()

    assert sent == 0
    assert _deliveries(customer_id, TEMPLATE_PROMOTION_EXPIRING) == []


def test_already_expired_promotion_is_not_notified(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Lazy-expiry (promotion/service.py's own convention): status may
    still read ACTIVE past expires_at until something reads it — this
    task must not treat that as "expiring soon"."""
    customer_id = _new_customer(api_client, sms)
    now = datetime.now(UTC)
    _insert_entitlement(customer_id, expires_at=now - timedelta(days=1))

    db = SessionLocal()
    try:
        sent = asyncio.run(check_expiring_promotions(db=db, now=now))
    finally:
        db.close()

    assert sent == 0


def test_promotion_expiring_check_is_idempotent_across_runs(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    customer_id = _new_customer(api_client, sms)
    now = datetime.now(UTC)
    _insert_entitlement(customer_id, expires_at=now + timedelta(days=1))

    async def _run_twice() -> None:
        db = SessionLocal()
        try:
            await check_expiring_promotions(db=db, now=now)
            await check_expiring_promotions(db=db, now=now + timedelta(hours=1))
        finally:
            db.close()

    asyncio.run(_run_twice())

    assert len(_deliveries(customer_id, TEMPLATE_PROMOTION_EXPIRING)) == 1


def test_promotion_warns_again_after_a_renewal_to_a_later_expiry(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """A renewed entitlement (same id, later expires_at) that later
    approaches expiry again must get a second, distinct warning — not
    be silently suppressed by the first one's dedup key."""
    customer_id = _new_customer(api_client, sms)
    now = datetime.now(UTC)
    entitlement_id = _insert_entitlement(
        customer_id, expires_at=now + timedelta(days=1)
    )

    db = SessionLocal()
    try:
        asyncio.run(check_expiring_promotions(db=db, now=now))
    finally:
        db.close()
    assert len(_deliveries(customer_id, TEMPLATE_PROMOTION_EXPIRING)) == 1

    later_now = now + timedelta(days=30)
    _update_entitlement_expiry(entitlement_id, later_now + timedelta(days=1))
    db = SessionLocal()
    try:
        asyncio.run(check_expiring_promotions(db=db, now=later_now))
    finally:
        db.close()

    rows = _deliveries(customer_id, TEMPLATE_PROMOTION_EXPIRING)
    assert len(rows) == 2
    assert rows[0].event_id != rows[1].event_id


def test_expiring_driver_document_notifies_the_driver(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_id = _new_driver(api_client, sms)
    now = datetime.now(UTC)

    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO driver.documents "
                "(id, driver_id, document_type, verification_status, expires_at) "
                "VALUES (:id, :driver_id, 'DRIVING_LICENSE', 'APPROVED', :expires_at)"
            ),
            {
                "id": str(uuid.uuid4()),
                "driver_id": driver_id,
                "expires_at": now + timedelta(days=1),
            },
        )
        db.commit()
    finally:
        db.close()

    db = SessionLocal()
    try:
        sent = asyncio.run(check_expiring_documents(db=db, now=now))
    finally:
        db.close()

    assert sent == 1
    rows = _deliveries(driver_id, TEMPLATE_DOCUMENT_EXPIRING)
    assert len(rows) == 1
    assert rows[0].status == "SENT"


def test_expiring_vehicle_document_notifies_the_owning_driver(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_access_token = _login(api_client, sms, "DRIVER")
    driver_headers = {"Authorization": f"Bearer {driver_access_token}"}
    api_client.patch(
        "/api/v1/drivers/me", json={"full_name": "Ravi Kumar"}, headers=driver_headers
    )
    driver_id = api_client.get("/api/v1/drivers/me", headers=driver_headers).json()[
        "data"
    ]["driver_id"]
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
    now = datetime.now(UTC)

    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO vehicle.documents "
                "(id, vehicle_id, document_type, verification_status, expires_at) "
                "VALUES (:id, :vehicle_id, 'INSURANCE', 'APPROVED', :expires_at)"
            ),
            {
                "id": str(uuid.uuid4()),
                "vehicle_id": vehicle_id,
                "expires_at": now + timedelta(days=1),
            },
        )
        db.commit()
    finally:
        db.close()

    db = SessionLocal()
    try:
        sent = asyncio.run(check_expiring_documents(db=db, now=now))
    finally:
        db.close()

    assert sent == 1
    rows = _deliveries(driver_id, TEMPLATE_DOCUMENT_EXPIRING)
    assert len(rows) == 1


# --- Scheduled broadcasts (Admin Web §4.12, ADR-0055 Tier C) --------------
#
# This file's own truncate_integration_tables autouse fixture gives each
# test a genuinely empty customer.customers/driver.drivers/notification.*
# state — unlike test_admin_api.py (which accumulates state across its
# whole run), so ALL_CUSTOMERS/ALL_DRIVERS audience counts can be
# asserted exactly here, not just with ">= 1".


def _create_broadcast(
    api_client: TestClient,
    sms: CapturingSmsProvider,
    *,
    audience_type: AudienceType,
    scheduled_at: datetime | None,
    now: datetime,
) -> tuple[uuid.UUID, str]:
    """Returns (broadcast_id, template_key) — template_key is a fresh
    random uuid4 generated inside create_broadcast() itself, not
    derived from broadcast_id, so callers that need it (to look up the
    Delivery rows it produced) can't reconstruct it and must get it
    back here."""
    admin_id = _provision_admin_id(api_client, sms)
    db = SessionLocal()
    try:
        service = NotificationService(
            deliveries=SqlAlchemyDeliveryRepository(db),
            preferences=SqlAlchemyPreferencesRepository(db),
            templates=SqlAlchemyTemplateRepository(db),
            broadcasts=SqlAlchemyBroadcastRepository(db),
        )
        broadcast = service.create_broadcast(
            channel=Channel.IN_APP,
            subject=None,
            body="Scheduled broadcast body.",
            audience_type=audience_type,
            audience_user_ids=None,
            scheduled_at=scheduled_at,
            created_by=admin_id,
            now=now,
        )
        db.commit()
        return broadcast.id, broadcast.template_key
    finally:
        db.close()


def test_send_scheduled_broadcasts_dispatches_a_due_broadcast(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    customer_id = _new_customer(api_client, sms)
    now = datetime.now(UTC)
    broadcast_id, template_key = _create_broadcast(
        api_client,
        sms,
        audience_type=AudienceType.ALL_CUSTOMERS,
        scheduled_at=now - timedelta(minutes=1),
        # A genuinely-past scheduled_at (Broadcast.new() only normalizes
        # it to None — "send now" — relative to its OWN `now`, at
        # creation time; passing a `now` an hour earlier than the real
        # `now` above keeps this row SCHEDULED after creation, so this
        # test actually exercises the polling path, not
        # create_broadcast()'s own immediate-send normalization.
        now=now - timedelta(hours=1),
    )

    db = SessionLocal()
    try:
        dispatched = asyncio.run(send_scheduled_broadcasts(db=db, now=now))
    finally:
        db.close()

    assert dispatched == 1
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT status, sent_count, failed_count FROM "
                "notification.broadcasts WHERE id = :id"
            ),
            {"id": str(broadcast_id)},
        ).one()
    finally:
        db.close()
    assert row.status == "SENT"
    assert row.sent_count == 1
    assert row.failed_count == 0
    rows = _deliveries(customer_id, template_key)
    assert len(rows) == 1
    assert rows[0].status == "SENT"


def _insert_failed_delivery(
    *, user_id: str, channel: str, template_key: str
) -> uuid.UUID:
    delivery_id = uuid.uuid4()
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO notification.deliveries "
                "(id, user_id, channel, template_key, event_id, status, "
                "created_at) "
                "VALUES (:id, :user_id, :channel, :template_key, NULL, "
                "'FAILED', :now)"
            ),
            {
                "id": str(delivery_id),
                "user_id": user_id,
                "channel": channel,
                "template_key": template_key,
                "now": datetime.now(UTC),
            },
        )
        db.commit()
    finally:
        db.close()
    return delivery_id


def _delivery_status_and_retry_count(delivery_id: uuid.UUID) -> tuple[str, int]:
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT status, retry_count FROM notification.deliveries WHERE id = :id"
            ),
            {"id": str(delivery_id)},
        ).one()
        return row.status, row.retry_count
    finally:
        db.close()


# --- retry_failed_notifications (ADR-0075) --------------------------------


def test_retry_failed_notifications_retries_a_failed_sms_and_marks_sent(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    customer_id = _new_customer(api_client, sms)
    delivery_id = _insert_failed_delivery(
        user_id=customer_id, channel="SMS", template_key="RIDE_ACCEPTED"
    )

    db = SessionLocal()
    try:
        retried = asyncio.run(retry_failed_notifications(db=db, now=datetime.now(UTC)))
    finally:
        db.close()

    assert retried == 1
    status, retry_count = _delivery_status_and_retry_count(delivery_id)
    assert status == "SENT"
    assert retry_count == 1


def test_retry_failed_notifications_ignores_pending_and_sent_rows(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    customer_id = _new_customer(api_client, sms)
    db = SessionLocal()
    try:
        for status, key in (("PENDING", "A"), ("SENT", "B")):
            db.execute(
                text(
                    "INSERT INTO notification.deliveries "
                    "(id, user_id, channel, template_key, event_id, status, "
                    "created_at) "
                    "VALUES (:id, :user_id, 'SMS', :key, NULL, :status, :now)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "user_id": customer_id,
                    "key": key,
                    "status": status,
                    "now": datetime.now(UTC),
                },
            )
        db.commit()
    finally:
        db.close()

    db = SessionLocal()
    try:
        retried = asyncio.run(retry_failed_notifications(db=db, now=datetime.now(UTC)))
    finally:
        db.close()

    assert retried == 0


def test_retry_failed_notifications_never_retries_the_same_row_twice(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    customer_id = _new_customer(api_client, sms)
    delivery_id = _insert_failed_delivery(
        user_id=customer_id, channel="SMS", template_key="RIDE_ACCEPTED"
    )

    async def _run_twice() -> tuple[int, int]:
        db = SessionLocal()
        try:
            first = await retry_failed_notifications(db=db, now=datetime.now(UTC))
        finally:
            db.close()
        db = SessionLocal()
        try:
            second = await retry_failed_notifications(db=db, now=datetime.now(UTC))
        finally:
            db.close()
        return first, second

    first, second = asyncio.run(_run_twice())

    assert first == 1
    assert second == 0
    _status, retry_count = _delivery_status_and_retry_count(delivery_id)
    assert retry_count == 1


def test_send_scheduled_broadcasts_skips_a_not_yet_due_broadcast(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _new_driver(api_client, sms)
    now = datetime.now(UTC)
    broadcast_id, _template_key = _create_broadcast(
        api_client,
        sms,
        audience_type=AudienceType.ALL_DRIVERS,
        scheduled_at=now + timedelta(days=1),
        now=now,
    )

    db = SessionLocal()
    try:
        dispatched = asyncio.run(send_scheduled_broadcasts(db=db, now=now))
    finally:
        db.close()

    assert dispatched == 0
    db = SessionLocal()
    try:
        status = db.execute(
            text("SELECT status FROM notification.broadcasts WHERE id = :id"),
            {"id": str(broadcast_id)},
        ).scalar_one()
    finally:
        db.close()
    assert status == "SCHEDULED"
