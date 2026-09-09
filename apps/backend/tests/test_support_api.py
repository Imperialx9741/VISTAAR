"""Integration tests: real HTTP layer (TestClient) + real Postgres,
exercising POST /api/v1/support/cases and GET /api/v1/support/cases/
{case_id} end-to-end (api-contracts.md §44), plus real-Postgres tests
for SupportService.assign_case()/resolve_case()/post_message() — none of
which has an HTTP endpoint yet (ADR-0022 Decision 6), so those are
called directly against the service, matching
tests/test_wallet_api.py's established technique. A real-concurrency
test proves assign_case()'s row lock.

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
from modules.admin.models import AdminUserORM
from modules.identity.dependencies import get_sms_provider_dependency
from modules.identity.security import decode_access_token
from modules.support.domain.entities import SenderType
from modules.support.domain.errors import SupportCaseNotAssignableError
from modules.support.repositories import (
    SqlAlchemySupportCaseRepository,
    SqlAlchemySupportMessageRepository,
)
from modules.support.service import SupportService


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


def _account_id_from_token(access_token: str) -> uuid.UUID:
    payload = decode_access_token(access_token)
    return uuid.UUID(payload["sub"])


def _login_as_new_customer(
    api_client: TestClient, sms: CapturingSmsProvider
) -> tuple[dict[str, str], uuid.UUID]:
    access_token = _login(api_client, sms, "CUSTOMER")
    return {"Authorization": f"Bearer {access_token}"}, _account_id_from_token(
        access_token
    )


def _provision_admin(account_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        db.add(AdminUserORM(id=account_id, role="SUPER_ADMIN", status="ACTIVE"))
        db.commit()
    finally:
        db.close()


def _login_admin(api_client: TestClient, sms: CapturingSmsProvider) -> dict[str, str]:
    access_token = _login(api_client, sms, "ADMIN")
    _provision_admin(_account_id_from_token(access_token))
    return {"Authorization": f"Bearer {access_token}"}


def _create_case(
    api_client: TestClient,
    headers: dict[str, str],
    *,
    category: str | None = "PAYMENT",
    ride_id: str | None = None,
    message: str = "Why was I charged ₹30?",
) -> dict[str, object]:
    response = api_client.post(
        "/api/v1/support/cases",
        json={"category": category, "ride_id": ride_id, "message": message},
        headers=headers,
    )
    assert response.status_code == 201
    data: dict[str, object] = response.json()["data"]
    return data


# --- Create Support Case -----------------------------------------------------


def test_create_support_case_succeeds(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers, _ = _login_as_new_customer(api_client, sms)

    case = _create_case(api_client, headers)

    assert case["status"] == "OPEN"
    assert case["category"] == "PAYMENT"
    assert case["priority"] == "NORMAL"
    assert case["assigned_admin_id"] is None
    uuid.UUID(str(case["case_id"]))


def test_create_support_case_without_category_or_ride(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers, _ = _login_as_new_customer(api_client, sms)

    case = _create_case(api_client, headers, category=None)

    assert case["category"] is None
    assert case["ride_id"] is None


def test_create_support_case_rejects_blank_message(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers, _ = _login_as_new_customer(api_client, sms)

    response = api_client.post(
        "/api/v1/support/cases",
        json={"category": "PAYMENT", "message": "   "},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_create_support_case_unauthenticated_is_rejected(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/api/v1/support/cases", json={"category": "PAYMENT", "message": "x"}
    )
    assert response.status_code == 401


def test_create_support_case_rejects_a_ride_the_caller_does_not_own(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    other_headers, _ = _login_as_new_customer(api_client, sms)
    other_ride = api_client.post(
        "/api/v1/rides",
        json={
            "pickup": {"latitude": 25.5941, "longitude": 85.1376},
            "destination": {"latitude": 25.6120, "longitude": 85.1580},
            "vehicle_category": "CAB",
            "cab_tier": "ECO",
            "payment_method": "ONLINE",
        },
        headers={**other_headers, "Idempotency-Key": f"ride-{uuid.uuid4()}"},
    ).json()["data"]

    headers, _ = _login_as_new_customer(api_client, sms)
    response = api_client.post(
        "/api/v1/support/cases",
        json={"category": "PAYMENT", "ride_id": other_ride["ride_id"], "message": "x"},
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RIDE_NOT_FOUND"


def test_create_support_case_writes_a_case_created_outbox_event(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers, _ = _login_as_new_customer(api_client, sms)

    case = _create_case(api_client, headers)

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT payload FROM shared.outbox_events "
                "WHERE aggregate_id = :id AND event_type = 'support.case_created'"
            ),
            {"id": case["case_id"]},
        ).fetchone()
        assert row is not None
        assert row.payload["data"]["case_id"] == case["case_id"]
        assert row.payload["data"]["category"] == "PAYMENT"
        assert row.payload["data"]["priority"] == "NORMAL"
        assert row.payload["producer"] == "support-service"
    finally:
        db.close()


# --- List My Support Cases (added 2026-09-04) ---------------------------


def test_list_my_support_cases_is_empty_for_a_new_customer(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers, _ = _login_as_new_customer(api_client, sms)

    response = api_client.get("/api/v1/support/cases", headers=headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["items"] == []
    assert data["pagination"] == {
        "page": 1,
        "page_size": 20,
        "total": 0,
        "total_pages": 0,
    }


def test_list_my_support_cases_returns_only_the_callers_own_cases(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """IDOR safety: another customer's case must never appear."""
    mine_headers, _ = _login_as_new_customer(api_client, sms)
    mine = _create_case(api_client, mine_headers)

    other_headers, _ = _login_as_new_customer(api_client, sms)
    _create_case(api_client, other_headers)

    response = api_client.get("/api/v1/support/cases", headers=mine_headers)

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert [item["case_id"] for item in items] == [mine["case_id"]]


def test_list_my_support_cases_orders_newest_first(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers, _ = _login_as_new_customer(api_client, sms)
    first = _create_case(api_client, headers, message="First issue")
    second = _create_case(api_client, headers, message="Second issue")

    response = api_client.get("/api/v1/support/cases", headers=headers)

    items = response.json()["data"]["items"]
    assert [item["case_id"] for item in items] == [
        second["case_id"],
        first["case_id"],
    ]


def test_list_my_support_cases_filters_by_status(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    customer_headers, _ = _login_as_new_customer(api_client, sms)
    open_case = _create_case(api_client, customer_headers)
    resolved_case = _create_case(api_client, customer_headers)
    admin_headers = _login_admin(api_client, sms)
    admin_id = _account_id_from_token(
        admin_headers["Authorization"].removeprefix("Bearer ")
    )

    db = SessionLocal()
    try:
        service = SupportService(
            cases=SqlAlchemySupportCaseRepository(db),
            messages=SqlAlchemySupportMessageRepository(db),
        )
        service.assign_case(
            case_id=uuid.UUID(str(resolved_case["case_id"])),
            admin_id=admin_id,
            now=datetime.now(UTC),
        )
        service.resolve_case(
            case_id=uuid.UUID(str(resolved_case["case_id"])), now=datetime.now(UTC)
        )
        db.commit()
    finally:
        db.close()

    response = api_client.get(
        "/api/v1/support/cases", params={"status": "OPEN"}, headers=customer_headers
    )

    items = response.json()["data"]["items"]
    assert [item["case_id"] for item in items] == [open_case["case_id"]]


def test_list_my_support_cases_rejects_an_unknown_status(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers, _ = _login_as_new_customer(api_client, sms)

    response = api_client.get(
        "/api/v1/support/cases", params={"status": "NOT_A_REAL_STATUS"}, headers=headers
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_list_my_support_cases_paginates(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers, _ = _login_as_new_customer(api_client, sms)
    for i in range(3):
        _create_case(api_client, headers, message=f"issue {i}")

    response = api_client.get(
        "/api/v1/support/cases",
        params={"page": 1, "page_size": 2},
        headers=headers,
    )

    data = response.json()["data"]
    assert len(data["items"]) == 2
    assert data["pagination"] == {
        "page": 1,
        "page_size": 2,
        "total": 3,
        "total_pages": 2,
    }


def test_list_my_support_cases_driver_can_also_list_their_own(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_token = _login(api_client, sms, "DRIVER")
    driver_headers = {"Authorization": f"Bearer {driver_token}"}
    case = _create_case(api_client, driver_headers)

    response = api_client.get("/api/v1/support/cases", headers=driver_headers)

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert [item["case_id"] for item in items] == [case["case_id"]]


def test_list_my_support_cases_unauthenticated_is_rejected(
    api_client: TestClient,
) -> None:
    response = api_client.get("/api/v1/support/cases")
    assert response.status_code == 401


def test_list_my_support_cases_rejects_admin(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """This is the self-service endpoint (a caller's own cases only) —
    an admin has no "own cases" concept here; Admin Web's own case
    search is the separate, already-existing SupportService.
    search_cases()/admin surface, not this one."""
    admin_headers = _login_admin(api_client, sms)

    response = api_client.get("/api/v1/support/cases", headers=admin_headers)

    assert response.status_code == 403


# --- Get Support Case ---------------------------------------------------


def test_get_support_case_returns_the_case_and_its_first_message(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers, _ = _login_as_new_customer(api_client, sms)
    case = _create_case(api_client, headers, message="Why was I charged ₹30?")

    response = api_client.get(
        f"/api/v1/support/cases/{case['case_id']}", headers=headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["case_id"] == case["case_id"]
    assert len(data["messages"]) == 1
    assert data["messages"][0]["message"] == "Why was I charged ₹30?"
    assert data["messages"][0]["sender_type"] == "CUSTOMER"


def test_get_support_case_denies_another_customers_case(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    owner_headers, _ = _login_as_new_customer(api_client, sms)
    case = _create_case(api_client, owner_headers)

    other_headers, _ = _login_as_new_customer(api_client, sms)
    response = api_client.get(
        f"/api/v1/support/cases/{case['case_id']}", headers=other_headers
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_get_support_case_allows_admin_to_view_any_case(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    customer_headers, _ = _login_as_new_customer(api_client, sms)
    case = _create_case(api_client, customer_headers)
    admin_headers = _login_admin(api_client, sms)

    response = api_client.get(
        f"/api/v1/support/cases/{case['case_id']}", headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["data"]["case_id"] == case["case_id"]


def test_get_support_case_unknown_id_is_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers, _ = _login_as_new_customer(api_client, sms)

    response = api_client.get(f"/api/v1/support/cases/{uuid.uuid4()}", headers=headers)

    assert response.status_code == 404


# --- assign / resolve / post_message (no HTTP endpoint, ADR-0022) -----------


def test_assign_then_resolve_lifecycle(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    customer_headers, _ = _login_as_new_customer(api_client, sms)
    case = _create_case(api_client, customer_headers)
    case_id = uuid.UUID(str(case["case_id"]))
    admin_headers = _login_admin(api_client, sms)
    admin_id = _account_id_from_token(admin_headers["Authorization"].split(" ")[1])

    db = SessionLocal()
    try:
        service = SupportService(
            cases=SqlAlchemySupportCaseRepository(db),
            messages=SqlAlchemySupportMessageRepository(db),
        )
        assigned = service.assign_case(
            case_id=case_id, admin_id=admin_id, now=datetime.now(UTC)
        )
        db.commit()
        assert assigned.status.value == "ASSIGNED"
        assert assigned.assigned_admin_id == admin_id

        reply = service.post_message(
            case_id=case_id,
            sender_type=SenderType.ADMIN,
            sender_id=admin_id,
            message="Looking into this now.",
            now=datetime.now(UTC),
        )
        db.commit()
        assert reply.sender_type is SenderType.ADMIN

        resolved = service.resolve_case(case_id=case_id, now=datetime.now(UTC))
        db.commit()
        assert resolved.status.value == "RESOLVED"
    finally:
        db.close()

    response = api_client.get(
        f"/api/v1/support/cases/{case_id}", headers=customer_headers
    )
    data = response.json()["data"]
    assert data["status"] == "RESOLVED"
    assert len(data["messages"]) == 2


def _assign(case_id: uuid.UUID, admin_id: uuid.UUID) -> str:
    """Runs in its own thread with its own DB session/connection.
    Returns "OK" or "NOT_ASSIGNABLE"."""
    db = SessionLocal()
    try:
        service = SupportService(
            cases=SqlAlchemySupportCaseRepository(db),
            messages=SqlAlchemySupportMessageRepository(db),
        )
        try:
            service.assign_case(
                case_id=case_id, admin_id=admin_id, now=datetime.now(UTC)
            )
        except SupportCaseNotAssignableError:
            db.rollback()
            return "NOT_ASSIGNABLE"
        db.commit()
        return "OK"
    finally:
        db.close()


def test_concurrent_assign_attempts_apply_exactly_once(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Same real-concurrency technique as
    test_safety_api.py::test_concurrent_acknowledge_attempts_apply_exactly_once
    — real row-locking (get_by_id_for_update) serializes two concurrent
    assign attempts on the same case; exactly one must succeed."""
    customer_headers, _ = _login_as_new_customer(api_client, sms)
    case = _create_case(api_client, customer_headers)
    case_id = uuid.UUID(str(case["case_id"]))
    admin_id = uuid.uuid4()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: _assign(case_id, admin_id), range(2)))

    assert results.count("OK") == 1
    assert results.count("NOT_ASSIGNABLE") == 1

    db = SessionLocal()
    try:
        status = db.execute(
            text("SELECT status FROM support.cases WHERE id = :id"),
            {"id": str(case_id)},
        ).scalar()
        assert status == "ASSIGNED"
    finally:
        db.close()
