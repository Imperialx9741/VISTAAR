"""Integration tests: real HTTP layer (TestClient) + real Postgres,
exercising GET /api/v1/customers/me/promotions end-to-end, the
GrantWelcomePromotion composition at GET /api/v1/customers/me
(ADR-0019 Decision 4), and real-Postgres/real-concurrency tests for
PromotionService.reserve_entitlement()/consume_reservation()/
restore_reservation() called directly against the service (no literal
`/internal/promotions/...` HTTP endpoint exists for calling these
commands directly — ADR-0019 Decision 3), each concurrent call from its
own real thread with its own independent DB session, matching
tests/test_wallet_api.py's established technique. The commands
themselves ARE composed into the real ride-lifecycle HTTP endpoints
(reserve at Create Ride; consume/restore at ride completion/
cancellation, ADR-0070, 2026-09-04) — that composition's own real-HTTP
proof lives in tests/test_ride_lifecycle_api.py, not here.

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
from modules.identity.dependencies import get_sms_provider_dependency
from modules.identity.security import decode_access_token
from modules.promotion.domain.errors import PromotionAlreadyUsedError
from modules.promotion.repositories import (
    SqlAlchemyCampaignRepository,
    SqlAlchemyEntitlementRepository,
    SqlAlchemyReservationRepository,
    SqlAlchemyUsageRepository,
)
from modules.promotion.service import PromotionService


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


def _new_customer_with_profile(
    api_client: TestClient, sms: CapturingSmsProvider
) -> tuple[dict, uuid.UUID]:
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
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    # GET /me is the composition point that grants the welcome promotion
    # (ADR-0019 Decision 4) — same call test_customer_api.py already
    # relies on for auto-provisioning.
    profile = api_client.get("/api/v1/customers/me", headers=headers).json()["data"]
    return headers, uuid.UUID(profile["customer_id"])


def _create_ride(api_client: TestClient, headers: dict) -> uuid.UUID:
    """promotion.reservations.ride_id / promotion.usage.ride_id have a
    real foreign key to ride.rides (database-design.md §24.2/24.3,
    unlike wallet.transactions.ride_id which is nullable) — a genuine
    ride must exist first, via the real POST /api/v1/rides endpoint
    (Task 3.1)."""
    response = api_client.post(
        "/api/v1/rides",
        json={
            "pickup": {"latitude": 25.5941, "longitude": 85.1376},
            "destination": {"latitude": 25.6120, "longitude": 85.1580},
            "vehicle_category": "CAB",
            "cab_tier": "ECO",  # ADR-0020 Decision 1
            "payment_method": "ONLINE",
        },
        headers={**headers, "Idempotency-Key": f"test-{uuid.uuid4()}"},
    )
    assert response.status_code == 201
    return uuid.UUID(response.json()["data"]["ride_id"])


def _seed_entitlement_with_remaining_uses(
    customer_id: uuid.UUID, remaining_uses: int
) -> uuid.UUID:
    """Reaches a controlled "N uses left" state directly via SQL — the
    real-concurrency test below needs an exact remaining_uses=1 race,
    which grant_welcome_promotion() (3 uses) doesn't produce on its own."""
    entitlement_id = uuid.uuid4()
    now = datetime.now(UTC)
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO promotion.entitlements "
                "(id, customer_id, promotion_type, total_uses, remaining_uses, "
                "discount_percent, max_discount_amount, activated_at, "
                "expires_at, status) "
                "VALUES (:id, :customer_id, 'WELCOME', 3, :remaining_uses, 50, "
                "NULL, :now, :expires_at, 'ACTIVE')"
            ),
            {
                "id": str(entitlement_id),
                "customer_id": str(customer_id),
                "remaining_uses": remaining_uses,
                "now": now,
                "expires_at": now.replace(year=now.year + 1),
            },
        )
        db.commit()
    finally:
        db.close()
    return entitlement_id


# --- Get Promotions (composition with GET /api/v1/customers/me) --------


def test_get_my_profile_grants_welcome_promotion(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers, _ = _new_customer_with_profile(api_client, sms)

    response = api_client.get("/api/v1/customers/me/promotions", headers=headers)

    assert response.status_code == 200
    promotions = response.json()["data"]["promotions"]
    assert len(promotions) == 1
    assert promotions[0]["type"] == "WELCOME"
    assert promotions[0]["discount_percent"] == 50.0
    assert promotions[0]["remaining_uses"] == 3


def test_welcome_promotion_is_granted_exactly_once(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers, _ = _new_customer_with_profile(api_client, sms)

    api_client.get("/api/v1/customers/me", headers=headers)  # second access
    api_client.get("/api/v1/customers/me", headers=headers)  # third access

    response = api_client.get("/api/v1/customers/me/promotions", headers=headers)
    promotions = response.json()["data"]["promotions"]
    assert len(promotions) == 1


def test_get_my_promotions_unauthenticated_is_rejected(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/customers/me/promotions")
    assert response.status_code == 401


# --- Reserve / Consume / Restore lifecycle (called directly — no literal
# /internal/promotions/... endpoint, ADR-0019 Decision 3; the real
# ride-lifecycle HTTP composition is proven in test_ride_lifecycle_api.py
# instead, ADR-0070) ------------------------------------------------------


def test_reserve_then_consume_lifecycle(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers, customer_id = _new_customer_with_profile(api_client, sms)
    # A dedicated, separately-seeded entitlement (remaining_uses=3,
    # expires later than the auto-granted WELCOME one) — not the
    # customer's real WELCOME entitlement, which _create_ride() below
    # would otherwise also auto-reserve against (ADR-0020 Decision 6),
    # leaving remaining_uses at an unpredictable value for this test to
    # assert on.
    entitlement_id = _seed_entitlement_with_remaining_uses(customer_id, 3)
    ride_id = _create_ride(api_client, headers)

    db = SessionLocal()
    try:
        service = PromotionService(
            entitlements=SqlAlchemyEntitlementRepository(db),
            usages=SqlAlchemyUsageRepository(db),
            reservations=SqlAlchemyReservationRepository(db),
            campaigns=SqlAlchemyCampaignRepository(db),
        )
        reservation = service.reserve_entitlement(
            customer_id=customer_id,
            entitlement_id=entitlement_id,
            ride_id=ride_id,
            now=datetime.now(UTC),
        )
        db.commit()
        assert reservation.status.value == "RESERVED"

        usage = service.consume_reservation(
            reservation_id=reservation.id,
            discount_amount=Decimal("25.00"),
            now=datetime.now(UTC),
        )
        db.commit()
        assert usage.status.value == "CONSUMED"
    finally:
        db.close()

    db = SessionLocal()
    try:
        remaining = db.execute(
            text("SELECT remaining_uses FROM promotion.entitlements WHERE id = :id"),
            {"id": str(entitlement_id)},
        ).scalar()
        assert remaining == 2  # decremented at reserve time, not consume time
    finally:
        db.close()


# --- Redeem Campaign Code (ADR-0041) ----------------------------------


def _account_id_from_token(access_token: str) -> uuid.UUID:
    payload = decode_access_token(access_token)
    return uuid.UUID(payload["sub"])


def _new_admin_account_id(
    api_client: TestClient, sms: CapturingSmsProvider
) -> uuid.UUID:
    """A real identity.accounts row (account_type=ADMIN) via the
    ordinary OTP flow — admin.users.id and promotion.campaigns.
    created_by both have a real FK to identity.accounts(id), so a
    fresh uuid.uuid4() with no backing account row is rejected."""
    phone = _random_phone()
    request_response = api_client.post(
        "/api/v1/auth/otp/request",
        json={"phone": phone, "account_type": "ADMIN"},
    )
    challenge_id = request_response.json()["data"]["challenge_id"]
    otp = sms.sent[phone]
    tokens = api_client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "otp": otp},
    ).json()["data"]
    return _account_id_from_token(tokens["access_token"])


def _seed_active_campaign(
    api_client: TestClient,
    sms: CapturingSmsProvider,
    *,
    code: str,
    discount_type: str = "PERCENT",
    discount_value: Decimal = Decimal("50"),
    max_discount_amount: Decimal | None = Decimal("100"),
    minimum_fare: Decimal | None = None,
    vehicle_category: str | None = None,
    per_customer_use_limit: int = 1,
    total_usage_limit: int | None = None,
) -> uuid.UUID:
    """Direct-SQL seed, same technique as
    _seed_entitlement_with_remaining_uses above — an admin.users row is
    inserted too, since promotion.campaigns.created_by has a real FK to
    it (no full HTTP admin-auth flow needed just to exercise
    redemption)."""
    campaign_id = uuid.uuid4()
    admin_id = _new_admin_account_id(api_client, sms)
    now = datetime.now(UTC)
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO admin.users (id, role, status) "
                "VALUES (:id, 'SUPER_ADMIN', 'ACTIVE')"
            ),
            {"id": str(admin_id)},
        )
        db.execute(
            text(
                "INSERT INTO promotion.campaigns "
                "(id, code, name, vehicle_category, discount_type, discount_value, "
                "max_discount_amount, minimum_fare, eligible_scope, "
                "per_customer_use_limit, total_usage_limit, ride_count_limit, "
                "starts_at, ends_at, status, created_by, created_at) "
                "VALUES (:id, :code, 'Test campaign', :vehicle_category, "
                ":discount_type, :discount_value, :max_discount_amount, "
                ":minimum_fare, 'ALL', :per_customer_use_limit, "
                ":total_usage_limit, NULL, :starts_at, :ends_at, 'ACTIVE', "
                ":created_by, :now)"
            ),
            {
                "id": str(campaign_id),
                "code": code,
                "vehicle_category": vehicle_category,
                "discount_type": discount_type,
                "discount_value": discount_value,
                "max_discount_amount": max_discount_amount,
                "minimum_fare": minimum_fare,
                "per_customer_use_limit": per_customer_use_limit,
                "total_usage_limit": total_usage_limit,
                "starts_at": now.replace(year=now.year - 1),
                "ends_at": now.replace(year=now.year + 1),
                "created_by": str(admin_id),
                "now": now,
            },
        )
        db.commit()
    finally:
        db.close()
    return campaign_id


def test_redeem_campaign_code_creates_entitlement(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers, _customer_id = _new_customer_with_profile(api_client, sms)
    # Randomized, not the fixed "APITEST50" this test previously used —
    # promotion.campaigns.code is a real UNIQUE constraint against a
    # persistent test database with no per-test rollback (tests/
    # conftest.py), so a fixed code collides the second time this test
    # runs in the same session, the same class of gap this codebase has
    # hit repeatedly for other fixed test values.
    code = f"CODE{secrets.randbelow(10**8):08d}"
    _seed_active_campaign(api_client, sms, code=code)

    response = api_client.post(
        "/api/v1/customers/me/promotions/redeem",
        json={"code": code, "vehicle_category": "CAB", "fare": 500},
        headers=headers,
    )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["type"] == "CAMPAIGN"
    assert data["discount_percent"] == 50.0
    assert data["campaign_id"] is not None

    listed = api_client.get("/api/v1/customers/me/promotions", headers=headers)
    types = [p["type"] for p in listed.json()["data"]["promotions"]]
    assert "CAMPAIGN" in types


def test_redeem_campaign_code_unknown_code_returns_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers, _customer_id = _new_customer_with_profile(api_client, sms)

    response = api_client.post(
        "/api/v1/customers/me/promotions/redeem",
        json={"code": "NOPE", "vehicle_category": "CAB", "fare": 500},
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_redeem_campaign_code_over_per_customer_limit_returns_usage_limit_exceeded(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers, _customer_id = _new_customer_with_profile(api_client, sms)
    # Randomized, not the fixed "ONETIME" this test previously used —
    # same UNIQUE-constraint-collision reasoning as
    # test_redeem_campaign_code_creates_entitlement above.
    code = f"CODE{secrets.randbelow(10**8):08d}"
    _seed_active_campaign(api_client, sms, code=code, per_customer_use_limit=1)
    api_client.post(
        "/api/v1/customers/me/promotions/redeem",
        json={"code": code, "vehicle_category": "CAB", "fare": 500},
        headers=headers,
    )

    response = api_client.post(
        "/api/v1/customers/me/promotions/redeem",
        json={"code": code, "vehicle_category": "CAB", "fare": 500},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CAMPAIGN_USAGE_LIMIT_EXCEEDED"


def test_redeem_campaign_code_unauthenticated_is_rejected(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/api/v1/customers/me/promotions/redeem",
        json={"code": "ANY", "vehicle_category": "CAB", "fare": 500},
    )
    assert response.status_code == 401


def test_reserve_then_restore_lifecycle(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers, customer_id = _new_customer_with_profile(api_client, sms)
    # See test_reserve_then_consume_lifecycle's comment above — a
    # dedicated entitlement, decoupled from the auto-granted WELCOME one
    # _create_ride() below also auto-reserves against.
    entitlement_id = _seed_entitlement_with_remaining_uses(customer_id, 3)
    ride_id = _create_ride(api_client, headers)

    db = SessionLocal()
    try:
        service = PromotionService(
            entitlements=SqlAlchemyEntitlementRepository(db),
            usages=SqlAlchemyUsageRepository(db),
            reservations=SqlAlchemyReservationRepository(db),
            campaigns=SqlAlchemyCampaignRepository(db),
        )
        reservation = service.reserve_entitlement(
            customer_id=customer_id,
            entitlement_id=entitlement_id,
            ride_id=ride_id,
            now=datetime.now(UTC),
        )
        db.commit()

        restored = service.restore_reservation(
            reservation_id=reservation.id, now=datetime.now(UTC)
        )
        db.commit()
        assert restored.status.value == "RESTORED"
    finally:
        db.close()

    db = SessionLocal()
    try:
        remaining = db.execute(
            text("SELECT remaining_uses FROM promotion.entitlements WHERE id = :id"),
            {"id": str(entitlement_id)},
        ).scalar()
        assert remaining == 3  # given back
    finally:
        db.close()


# --- PromotionService.reserve_entitlement() real-concurrency test ------


def _reserve(
    customer_id: uuid.UUID, entitlement_id: uuid.UUID, ride_id: uuid.UUID
) -> str:
    """Runs in its own thread with its own DB session/connection.
    Returns "OK" or "EXHAUSTED"."""
    db = SessionLocal()
    try:
        service = PromotionService(
            entitlements=SqlAlchemyEntitlementRepository(db),
            usages=SqlAlchemyUsageRepository(db),
            reservations=SqlAlchemyReservationRepository(db),
            campaigns=SqlAlchemyCampaignRepository(db),
        )
        try:
            service.reserve_entitlement(
                customer_id=customer_id,
                entitlement_id=entitlement_id,
                ride_id=ride_id,
                now=datetime.now(UTC),
            )
        except PromotionAlreadyUsedError:
            db.rollback()
            return "EXHAUSTED"
        db.commit()
        return "OK"
    finally:
        db.close()


def test_concurrent_reservations_never_take_more_than_remaining_uses(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """database-design.md §44's row lock (get_by_id_for_update()): an
    entitlement with exactly 1 remaining use, raced by two concurrent
    reservations (different rides) — exactly one must succeed."""
    headers, customer_id = _new_customer_with_profile(api_client, sms)
    entitlement_id = _seed_entitlement_with_remaining_uses(customer_id, 1)
    ride_ids = [_create_ride(api_client, headers), _create_ride(api_client, headers)]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda ride_id: _reserve(customer_id, entitlement_id, ride_id),
                ride_ids,
            )
        )

    assert results.count("OK") == 1
    assert results.count("EXHAUSTED") == 1

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT remaining_uses, status FROM promotion.entitlements "
                "WHERE id = :id"
            ),
            {"id": str(entitlement_id)},
        ).fetchone()
        assert row is not None
        assert row.remaining_uses == 0
        assert row.status == "EXHAUSTED"

        reservation_count = db.execute(
            text(
                "SELECT COUNT(*) FROM promotion.reservations WHERE entitlement_id = :id"
            ),
            {"id": str(entitlement_id)},
        ).scalar()
        assert reservation_count == 1
    finally:
        db.close()


# --- ConsumePromotion/RestorePromotion double-resolve protection --------
#
# The 2026-09-04 fix (ADR-0070): consume_reservation()/restore_reservation()
# now lock the reservation row itself (get_by_id_for_update()), closing a
# real race that plain get_by_id() left open — two concurrent or replayed
# calls against the *same* reservation_id could both observe RESERVED
# before either committed and both proceed, double-consuming or
# double-restoring it. consume_reservation() also has a database-level
# backstop (uq_promotion_ride_use) even without this fix; restore_
# reservation() had none — remaining_uses is a plain mutable counter, not
# a unique-constrained INSERT — so this test is the real proof that gap is
# closed, not just the doubly-covered consume case.


def _restore(reservation_id: uuid.UUID) -> str:
    """Runs in its own thread with its own DB session/connection.
    Returns "OK" or "ALREADY_RESOLVED"."""
    db = SessionLocal()
    try:
        service = PromotionService(
            entitlements=SqlAlchemyEntitlementRepository(db),
            usages=SqlAlchemyUsageRepository(db),
            reservations=SqlAlchemyReservationRepository(db),
            campaigns=SqlAlchemyCampaignRepository(db),
        )
        try:
            service.restore_reservation(
                reservation_id=reservation_id, now=datetime.now(UTC)
            )
        except PromotionAlreadyUsedError:
            db.rollback()
            return "ALREADY_RESOLVED"
        db.commit()
        return "OK"
    finally:
        db.close()


def test_concurrent_restores_of_the_same_reservation_never_double_restore(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Two threads racing to restore the exact same (already-RESERVED)
    reservation — exactly one must succeed, and remaining_uses must be
    incremented exactly once, not twice."""
    headers, customer_id = _new_customer_with_profile(api_client, sms)
    entitlement_id = _seed_entitlement_with_remaining_uses(customer_id, 3)
    ride_id = _create_ride(api_client, headers)

    db = SessionLocal()
    try:
        service = PromotionService(
            entitlements=SqlAlchemyEntitlementRepository(db),
            usages=SqlAlchemyUsageRepository(db),
            reservations=SqlAlchemyReservationRepository(db),
            campaigns=SqlAlchemyCampaignRepository(db),
        )
        reservation = service.reserve_entitlement(
            customer_id=customer_id,
            entitlement_id=entitlement_id,
            ride_id=ride_id,
            now=datetime.now(UTC),
        )
        db.commit()
    finally:
        db.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: _restore(reservation.id), range(2)))

    assert results.count("OK") == 1
    assert results.count("ALREADY_RESOLVED") == 1

    db = SessionLocal()
    try:
        remaining = db.execute(
            text("SELECT remaining_uses FROM promotion.entitlements WHERE id = :id"),
            {"id": str(entitlement_id)},
        ).scalar()
        # 3 -> 2 at reserve time -> 3 again from exactly one restore, never 4.
        assert remaining == 3

        status = db.execute(
            text("SELECT status FROM promotion.reservations WHERE id = :id"),
            {"id": str(reservation.id)},
        ).scalar()
        assert status == "RESTORED"
    finally:
        db.close()


def _consume(reservation_id: uuid.UUID) -> str:
    """Runs in its own thread with its own DB session/connection.
    Returns "OK" or "ALREADY_RESOLVED"."""
    db = SessionLocal()
    try:
        service = PromotionService(
            entitlements=SqlAlchemyEntitlementRepository(db),
            usages=SqlAlchemyUsageRepository(db),
            reservations=SqlAlchemyReservationRepository(db),
            campaigns=SqlAlchemyCampaignRepository(db),
        )
        try:
            service.consume_reservation(
                reservation_id=reservation_id,
                discount_amount=Decimal("25.00"),
                now=datetime.now(UTC),
            )
        except PromotionAlreadyUsedError:
            db.rollback()
            return "ALREADY_RESOLVED"
        db.commit()
        return "OK"
    finally:
        db.close()


def test_concurrent_consumes_of_the_same_reservation_never_double_consume(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Same race as above, for consume — exactly one Usage row must be
    written, never two."""
    headers, customer_id = _new_customer_with_profile(api_client, sms)
    entitlement_id = _seed_entitlement_with_remaining_uses(customer_id, 3)
    ride_id = _create_ride(api_client, headers)

    db = SessionLocal()
    try:
        service = PromotionService(
            entitlements=SqlAlchemyEntitlementRepository(db),
            usages=SqlAlchemyUsageRepository(db),
            reservations=SqlAlchemyReservationRepository(db),
            campaigns=SqlAlchemyCampaignRepository(db),
        )
        reservation = service.reserve_entitlement(
            customer_id=customer_id,
            entitlement_id=entitlement_id,
            ride_id=ride_id,
            now=datetime.now(UTC),
        )
        db.commit()
    finally:
        db.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: _consume(reservation.id), range(2)))

    assert results.count("OK") == 1
    assert results.count("ALREADY_RESOLVED") == 1

    db = SessionLocal()
    try:
        usage_count = db.execute(
            text("SELECT COUNT(*) FROM promotion.usage WHERE entitlement_id = :id"),
            {"id": str(entitlement_id)},
        ).scalar()
        assert usage_count == 1
    finally:
        db.close()
