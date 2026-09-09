"""Integration tests for modules.ride.tasks (ADR-0057) against a real
Postgres test database — same rationale/shape as
test_notification_tasks.py: promote_due_scheduled_rides() builds its
own SqlAlchemy-backed RideService/MatchingService internally and reads/
writes real rows, so a real DB is needed. Redis is also needed
(RedisNearbyDriverIndex, composed the same way modules/matching/
dependencies.py's own get_matching_service() already does) — skipped,
not failed, if either is unreachable.

Async calls are driven via asyncio.run() from ordinary sync test
functions — no pytest-asyncio plugin is configured in this codebase.
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from core.database import SessionLocal
from core.redis import get_redis_client
from main import app
from modules.identity.dependencies import get_sms_provider_dependency
from modules.ride.tasks import promote_due_scheduled_rides


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
    try:
        asyncio.run(_check_redis())
    except Exception:
        return False
    return True


async def _check_redis() -> None:
    client = get_redis_client()
    try:
        await client.ping()
    finally:
        await client.aclose()


pytestmark = pytest.mark.skipif(
    not _infra_available(),
    reason="Postgres or Redis is offline/unreachable (start docker-compose.dev.yml)",
)


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


def _login_as_new_customer(api_client: TestClient, sms: CapturingSmsProvider) -> str:
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
    access_token: str = tokens["access_token"]
    return access_token


def _create_scheduled_ride(
    api_client: TestClient, headers: dict, *, scheduled_for: datetime
) -> str:
    response = api_client.post(
        "/api/v1/rides",
        json={
            "pickup": {"latitude": 25.5941, "longitude": 85.1376},
            "destination": {"latitude": 25.6120, "longitude": 85.1580},
            "vehicle_category": "CAB",
            "cab_tier": "ECO",
            "payment_method": "ONLINE",
            "scheduled_for": scheduled_for.isoformat(),
        },
        headers={**headers, "Idempotency-Key": f"scheduled-{secrets.token_hex(8)}"},
    )
    assert response.status_code == 201, response.text
    ride_id: str = response.json()["data"]["ride_id"]
    return ride_id


def _ride_status(ride_id: str) -> str:
    db = SessionLocal()
    try:
        return db.execute(
            text("SELECT status FROM ride.rides WHERE id = :id"), {"id": ride_id}
        ).scalar_one()
    finally:
        db.close()


def test_promotes_a_ride_whose_lock_in_window_has_arrived(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """The 1-hour minimum lead time means a ride can never be created
    already due (lock_in_at = scheduled_for - 30min is always >= 30min
    in the future at creation) — simulate time passing by calling the
    task with a `now` later than real wall-clock time instead, same
    technique test_notification_tasks.py's own
    test_send_scheduled_broadcasts_dispatches_a_due_broadcast() already
    uses (there, in the opposite direction — a scheduled_at set relative
    to an artificially-earlier `now` at creation)."""
    access_token = _login_as_new_customer(api_client, sms)
    headers = {"Authorization": f"Bearer {access_token}"}
    # Comfortably above the 1-hour minimum lead time.
    scheduled_for = datetime.now(UTC) + timedelta(hours=1, minutes=2)
    ride_id = _create_scheduled_ride(api_client, headers, scheduled_for=scheduled_for)
    assert _ride_status(ride_id) == "SCHEDULED"

    db = SessionLocal()
    try:
        # lock_in_at = scheduled_for - 30min; simulate that moment having
        # arrived.
        promoted = asyncio.run(
            promote_due_scheduled_rides(
                db=db, now=scheduled_for - timedelta(minutes=25)
            )
        )
    finally:
        db.close()

    assert promoted == 1
    assert _ride_status(ride_id) == "SEARCHING"


def test_promoting_a_ride_publishes_schedule_promoted_event(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    headers = {"Authorization": f"Bearer {access_token}"}
    scheduled_for = datetime.now(UTC) + timedelta(hours=1, minutes=2)
    ride_id = _create_scheduled_ride(api_client, headers, scheduled_for=scheduled_for)

    db = SessionLocal()
    try:
        asyncio.run(
            promote_due_scheduled_rides(
                db=db, now=scheduled_for - timedelta(minutes=25)
            )
        )
    finally:
        db.close()

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT event_type FROM shared.outbox_events "
                "WHERE aggregate_id = :ride_id "
                "AND event_type = 'ride.schedule_promoted'"
            ),
            {"ride_id": ride_id},
        ).fetchone()
    finally:
        db.close()
    assert row is not None


def test_does_not_promote_a_ride_not_yet_due(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    headers = {"Authorization": f"Bearer {access_token}"}
    # 24 hours out — lock_in_at is 23.5 hours in the future, nowhere
    # near due.
    scheduled_for = datetime.now(UTC) + timedelta(hours=24)
    ride_id = _create_scheduled_ride(api_client, headers, scheduled_for=scheduled_for)

    db = SessionLocal()
    try:
        promoted = asyncio.run(
            promote_due_scheduled_rides(db=db, now=datetime.now(UTC))
        )
    finally:
        db.close()

    assert promoted == 0
    assert _ride_status(ride_id) == "SCHEDULED"


def test_is_a_no_op_when_nothing_is_due(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    db = SessionLocal()
    try:
        promoted = asyncio.run(
            promote_due_scheduled_rides(db=db, now=datetime.now(UTC))
        )
    finally:
        db.close()

    assert promoted == 0
