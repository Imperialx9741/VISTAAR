"""Integration tests: real HTTP layer (TestClient) + real Postgres,
exercising POST /api/v1/rides end-to-end, authenticated via a real OTP
login through modules.identity — same layered pattern as
tests/test_customer_api.py.

Skips (not fails) when Postgres is genuinely unreachable.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from core.database import SessionLocal
from main import app
from modules.identity.dependencies import get_sms_provider_dependency
from modules.identity.security import decode_access_token
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


def _login_as(
    api_client: TestClient, sms: CapturingSmsProvider, *, account_type: str
) -> str:
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


def _login_as_new_customer(api_client: TestClient, sms: CapturingSmsProvider) -> str:
    return _login_as(api_client, sms, account_type="CUSTOMER")


VALID_BODY = {
    "pickup": {"latitude": 25.5941, "longitude": 85.1376},
    "destination": {"latitude": 25.6120, "longitude": 85.1580},
    "vehicle_category": "CAB",
    "cab_tier": "ECO",
    "payment_method": "ONLINE",
}


def _idempotency_key() -> str:
    return f"test-{uuid.uuid4()}"


def _account_id_from_token(access_token: str) -> uuid.UUID:
    payload = decode_access_token(access_token)
    return uuid.UUID(payload["sub"])


def _create_real_ride(api_client: TestClient, access_token: str) -> uuid.UUID:
    """penalty.penalties.ride_id has a real foreign key to ride.rides.id
    (unlike user_id, deliberately generic/FK-less) — a penalty seeded
    against a random UUID fails, so tests that need a real OUTSTANDING
    penalty need a real ride to attach it to first."""
    ride = api_client.post(
        "/api/v1/rides",
        json=VALID_BODY,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Idempotency-Key": _idempotency_key(),
        },
    ).json()["data"]
    return uuid.UUID(ride["ride_id"])


def test_create_ride_succeeds_for_authenticated_customer(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)

    response = api_client.post(
        "/api/v1/rides",
        json=VALID_BODY,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Idempotency-Key": _idempotency_key(),
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["error"] is None
    assert "request_id" in body
    assert body["data"]["status"] == "SEARCHING"
    # ADR-0020 Decision 6 (closes ADR-0010 Decision 1's `fare: null`):
    # CAB_ECO's seeded rate (migration 61a5a80a044e) is ₹55 base + ₹12/km;
    # VALID_BODY's pickup/destination haversine to ~2.854km, so
    # 55 + (12 * 2.854 ≈ 34.25) = 89.25, above the ₹79 minimum (no floor
    # applied). This customer has no promotion (never called GET
    # /api/v1/customers/me, the only composition point that grants one —
    # ADR-0019 Decision 4), so discount is 0.
    fare = body["data"]["fare"]
    assert fare is not None
    assert fare["total"] == 89.25
    assert fare["base"] == 89.25
    assert fare["discount"] == 0.0
    assert fare["currency"] == "INR"
    uuid.UUID(body["data"]["ride_id"])  # a real UUID


def test_create_ride_reserves_an_eligible_promotion_and_applies_the_discount(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """ADR-0020 Decision 6 — closes ADR-0019 Item 6: api-contracts.md
    §12's "Apply eligible promotion" step, composed now that a real fare
    exists to apply it against."""
    access_token = _login_as_new_customer(api_client, sms)
    headers = {"Authorization": f"Bearer {access_token}"}
    # GET /me is the composition point that grants a WELCOME entitlement
    # (BR-058: 50% off, ADR-0019 Decision 4).
    api_client.get("/api/v1/customers/me", headers=headers)

    response = api_client.post(
        "/api/v1/rides",
        json=VALID_BODY,
        headers={**headers, "Idempotency-Key": _idempotency_key()},
    )

    assert response.status_code == 201
    fare = response.json()["data"]["fare"]
    assert fare is not None
    assert fare["base"] == 89.25
    assert fare["discount"] == 44.62  # 89.25 * 50%, ROUND_HALF_EVEN
    assert fare["total"] == 44.63

    ride_id = response.json()["data"]["ride_id"]
    db = SessionLocal()
    try:
        entitlement_row = db.execute(
            text(
                "SELECT remaining_uses FROM promotion.entitlements e "
                "JOIN promotion.reservations r ON r.entitlement_id = e.id "
                "WHERE r.ride_id = :ride_id"
            ),
            {"ride_id": ride_id},
        ).fetchone()
        assert entitlement_row is not None
        assert entitlement_row.remaining_uses == 2  # decremented at reserve time
    finally:
        db.close()


def test_created_ride_is_owned_by_the_authenticated_customer(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    response = api_client.post(
        "/api/v1/rides",
        json=VALID_BODY,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Idempotency-Key": _idempotency_key(),
        },
    )
    ride_id = response.json()["data"]["ride_id"]

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT c.id FROM ride.rides r "
                "JOIN customer.customers c ON c.id = r.customer_id "
                "WHERE r.id = :ride_id"
            ),
            {"ride_id": ride_id},
        ).fetchone()
        assert row is not None
    finally:
        db.close()


def test_unauthenticated_request_is_rejected(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/rides",
        json=VALID_BODY,
        headers={"Idempotency-Key": _idempotency_key()},
    )
    assert response.status_code == 401


def test_driver_account_cannot_create_a_ride(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as(api_client, sms, account_type="DRIVER")

    response = api_client.post(
        "/api/v1/rides",
        json=VALID_BODY,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Idempotency-Key": _idempotency_key(),
        },
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    "bad_pickup",
    [
        {"latitude": 999.0, "longitude": 85.1376},
        {"latitude": 25.59, "longitude": -999.0},
    ],
)
def test_invalid_pickup_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider, bad_pickup: dict[str, float]
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    body = {**VALID_BODY, "pickup": bad_pickup}

    response = api_client.post(
        "/api/v1/rides",
        json=body,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Idempotency-Key": _idempotency_key(),
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_invalid_destination_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    body = {**VALID_BODY, "destination": {"latitude": 999.0, "longitude": 85.1376}}

    response = api_client.post(
        "/api/v1/rides",
        json=body,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Idempotency-Key": _idempotency_key(),
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_cab_without_a_tier_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """ADR-0020 Decision 1."""
    access_token = _login_as_new_customer(api_client, sms)
    body = {**VALID_BODY, "cab_tier": None}

    response = api_client.post(
        "/api/v1/rides",
        json=body,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Idempotency-Key": _idempotency_key(),
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_invalid_vehicle_category_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    body = {**VALID_BODY, "vehicle_category": "TRUCK"}

    response = api_client.post(
        "/api/v1/rides",
        json=body,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Idempotency-Key": _idempotency_key(),
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_missing_idempotency_key_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)

    response = api_client.post(
        "/api/v1/rides",
        json=VALID_BODY,
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 422


def test_ride_and_state_history_persist_in_postgres_with_correct_geometry(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    response = api_client.post(
        "/api/v1/rides",
        json=VALID_BODY,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Idempotency-Key": _idempotency_key(),
        },
    )
    ride_id = response.json()["data"]["ride_id"]

    db = SessionLocal()
    try:
        ride_row = db.execute(
            text(
                "SELECT status, active_fare_quote_id, "
                "ST_Y(original_pickup) AS pickup_lat, "
                "ST_X(original_pickup) AS pickup_lng, "
                "ST_Y(original_destination) AS dest_lat, "
                "ST_X(original_destination) AS dest_lng "
                "FROM ride.rides WHERE id = :id"
            ),
            {"id": ride_id},
        ).fetchone()
        assert ride_row is not None
        assert ride_row.status == "SEARCHING"
        # ADR-0020 Decision 6: set right after PricingService.
        # calculate_fare() creates the initial quote.
        assert ride_row.active_fare_quote_id is not None
        assert ride_row.pickup_lat == pytest.approx(25.5941)
        assert ride_row.pickup_lng == pytest.approx(85.1376)
        assert ride_row.dest_lat == pytest.approx(25.6120)
        assert ride_row.dest_lng == pytest.approx(85.1580)

        history_row = db.execute(
            text(
                "SELECT from_status, to_status, actor_type, actor_id "
                "FROM ride.state_history WHERE ride_id = :id"
            ),
            {"id": ride_id},
        ).fetchone()
        assert history_row is not None
        assert history_row.from_status is None
        assert history_row.to_status == "SEARCHING"
        assert history_row.actor_type == "CUSTOMER"
    finally:
        db.close()


def test_ride_creation_writes_a_ride_requested_outbox_event(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Phase 3 / Event & Outbox Foundation (ADR-0017) — the outbox row
    is written in the same transaction as the ride itself, independent
    of whether Kafka is reachable (event-contracts.md §2)."""
    access_token = _login_as_new_customer(api_client, sms)
    response = api_client.post(
        "/api/v1/rides",
        json=VALID_BODY,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Idempotency-Key": _idempotency_key(),
        },
    )
    ride_id = response.json()["data"]["ride_id"]

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT aggregate_type, event_type, event_version, "
                "published_at, payload "
                "FROM shared.outbox_events "
                "WHERE aggregate_id = :id AND event_type = 'ride.requested'"
            ),
            {"id": ride_id},
        ).fetchone()
        assert row is not None
        assert row.aggregate_type == "ride"
        assert row.event_version == 1
        assert row.published_at is None  # publisher hasn't run in-test
        assert row.payload["data"]["ride_id"] == ride_id
        assert row.payload["data"]["status"] == "SEARCHING"
        assert row.payload["producer"] == "ride-service"
    finally:
        db.close()


def test_idempotency_key_replay_with_same_body_returns_same_ride(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Idempotency-Key": _idempotency_key(),
    }

    first = api_client.post("/api/v1/rides", json=VALID_BODY, headers=headers)
    second = api_client.post("/api/v1/rides", json=VALID_BODY, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["data"]["ride_id"] == second.json()["data"]["ride_id"]

    db = SessionLocal()
    try:
        count = db.execute(
            text("SELECT COUNT(*) FROM ride.rides WHERE id = :id"),
            {"id": first.json()["data"]["ride_id"]},
        ).scalar()
        assert count == 1
    finally:
        db.close()


def test_idempotency_key_reuse_with_different_body_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    key = _idempotency_key()
    headers = {"Authorization": f"Bearer {access_token}", "Idempotency-Key": key}

    first = api_client.post("/api/v1/rides", json=VALID_BODY, headers=headers)
    different_body = {**VALID_BODY, "vehicle_category": "AUTO"}
    second = api_client.post("/api/v1/rides", json=different_body, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSE"


def test_two_different_idempotency_keys_create_two_rides(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """No "one active ride" business rule is documented — none is
    invented (ADR-0010 Decision 5). Two genuinely different requests
    from the same customer both succeed."""
    access_token = _login_as_new_customer(api_client, sms)
    headers = {"Authorization": f"Bearer {access_token}"}

    first = api_client.post(
        "/api/v1/rides",
        json=VALID_BODY,
        headers={**headers, "Idempotency-Key": _idempotency_key()},
    )
    second = api_client.post(
        "/api/v1/rides",
        json=VALID_BODY,
        headers={**headers, "Idempotency-Key": _idempotency_key()},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["data"]["ride_id"] != second.json()["data"]["ride_id"]


def test_concurrent_requests_with_the_same_idempotency_key_create_exactly_one_ride(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Real concurrency test: fires two genuinely concurrent HTTP
    requests (ThreadPoolExecutor, real OS threads, real independent DB
    connections per request — same technique as
    tests/test_vehicle_api.py's activation-conflict test) with the same
    Idempotency-Key and the same body. shared.idempotency_keys.key's
    UNIQUE constraint (database-design.md §35) is the concurrency-safety
    mechanism (see shared/idempotency.py) — exactly one request creates
    a ride; the other either replays that response or is momentarily
    rejected as "still in progress", never creates a second ride."""
    access_token = _login_as_new_customer(api_client, sms)
    key = _idempotency_key()
    headers = {"Authorization": f"Bearer {access_token}", "Idempotency-Key": key}

    def _post() -> int:
        return api_client.post(
            "/api/v1/rides", json=VALID_BODY, headers=headers
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: _post(), range(2)))

    assert 201 in results

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT response_body->'data'->>'ride_id' AS ride_id "
                "FROM shared.idempotency_keys WHERE key = :key"
            ),
            {"key": key},
        ).fetchone()
        assert row is not None
        ride_id = row.ride_id
        assert ride_id is not None

        count = db.execute(
            text("SELECT COUNT(*) FROM ride.rides WHERE id = :id"), {"id": ride_id}
        ).scalar()
        assert count == 1
    finally:
        db.close()


# --- Customer Cancellation (SEARCHING only, Phase 3 / Task 3.3, ADR-0012) --


def test_cancel_searching_ride_succeeds_and_is_free(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    headers = {"Authorization": f"Bearer {access_token}"}
    ride = api_client.post(
        "/api/v1/rides",
        json=VALID_BODY,
        headers={**headers, "Idempotency-Key": _idempotency_key()},
    ).json()["data"]

    response = api_client.post(
        f"/api/v1/rides/{ride['ride_id']}/cancel",
        json={"reason": "CUSTOMER_CHANGED_PLANS"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["ride_status"] == "CANCELLED"
    assert body["data"]["charge"] is None  # ADR-0012 Decision 1


def test_cancelled_ride_and_state_history_persist_in_postgres(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    headers = {"Authorization": f"Bearer {access_token}"}
    ride = api_client.post(
        "/api/v1/rides",
        json=VALID_BODY,
        headers={**headers, "Idempotency-Key": _idempotency_key()},
    ).json()["data"]

    api_client.post(
        f"/api/v1/rides/{ride['ride_id']}/cancel",
        json={"reason": "CUSTOMER_CHANGED_PLANS"},
        headers=headers,
    )

    db = SessionLocal()
    try:
        ride_row = db.execute(
            text("SELECT status, cancelled_at FROM ride.rides WHERE id = :id"),
            {"id": ride["ride_id"]},
        ).fetchone()
        assert ride_row is not None
        assert ride_row.status == "CANCELLED"
        assert ride_row.cancelled_at is not None

        history_row = db.execute(
            text(
                "SELECT from_status, to_status, reason, actor_type "
                "FROM ride.state_history WHERE ride_id = :id "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"id": ride["ride_id"]},
        ).fetchone()
        assert history_row is not None
        assert history_row.from_status == "SEARCHING"
        assert history_row.to_status == "CANCELLED"
        assert history_row.reason == "CUSTOMER_CHANGED_PLANS"
        assert history_row.actor_type == "CUSTOMER"
    finally:
        db.close()


def test_cancel_ride_unauthenticated_is_rejected(api_client: TestClient) -> None:
    response = api_client.post(
        f"/api/v1/rides/{uuid.uuid4()}/cancel", json={"reason": "x"}
    )
    assert response.status_code == 401


def test_driver_cannot_cancel_a_ride(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    customer_token = _login_as_new_customer(api_client, sms)
    ride = api_client.post(
        "/api/v1/rides",
        json=VALID_BODY,
        headers={
            "Authorization": f"Bearer {customer_token}",
            "Idempotency-Key": _idempotency_key(),
        },
    ).json()["data"]
    driver_token = _login_as(api_client, sms, account_type="DRIVER")

    response = api_client.post(
        f"/api/v1/rides/{ride['ride_id']}/cancel",
        json={"reason": "x"},
        headers={"Authorization": f"Bearer {driver_token}"},
    )

    assert response.status_code == 403


def test_cancel_another_customers_ride_is_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    owner_token = _login_as_new_customer(api_client, sms)
    ride = api_client.post(
        "/api/v1/rides",
        json=VALID_BODY,
        headers={
            "Authorization": f"Bearer {owner_token}",
            "Idempotency-Key": _idempotency_key(),
        },
    ).json()["data"]
    other_token = _login_as_new_customer(api_client, sms)

    response = api_client.post(
        f"/api/v1/rides/{ride['ride_id']}/cancel",
        json={"reason": "x"},
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RIDE_NOT_FOUND"


def test_cancel_unknown_ride_is_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    response = api_client.post(
        f"/api/v1/rides/{uuid.uuid4()}/cancel",
        json={"reason": "x"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RIDE_NOT_FOUND"


def test_cancel_already_cancelled_ride_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    headers = {"Authorization": f"Bearer {access_token}"}
    ride = api_client.post(
        "/api/v1/rides",
        json=VALID_BODY,
        headers={**headers, "Idempotency-Key": _idempotency_key()},
    ).json()["data"]
    api_client.post(
        f"/api/v1/rides/{ride['ride_id']}/cancel",
        json={"reason": "x"},
        headers=headers,
    )

    second = api_client.post(
        f"/api/v1/rides/{ride['ride_id']}/cancel",
        json={"reason": "x"},
        headers=headers,
    )

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "RIDE_NOT_CANCELLABLE"


def test_cancel_ride_rejects_blank_reason(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    headers = {"Authorization": f"Bearer {access_token}"}
    ride = api_client.post(
        "/api/v1/rides",
        json=VALID_BODY,
        headers={**headers, "Idempotency-Key": _idempotency_key()},
    ).json()["data"]

    response = api_client.post(
        f"/api/v1/rides/{ride['ride_id']}/cancel",
        json={"reason": "   "},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


# --- Outstanding Customer Penalty Display (ADR-0026, 2026-09-02) ----------


def test_create_ride_includes_no_outstanding_penalty_for_a_clean_customer(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)

    response = api_client.post(
        "/api/v1/rides",
        json=VALID_BODY,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Idempotency-Key": _idempotency_key(),
        },
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["outstanding_penalty"] is None
    assert data["total_payable"]["outstanding_penalty"] == 0.0
    assert data["total_payable"]["total"] == data["total_payable"]["ride_fare"]


def test_create_ride_includes_outstanding_penalty_when_one_exists(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    customer_id = _account_id_from_token(access_token)
    ride_id_1 = _create_real_ride(api_client, access_token)
    ride_id_2 = _create_real_ride(api_client, access_token)

    db = SessionLocal()
    try:
        penalty_service = PenaltyService(
            penalties=SqlAlchemyPenaltyRepository(db),
            strikes=SqlAlchemyStrikeRepository(db),
        )
        # BR-047/048: the first qualifying cancellation is free (₹0,
        # auto-SETTLED); the second produces a real ₹15 OUTSTANDING
        # penalty — the only way to reach that state through the real
        # domain service rather than a hand-crafted row.
        penalty_service.record_customer_cancellation(
            customer_id=customer_id, ride_id=ride_id_1, now=datetime.now(UTC)
        )
        penalty_service.record_customer_cancellation(
            customer_id=customer_id, ride_id=ride_id_2, now=datetime.now(UTC)
        )
        db.commit()
    finally:
        db.close()

    response = api_client.post(
        "/api/v1/rides",
        json=VALID_BODY,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Idempotency-Key": _idempotency_key(),
        },
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["outstanding_penalty"] == {"amount": 15.0, "currency": "INR"}
    total_payable = data["total_payable"]
    assert total_payable["outstanding_penalty"] == 15.0
    assert total_payable["ride_fare"] == data["fare"]["total"]
    assert total_payable["total"] == data["fare"]["total"] + 15.0
    assert total_payable["currency"] == "INR"
    # BR-057, ADR-0026 rule 3: never blocks booking, only informs it.
    assert data["status"] == "SEARCHING"


def test_create_ride_outstanding_penalty_never_includes_another_customers(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    other_access_token = _login_as_new_customer(api_client, sms)
    other_customer_id = _account_id_from_token(other_access_token)
    other_ride_id_1 = _create_real_ride(api_client, other_access_token)
    other_ride_id_2 = _create_real_ride(api_client, other_access_token)

    db = SessionLocal()
    try:
        penalty_service = PenaltyService(
            penalties=SqlAlchemyPenaltyRepository(db),
            strikes=SqlAlchemyStrikeRepository(db),
        )
        penalty_service.record_customer_cancellation(
            customer_id=other_customer_id,
            ride_id=other_ride_id_1,
            now=datetime.now(UTC),
        )
        penalty_service.record_customer_cancellation(
            customer_id=other_customer_id,
            ride_id=other_ride_id_2,
            now=datetime.now(UTC),
        )
        db.commit()
    finally:
        db.close()

    access_token = _login_as_new_customer(api_client, sms)

    response = api_client.post(
        "/api/v1/rides",
        json=VALID_BODY,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Idempotency-Key": _idempotency_key(),
        },
    )

    assert response.status_code == 201
    assert response.json()["data"]["outstanding_penalty"] is None


def test_cancelling_a_ride_releases_its_attached_penalty_for_the_next_ride(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Customer Outstanding Penalty Settlement (ADR-0066, owner decision
    2026-09-03): a ride carrying an attached penalty forward that gets
    cancelled before completion must not silently lose track of that
    penalty — it releases back to unattached-OUTSTANDING so the
    customer's next actual ride can pick it up instead."""
    access_token = _login_as_new_customer(api_client, sms)
    headers = {"Authorization": f"Bearer {access_token}"}
    customer_id = _account_id_from_token(access_token)
    ride_id_1 = _create_real_ride(api_client, access_token)
    ride_id_2 = _create_real_ride(api_client, access_token)

    db = SessionLocal()
    try:
        penalty_service = PenaltyService(
            penalties=SqlAlchemyPenaltyRepository(db),
            strikes=SqlAlchemyStrikeRepository(db),
        )
        penalty_service.record_customer_cancellation(
            customer_id=customer_id, ride_id=ride_id_1, now=datetime.now(UTC)
        )
        penalty_service.record_customer_cancellation(
            customer_id=customer_id, ride_id=ride_id_2, now=datetime.now(UTC)
        )
        db.commit()
    finally:
        db.close()

    # This ride attaches the ₹15 OUTSTANDING penalty (ADR-0066).
    first_response = api_client.post(
        "/api/v1/rides",
        json=VALID_BODY,
        headers={**headers, "Idempotency-Key": _idempotency_key()},
    )
    assert first_response.status_code == 201
    first_data = first_response.json()["data"]
    assert first_data["outstanding_penalty"] == {"amount": 15.0, "currency": "INR"}
    first_ride_id = first_data["ride_id"]

    cancel_response = api_client.post(
        f"/api/v1/rides/{first_ride_id}/cancel",
        json={"reason": "CUSTOMER_CHANGED_PLANS"},
        headers=headers,
    )
    assert cancel_response.status_code == 200

    # The penalty must still show as outstanding on the *next* ride —
    # not silently lost because the ride carrying it was cancelled.
    second_response = api_client.post(
        "/api/v1/rides",
        json=VALID_BODY,
        headers={**headers, "Idempotency-Key": _idempotency_key()},
    )
    assert second_response.status_code == 201
    second_data = second_response.json()["data"]
    assert second_data["outstanding_penalty"] == {"amount": 15.0, "currency": "INR"}

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT settlement_ride_id FROM penalty.penalties "
                "WHERE user_id = :customer_id AND amount = 15.00"
            ),
            {"customer_id": str(customer_id)},
        ).fetchone()
        assert row is not None
        assert str(row.settlement_ride_id) == second_data["ride_id"]
    finally:
        db.close()
