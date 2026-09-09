"""Integration tests: real HTTP layer (TestClient) + real Postgres,
exercising the Admin API end-to-end (Phase 2 / Task 2.7A; extended
ADR-0040/BR-126/BR-127 for Admin Management and the permission model).

The *first* Super Admin a test needs is inserted directly via SQLAlchemy
(`_provision_admin()` below) — same as `scripts/provision_admin.py`'s
own ops-only bootstrapping, still the only way to create a Super Admin
at all (BR-127: no HTTP endpoint ever exists for that specifically).
Every *employee* admin used below, though, is created through the real
`POST /api/v1/admin/admins` endpoint (ADR-0040) — no direct-DB shortcut
for that one, since testing it *is* the point.

Skips (not fails) when Postgres is genuinely unreachable.
"""

from __future__ import annotations

import asyncio
import secrets
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from core.database import SessionLocal
from main import app
from modules.admin.models import AdminUserORM
from modules.identity.dependencies import get_sms_provider_dependency
from modules.identity.security import decode_access_token
from modules.notification.domain.entities import Channel
from modules.notification.repositories import (
    SqlAlchemyDeliveryRepository,
    SqlAlchemyPreferencesRepository,
    SqlAlchemyTemplateRepository,
)
from modules.notification.service import NotificationService
from modules.penalty.repositories import (
    SqlAlchemyPenaltyRepository,
    SqlAlchemyStrikeRepository,
)
from modules.penalty.service import PenaltyService
from modules.safety.repositories import (
    SqlAlchemySafetyEventRepository,
    SqlAlchemySafetyIncidentRepository,
)
from modules.safety.service import SafetyService
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
    """Stands in for scripts/provision_admin.py --role super_admin —
    same effect (a real admin.users row with role=SUPER_ADMIN), reached
    directly since BR-127 keeps this ops-only, never an HTTP endpoint."""
    db = SessionLocal()
    try:
        db.add(AdminUserORM(id=account_id, role="SUPER_ADMIN", status="ACTIVE"))
        db.commit()
    finally:
        db.close()


def _login_admin(api_client: TestClient, sms: CapturingSmsProvider) -> tuple[str, dict]:
    """A Super Admin — used throughout this file's non-permission-
    specific tests exactly the way a real ops-provisioned admin would
    be: full implicit access, nothing to configure. Permission-specific
    behavior (employee admins, VIEW/MANAGE gating) has its own tests
    below, using POST /api/v1/admin/admins instead of this helper."""
    access_token = _login(api_client, sms, "ADMIN")
    account_id = _account_id_from_token(access_token)
    _provision_admin(account_id)
    return access_token, {"Authorization": f"Bearer {access_token}"}


def _create_employee_admin(
    api_client: TestClient,
    super_admin_headers: dict,
    *,
    permissions: list[dict] | None = None,
) -> tuple[str, str]:
    """Creates a real employee admin via the actual HTTP endpoint
    (ADR-0040). Returns (admin_id, phone) — the phone lets the caller
    separately log in as this exact admin via the ordinary OTP flow
    (POST .../admins never returns a credential, same as
    scripts/provision_admin.py's own script)."""
    phone = _random_phone()
    response = api_client.post(
        "/api/v1/admin/admins",
        json={"phone": phone, "permissions": permissions or []},
        headers=super_admin_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["admin_id"], phone


def _login_employee_admin(
    api_client: TestClient, sms: CapturingSmsProvider, phone: str
) -> dict:
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
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _new_driver_with_profile(
    api_client: TestClient, sms: CapturingSmsProvider
) -> tuple[str, dict]:
    access_token = _login(api_client, sms, "DRIVER")
    headers = {"Authorization": f"Bearer {access_token}"}
    response = api_client.patch(
        "/api/v1/drivers/me", json={"full_name": "Ravi Kumar"}, headers=headers
    )
    driver_id: str = response.json()["data"]["driver_id"]
    return driver_id, headers


def _new_customer_with_profile(
    api_client: TestClient, sms: CapturingSmsProvider
) -> tuple[str, dict]:
    access_token = _login(api_client, sms, "CUSTOMER")
    headers = {"Authorization": f"Bearer {access_token}"}
    profile = api_client.get("/api/v1/customers/me", headers=headers).json()["data"]
    customer_id: str = profile["customer_id"]
    return customer_id, headers


def _trigger_sos_directly(reporter_id: uuid.UUID) -> uuid.UUID:
    """Direct-service-layer seed, same technique as
    _credit_wallet_directly below — the real HTTP endpoint
    (POST /api/v1/rides/{ride_id}/sos) requires an owned ride, more
    setup than this admin-side test needs; ride_id stays NULL, which is
    a real, supported shape (safety.incidents.ride_id is nullable)."""
    db = SessionLocal()
    try:
        service = SafetyService(
            incidents=SqlAlchemySafetyIncidentRepository(db),
            events=SqlAlchemySafetyEventRepository(db),
        )
        incident = service.trigger_sos(
            ride_id=None,
            reporter_id=reporter_id,
            incident_type="OTHER",
            latitude=25.5941,
            longitude=85.1376,
            now=datetime.now(UTC),
        )
        db.commit()
        return incident.id
    finally:
        db.close()


def _credit_wallet_directly(driver_id: uuid.UUID, *, amount: Decimal) -> None:
    """Same direct-service-layer technique as
    tests/test_wallet_api.py::_credit_directly — no HTTP endpoint exists
    for an unprompted wallet credit."""
    db = SessionLocal()
    try:
        service = WalletService(wallets=SqlAlchemyWalletRepository(db))
        service.credit(
            driver_id=driver_id,
            amount=amount,
            transaction_type="FEE_REVERSAL",
            ride_id=None,
            idempotency_key=f"test:{uuid.uuid4()}",
            now=datetime.now(UTC),
            reference_type=None,
            reference_id=None,
        )
        db.commit()
    finally:
        db.close()


def _new_vehicle(api_client: TestClient, driver_headers: dict) -> str:
    response = api_client.post(
        "/api/v1/drivers/me/vehicles",
        json={
            "category": "CAB",
            "cab_tier": "ECO",  # ADR-0020 Decision 1
            "registration_number": _random_registration(),
        },
        headers=driver_headers,
    )
    vehicle_id: str = response.json()["data"]["vehicle_id"]
    return vehicle_id


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
    """Stands in for the not-yet-triggered manual-review completion
    (Task 2.6B: CompleteManualReview -> apply_verification_outcome, no
    HTTP endpoint exists) — same "reach a state no endpoint produces yet"
    pattern as _provision_admin()/test_vehicle_api.py's _approve_vehicle()."""
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


def _make_driver_approvable(api_client: TestClient, driver_headers: dict) -> None:
    """Submits and approves both BR-123-required driver documents
    (GOVERNMENT_ID, DRIVING_LICENSE) so Approve Driver will succeed."""
    for document_type in ("GOVERNMENT_ID", "DRIVING_LICENSE"):
        document_id = _submit_driver_document(api_client, driver_headers, document_type)
        _mark_driver_document_approved(document_id)


def _submit_vehicle_document(vehicle_id: str, document_type: str) -> str:
    """No HTTP endpoint exists for vehicle documents (ADR-0007) — created
    directly via the service layer against the real DB, same pattern as
    tests/test_verification_integration.py."""
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


def _make_vehicle_approvable(vehicle_id: str) -> None:
    """Submits and approves both BR-123-required vehicle documents
    (RC, INSURANCE) so Approve Vehicle will succeed."""
    for document_type in ("RC", "INSURANCE"):
        document_id = _submit_vehicle_document(vehicle_id, document_type)
        _mark_vehicle_document_approved(document_id)


# --- Authentication/authorization -------------------------------------


def test_unauthenticated_driver_review_is_rejected(api_client: TestClient) -> None:
    response = api_client.get(f"/api/v1/admin/drivers/{uuid.uuid4()}")
    assert response.status_code == 401


def test_non_admin_cannot_access_admin_routes(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_id, driver_headers = _new_driver_with_profile(api_client, sms)

    response = api_client.get(
        f"/api/v1/admin/drivers/{driver_id}", headers=driver_headers
    )

    assert response.status_code == 403


def test_admin_account_without_admin_users_row_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "ADMIN")  # no _provision_admin() call
    driver_id, _ = _new_driver_with_profile(api_client, sms)

    response = api_client.get(
        f"/api/v1/admin/drivers/{driver_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


# --- Driver approval/rejection -----------------------------------------


def test_driver_review_returns_documents_and_verification_cases(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_id, driver_headers = _new_driver_with_profile(api_client, sms)
    api_client.post(
        "/api/v1/drivers/me/documents",
        json={"document_type": "DRIVING_LICENSE", "evidence_uri": "ref-1"},
        headers=driver_headers,
    )
    _, admin_headers = _login_admin(api_client, sms)

    response = api_client.get(
        f"/api/v1/admin/drivers/{driver_id}", headers=admin_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["driver_id"] == driver_id
    assert data["phone"].startswith("+91")
    assert len(data["documents"]) == 1
    assert data["documents"][0]["document_type"] == "DRIVING_LICENSE"
    assert len(data["documents"][0]["verification_cases"]) == 1
    assert data["documents"][0]["verification_cases"][0]["status"] == "PENDING"


def test_approve_driver_succeeds_and_is_reflected_on_review(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_id, driver_headers = _new_driver_with_profile(api_client, sms)
    _make_driver_approvable(api_client, driver_headers)
    _, admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        f"/api/v1/admin/drivers/{driver_id}/approve", headers=admin_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["verification_status"] == "APPROVED"
    assert data["operational_status"] == "OFFLINE"  # untouched

    review = api_client.get(f"/api/v1/admin/drivers/{driver_id}", headers=admin_headers)
    assert review.json()["data"]["verification_status"] == "APPROVED"


def test_approve_driver_twice_returns_invalid_state_transition(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_id, driver_headers = _new_driver_with_profile(api_client, sms)
    _make_driver_approvable(api_client, driver_headers)
    _, admin_headers = _login_admin(api_client, sms)
    api_client.post(f"/api/v1/admin/drivers/{driver_id}/approve", headers=admin_headers)

    response = api_client.post(
        f"/api/v1/admin/drivers/{driver_id}/approve", headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


# --- BR-123: required-document gate on Approve Driver -------------------


def test_approve_driver_blocked_when_no_documents_submitted(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_id, _ = _new_driver_with_profile(api_client, sms)
    _, admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        f"/api/v1/admin/drivers/{driver_id}/approve", headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DRIVER_NOT_ELIGIBLE"
    # Verification_status must not have moved off PENDING.
    review = api_client.get(f"/api/v1/admin/drivers/{driver_id}", headers=admin_headers)
    assert review.json()["data"]["verification_status"] == "PENDING"


def test_approve_driver_blocked_when_required_document_pending(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_id, driver_headers = _new_driver_with_profile(api_client, sms)
    # GOVERNMENT_ID approved, DRIVING_LICENSE submitted but left PENDING.
    gov_id_document_id = _submit_driver_document(
        api_client, driver_headers, "GOVERNMENT_ID"
    )
    _mark_driver_document_approved(gov_id_document_id)
    _submit_driver_document(api_client, driver_headers, "DRIVING_LICENSE")
    _, admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        f"/api/v1/admin/drivers/{driver_id}/approve", headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DRIVER_NOT_ELIGIBLE"


def test_approve_driver_blocked_when_required_document_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_id, driver_headers = _new_driver_with_profile(api_client, sms)
    _make_driver_approvable(api_client, driver_headers)
    # Now reject the GOVERNMENT_ID document directly (no HTTP endpoint
    # for document-level rejection exists — Task 2.6B service layer only).
    db = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE driver.documents SET verification_status = 'REJECTED' "
                "WHERE driver_id = :driver_id AND document_type = 'GOVERNMENT_ID'"
            ),
            {"driver_id": driver_id},
        )
        db.commit()
    finally:
        db.close()
    _, admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        f"/api/v1/admin/drivers/{driver_id}/approve", headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DRIVER_NOT_ELIGIBLE"


def test_approve_driver_blocked_when_required_document_expired(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_id, driver_headers = _new_driver_with_profile(api_client, sms)
    gov_id_document_id = _submit_driver_document(
        api_client, driver_headers, "GOVERNMENT_ID"
    )
    _mark_driver_document_approved(gov_id_document_id)
    # Driving licence: APPROVED but already expired.
    license_response = api_client.post(
        "/api/v1/drivers/me/documents",
        json={
            "document_type": "DRIVING_LICENSE",
            "evidence_uri": "ref-1",
            "expires_at": "2020-01-01T00:00:00Z",
        },
        headers=driver_headers,
    )
    license_document_id = license_response.json()["data"]["document_id"]
    _mark_driver_document_approved(license_document_id)
    _, admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        f"/api/v1/admin/drivers/{driver_id}/approve", headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DRIVER_NOT_ELIGIBLE"


def test_approve_driver_blocked_attempt_does_not_write_audit_log(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """A BR-123-blocked approval must not create a fake successful audit
    entry — the same DB transaction that fails to approve also never
    reaches record_audit_log()."""
    driver_id, _ = _new_driver_with_profile(api_client, sms)
    _, admin_headers = _login_admin(api_client, sms)

    api_client.post(f"/api/v1/admin/drivers/{driver_id}/approve", headers=admin_headers)

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT id FROM admin.audit_logs WHERE target_id = :target_id "
                "AND action = 'APPROVE_DRIVER'"
            ),
            {"target_id": driver_id},
        ).fetchone()
        assert row is None
    finally:
        db.close()


def test_reject_driver_succeeds_with_reason(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_id, _ = _new_driver_with_profile(api_client, sms)
    _, admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        f"/api/v1/admin/drivers/{driver_id}/reject",
        json={"reason": "Document illegible"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["verification_status"] == "REJECTED"


def test_approve_driver_creates_audit_log_with_correct_states(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    driver_id, driver_headers = _new_driver_with_profile(api_client, sms)
    _make_driver_approvable(api_client, driver_headers)
    admin_access_token, admin_headers = _login_admin(api_client, sms)
    admin_id = _account_id_from_token(admin_access_token)

    api_client.post(f"/api/v1/admin/drivers/{driver_id}/approve", headers=admin_headers)

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT admin_id, action, target_type, target_id, "
                "before_state, after_state FROM admin.audit_logs "
                "WHERE target_id = :target_id AND action = 'APPROVE_DRIVER'"
            ),
            {"target_id": driver_id},
        ).fetchone()
        assert row is not None
        assert str(row[0]) == str(admin_id)
        assert row[2] == "DRIVER"
        assert str(row[3]) == driver_id
        assert row[4] == {"verification_status": "PENDING"}
        assert row[5] == {"verification_status": "APPROVED"}
    finally:
        db.close()


# --- Vehicle approval/rejection -----------------------------------------


def test_approve_vehicle_succeeds_and_does_not_activate_it(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, driver_headers = _new_driver_with_profile(api_client, sms)
    vehicle_id = _new_vehicle(api_client, driver_headers)
    _make_vehicle_approvable(vehicle_id)
    _, admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        f"/api/v1/admin/vehicles/{vehicle_id}/approve", headers=admin_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["verification_status"] == "APPROVED"
    assert data["operational_status"] == "INACTIVE"  # untouched — ADR-0009


def test_approve_vehicle_twice_returns_invalid_state_transition(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, driver_headers = _new_driver_with_profile(api_client, sms)
    vehicle_id = _new_vehicle(api_client, driver_headers)
    _make_vehicle_approvable(vehicle_id)
    _, admin_headers = _login_admin(api_client, sms)
    api_client.post(
        f"/api/v1/admin/vehicles/{vehicle_id}/approve", headers=admin_headers
    )

    response = api_client.post(
        f"/api/v1/admin/vehicles/{vehicle_id}/approve", headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


# --- BR-123: required-document gate on Approve Vehicle -------------------


def test_approve_vehicle_blocked_when_no_documents_submitted(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, driver_headers = _new_driver_with_profile(api_client, sms)
    vehicle_id = _new_vehicle(api_client, driver_headers)
    _, admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        f"/api/v1/admin/vehicles/{vehicle_id}/approve", headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VEHICLE_NOT_ELIGIBLE"


def test_approve_vehicle_blocked_when_required_document_pending(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, driver_headers = _new_driver_with_profile(api_client, sms)
    vehicle_id = _new_vehicle(api_client, driver_headers)
    rc_document_id = _submit_vehicle_document(vehicle_id, "RC")
    _mark_vehicle_document_approved(rc_document_id)
    _submit_vehicle_document(vehicle_id, "INSURANCE")  # stays PENDING
    _, admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        f"/api/v1/admin/vehicles/{vehicle_id}/approve", headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VEHICLE_NOT_ELIGIBLE"


def test_approve_vehicle_blocked_when_required_document_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, driver_headers = _new_driver_with_profile(api_client, sms)
    vehicle_id = _new_vehicle(api_client, driver_headers)
    _make_vehicle_approvable(vehicle_id)
    db = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE vehicle.documents SET verification_status = 'REJECTED' "
                "WHERE vehicle_id = :vehicle_id AND document_type = 'RC'"
            ),
            {"vehicle_id": vehicle_id},
        )
        db.commit()
    finally:
        db.close()
    _, admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        f"/api/v1/admin/vehicles/{vehicle_id}/approve", headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VEHICLE_NOT_ELIGIBLE"


def test_approve_vehicle_blocked_when_required_document_expired(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, driver_headers = _new_driver_with_profile(api_client, sms)
    vehicle_id = _new_vehicle(api_client, driver_headers)
    rc_document_id = _submit_vehicle_document(vehicle_id, "RC")
    _mark_vehicle_document_approved(rc_document_id)
    insurance_document_id = _submit_vehicle_document(vehicle_id, "INSURANCE")
    _mark_vehicle_document_approved(insurance_document_id)
    db = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE vehicle.documents SET expires_at = '2020-01-01T00:00:00Z' "
                "WHERE id = :id"
            ),
            {"id": insurance_document_id},
        )
        db.commit()
    finally:
        db.close()
    _, admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        f"/api/v1/admin/vehicles/{vehicle_id}/approve", headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VEHICLE_NOT_ELIGIBLE"


def test_approve_vehicle_ignores_vehicle_photo_document(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """VEHICLE_PHOTO is deliberately excluded from BR-123's required set
    (ADR-0009 point C) — approval must succeed without one."""
    _, driver_headers = _new_driver_with_profile(api_client, sms)
    vehicle_id = _new_vehicle(api_client, driver_headers)
    _make_vehicle_approvable(vehicle_id)  # RC + INSURANCE only, no photo
    _, admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        f"/api/v1/admin/vehicles/{vehicle_id}/approve", headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["data"]["verification_status"] == "APPROVED"


def test_reject_vehicle_succeeds_with_reason(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, driver_headers = _new_driver_with_profile(api_client, sms)
    vehicle_id = _new_vehicle(api_client, driver_headers)
    _, admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        f"/api/v1/admin/vehicles/{vehicle_id}/reject",
        json={"reason": "RC mismatch"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["verification_status"] == "REJECTED"


def test_approve_nonexistent_vehicle_returns_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        f"/api/v1/admin/vehicles/{uuid.uuid4()}/approve", headers=admin_headers
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


# --- Permission enforcement (ADR-0040, BR-126) — "non-negotiable" per
# docs/15-admin-web/admin-web-implementation-plan.md §8: a real 403
# from the backend, not just a hidden button. ------------------------


def test_employee_admin_with_no_permissions_is_forbidden(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    driver_id, _driver_headers = _new_driver_with_profile(api_client, sms)
    _admin_id, phone = _create_employee_admin(api_client, super_admin_headers)
    employee_headers = _login_employee_admin(api_client, sms, phone)

    response = api_client.get(
        f"/api/v1/admin/drivers/{driver_id}", headers=employee_headers
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_employee_admin_with_view_permission_can_read_but_not_manage(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    driver_id, _driver_headers = _new_driver_with_profile(api_client, sms)
    _admin_id, phone = _create_employee_admin(
        api_client,
        super_admin_headers,
        permissions=[{"module": "DRIVERS", "access_level": "VIEW"}],
    )
    employee_headers = _login_employee_admin(api_client, sms, phone)

    read = api_client.get(
        f"/api/v1/admin/drivers/{driver_id}", headers=employee_headers
    )
    assert read.status_code == 200

    write = api_client.post(
        f"/api/v1/admin/drivers/{driver_id}/approve", headers=employee_headers
    )
    assert write.status_code == 403
    assert write.json()["error"]["code"] == "FORBIDDEN"


def test_employee_admin_with_manage_permission_can_approve(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    driver_id, driver_headers = _new_driver_with_profile(api_client, sms)
    _make_driver_approvable(api_client, driver_headers)
    _admin_id, phone = _create_employee_admin(
        api_client,
        super_admin_headers,
        permissions=[{"module": "DRIVERS", "access_level": "MANAGE"}],
    )
    employee_headers = _login_employee_admin(api_client, sms, phone)

    response = api_client.post(
        f"/api/v1/admin/drivers/{driver_id}/approve", headers=employee_headers
    )

    assert response.status_code == 200
    assert response.json()["data"]["verification_status"] == "APPROVED"


def test_employee_admin_cannot_reach_admin_management(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """ADMIN_MANAGEMENT is never grantable (BR-126) — even an employee
    admin with MANAGE on every other module they were given still gets
    403 here."""
    _, super_admin_headers = _login_admin(api_client, sms)
    _admin_id, phone = _create_employee_admin(
        api_client,
        super_admin_headers,
        permissions=[{"module": "DRIVERS", "access_level": "MANAGE"}],
    )
    employee_headers = _login_employee_admin(api_client, sms, phone)

    response = api_client.get("/api/v1/admin/admins", headers=employee_headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# --- Admin Management (ADR-0040, BR-126/BR-127) -----------------------


def test_create_employee_admin_returns_the_new_admin_and_its_permissions(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        "/api/v1/admin/admins",
        json={
            "phone": _random_phone(),
            "permissions": [{"module": "RIDES", "access_level": "VIEW"}],
        },
        headers=super_admin_headers,
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["role"] == "ADMIN"
    assert data["status"] == "ACTIVE"
    assert data["permissions"] == [{"module": "RIDES", "access_level": "VIEW"}]


def test_create_employee_admin_rejects_granting_admin_management(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        "/api/v1/admin/admins",
        json={
            "phone": _random_phone(),
            "permissions": [{"module": "ADMIN_MANAGEMENT", "access_level": "VIEW"}],
        },
        headers=super_admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_create_employee_admin_twice_for_the_same_phone_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    phone = _random_phone()
    first = api_client.post(
        "/api/v1/admin/admins",
        json={"phone": phone, "permissions": []},
        headers=super_admin_headers,
    )
    assert first.status_code == 201

    second = api_client.post(
        "/api/v1/admin/admins",
        json={"phone": phone, "permissions": []},
        headers=super_admin_headers,
    )

    assert second.status_code == 422
    assert second.json()["error"]["code"] == "VALIDATION_FAILED"


def test_list_admins_includes_created_employee_admins(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    admin_id, _phone = _create_employee_admin(api_client, super_admin_headers)

    response = api_client.get("/api/v1/admin/admins", headers=super_admin_headers)

    assert response.status_code == 200
    ids = [item["admin_id"] for item in response.json()["data"]["items"]]
    assert admin_id in ids


def test_get_admin_returns_its_permissions(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    admin_id, _phone = _create_employee_admin(
        api_client,
        super_admin_headers,
        permissions=[{"module": "SAFETY", "access_level": "MANAGE"}],
    )

    response = api_client.get(
        f"/api/v1/admin/admins/{admin_id}", headers=super_admin_headers
    )

    assert response.status_code == 200
    assert response.json()["data"]["permissions"] == [
        {"module": "SAFETY", "access_level": "MANAGE"}
    ]


def test_update_permissions_replaces_the_whole_set(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    admin_id, _phone = _create_employee_admin(
        api_client,
        super_admin_headers,
        permissions=[{"module": "SAFETY", "access_level": "VIEW"}],
    )

    response = api_client.patch(
        f"/api/v1/admin/admins/{admin_id}/permissions",
        json={"permissions": [{"module": "SUPPORT", "access_level": "MANAGE"}]},
        headers=super_admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["permissions"] == [
        {"module": "SUPPORT", "access_level": "MANAGE"}
    ]


def test_disable_then_enable_admin(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    admin_id, phone = _create_employee_admin(
        api_client,
        super_admin_headers,
        permissions=[{"module": "RIDES", "access_level": "VIEW"}],
    )
    employee_headers = _login_employee_admin(api_client, sms, phone)

    disable = api_client.post(
        f"/api/v1/admin/admins/{admin_id}/disable", headers=super_admin_headers
    )
    assert disable.status_code == 200
    assert disable.json()["data"]["status"] == "DISABLED"

    blocked = api_client.get("/api/v1/admin/rides", headers=employee_headers)
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "ACCOUNT_SUSPENDED"

    enable = api_client.post(
        f"/api/v1/admin/admins/{admin_id}/enable", headers=super_admin_headers
    )
    assert enable.status_code == 200
    assert enable.json()["data"]["status"] == "ACTIVE"

    restored = api_client.get("/api/v1/admin/rides", headers=employee_headers)
    assert restored.status_code == 200


def test_update_permissions_refuses_to_target_a_super_admin(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    super_admin_id = _account_id_from_token(
        super_admin_headers["Authorization"].removeprefix("Bearer ")
    )

    response = api_client.patch(
        f"/api/v1/admin/admins/{super_admin_id}/permissions",
        json={"permissions": [{"module": "RIDES", "access_level": "VIEW"}]},
        headers=super_admin_headers,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_get_my_admin_profile_returns_role_and_permissions(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _admin_id, phone = _create_employee_admin(
        api_client,
        super_admin_headers,
        permissions=[{"module": "RIDES", "access_level": "VIEW"}],
    )
    employee_headers = _login_employee_admin(api_client, sms, phone)

    response = api_client.get("/api/v1/admin/me", headers=employee_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["role"] == "ADMIN"
    assert data["permissions"] == [{"module": "RIDES", "access_level": "VIEW"}]


# --- Campaigns / Offers & Coupons (ADR-0041) --------------------------------


def _campaign_body(**overrides: object) -> dict:
    body: dict = {
        "code": f"SAVE{secrets.randbelow(100000)}",
        "name": "50% off launch week",
        "vehicle_category": "CAB",
        "discount_type": "PERCENT",
        "discount_value": 50,
        "max_discount_amount": 100,
        "starts_at": "2026-01-01T00:00:00Z",
        "ends_at": "2030-01-01T00:00:00Z",
    }
    body.update(overrides)
    return body


def test_create_campaign_starts_as_draft(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        "/api/v1/admin/campaigns",
        json=_campaign_body(),
        headers=super_admin_headers,
    )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["status"] == "DRAFT"
    assert data["discount_type"] == "PERCENT"


def test_campaign_lifecycle_activate_pause_end(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    campaign_id = api_client.post(
        "/api/v1/admin/campaigns",
        json=_campaign_body(),
        headers=super_admin_headers,
    ).json()["data"]["campaign_id"]

    activated = api_client.post(
        f"/api/v1/admin/campaigns/{campaign_id}/activate", headers=super_admin_headers
    )
    assert activated.status_code == 200
    assert activated.json()["data"]["status"] == "ACTIVE"

    paused = api_client.post(
        f"/api/v1/admin/campaigns/{campaign_id}/pause", headers=super_admin_headers
    )
    assert paused.status_code == 200
    assert paused.json()["data"]["status"] == "PAUSED"

    ended = api_client.post(
        f"/api/v1/admin/campaigns/{campaign_id}/end", headers=super_admin_headers
    )
    assert ended.status_code == 200
    assert ended.json()["data"]["status"] == "ENDED"

    reactivate = api_client.post(
        f"/api/v1/admin/campaigns/{campaign_id}/activate", headers=super_admin_headers
    )
    assert reactivate.status_code == 409
    assert reactivate.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_edit_campaign_rejected_once_active(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    campaign_id = api_client.post(
        "/api/v1/admin/campaigns",
        json=_campaign_body(),
        headers=super_admin_headers,
    ).json()["data"]["campaign_id"]
    api_client.post(
        f"/api/v1/admin/campaigns/{campaign_id}/activate", headers=super_admin_headers
    )

    response = api_client.patch(
        f"/api/v1/admin/campaigns/{campaign_id}",
        json=_campaign_body(name="Changed name"),
        headers=super_admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_list_and_get_campaign(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    campaign_id = api_client.post(
        "/api/v1/admin/campaigns",
        json=_campaign_body(),
        headers=super_admin_headers,
    ).json()["data"]["campaign_id"]

    listed = api_client.get(
        "/api/v1/admin/campaigns?status=DRAFT", headers=super_admin_headers
    )
    assert listed.status_code == 200
    assert any(c["campaign_id"] == campaign_id for c in listed.json()["data"]["items"])

    got = api_client.get(
        f"/api/v1/admin/campaigns/{campaign_id}", headers=super_admin_headers
    )
    assert got.status_code == 200
    assert got.json()["data"]["campaign_id"] == campaign_id


def test_employee_admin_without_offers_coupons_access_is_forbidden(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _admin_id, phone = _create_employee_admin(api_client, super_admin_headers)
    employee_headers = _login_employee_admin(api_client, sms, phone)

    response = api_client.post(
        "/api/v1/admin/campaigns",
        json=_campaign_body(),
        headers=employee_headers,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_employee_admin_with_offers_coupons_manage_can_create_and_activate(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _admin_id, phone = _create_employee_admin(
        api_client,
        super_admin_headers,
        permissions=[{"module": "OFFERS_COUPONS", "access_level": "MANAGE"}],
    )
    employee_headers = _login_employee_admin(api_client, sms, phone)

    created = api_client.post(
        "/api/v1/admin/campaigns",
        json=_campaign_body(),
        headers=employee_headers,
    )
    assert created.status_code == 201
    campaign_id = created.json()["data"]["campaign_id"]

    activated = api_client.post(
        f"/api/v1/admin/campaigns/{campaign_id}/activate", headers=employee_headers
    )
    assert activated.status_code == 200


# --- CSV Bulk Customer Targeting (Admin Web §4.10, ADR-0041 §9) ------------


def _new_customer_with_known_phone(
    api_client: TestClient, sms: CapturingSmsProvider
) -> tuple[str, str]:
    """Same flow _new_customer_with_profile() above uses, but also
    returns the phone number a CSV row needs to resolve back to this
    customer — _login()'s own randomized phone is otherwise discarded."""
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
    api_client.get("/api/v1/customers/me", headers=headers)  # provisions the row
    return phone, headers["Authorization"]


def _upload_csv(
    api_client: TestClient, campaign_id: str, headers: dict, csv_text: str
) -> httpx.Response:
    return api_client.post(
        f"/api/v1/admin/campaigns/{campaign_id}/eligible-customers/bulk",
        files={"file": ("customers.csv", csv_text, "text/csv")},
        headers=headers,
    )


def test_bulk_upload_adds_a_matched_customer_and_reports_the_rest(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    phone, _customer_auth = _new_customer_with_known_phone(api_client, sms)
    campaign_id = api_client.post(
        "/api/v1/admin/campaigns",
        json=_campaign_body(eligible_scope="SELECTED"),
        headers=super_admin_headers,
    ).json()["data"]["campaign_id"]
    csv_text = f"phone\n{phone}\nnot-a-phone\n+919999999999\n"

    response = _upload_csv(api_client, campaign_id, super_admin_headers, csv_text)

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["added"] == 1
    assert data["already_eligible"] == 0
    assert len(data["unmatched"]) == 2
    reasons = {u["reason"] for u in data["unmatched"]}
    assert "invalid phone number" in reasons
    assert "no customer account" in reasons
    rows = {u["row"] for u in data["unmatched"]}
    assert rows == {3, 4}  # header is row 1, the matched phone is row 2


def test_bulk_upload_is_additive_across_two_uploads(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    first_phone, _ = _new_customer_with_known_phone(api_client, sms)
    second_phone, _ = _new_customer_with_known_phone(api_client, sms)
    campaign_id = api_client.post(
        "/api/v1/admin/campaigns",
        json=_campaign_body(eligible_scope="SELECTED"),
        headers=super_admin_headers,
    ).json()["data"]["campaign_id"]
    _upload_csv(api_client, campaign_id, super_admin_headers, f"phone\n{first_phone}\n")

    second = _upload_csv(
        api_client,
        campaign_id,
        super_admin_headers,
        f"phone\n{first_phone}\n{second_phone}\n",
    )

    assert second.status_code == 200
    data = second.json()["data"]
    # first_phone was already eligible from the prior upload — additive
    # semantics mean it's reported already_eligible, not re-added or an
    # error; only second_phone is newly added.
    assert data["added"] == 1
    assert data["already_eligible"] == 1
    assert data["unmatched"] == []


def test_bulk_upload_rejects_malformed_csv_missing_phone_header(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    campaign_id = api_client.post(
        "/api/v1/admin/campaigns",
        json=_campaign_body(eligible_scope="SELECTED"),
        headers=super_admin_headers,
    ).json()["data"]["campaign_id"]

    response = _upload_csv(
        api_client, campaign_id, super_admin_headers, "not_phone\n+919999999999\n"
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_bulk_upload_rejects_all_scope_campaign(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    campaign_id = api_client.post(
        "/api/v1/admin/campaigns",
        json=_campaign_body(eligible_scope="ALL"),
        headers=super_admin_headers,
    ).json()["data"]["campaign_id"]

    response = _upload_csv(
        api_client, campaign_id, super_admin_headers, "phone\n+919999999999\n"
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_bulk_upload_rejected_once_campaign_is_active(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    campaign_id = api_client.post(
        "/api/v1/admin/campaigns",
        json=_campaign_body(eligible_scope="SELECTED"),
        headers=super_admin_headers,
    ).json()["data"]["campaign_id"]
    api_client.post(
        f"/api/v1/admin/campaigns/{campaign_id}/activate", headers=super_admin_headers
    )

    response = _upload_csv(
        api_client, campaign_id, super_admin_headers, "phone\n+919999999999\n"
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_bulk_upload_for_unknown_campaign_returns_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = _upload_csv(
        api_client, str(uuid.uuid4()), super_admin_headers, "phone\n+919999999999\n"
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_bulk_upload_requires_offers_coupons_manage(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    campaign_id = api_client.post(
        "/api/v1/admin/campaigns",
        json=_campaign_body(eligible_scope="SELECTED"),
        headers=super_admin_headers,
    ).json()["data"]["campaign_id"]
    _admin_id, phone = _create_employee_admin(api_client, super_admin_headers)
    employee_headers = _login_employee_admin(api_client, sms, phone)

    response = _upload_csv(
        api_client, campaign_id, employee_headers, "phone\n+919999999999\n"
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# --- Audit Logs (Admin Web module #18) --------------------------------------


def test_search_audit_logs_finds_a_written_entry(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    new_admin_id, _phone = _create_employee_admin(api_client, super_admin_headers)

    response = api_client.get(
        "/api/v1/admin/audit-logs",
        params={"action": "CREATE_ADMIN", "target_id": new_admin_id},
        headers=super_admin_headers,
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    entry = items[0]
    assert entry["action"] == "CREATE_ADMIN"
    assert entry["target_type"] == "ADMIN"
    assert entry["target_id"] == new_admin_id
    assert entry["after_state"]["admin_id"] == new_admin_id


def test_search_audit_logs_filters_by_admin_id(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    super_admin_token, super_admin_headers = _login_admin(api_client, sms)
    super_admin_id = _account_id_from_token(super_admin_token)
    _create_employee_admin(api_client, super_admin_headers)
    _create_employee_admin(api_client, super_admin_headers)

    response = api_client.get(
        "/api/v1/admin/audit-logs",
        params={"admin_id": str(super_admin_id), "action": "CREATE_ADMIN"},
        headers=super_admin_headers,
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 2
    assert all(entry["admin_id"] == str(super_admin_id) for entry in items)


def test_search_audit_logs_filters_by_date_range(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    super_admin_token, super_admin_headers = _login_admin(api_client, sms)
    super_admin_id = _account_id_from_token(super_admin_token)
    _create_employee_admin(api_client, super_admin_headers)

    future_window = api_client.get(
        "/api/v1/admin/audit-logs",
        params={
            "admin_id": str(super_admin_id),
            "action": "CREATE_ADMIN",
            "created_after": "2099-01-01T00:00:00Z",
        },
        headers=super_admin_headers,
    )
    assert future_window.status_code == 200
    assert future_window.json()["data"]["items"] == []

    open_window = api_client.get(
        "/api/v1/admin/audit-logs",
        params={
            "admin_id": str(super_admin_id),
            "action": "CREATE_ADMIN",
            "created_after": "2020-01-01T00:00:00Z",
            "created_before": "2099-01-01T00:00:00Z",
        },
        headers=super_admin_headers,
    )
    assert open_window.status_code == 200
    assert len(open_window.json()["data"]["items"]) == 1


def test_employee_admin_without_audit_logs_access_is_forbidden(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _admin_id, phone = _create_employee_admin(api_client, super_admin_headers)
    employee_headers = _login_employee_admin(api_client, sms, phone)

    response = api_client.get("/api/v1/admin/audit-logs", headers=employee_headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_employee_admin_with_audit_logs_view_access_can_read(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _admin_id, phone = _create_employee_admin(
        api_client,
        super_admin_headers,
        permissions=[{"module": "AUDIT_LOGS", "access_level": "VIEW"}],
    )
    employee_headers = _login_employee_admin(api_client, sms, phone)

    response = api_client.get("/api/v1/admin/audit-logs", headers=employee_headers)

    assert response.status_code == 200


def test_unauthenticated_search_audit_logs_is_rejected(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/admin/audit-logs")
    assert response.status_code == 401


# --- Customers (Admin Web §4.1) ---------------------------------------------


def test_search_customers_finds_by_name(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    customer_id, customer_headers = _new_customer_with_profile(api_client, sms)
    unique_name = f"Zeta{secrets.randbelow(1_000_000)}"
    api_client.patch(
        "/api/v1/customers/me",
        json={"full_name": unique_name},
        headers=customer_headers,
    )

    response = api_client.get(
        "/api/v1/admin/customers",
        params={"query": unique_name},
        headers=super_admin_headers,
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["customer_id"] == customer_id
    assert "phone" not in items[0]


def test_get_customer_detail_includes_phone(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    customer_id, _customer_headers = _new_customer_with_profile(api_client, sms)

    response = api_client.get(
        f"/api/v1/admin/customers/{customer_id}", headers=super_admin_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["customer_id"] == customer_id
    assert data["phone"].startswith("+91")


def test_get_customer_detail_unknown_id_returns_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.get(
        f"/api/v1/admin/customers/{uuid.uuid4()}", headers=super_admin_headers
    )

    assert response.status_code == 404


# --- Drivers search + suspend/reactivate (Admin Web §4.2) -------------------


def test_search_drivers_finds_by_name_and_status(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    driver_id, driver_headers = _new_driver_with_profile(api_client, sms)
    unique_name = f"Yeti{secrets.randbelow(1_000_000)}"
    api_client.patch(
        "/api/v1/drivers/me", json={"full_name": unique_name}, headers=driver_headers
    )

    response = api_client.get(
        "/api/v1/admin/drivers",
        params={"query": unique_name, "status": "PENDING"},
        headers=super_admin_headers,
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["driver_id"] == driver_id


def test_suspend_then_reactivate_driver(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    driver_id, driver_headers = _new_driver_with_profile(api_client, sms)
    _make_driver_approvable(api_client, driver_headers)
    api_client.post(
        f"/api/v1/admin/drivers/{driver_id}/approve", headers=super_admin_headers
    )

    suspended = api_client.post(
        f"/api/v1/admin/drivers/{driver_id}/suspend",
        json={"reason": "Repeated customer complaints"},
        headers=super_admin_headers,
    )
    assert suspended.status_code == 200
    assert suspended.json()["data"]["operational_status"] == "SUSPENDED"

    reactivated = api_client.post(
        f"/api/v1/admin/drivers/{driver_id}/reactivate", headers=super_admin_headers
    )
    assert reactivated.status_code == 200
    assert reactivated.json()["data"]["operational_status"] == "OFFLINE"


def test_suspend_driver_twice_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    driver_id, driver_headers = _new_driver_with_profile(api_client, sms)
    _make_driver_approvable(api_client, driver_headers)
    api_client.post(
        f"/api/v1/admin/drivers/{driver_id}/approve", headers=super_admin_headers
    )
    api_client.post(
        f"/api/v1/admin/drivers/{driver_id}/suspend",
        json={},
        headers=super_admin_headers,
    )

    response = api_client.post(
        f"/api/v1/admin/drivers/{driver_id}/suspend",
        json={},
        headers=super_admin_headers,
    )

    assert response.status_code == 409


# --- Vehicles search + detail + documents (Admin Web §4.3/§4.4) -------------


def test_search_vehicles_finds_by_registration_number(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _driver_id, driver_headers = _new_driver_with_profile(api_client, sms)
    vehicle_id = _new_vehicle(api_client, driver_headers)
    vehicle_data = api_client.get(
        f"/api/v1/admin/vehicles/{vehicle_id}", headers=super_admin_headers
    )
    assert vehicle_data.status_code == 200
    registration_number = vehicle_data.json()["data"]["registration_number"]

    response = api_client.get(
        "/api/v1/admin/vehicles",
        params={"query": registration_number},
        headers=super_admin_headers,
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["vehicle_id"] == vehicle_id


def test_get_vehicle_detail_unknown_id_returns_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.get(
        f"/api/v1/admin/vehicles/{uuid.uuid4()}", headers=super_admin_headers
    )

    assert response.status_code == 404


def test_list_vehicle_documents(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _driver_id, driver_headers = _new_driver_with_profile(api_client, sms)
    vehicle_id = _new_vehicle(api_client, driver_headers)
    _submit_vehicle_document(vehicle_id, "RC")

    response = api_client.get(
        f"/api/v1/admin/vehicles/{vehicle_id}/documents", headers=super_admin_headers
    )

    assert response.status_code == 200
    documents = response.json()["data"]["documents"]
    assert len(documents) == 1
    assert documents[0]["document_type"] == "RC"


def test_list_vehicle_documents_unknown_vehicle_returns_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.get(
        f"/api/v1/admin/vehicles/{uuid.uuid4()}/documents", headers=super_admin_headers
    )

    assert response.status_code == 404


# --- Verification queue (Admin Web §4.4) ------------------------------------


def test_search_verification_queue_filters_by_status(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _driver_id, driver_headers = _new_driver_with_profile(api_client, sms)
    document_id = _submit_driver_document(api_client, driver_headers, "GOVERNMENT_ID")

    response = api_client.get(
        "/api/v1/admin/verification/queue",
        params={"status": "PENDING"},
        headers=super_admin_headers,
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert any(
        item["subject_id"] == document_id
        and item["subject_type"] == "DRIVER_DOCUMENT"
        and item["status"] == "PENDING"
        for item in items
    )


# --- Permission gating (one representative check across this whole batch) --


def test_employee_admin_needs_module_specific_access_for_new_search_endpoints(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _admin_id, phone = _create_employee_admin(
        api_client,
        super_admin_headers,
        permissions=[{"module": "CUSTOMERS", "access_level": "VIEW"}],
    )
    employee_headers = _login_employee_admin(api_client, sms, phone)

    allowed = api_client.get("/api/v1/admin/customers", headers=employee_headers)
    assert allowed.status_code == 200

    forbidden = api_client.get("/api/v1/admin/drivers", headers=employee_headers)
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"


# --- Wallet Transaction History (Admin Web §4.7) ----------------------------


def test_list_driver_wallet_transactions(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    driver_id, _driver_headers = _new_driver_with_profile(api_client, sms)
    _credit_wallet_directly(uuid.UUID(driver_id), amount=Decimal("100"))

    response = api_client.get(
        f"/api/v1/admin/wallets/{driver_id}/transactions",
        headers=super_admin_headers,
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["transaction_type"] == "FEE_REVERSAL"
    assert items[0]["direction"] == "CREDIT"
    assert items[0]["amount"] == 100.0


def test_list_driver_wallet_transactions_filters_by_type(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    driver_id, _driver_headers = _new_driver_with_profile(api_client, sms)
    _credit_wallet_directly(uuid.UUID(driver_id), amount=Decimal("50"))

    response = api_client.get(
        f"/api/v1/admin/wallets/{driver_id}/transactions",
        params={"type": "PLATFORM_FEE"},
        headers=super_admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["items"] == []


def test_list_driver_wallet_transactions_unknown_type_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    driver_id, _driver_headers = _new_driver_with_profile(api_client, sms)

    response = api_client.get(
        f"/api/v1/admin/wallets/{driver_id}/transactions",
        params={"type": "NOT_A_REAL_TYPE"},
        headers=super_admin_headers,
    )

    assert response.status_code == 422


# --- Referrals (Admin Web §4.11) --------------------------------------------


def test_search_referrals_shows_activated_referral_with_reward(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    referrer_id, referrer_headers = _new_customer_with_profile(api_client, sms)
    code = api_client.get(
        "/api/v1/customers/me/referral", headers=referrer_headers
    ).json()["data"]["code"]
    referred_id, referred_headers = _new_customer_with_profile(api_client, sms)

    attach = api_client.post(
        "/api/v1/referrals/attach", json={"code": code}, headers=referred_headers
    )
    assert attach.status_code == 200, attach.text

    response = api_client.get(
        "/api/v1/admin/referrals",
        params={"status": "ACTIVATED"},
        headers=super_admin_headers,
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    match = next(item for item in items if item["referred_id"] == referred_id)
    assert match["referrer_id"] == referrer_id
    assert match["status"] == "ACTIVATED"
    assert len(match["rewards"]) >= 1
    assert match["rewards"][0]["reward_type"] == "CUSTOMER_REFERRAL_PROMOTION"


def test_search_referrals_unknown_status_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.get(
        "/api/v1/admin/referrals",
        params={"status": "NOT_A_REAL_STATUS"},
        headers=super_admin_headers,
    )

    assert response.status_code == 422


# --- Referral Reward Configuration (Admin Web §4.11, ADR-0043) --------------
#
# Unlike fare rules (keyed by vehicle_category, so tests use a fresh
# random category to avoid collision), a driver-bonus rule has no key
# column at all — there is only ever one global active policy, and
# every test-database write here is a real commit (tests/conftest.py:
# no per-test transaction rollback). Any test that publishes a
# driver-bonus rule therefore restores the 100/100 baseline in a
# `finally`, matching what the migration seeds and what
# test_referral_api.py's driver-referral-bonus tests assert.


def _restore_driver_bonus_baseline(
    api_client: TestClient, super_admin_headers: dict
) -> None:
    rule_id = api_client.post(
        "/api/v1/admin/referral-config/driver-bonus",
        json={"referred_amount": 100, "referrer_amount": 100},
        headers=super_admin_headers,
    ).json()["data"]["rule_id"]
    api_client.post(
        f"/api/v1/admin/referral-config/driver-bonus/{rule_id}/publish",
        json={},
        headers=super_admin_headers,
    )


# customer_reward_rules IS keyed by reward_type, but each key still has
# only one active row at a time and every write here is a real commit
# — the same restore discipline applies per reward_type.
_CUSTOMER_REWARD_BASELINE = {
    "REFERRAL_REFERRED": {"discount_percent": 50, "total_uses": 3},
    "REFERRAL_REFERRING": {"discount_percent": 50, "total_uses": 2},
}


def _restore_customer_reward_baseline(
    api_client: TestClient, super_admin_headers: dict, reward_type: str
) -> None:
    baseline = _CUSTOMER_REWARD_BASELINE[reward_type]
    rule_id = api_client.post(
        "/api/v1/admin/referral-config/customer-rewards",
        json={"reward_type": reward_type, **baseline},
        headers=super_admin_headers,
    ).json()["data"]["rule_id"]
    api_client.post(
        f"/api/v1/admin/referral-config/customer-rewards/{rule_id}/publish",
        json={},
        headers=super_admin_headers,
    )


def test_create_driver_bonus_rule_starts_as_draft(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        "/api/v1/admin/referral-config/driver-bonus",
        json={"referred_amount": 120, "referrer_amount": 90},
        headers=super_admin_headers,
    )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["status"] == "DRAFT"
    assert data["referred_amount"] == 120
    assert data["referrer_amount"] == 90
    assert data["effective_from"] is None


def test_driver_bonus_rule_lifecycle_submit_then_publish(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    try:
        rule_id = api_client.post(
            "/api/v1/admin/referral-config/driver-bonus",
            json={"referred_amount": 150, "referrer_amount": 150},
            headers=super_admin_headers,
        ).json()["data"]["rule_id"]

        reviewed = api_client.post(
            f"/api/v1/admin/referral-config/driver-bonus/{rule_id}/submit-for-review",
            headers=super_admin_headers,
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["data"]["status"] == "IN_REVIEW"

        published = api_client.post(
            f"/api/v1/admin/referral-config/driver-bonus/{rule_id}/publish",
            json={},
            headers=super_admin_headers,
        )
        assert published.status_code == 200
        data = published.json()["data"]
        assert data["status"] == "PUBLISHED"
        assert data["effective_from"] is not None
    finally:
        _restore_driver_bonus_baseline(api_client, super_admin_headers)


def test_publish_driver_bonus_rule_closes_out_the_previous_one(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    try:
        old_rule_id = api_client.post(
            "/api/v1/admin/referral-config/driver-bonus",
            json={"referred_amount": 100, "referrer_amount": 100},
            headers=super_admin_headers,
        ).json()["data"]["rule_id"]
        api_client.post(
            f"/api/v1/admin/referral-config/driver-bonus/{old_rule_id}/publish",
            json={},
            headers=super_admin_headers,
        )

        new_rule_id = api_client.post(
            "/api/v1/admin/referral-config/driver-bonus",
            json={"referred_amount": 200, "referrer_amount": 200},
            headers=super_admin_headers,
        ).json()["data"]["rule_id"]
        api_client.post(
            f"/api/v1/admin/referral-config/driver-bonus/{new_rule_id}/publish",
            json={},
            headers=super_admin_headers,
        )

        old_rule = api_client.get(
            f"/api/v1/admin/referral-config/driver-bonus/{old_rule_id}",
            headers=super_admin_headers,
        ).json()["data"]
        assert old_rule["effective_until"] is not None

        new_rule = api_client.get(
            f"/api/v1/admin/referral-config/driver-bonus/{new_rule_id}",
            headers=super_admin_headers,
        ).json()["data"]
        assert new_rule["effective_until"] is None
    finally:
        _restore_driver_bonus_baseline(api_client, super_admin_headers)


def test_create_driver_bonus_rule_rejects_non_positive_amount(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        "/api/v1/admin/referral-config/driver-bonus",
        json={"referred_amount": 0, "referrer_amount": 100},
        headers=super_admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_create_customer_reward_rule_starts_as_draft(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        "/api/v1/admin/referral-config/customer-rewards",
        json={
            "reward_type": "REFERRAL_REFERRED",
            "discount_percent": 40,
            "total_uses": 3,
        },
        headers=super_admin_headers,
    )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["status"] == "DRAFT"
    assert data["reward_type"] == "REFERRAL_REFERRED"
    assert data["discount_percent"] == 40
    assert data["total_uses"] == 3


def test_customer_reward_rule_lifecycle_submit_then_publish(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    try:
        rule_id = api_client.post(
            "/api/v1/admin/referral-config/customer-rewards",
            json={
                "reward_type": "REFERRAL_REFERRING",
                "discount_percent": 60,
                "total_uses": 2,
            },
            headers=super_admin_headers,
        ).json()["data"]["rule_id"]

        reviewed = api_client.post(
            f"/api/v1/admin/referral-config/customer-rewards/{rule_id}"
            "/submit-for-review",
            headers=super_admin_headers,
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["data"]["status"] == "IN_REVIEW"

        published = api_client.post(
            f"/api/v1/admin/referral-config/customer-rewards/{rule_id}/publish",
            json={},
            headers=super_admin_headers,
        )
        assert published.status_code == 200
        data = published.json()["data"]
        assert data["status"] == "PUBLISHED"
        assert data["effective_from"] is not None
    finally:
        _restore_customer_reward_baseline(
            api_client, super_admin_headers, "REFERRAL_REFERRING"
        )


def test_publish_customer_reward_rule_closes_out_previous_for_same_reward_type(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    try:
        old_rule_id = api_client.post(
            "/api/v1/admin/referral-config/customer-rewards",
            json={
                "reward_type": "REFERRAL_REFERRED",
                "discount_percent": 50,
                "total_uses": 3,
            },
            headers=super_admin_headers,
        ).json()["data"]["rule_id"]
        api_client.post(
            f"/api/v1/admin/referral-config/customer-rewards/{old_rule_id}/publish",
            json={},
            headers=super_admin_headers,
        )

        new_rule_id = api_client.post(
            "/api/v1/admin/referral-config/customer-rewards",
            json={
                "reward_type": "REFERRAL_REFERRED",
                "discount_percent": 55,
                "total_uses": 4,
            },
            headers=super_admin_headers,
        ).json()["data"]["rule_id"]
        api_client.post(
            f"/api/v1/admin/referral-config/customer-rewards/{new_rule_id}/publish",
            json={},
            headers=super_admin_headers,
        )

        old_rule = api_client.get(
            f"/api/v1/admin/referral-config/customer-rewards/{old_rule_id}",
            headers=super_admin_headers,
        ).json()["data"]
        assert old_rule["effective_until"] is not None

        new_rule = api_client.get(
            f"/api/v1/admin/referral-config/customer-rewards/{new_rule_id}",
            headers=super_admin_headers,
        ).json()["data"]
        assert new_rule["effective_until"] is None
    finally:
        _restore_customer_reward_baseline(
            api_client, super_admin_headers, "REFERRAL_REFERRED"
        )


def test_list_customer_reward_rules_filters_by_reward_type_and_status(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    api_client.post(
        "/api/v1/admin/referral-config/customer-rewards",
        json={
            "reward_type": "REFERRAL_REFERRING",
            "discount_percent": 33,
            "total_uses": 5,
        },
        headers=super_admin_headers,
    )

    response = api_client.get(
        "/api/v1/admin/referral-config/customer-rewards",
        params={"reward_type": "REFERRAL_REFERRING", "status": "DRAFT"},
        headers=super_admin_headers,
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) >= 1
    assert all(item["reward_type"] == "REFERRAL_REFERRING" for item in items)
    assert all(item["status"] == "DRAFT" for item in items)


def test_publish_driver_bonus_rule_twice_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    rule_id = api_client.post(
        "/api/v1/admin/referral-config/driver-bonus",
        json={"referred_amount": 100, "referrer_amount": 100},
        headers=super_admin_headers,
    ).json()["data"]["rule_id"]
    api_client.post(
        f"/api/v1/admin/referral-config/driver-bonus/{rule_id}/publish",
        json={},
        headers=super_admin_headers,
    )

    response = api_client.post(
        f"/api/v1/admin/referral-config/driver-bonus/{rule_id}/publish",
        json={},
        headers=super_admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_employee_admin_without_referrals_access_is_forbidden_for_reward_config(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _admin_id, phone = _create_employee_admin(api_client, super_admin_headers)
    employee_headers = _login_employee_admin(api_client, sms, phone)

    response = api_client.post(
        "/api/v1/admin/referral-config/driver-bonus",
        json={"referred_amount": 100, "referrer_amount": 100},
        headers=employee_headers,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# --- Fare Management (Admin Web §4.8, ADR-0042) -----------------------------


def _fare_rule_body(**overrides: object) -> dict:
    body: dict = {
        "vehicle_category": f"TEST_CAT_{secrets.randbelow(1_000_000)}",
        "base_fare": 55,
        "per_km": 12,
        "minimum_fare": 79,
    }
    body.update(overrides)
    return body


def test_create_fare_rule_starts_as_draft(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        "/api/v1/admin/fare-rules",
        json=_fare_rule_body(),
        headers=super_admin_headers,
    )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["status"] == "DRAFT"
    assert data["effective_from"] is None


def test_fare_rule_lifecycle_submit_then_publish(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    category = f"TEST_CAT_{secrets.randbelow(1_000_000)}"
    rule_id = api_client.post(
        "/api/v1/admin/fare-rules",
        json=_fare_rule_body(vehicle_category=category),
        headers=super_admin_headers,
    ).json()["data"]["rule_id"]

    reviewed = api_client.post(
        f"/api/v1/admin/fare-rules/{rule_id}/submit-for-review",
        headers=super_admin_headers,
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["data"]["status"] == "IN_REVIEW"

    published = api_client.post(
        f"/api/v1/admin/fare-rules/{rule_id}/publish",
        json={},
        headers=super_admin_headers,
    )
    assert published.status_code == 200
    data = published.json()["data"]
    assert data["status"] == "PUBLISHED"
    assert data["effective_from"] is not None


def test_publish_fare_rule_closes_out_the_previous_one(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    category = f"TEST_CAT_{secrets.randbelow(1_000_000)}"
    old_rule_id = api_client.post(
        "/api/v1/admin/fare-rules",
        json=_fare_rule_body(vehicle_category=category),
        headers=super_admin_headers,
    ).json()["data"]["rule_id"]
    api_client.post(
        f"/api/v1/admin/fare-rules/{old_rule_id}/publish",
        json={},
        headers=super_admin_headers,
    )

    new_rule_id = api_client.post(
        "/api/v1/admin/fare-rules",
        json=_fare_rule_body(vehicle_category=category, base_fare=60),
        headers=super_admin_headers,
    ).json()["data"]["rule_id"]
    api_client.post(
        f"/api/v1/admin/fare-rules/{new_rule_id}/publish",
        json={},
        headers=super_admin_headers,
    )

    old_rule = api_client.get(
        f"/api/v1/admin/fare-rules/{old_rule_id}", headers=super_admin_headers
    ).json()["data"]
    assert old_rule["effective_until"] is not None

    new_rule = api_client.get(
        f"/api/v1/admin/fare-rules/{new_rule_id}", headers=super_admin_headers
    ).json()["data"]
    assert new_rule["effective_until"] is None


def test_publish_fare_rule_twice_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    rule_id = api_client.post(
        "/api/v1/admin/fare-rules",
        json=_fare_rule_body(),
        headers=super_admin_headers,
    ).json()["data"]["rule_id"]
    api_client.post(
        f"/api/v1/admin/fare-rules/{rule_id}/publish",
        json={},
        headers=super_admin_headers,
    )

    response = api_client.post(
        f"/api/v1/admin/fare-rules/{rule_id}/publish",
        json={},
        headers=super_admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_list_fare_rules_filters_by_category_and_status(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    category = f"TEST_CAT_{secrets.randbelow(1_000_000)}"
    api_client.post(
        "/api/v1/admin/fare-rules",
        json=_fare_rule_body(vehicle_category=category),
        headers=super_admin_headers,
    )

    response = api_client.get(
        "/api/v1/admin/fare-rules",
        params={"vehicle_category": category, "status": "DRAFT"},
        headers=super_admin_headers,
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["vehicle_category"] == category


def test_create_fare_rule_rejects_negative_base_fare(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        "/api/v1/admin/fare-rules",
        json=_fare_rule_body(base_fare=-5),
        headers=super_admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_employee_admin_without_fare_management_access_is_forbidden(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _admin_id, phone = _create_employee_admin(api_client, super_admin_headers)
    employee_headers = _login_employee_admin(api_client, sms, phone)

    response = api_client.post(
        "/api/v1/admin/fare-rules",
        json=_fare_rule_body(),
        headers=employee_headers,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# --- Platform Fee Management (Admin Web §4.8's own new row, ADR-0045) ------
#
# Unlike fare rules (keyed by an arbitrary vehicle_category string, so
# tests use a fresh random category), platform_fee_rules is keyed by
# the closed 3-value BIKE/AUTO/CAB set — there is no room for a
# collision-free test-only category. Every test that publishes here
# therefore restores the seeded baseline (BIKE ₹2, AUTO ₹5, CAB ₹10)
# afterward, same discipline as this file's own driver-bonus-rule tests
# above (§4.11) and for the identical reason: every write here is a
# real commit against a shared test database (tests/conftest.py — no
# per-test rollback).

_PLATFORM_FEE_BASELINE = {"BIKE": 2, "AUTO": 5, "CAB": 10}


def _restore_platform_fee_baseline(
    api_client: TestClient, super_admin_headers: dict, vehicle_category: str
) -> None:
    rule_id = api_client.post(
        "/api/v1/admin/platform-fee-rules",
        json={
            "vehicle_category": vehicle_category,
            "fee_amount": _PLATFORM_FEE_BASELINE[vehicle_category],
        },
        headers=super_admin_headers,
    ).json()["data"]["rule_id"]
    api_client.post(
        f"/api/v1/admin/platform-fee-rules/{rule_id}/publish",
        json={},
        headers=super_admin_headers,
    )


def test_create_platform_fee_rule_starts_as_draft(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        "/api/v1/admin/platform-fee-rules",
        json={"vehicle_category": "BIKE", "fee_amount": 3},
        headers=super_admin_headers,
    )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["status"] == "DRAFT"
    assert data["vehicle_category"] == "BIKE"
    assert data["fee_amount"] == 3
    assert data["effective_from"] is None


def test_platform_fee_rule_lifecycle_submit_then_publish(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    try:
        rule_id = api_client.post(
            "/api/v1/admin/platform-fee-rules",
            json={"vehicle_category": "AUTO", "fee_amount": 6},
            headers=super_admin_headers,
        ).json()["data"]["rule_id"]

        reviewed = api_client.post(
            f"/api/v1/admin/platform-fee-rules/{rule_id}/submit-for-review",
            headers=super_admin_headers,
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["data"]["status"] == "IN_REVIEW"

        published = api_client.post(
            f"/api/v1/admin/platform-fee-rules/{rule_id}/publish",
            json={},
            headers=super_admin_headers,
        )
        assert published.status_code == 200
        data = published.json()["data"]
        assert data["status"] == "PUBLISHED"
        assert data["effective_from"] is not None
    finally:
        _restore_platform_fee_baseline(api_client, super_admin_headers, "AUTO")


def test_publish_platform_fee_rule_closes_out_the_previous_one(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    try:
        old_rule_id = api_client.post(
            "/api/v1/admin/platform-fee-rules",
            json={"vehicle_category": "CAB", "fee_amount": 10},
            headers=super_admin_headers,
        ).json()["data"]["rule_id"]
        api_client.post(
            f"/api/v1/admin/platform-fee-rules/{old_rule_id}/publish",
            json={},
            headers=super_admin_headers,
        )

        new_rule_id = api_client.post(
            "/api/v1/admin/platform-fee-rules",
            json={"vehicle_category": "CAB", "fee_amount": 12},
            headers=super_admin_headers,
        ).json()["data"]["rule_id"]
        api_client.post(
            f"/api/v1/admin/platform-fee-rules/{new_rule_id}/publish",
            json={},
            headers=super_admin_headers,
        )

        old_rule = api_client.get(
            f"/api/v1/admin/platform-fee-rules/{old_rule_id}",
            headers=super_admin_headers,
        ).json()["data"]
        assert old_rule["effective_until"] is not None

        new_rule = api_client.get(
            f"/api/v1/admin/platform-fee-rules/{new_rule_id}",
            headers=super_admin_headers,
        ).json()["data"]
        assert new_rule["effective_until"] is None
    finally:
        _restore_platform_fee_baseline(api_client, super_admin_headers, "CAB")


def test_create_platform_fee_rule_rejects_negative_amount(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        "/api/v1/admin/platform-fee-rules",
        json={"vehicle_category": "BIKE", "fee_amount": -5},
        headers=super_admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_create_platform_fee_rule_rejects_unknown_category(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        "/api/v1/admin/platform-fee-rules",
        json={"vehicle_category": "CAB_ECO", "fee_amount": 5},
        headers=super_admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_list_platform_fee_rules_filters_by_category_and_status(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    api_client.post(
        "/api/v1/admin/platform-fee-rules",
        json={"vehicle_category": "BIKE", "fee_amount": 4},
        headers=super_admin_headers,
    )

    response = api_client.get(
        "/api/v1/admin/platform-fee-rules",
        params={"vehicle_category": "BIKE", "status": "DRAFT"},
        headers=super_admin_headers,
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) >= 1
    assert all(item["vehicle_category"] == "BIKE" for item in items)
    assert all(item["status"] == "DRAFT" for item in items)


def test_publish_platform_fee_rule_twice_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    try:
        rule_id = api_client.post(
            "/api/v1/admin/platform-fee-rules",
            json={"vehicle_category": "BIKE", "fee_amount": 2},
            headers=super_admin_headers,
        ).json()["data"]["rule_id"]
        api_client.post(
            f"/api/v1/admin/platform-fee-rules/{rule_id}/publish",
            json={},
            headers=super_admin_headers,
        )

        response = api_client.post(
            f"/api/v1/admin/platform-fee-rules/{rule_id}/publish",
            json={},
            headers=super_admin_headers,
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"
    finally:
        _restore_platform_fee_baseline(api_client, super_admin_headers, "BIKE")


def test_employee_admin_without_finance_access_is_forbidden_for_platform_fee(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _admin_id, phone = _create_employee_admin(api_client, super_admin_headers)
    employee_headers = _login_employee_admin(api_client, sms, phone)

    response = api_client.post(
        "/api/v1/admin/platform-fee-rules",
        json={"vehicle_category": "BIKE", "fee_amount": 2},
        headers=employee_headers,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# --- Safety / SOS (Admin Web §4.13) -----------------------------------------


def test_safety_incident_lifecycle_acknowledge_escalate_resolve(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    customer_id, _customer_headers = _new_customer_with_profile(api_client, sms)
    incident_id = _trigger_sos_directly(uuid.UUID(customer_id))

    acknowledged = api_client.post(
        f"/api/v1/admin/safety/incidents/{incident_id}/acknowledge",
        headers=super_admin_headers,
    )
    assert acknowledged.status_code == 200
    assert acknowledged.json()["data"]["status"] == "ACKNOWLEDGED"

    escalated = api_client.post(
        f"/api/v1/admin/safety/incidents/{incident_id}/escalate",
        headers=super_admin_headers,
    )
    assert escalated.status_code == 200
    assert escalated.json()["data"]["status"] == "IN_PROGRESS"

    resolved = api_client.post(
        f"/api/v1/admin/safety/incidents/{incident_id}/resolve",
        headers=super_admin_headers,
    )
    assert resolved.status_code == 200
    assert resolved.json()["data"]["status"] == "RESOLVED"


def test_search_safety_incidents_filters_by_status(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    customer_id, _customer_headers = _new_customer_with_profile(api_client, sms)
    incident_id = _trigger_sos_directly(uuid.UUID(customer_id))

    response = api_client.get(
        "/api/v1/admin/safety/incidents",
        params={"status": "OPEN"},
        headers=super_admin_headers,
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert any(item["incident_id"] == str(incident_id) for item in items)


def test_escalate_safety_incident_before_acknowledge_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    customer_id, _customer_headers = _new_customer_with_profile(api_client, sms)
    incident_id = _trigger_sos_directly(uuid.UUID(customer_id))

    response = api_client.post(
        f"/api/v1/admin/safety/incidents/{incident_id}/escalate",
        headers=super_admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_employee_admin_without_safety_access_is_forbidden(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _admin_id, phone = _create_employee_admin(api_client, super_admin_headers)
    employee_headers = _login_employee_admin(api_client, sms, phone)

    response = api_client.get(
        "/api/v1/admin/safety/incidents", headers=employee_headers
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# --- Support / Disputes (Admin Web §4.14) -----------------------------------


def _create_support_case(api_client: TestClient, headers: dict) -> str:
    response = api_client.post(
        "/api/v1/support/cases",
        json={"message": "My ride overcharged me."},
        headers=headers,
    )
    case_id: str = response.json()["data"]["case_id"]
    return case_id


def test_search_support_cases_finds_created_case(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _customer_id, customer_headers = _new_customer_with_profile(api_client, sms)
    case_id = _create_support_case(api_client, customer_headers)

    response = api_client.get(
        "/api/v1/admin/support/cases",
        params={"status": "OPEN"},
        headers=super_admin_headers,
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert any(item["case_id"] == case_id for item in items)


def test_get_support_case_detail_includes_messages(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _customer_id, customer_headers = _new_customer_with_profile(api_client, sms)
    case_id = _create_support_case(api_client, customer_headers)

    response = api_client.get(
        f"/api/v1/admin/support/cases/{case_id}", headers=super_admin_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["case_id"] == case_id
    assert len(data["messages"]) == 1
    assert data["messages"][0]["message"] == "My ride overcharged me."


def test_resolve_support_case(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _customer_id, customer_headers = _new_customer_with_profile(api_client, sms)
    case_id = _create_support_case(api_client, customer_headers)

    response = api_client.post(
        f"/api/v1/admin/support/cases/{case_id}/resolve", headers=super_admin_headers
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "RESOLVED"


def test_resolve_support_case_twice_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _customer_id, customer_headers = _new_customer_with_profile(api_client, sms)
    case_id = _create_support_case(api_client, customer_headers)
    api_client.post(
        f"/api/v1/admin/support/cases/{case_id}/resolve", headers=super_admin_headers
    )

    response = api_client.post(
        f"/api/v1/admin/support/cases/{case_id}/resolve", headers=super_admin_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


# --- Notifications (Admin Web §4.12) ----------------------------------------


def _send_in_app_notification_directly(user_id: uuid.UUID) -> None:
    """Direct-service-layer seed — no HTTP endpoint exists for this
    module (ADR-0034 Decision 1); IN_APP needs no sms_provider. Same
    asyncio.run()-from-a-sync-test technique tests/test_notification_
    service.py already established (no pytest-asyncio plugin
    configured)."""
    db = SessionLocal()
    try:
        service = NotificationService(
            deliveries=SqlAlchemyDeliveryRepository(db),
            preferences=SqlAlchemyPreferencesRepository(db),
        )
        asyncio.run(
            service.send(
                user_id=user_id,
                channel=Channel.IN_APP,
                template_key="RIDE_ACCEPTED",
                recipient=None,
                event_id=None,
                now=datetime.now(UTC),
            )
        )
        db.commit()
    finally:
        db.close()


def test_search_notification_deliveries_finds_sent_delivery(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    customer_id, _customer_headers = _new_customer_with_profile(api_client, sms)
    _send_in_app_notification_directly(uuid.UUID(customer_id))

    response = api_client.get(
        "/api/v1/admin/notifications/deliveries",
        params={"user_id": customer_id, "channel": "IN_APP"},
        headers=super_admin_headers,
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["channel"] == "IN_APP"
    assert items[0]["status"] == "SENT"
    assert items[0]["template_key"] == "RIDE_ACCEPTED"


def test_search_notification_deliveries_unknown_channel_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.get(
        "/api/v1/admin/notifications/deliveries",
        params={"channel": "CARRIER_PIGEON"},
        headers=super_admin_headers,
    )

    assert response.status_code == 422


def test_employee_admin_without_notifications_access_is_forbidden(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _admin_id, phone = _create_employee_admin(api_client, super_admin_headers)
    employee_headers = _login_employee_admin(api_client, sms, phone)

    response = api_client.get(
        "/api/v1/admin/notifications/deliveries", headers=employee_headers
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# --- Notification Template Management (Admin Web §4.12, ADR-0044) ----------
#
# Unlike referral-config (§4.11 above, a single global row per key),
# every test here uses a fresh random template_key — a real
# (template_key, channel) pair's version chain is independent of every
# other pair's, so there's no shared global state to restore afterward,
# and the seeded RIDE_ACCEPTED/RIDE_ARRIVED SMS baseline is never
# touched.


def _template_body(**overrides: object) -> dict:
    body: dict = {
        "template_key": f"TEST_TPL_{secrets.randbelow(1_000_000)}",
        "channel": "SMS",
        "body": "Test template wording.",
    }
    body.update(overrides)
    return body


def test_create_notification_template_starts_as_draft(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        "/api/v1/admin/notifications/templates",
        json=_template_body(),
        headers=super_admin_headers,
    )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["status"] == "DRAFT"
    assert data["version"] == 1


def test_notification_template_lifecycle_create_then_publish(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    template_id = api_client.post(
        "/api/v1/admin/notifications/templates",
        json=_template_body(),
        headers=super_admin_headers,
    ).json()["data"]["template_id"]

    published = api_client.post(
        f"/api/v1/admin/notifications/templates/{template_id}/publish",
        headers=super_admin_headers,
    )

    assert published.status_code == 200
    assert published.json()["data"]["status"] == "PUBLISHED"


def test_create_notification_template_next_version_for_existing_key_channel(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    key = f"TEST_TPL_{secrets.randbelow(1_000_000)}"
    api_client.post(
        "/api/v1/admin/notifications/templates",
        json=_template_body(template_key=key),
        headers=super_admin_headers,
    )

    v2 = api_client.post(
        "/api/v1/admin/notifications/templates",
        json=_template_body(template_key=key, body="Revised wording."),
        headers=super_admin_headers,
    )

    assert v2.status_code == 201
    assert v2.json()["data"]["version"] == 2

    # A different channel for the same key starts its own chain at 1.
    push_v1 = api_client.post(
        "/api/v1/admin/notifications/templates",
        json=_template_body(template_key=key, channel="PUSH", title="Heads up"),
        headers=super_admin_headers,
    )
    assert push_v1.status_code == 201
    assert push_v1.json()["data"]["version"] == 1


def test_publish_notification_template_archives_the_previous_version(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    key = f"TEST_TPL_{secrets.randbelow(1_000_000)}"
    v1_id = api_client.post(
        "/api/v1/admin/notifications/templates",
        json=_template_body(template_key=key),
        headers=super_admin_headers,
    ).json()["data"]["template_id"]
    api_client.post(
        f"/api/v1/admin/notifications/templates/{v1_id}/publish",
        headers=super_admin_headers,
    )

    v2_id = api_client.post(
        "/api/v1/admin/notifications/templates",
        json=_template_body(template_key=key, body="v2 wording"),
        headers=super_admin_headers,
    ).json()["data"]["template_id"]
    api_client.post(
        f"/api/v1/admin/notifications/templates/{v2_id}/publish",
        headers=super_admin_headers,
    )

    v1 = api_client.get(
        f"/api/v1/admin/notifications/templates/{v1_id}",
        headers=super_admin_headers,
    ).json()["data"]
    assert v1["status"] == "ARCHIVED"

    v2 = api_client.get(
        f"/api/v1/admin/notifications/templates/{v2_id}",
        headers=super_admin_headers,
    ).json()["data"]
    assert v2["status"] == "PUBLISHED"


def test_publish_notification_template_twice_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    template_id = api_client.post(
        "/api/v1/admin/notifications/templates",
        json=_template_body(),
        headers=super_admin_headers,
    ).json()["data"]["template_id"]
    api_client.post(
        f"/api/v1/admin/notifications/templates/{template_id}/publish",
        headers=super_admin_headers,
    )

    response = api_client.post(
        f"/api/v1/admin/notifications/templates/{template_id}/publish",
        headers=super_admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_list_notification_templates_filters_by_key_channel_and_status(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    key = f"TEST_TPL_{secrets.randbelow(1_000_000)}"
    api_client.post(
        "/api/v1/admin/notifications/templates",
        json=_template_body(template_key=key),
        headers=super_admin_headers,
    )

    response = api_client.get(
        "/api/v1/admin/notifications/templates",
        params={"template_key": key, "channel": "SMS", "status": "DRAFT"},
        headers=super_admin_headers,
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["template_key"] == key


def test_list_notification_templates_unknown_channel_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.get(
        "/api/v1/admin/notifications/templates",
        params={"channel": "CARRIER_PIGEON"},
        headers=super_admin_headers,
    )

    assert response.status_code == 422


def test_employee_admin_without_notifications_access_is_forbidden_for_templates(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _admin_id, phone = _create_employee_admin(api_client, super_admin_headers)
    employee_headers = _login_employee_admin(api_client, sms, phone)

    response = api_client.post(
        "/api/v1/admin/notifications/templates",
        json=_template_body(),
        headers=employee_headers,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_published_template_is_stamped_onto_the_next_real_delivery(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """End-to-end against the real database (not the fake-repository
    unit tests in test_notification_service.py): NotificationService.
    send(), backed by the real SqlAlchemyTemplateRepository, actually
    finds the PUBLISHED row through the partial unique index and
    stamps its id onto the created delivery (ADR-0044 Decision 2)."""
    _, super_admin_headers = _login_admin(api_client, sms)
    key = f"TEST_TPL_{secrets.randbelow(1_000_000)}"
    template_id = api_client.post(
        "/api/v1/admin/notifications/templates",
        json=_template_body(template_key=key, channel="IN_APP"),
        headers=super_admin_headers,
    ).json()["data"]["template_id"]
    api_client.post(
        f"/api/v1/admin/notifications/templates/{template_id}/publish",
        headers=super_admin_headers,
    )

    customer_id, _customer_headers = _new_customer_with_profile(api_client, sms)
    db = SessionLocal()
    try:
        service = NotificationService(
            deliveries=SqlAlchemyDeliveryRepository(db),
            preferences=SqlAlchemyPreferencesRepository(db),
            templates=SqlAlchemyTemplateRepository(db),
        )
        asyncio.run(
            service.send(
                user_id=uuid.UUID(customer_id),
                channel=Channel.IN_APP,
                template_key=key,
                recipient=None,
                event_id=None,
                now=datetime.now(UTC),
            )
        )
        db.commit()

        stamped = db.execute(
            text(
                "SELECT template_version_id FROM notification.deliveries "
                "WHERE user_id = :user_id AND template_key = :key"
            ),
            {"user_id": customer_id, "key": key},
        ).scalar_one()
    finally:
        db.close()

    assert str(stamped) == template_id


# --- Compose/Send Broadcast + Audience Selection (Admin Web §4.12,
#     ADR-0055 Tier C) --------------------------------------------------
#
# IN_APP throughout — this file's own CapturingSmsProvider only
# implements send_otp() (every other test file's copy is identical), not
# send_message(), so an SMS-channel broadcast here would just count its
# recipient as failed_count (dispatch_broadcast()'s per-recipient
# try/except catching the missing method) rather than actually
# exercising a send; SMS phone-resolution and provider dispatch are
# fully covered instead by tests/test_broadcast_dispatch.py's own
# fake-provider unit tests. ALL_CUSTOMERS/ALL_DRIVERS/ONLINE_DRIVERS
# below only assert `>= 1`, not exact counts — this file accumulates
# state across its whole run (no truncate_integration_tables here), the
# same reasoning every other Reports-style aggregate assertion in this
# file already uses; exact-count coverage for those two audience types
# lives in tests/test_notification_tasks.py, whose own autouse
# truncate fixture gives each test a genuinely empty table.


def _broadcast_body(**overrides: object) -> dict:
    body: dict = {
        "channel": "IN_APP",
        "body": "Test broadcast wording.",
        "audience_type": "SELECTED",
        "audience_user_ids": [],
    }
    body.update(overrides)
    return body


def test_create_broadcast_selected_audience_sends_immediately(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    customer_1, _ = _new_customer_with_profile(api_client, sms)
    customer_2, _ = _new_customer_with_profile(api_client, sms)

    response = api_client.post(
        "/api/v1/admin/notifications/broadcasts",
        json=_broadcast_body(
            subject="Maintenance notice",
            audience_type="SELECTED",
            audience_user_ids=[customer_1, customer_2],
        ),
        headers=super_admin_headers,
    )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["status"] == "SENT"
    assert data["sent_count"] == 2
    assert data["failed_count"] == 0
    assert data["scheduled_at"] is None
    assert data["sent_at"] is not None


def test_create_broadcast_scheduled_stays_scheduled(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()

    response = api_client.post(
        "/api/v1/admin/notifications/broadcasts",
        json=_broadcast_body(
            audience_type="ALL_DRIVERS", audience_user_ids=None, scheduled_at=future
        ),
        headers=super_admin_headers,
    )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["status"] == "SCHEDULED"
    assert data["sent_count"] == 0
    assert data["sent_at"] is None


def test_create_broadcast_online_drivers_audience(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    lat, lng = _random_matching_point()
    driver_id, driver_headers = _new_driver_with_profile(api_client, sms)
    _make_driver_approvable(api_client, driver_headers)
    api_client.post(
        f"/api/v1/admin/drivers/{driver_id}/approve", headers=super_admin_headers
    )
    vehicle_id = _new_vehicle(api_client, driver_headers)
    _make_vehicle_approvable(vehicle_id)
    api_client.post(
        f"/api/v1/admin/vehicles/{vehicle_id}/approve", headers=super_admin_headers
    )
    api_client.post(
        f"/api/v1/drivers/me/vehicles/{vehicle_id}/activate", headers=driver_headers
    )
    api_client.post("/api/v1/drivers/me/online", headers=driver_headers)
    api_client.post(
        "/api/v1/drivers/me/location",
        json={"latitude": lat, "longitude": lng},
        headers=driver_headers,
    )

    response = api_client.post(
        "/api/v1/admin/notifications/broadcasts",
        json=_broadcast_body(audience_type="ONLINE_DRIVERS", audience_user_ids=None),
        headers=super_admin_headers,
    )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["status"] == "SENT"
    assert data["sent_count"] >= 1


def test_create_broadcast_rejects_whatsapp_channel(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        "/api/v1/admin/notifications/broadcasts",
        json=_broadcast_body(
            channel="WHATSAPP", audience_type="ALL_DRIVERS", audience_user_ids=None
        ),
        headers=super_admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_create_broadcast_rejects_unknown_audience_type(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        "/api/v1/admin/notifications/broadcasts",
        json=_broadcast_body(audience_type="EVERYONE_EVER", audience_user_ids=None),
        headers=super_admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_create_broadcast_selected_without_ids_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        "/api/v1/admin/notifications/broadcasts",
        json=_broadcast_body(audience_type="SELECTED", audience_user_ids=[]),
        headers=super_admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_employee_admin_without_notifications_access_cannot_create_broadcast(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _admin_id, phone = _create_employee_admin(api_client, super_admin_headers)
    employee_headers = _login_employee_admin(api_client, sms, phone)

    response = api_client.post(
        "/api/v1/admin/notifications/broadcasts",
        json=_broadcast_body(audience_type="ALL_DRIVERS", audience_user_ids=None),
        headers=employee_headers,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_employee_admin_with_notifications_view_cannot_create_broadcast(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """MANAGE is required to send a broadcast — the same bar Template
    create/publish already sets, not VIEW."""
    _, super_admin_headers = _login_admin(api_client, sms)
    _admin_id, phone = _create_employee_admin(
        api_client,
        super_admin_headers,
        permissions=[{"module": "NOTIFICATIONS", "access_level": "VIEW"}],
    )
    employee_headers = _login_employee_admin(api_client, sms, phone)

    response = api_client.post(
        "/api/v1/admin/notifications/broadcasts",
        json=_broadcast_body(audience_type="ALL_DRIVERS", audience_user_ids=None),
        headers=employee_headers,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_search_broadcasts_filters_by_status(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    created_id = api_client.post(
        "/api/v1/admin/notifications/broadcasts",
        json=_broadcast_body(audience_type="ALL_DRIVERS", audience_user_ids=None),
        headers=super_admin_headers,
    ).json()["data"]["broadcast_id"]

    response = api_client.get(
        "/api/v1/admin/notifications/broadcasts",
        params={"status": "SENT", "page_size": 100},
        headers=super_admin_headers,
    )

    assert response.status_code == 200
    ids = [item["broadcast_id"] for item in response.json()["data"]["items"]]
    assert created_id in ids


def test_get_broadcast_returns_full_shape(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    created = api_client.post(
        "/api/v1/admin/notifications/broadcasts",
        json=_broadcast_body(
            subject="Heads up", audience_type="ALL_DRIVERS", audience_user_ids=None
        ),
        headers=super_admin_headers,
    ).json()["data"]

    response = api_client.get(
        f"/api/v1/admin/notifications/broadcasts/{created['broadcast_id']}",
        headers=super_admin_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["broadcast_id"] == created["broadcast_id"]
    assert data["subject"] == "Heads up"
    assert data["status"] == "SENT"


def test_get_unknown_broadcast_returns_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.get(
        f"/api/v1/admin/notifications/broadcasts/{uuid.uuid4()}",
        headers=super_admin_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


# --- Advertisements (Admin Web §4.15, ADR-0046) -----------------------


def _ad_campaign_body(**overrides: object) -> dict:
    body: dict = {"partner_name": "Admoto", "payout_amount": 1000}
    body.update(overrides)
    return body


def test_create_ad_campaign_starts_active(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        "/api/v1/admin/advertisements/campaigns",
        json=_ad_campaign_body(),
        headers=super_admin_headers,
    )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["status"] == "ACTIVE"
    assert data["partner_name"] == "Admoto"
    assert data["driver_share_percent"] == 80
    assert data["vistaar_share_percent"] == 20


def test_ad_campaign_pause_resume_end_lifecycle(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    campaign_id = api_client.post(
        "/api/v1/admin/advertisements/campaigns",
        json=_ad_campaign_body(),
        headers=super_admin_headers,
    ).json()["data"]["campaign_id"]

    paused = api_client.post(
        f"/api/v1/admin/advertisements/campaigns/{campaign_id}/pause",
        headers=super_admin_headers,
    )
    assert paused.status_code == 200
    assert paused.json()["data"]["status"] == "PAUSED"

    resumed = api_client.post(
        f"/api/v1/admin/advertisements/campaigns/{campaign_id}/resume",
        headers=super_admin_headers,
    )
    assert resumed.status_code == 200
    assert resumed.json()["data"]["status"] == "ACTIVE"

    ended = api_client.post(
        f"/api/v1/admin/advertisements/campaigns/{campaign_id}/end",
        headers=super_admin_headers,
    )
    assert ended.status_code == 200
    assert ended.json()["data"]["status"] == "ENDED"

    # Terminal — cannot resume an ENDED campaign.
    response = api_client.post(
        f"/api/v1/admin/advertisements/campaigns/{campaign_id}/resume",
        headers=super_admin_headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_assign_driver_to_paused_campaign_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    driver_id, _driver_headers = _new_driver_with_profile(api_client, sms)
    campaign_id = api_client.post(
        "/api/v1/admin/advertisements/campaigns",
        json=_ad_campaign_body(),
        headers=super_admin_headers,
    ).json()["data"]["campaign_id"]
    api_client.post(
        f"/api/v1/admin/advertisements/campaigns/{campaign_id}/pause",
        headers=super_admin_headers,
    )

    response = api_client.post(
        f"/api/v1/admin/advertisements/campaigns/{campaign_id}/assignments",
        json={"driver_id": driver_id},
        headers=super_admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_ad_campaign_to_payout_settlement_full_flow(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """End to end through the admin HTTP surface: Create -> Assign ->
    (proof submitted directly, since driver-side submission has no
    endpoint yet — ADR-0046 §5) -> Verify -> Calculate -> Settle,
    composing WalletService.credit(ADVERTISEMENT_PAYOUT) then
    mark_payout_paid() (ADR-0046 Decision 4)."""
    _, super_admin_headers = _login_admin(api_client, sms)
    driver_id, _driver_headers = _new_driver_with_profile(api_client, sms)
    campaign_id = api_client.post(
        "/api/v1/admin/advertisements/campaigns",
        json=_ad_campaign_body(payout_amount=1000),
        headers=super_admin_headers,
    ).json()["data"]["campaign_id"]

    assignment = api_client.post(
        f"/api/v1/admin/advertisements/campaigns/{campaign_id}/assignments",
        json={"driver_id": driver_id},
        headers=super_admin_headers,
    ).json()["data"]
    assignment_id = assignment["assignment_id"]

    # ADR-0018/ADR-0046: driver-side proof submission has no endpoint
    # yet — reach PROOF_SUBMITTED directly via SQL, the same
    # "reach a state no endpoint produces yet" pattern this codebase's
    # own test suite already established elsewhere.
    db = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE advertisement.driver_campaigns SET status = "
                "'PROOF_SUBMITTED', proof_uri = 'ref-install-photo', "
                "verification_status = 'PENDING' WHERE id = :id"
            ),
            {"id": assignment_id},
        )
        db.commit()
    finally:
        db.close()

    verified = api_client.post(
        f"/api/v1/admin/advertisements/assignments/{assignment_id}/verify",
        json={"approved": True},
        headers=super_admin_headers,
    )
    assert verified.status_code == 200
    assert verified.json()["data"]["verification_status"] == "APPROVED"

    payout = api_client.post(
        f"/api/v1/admin/advertisements/assignments/{assignment_id}/payouts/calculate",
        headers=super_admin_headers,
    ).json()["data"]
    assert payout["status"] == "PENDING"
    assert payout["driver_amount"] == 800.0
    assert payout["vistaar_amount"] == 200.0

    settled = api_client.post(
        f"/api/v1/admin/advertisements/payouts/{payout['payout_id']}/settle",
        headers=super_admin_headers,
    )
    assert settled.status_code == 200
    assert settled.json()["data"]["status"] == "PAID"

    db = SessionLocal()
    try:
        wallet_balance = db.execute(
            text("SELECT balance FROM wallet.wallets WHERE driver_id = :id"),
            {"id": driver_id},
        ).scalar()
        assert wallet_balance == Decimal("800.00")

        ledger_row = db.execute(
            text(
                "SELECT transaction_type, direction, amount FROM "
                "wallet.transactions WHERE driver_id = :id"
            ),
            {"id": driver_id},
        ).fetchone()
        assert ledger_row is not None
        assert ledger_row.transaction_type == "ADVERTISEMENT_PAYOUT"
        assert ledger_row.direction == "CREDIT"
    finally:
        db.close()


def test_search_ad_assignments_filters_by_campaign_and_status(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    driver_id, _driver_headers = _new_driver_with_profile(api_client, sms)
    campaign_id = api_client.post(
        "/api/v1/admin/advertisements/campaigns",
        json=_ad_campaign_body(),
        headers=super_admin_headers,
    ).json()["data"]["campaign_id"]
    api_client.post(
        f"/api/v1/admin/advertisements/campaigns/{campaign_id}/assignments",
        json={"driver_id": driver_id},
        headers=super_admin_headers,
    )

    response = api_client.get(
        "/api/v1/admin/advertisements/assignments",
        params={"campaign_id": campaign_id, "status": "ASSIGNED"},
        headers=super_admin_headers,
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["campaign_id"] == campaign_id


def test_list_ad_campaigns_unknown_status_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.get(
        "/api/v1/admin/advertisements/campaigns",
        params={"status": "NOT_A_REAL_STATUS"},
        headers=super_admin_headers,
    )

    assert response.status_code == 422


def test_employee_admin_without_advertisements_access_is_forbidden(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _admin_id, phone = _create_employee_admin(api_client, super_admin_headers)
    employee_headers = _login_employee_admin(api_client, sms, phone)

    response = api_client.post(
        "/api/v1/admin/advertisements/campaigns",
        json=_ad_campaign_body(),
        headers=employee_headers,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# --- Reports / Analytics (Admin Web §4.16, ADR-0047) ------------------


def _record_penalty_directly(customer_id: uuid.UUID, *, ride_id: uuid.UUID) -> None:
    """Direct-service-layer seed, same technique as
    _trigger_sos_directly/_credit_wallet_directly above — no HTTP
    endpoint creates a penalty on demand. `ride_id` must be a real
    ride.rides row (a real FK, despite the column being nullable in
    the schema for other callers)."""
    db = SessionLocal()
    try:
        service = PenaltyService(
            penalties=SqlAlchemyPenaltyRepository(db),
            strikes=SqlAlchemyStrikeRepository(db),
        )
        service.record_customer_cancellation(
            customer_id=customer_id, ride_id=ride_id, now=datetime.now(UTC)
        )
        db.commit()
    finally:
        db.close()


def _grant_welcome_entitlement_directly(customer_id: uuid.UUID) -> None:
    """Direct SQL seed — BR-058's WELCOME grant normally happens at
    registration (modules/customer/service.py), too much unrelated
    setup for what this report test needs from it."""
    now = datetime.now(UTC)
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO promotion.entitlements "
                "(id, customer_id, promotion_type, total_uses, remaining_uses, "
                "discount_percent, activated_at, expires_at, status) "
                "VALUES (:id, :customer_id, 'WELCOME', 3, 3, 50, :now, "
                ":expires, 'ACTIVE')"
            ),
            {
                "id": str(uuid.uuid4()),
                "customer_id": str(customer_id),
                "now": now,
                "expires": now + timedelta(days=30),
            },
        )
        db.commit()
    finally:
        db.close()


def test_rides_report_reflects_a_created_ride(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    customer_id, customer_headers = _new_customer_with_profile(api_client, sms)
    api_client.post(
        "/api/v1/rides",
        json={
            "pickup": {"latitude": 25.5941, "longitude": 85.1376},
            "destination": {"latitude": 25.6120, "longitude": 85.1580},
            "vehicle_category": "BIKE",
            "payment_method": "CASH",
        },
        headers={**customer_headers, "Idempotency-Key": f"test-{uuid.uuid4()}"},
    )

    response = api_client.get(
        "/api/v1/admin/reports/rides", headers=super_admin_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["rides_by_status"].get("SEARCHING", 0) >= 1
    assert data["rides_by_vehicle_category"].get("BIKE", 0) >= 1
    assert isinstance(data["average_fare"], float)
    assert isinstance(data["completion_rate"], float)
    assert "from" in data and "to" in data


def test_customers_report_reflects_a_new_customer(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _customer_id, _customer_headers = _new_customer_with_profile(api_client, sms)

    response = api_client.get(
        "/api/v1/admin/reports/customers", headers=super_admin_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total_customers"] >= 1
    assert data["new_customers_in_range"] >= 1


def test_drivers_report_reflects_a_new_driver(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _driver_id, _driver_headers = _new_driver_with_profile(api_client, sms)

    response = api_client.get(
        "/api/v1/admin/reports/drivers", headers=super_admin_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total_drivers"] >= 1
    assert data["by_verification_status"].get("PENDING", 0) >= 1
    assert data["new_drivers_in_range"] >= 1
    assert isinstance(data["by_operational_status"], dict)


def test_financial_report_reflects_a_fee_reversal(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    driver_id, _driver_headers = _new_driver_with_profile(api_client, sms)
    _credit_wallet_directly(uuid.UUID(driver_id), amount=Decimal("25.00"))

    response = api_client.get(
        "/api/v1/admin/reports/financial", headers=super_admin_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["fee_reversals"] >= 25.0
    assert data["by_transaction_type"].get("FEE_REVERSAL", 0) >= 1
    assert isinstance(data["platform_fee_collected"], float)
    assert isinstance(data["driver_referral_bonuses_paid"], float)
    assert isinstance(data["advertisement_payouts"], float)


def test_penalties_report_reflects_a_recorded_penalty(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    customer_id, customer_headers = _new_customer_with_profile(api_client, sms)
    ride = api_client.post(
        "/api/v1/rides",
        json={
            "pickup": {"latitude": 25.5941, "longitude": 85.1376},
            "destination": {"latitude": 25.6120, "longitude": 85.1580},
            "vehicle_category": "BIKE",
            "payment_method": "CASH",
        },
        headers={**customer_headers, "Idempotency-Key": f"test-{uuid.uuid4()}"},
    ).json()["data"]
    _record_penalty_directly(uuid.UUID(customer_id), ride_id=uuid.UUID(ride["ride_id"]))

    response = api_client.get(
        "/api/v1/admin/reports/penalties", headers=super_admin_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["penalties_by_type"].get("CUSTOMER_CANCELLATION", 0) >= 1
    assert sum(data["penalties_by_status"].values()) >= 1
    assert isinstance(data["total_amount_outstanding"], float)
    assert isinstance(data["total_amount_settled_in_range"], float)


def test_promotions_referrals_report_reflects_grants_and_referrals(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    referrer_id, referrer_headers = _new_customer_with_profile(api_client, sms)
    code = api_client.get(
        "/api/v1/customers/me/referral", headers=referrer_headers
    ).json()["data"]["code"]
    referred_id, referred_headers = _new_customer_with_profile(api_client, sms)
    api_client.post(
        "/api/v1/referrals/attach", json={"code": code}, headers=referred_headers
    )
    _grant_welcome_entitlement_directly(uuid.UUID(referrer_id))

    response = api_client.get(
        "/api/v1/admin/reports/promotions-referrals", headers=super_admin_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["entitlements_granted_in_range"].get("WELCOME", 0) >= 1
    assert data["referrals_by_status"].get("ACTIVATED", 0) >= 1
    assert data["rewards_issued_in_range"] >= 0.0
    assert isinstance(data["entitlements_used_in_range"], int)
    assert isinstance(data["total_discount_given"], float)


def test_safety_support_report_reflects_an_incident_and_a_case(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    customer_id, customer_headers = _new_customer_with_profile(api_client, sms)
    _trigger_sos_directly(uuid.UUID(customer_id))
    _create_support_case(api_client, customer_headers)

    response = api_client.get(
        "/api/v1/admin/reports/safety-support", headers=super_admin_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["incidents_by_status"].get("OPEN", 0) >= 1
    assert data["cases_by_status"].get("OPEN", 0) >= 1
    assert isinstance(data["average_incident_resolution_minutes"], float)
    assert isinstance(data["average_case_resolution_minutes"], float)


def test_notifications_report_reflects_a_sent_delivery(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    customer_id, _customer_headers = _new_customer_with_profile(api_client, sms)
    _send_in_app_notification_directly(uuid.UUID(customer_id))

    response = api_client.get(
        "/api/v1/admin/reports/notifications", headers=super_admin_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["deliveries_by_channel"].get("IN_APP", 0) >= 1
    assert data["deliveries_by_status"].get("SENT", 0) >= 1
    assert isinstance(data["delivery_success_rate"], float)


def test_matching_report_returns_the_documented_shape(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Real-offer seeding needs a full ride+driver+vehicle+accept flow
    (tests/test_matching_api.py's own fixture stack) — out of scope for
    this admin-report-shape check; the aggregate query methods
    themselves are covered by tests/test_matching_service.py's unit
    tests against a fake repository."""
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.get(
        "/api/v1/admin/reports/matching", headers=super_admin_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert isinstance(data["offers_by_status"], dict)
    assert isinstance(data["offer_acceptance_rate"], float)
    assert isinstance(data["average_time_to_accept_seconds"], float)


def test_reports_default_date_range_is_the_last_30_days(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.get(
        "/api/v1/admin/reports/customers", headers=super_admin_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    since = datetime.fromisoformat(data["from"])
    until = datetime.fromisoformat(data["to"])
    assert 29 <= (until - since).days <= 30


def test_employee_admin_without_reports_access_is_forbidden(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _admin_id, phone = _create_employee_admin(api_client, super_admin_headers)
    employee_headers = _login_employee_admin(api_client, sms, phone)

    response = api_client.get(
        "/api/v1/admin/reports/customers", headers=employee_headers
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# --- Dashboard (Admin Web §3) ------------------------------------------


def test_dashboard_summary_reflects_real_counts(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _driver_id, driver_headers = _new_driver_with_profile(api_client, sms)
    _make_driver_approvable(api_client, driver_headers)
    customer_id, customer_headers = _new_customer_with_profile(api_client, sms)
    _trigger_sos_directly(uuid.UUID(customer_id))
    _create_support_case(api_client, customer_headers)

    response = api_client.get(
        "/api/v1/admin/dashboard/summary", headers=super_admin_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["pending_driver_approvals"] >= 1
    assert data["open_sos_incidents"] >= 1
    assert data["open_support_cases"] >= 1
    assert isinstance(data["platform_fee_collected_today"], float)
    assert isinstance(data["outstanding_penalties"], int)
    assert isinstance(data["open_gps_disputes"], int)
    assert isinstance(data["pending_vehicle_approvals"], int)
    assert isinstance(data["online_drivers"], int)
    assert isinstance(data["rides_today_by_status"], dict)


def test_dashboard_summary_reflects_online_drivers_and_rides_today(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Both fields added 2026-08-28 — online_drivers now real once
    go_offline() actually cleans up its own Redis entry
    (modules/driver/router.py), rides_today_by_status reusing
    RideService.count_rides_by_status_in_range() (built for
    Reports/Analytics, ADR-0047)."""
    _, super_admin_headers = _login_admin(api_client, sms)
    driver_id, driver_headers = _new_driver_with_profile(api_client, sms)
    _make_driver_approvable(api_client, driver_headers)
    api_client.post(
        f"/api/v1/admin/drivers/{driver_id}/approve", headers=super_admin_headers
    )
    vehicle_id = _new_vehicle(api_client, driver_headers)
    _make_vehicle_approvable(vehicle_id)
    api_client.post(
        f"/api/v1/admin/vehicles/{vehicle_id}/approve", headers=super_admin_headers
    )
    api_client.post(
        f"/api/v1/drivers/me/vehicles/{vehicle_id}/activate", headers=driver_headers
    )
    api_client.post("/api/v1/drivers/me/online", headers=driver_headers)
    try:
        api_client.post(
            "/api/v1/drivers/me/location",
            json={"latitude": 22.111, "longitude": 88.222},
            headers=driver_headers,
        )

        customer_id, customer_headers = _new_customer_with_profile(api_client, sms)
        api_client.post(
            "/api/v1/rides",
            json={
                "pickup": {"latitude": 25.5941, "longitude": 85.1376},
                "destination": {"latitude": 25.6120, "longitude": 85.1580},
                "vehicle_category": "BIKE",
                "payment_method": "CASH",
            },
            headers={**customer_headers, "Idempotency-Key": f"test-{uuid.uuid4()}"},
        )

        response = api_client.get(
            "/api/v1/admin/dashboard/summary", headers=super_admin_headers
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["online_drivers"] >= 1
        assert data["rides_today_by_status"].get("SEARCHING", 0) >= 1
    finally:
        api_client.post("/api/v1/drivers/me/offline", headers=driver_headers)


def test_employee_admin_without_dashboard_access_is_forbidden(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _admin_id, phone = _create_employee_admin(api_client, super_admin_headers)
    employee_headers = _login_employee_admin(api_client, sms, phone)

    response = api_client.get(
        "/api/v1/admin/dashboard/summary", headers=employee_headers
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# --- Settings (Admin Web §4.19, ADR-0048) -----------------------------------
#
# A fixed, closed vocabulary of keys seeded by migration
# f2c6a819e3b4 — welcome_discount_percent (50) and welcome_total_uses
# (3), both PROMOTION_DEFAULT. Every test that PATCHes here restores
# the seeded baseline afterward, same discipline as this file's own
# platform-fee-rule tests above: every write here is a real commit
# against a shared test database (tests/conftest.py — no per-test
# rollback), and these two keys have no collision-free test-only
# variant the way an arbitrary fare-rule vehicle_category does.

_SETTINGS_BASELINE = {"welcome_discount_percent": 50, "welcome_total_uses": 3}


def _restore_setting_baseline(
    api_client: TestClient, super_admin_headers: dict, key: str
) -> None:
    api_client.patch(
        f"/api/v1/admin/settings/{key}",
        json={"value": _SETTINGS_BASELINE[key]},
        headers=super_admin_headers,
    )


def test_list_settings_returns_the_seeded_keys(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.get("/api/v1/admin/settings", headers=super_admin_headers)

    assert response.status_code == 200
    keys = {item["key"] for item in response.json()["data"]}
    assert {"welcome_discount_percent", "welcome_total_uses"} <= keys


def test_list_settings_filters_by_category(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.get(
        "/api/v1/admin/settings",
        params={"category": "PROMOTION_DEFAULT"},
        headers=super_admin_headers,
    )

    assert response.status_code == 200
    items = response.json()["data"]
    assert len(items) >= 2
    assert all(item["category"] == "PROMOTION_DEFAULT" for item in items)


def test_list_settings_rejects_unknown_category(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.get(
        "/api/v1/admin/settings",
        params={"category": "NOT_A_REAL_CATEGORY"},
        headers=super_admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_get_setting_returns_the_seeded_value(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.get(
        "/api/v1/admin/settings/welcome_discount_percent",
        headers=super_admin_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["key"] == "welcome_discount_percent"
    assert data["value"] == 50
    assert data["category"] == "PROMOTION_DEFAULT"


def test_get_setting_unknown_key_returns_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.get(
        "/api/v1/admin/settings/not_a_real_key", headers=super_admin_headers
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_update_setting_changes_the_value(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    try:
        response = api_client.patch(
            "/api/v1/admin/settings/welcome_discount_percent",
            json={"value": 75},
            headers=super_admin_headers,
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["value"] == 75

        fetched = api_client.get(
            "/api/v1/admin/settings/welcome_discount_percent",
            headers=super_admin_headers,
        )
        assert fetched.json()["data"]["value"] == 75
    finally:
        _restore_setting_baseline(
            api_client, super_admin_headers, "welcome_discount_percent"
        )


def test_update_setting_unknown_key_returns_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.patch(
        "/api/v1/admin/settings/not_a_real_key",
        json={"value": 1},
        headers=super_admin_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_employee_admin_without_settings_access_is_forbidden(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """SETTINGS is one of the two modules never grantable to an
    employee admin (BR-126, `_UNGRANTABLE_MODULES`) — same as
    ADMIN_MANAGEMENT — so no permission-grant setup is needed here at
    all; a freshly created employee admin can never reach this."""
    _, super_admin_headers = _login_admin(api_client, sms)
    _admin_id, phone = _create_employee_admin(api_client, super_admin_headers)
    employee_headers = _login_employee_admin(api_client, sms, phone)

    list_response = api_client.get("/api/v1/admin/settings", headers=employee_headers)
    patch_response = api_client.patch(
        "/api/v1/admin/settings/welcome_discount_percent",
        json={"value": 75},
        headers=employee_headers,
    )

    assert list_response.status_code == 403
    assert list_response.json()["error"]["code"] == "FORBIDDEN"
    assert patch_response.status_code == 403
    assert patch_response.json()["error"]["code"] == "FORBIDDEN"


# --- Matching / Offers (Admin Web §4.6, ADR-0054) ---------------------
#
# VIEW-only — no mutation exists here, matching ADR-0054's own
# constraint that the matching algorithm stays entirely driver-facing.
# Real-offer seeding needs the same full driver+vehicle+ride flow
# test_dashboard_summary_reflects_online_drivers_and_rides_today already
# uses above; the search/filter logic itself is covered by
# tests/test_matching_service.py's own unit tests against a fake
# repository (same split test_matching_report_returns_the_documented_
# shape's docstring already establishes for the Reports endpoint).


def _random_matching_point() -> tuple[float, float]:
    """A base coordinate randomized well outside any other test's
    search radius — copied from tests/test_matching_api.py's own
    _random_point() (same "no shared test-helper module" convention
    that file's docstring already states); Redis GEO entries from
    earlier test runs are never cleaned up (modules/matching/
    __init__.py), so reusing a fixed coordinate risks a stale driver
    from a previous test being dispatched to instead of this test's
    own new one."""
    lat = 30.0 + secrets.randbelow(1000) / 100.0
    lng = 65.0 + secrets.randbelow(1000) / 100.0
    return lat, lng


def _dispatch_a_real_offer(
    api_client: TestClient, sms: CapturingSmsProvider, super_admin_headers: dict
) -> tuple[str, str, str]:
    """Brings one driver online with an ACTIVE vehicle, then creates a
    matching ride as a new customer — POST /api/v1/rides dispatches
    synchronously (modules/ride/router.py), so a real matching.
    ride_offers row exists by the time this returns. Returns
    (offer_id, ride_id, driver_id). `_new_vehicle()` always creates a
    CAB/ECO vehicle (ADR-0020 Decision 1's own default) — the ride
    request below must match that category/tier exactly, or
    matching_category_key() eligibility never matches and no offer is
    dispatched (a silent, legitimate ADR-0011 Item 5 outcome elsewhere,
    but this helper needs a real offer to exist)."""
    lat, lng = _random_matching_point()
    driver_id, driver_headers = _new_driver_with_profile(api_client, sms)
    _make_driver_approvable(api_client, driver_headers)
    api_client.post(
        f"/api/v1/admin/drivers/{driver_id}/approve", headers=super_admin_headers
    )
    vehicle_id = _new_vehicle(api_client, driver_headers)
    _make_vehicle_approvable(vehicle_id)
    api_client.post(
        f"/api/v1/admin/vehicles/{vehicle_id}/approve", headers=super_admin_headers
    )
    api_client.post(
        f"/api/v1/drivers/me/vehicles/{vehicle_id}/activate", headers=driver_headers
    )
    api_client.post("/api/v1/drivers/me/online", headers=driver_headers)
    api_client.post(
        "/api/v1/drivers/me/location",
        json={"latitude": lat, "longitude": lng},
        headers=driver_headers,
    )

    _customer_id, customer_headers = _new_customer_with_profile(api_client, sms)
    ride_response = api_client.post(
        "/api/v1/rides",
        json={
            "pickup": {"latitude": lat, "longitude": lng},
            "destination": {"latitude": lat + 0.02, "longitude": lng + 0.02},
            "vehicle_category": "CAB",
            "cab_tier": "ECO",
            "payment_method": "CASH",
        },
        headers={**customer_headers, "Idempotency-Key": f"test-{uuid.uuid4()}"},
    )
    ride_id = ride_response.json()["data"]["ride_id"]

    offers_response = api_client.get(
        "/api/v1/drivers/me/ride-offers", headers=driver_headers
    )
    offer_id = offers_response.json()["data"]["offers"][0]["offer_id"]
    return offer_id, ride_id, driver_id


def test_online_drivers_reflects_real_counts_by_category(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    driver_id, driver_headers = _new_driver_with_profile(api_client, sms)
    _make_driver_approvable(api_client, driver_headers)
    api_client.post(
        f"/api/v1/admin/drivers/{driver_id}/approve", headers=super_admin_headers
    )
    vehicle_id = _new_vehicle(api_client, driver_headers)
    _make_vehicle_approvable(vehicle_id)
    api_client.post(
        f"/api/v1/admin/vehicles/{vehicle_id}/approve", headers=super_admin_headers
    )
    api_client.post(
        f"/api/v1/drivers/me/vehicles/{vehicle_id}/activate", headers=driver_headers
    )
    api_client.post("/api/v1/drivers/me/online", headers=driver_headers)
    try:
        api_client.post(
            "/api/v1/drivers/me/location",
            json={"latitude": 24.111, "longitude": 90.222},
            headers=driver_headers,
        )

        response = api_client.get(
            "/api/v1/admin/matching/online-drivers", headers=super_admin_headers
        )

        assert response.status_code == 200
        data = response.json()["data"]
        # _new_vehicle() always creates a CAB/ECO vehicle (ADR-0020
        # Decision 1's own default) — that's the real Redis key this
        # driver's location write lands under.
        assert data["by_category"]["CAB:ECO"] >= 1
        assert data["total"] >= 1
        assert data["total"] == sum(data["by_category"].values())
    finally:
        api_client.post("/api/v1/drivers/me/offline", headers=driver_headers)


def test_online_drivers_requires_matching_permission(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _admin_id, phone = _create_employee_admin(api_client, super_admin_headers)
    employee_headers = _login_employee_admin(api_client, sms, phone)

    response = api_client.get(
        "/api/v1/admin/matching/online-drivers", headers=employee_headers
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_search_offers_returns_a_dispatched_offer_with_documented_fields(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    offer_id, ride_id, driver_id = _dispatch_a_real_offer(
        api_client, sms, super_admin_headers
    )

    response = api_client.get(
        "/api/v1/admin/matching/offers",
        params={"ride_id": ride_id},
        headers=super_admin_headers,
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    offer = items[0]
    assert offer["offer_id"] == offer_id
    assert offer["ride_id"] == ride_id
    assert offer["driver_id"] == driver_id
    assert offer["status"] == "PENDING"
    assert "vehicle_id" in offer
    assert "expires_at" in offer
    assert "created_at" in offer
    # Documented/safe fields only — no coordinates, no Redis-derived
    # location or availability data (ADR-0054 §5).
    assert "latitude" not in offer
    assert "longitude" not in offer
    assert "pickup" not in offer


def test_search_offers_filters_by_status_and_driver_id(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    offer_id, _ride_id, driver_id = _dispatch_a_real_offer(
        api_client, sms, super_admin_headers
    )

    by_status = api_client.get(
        "/api/v1/admin/matching/offers",
        params={"status": "PENDING", "driver_id": driver_id},
        headers=super_admin_headers,
    )
    by_wrong_status = api_client.get(
        "/api/v1/admin/matching/offers",
        params={"status": "REJECTED", "driver_id": driver_id},
        headers=super_admin_headers,
    )

    assert by_status.status_code == 200
    ids = [o["offer_id"] for o in by_status.json()["data"]["items"]]
    assert offer_id in ids
    assert by_wrong_status.status_code == 200
    assert by_wrong_status.json()["data"]["items"] == []


def test_search_offers_rejects_unknown_status(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.get(
        "/api/v1/admin/matching/offers",
        params={"status": "NOT_A_REAL_STATUS"},
        headers=super_admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_search_offers_requires_matching_permission(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _admin_id, phone = _create_employee_admin(api_client, super_admin_headers)
    employee_headers = _login_employee_admin(api_client, sms, phone)

    response = api_client.get("/api/v1/admin/matching/offers", headers=employee_headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_employee_admin_with_matching_view_can_search_offers(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _admin_id, phone = _create_employee_admin(
        api_client,
        super_admin_headers,
        permissions=[{"module": "MATCHING", "access_level": "VIEW"}],
    )
    employee_headers = _login_employee_admin(api_client, sms, phone)

    response = api_client.get("/api/v1/admin/matching/offers", headers=employee_headers)

    assert response.status_code == 200


def test_get_offer_returns_full_documented_offer_data(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    offer_id, ride_id, driver_id = _dispatch_a_real_offer(
        api_client, sms, super_admin_headers
    )

    response = api_client.get(
        f"/api/v1/admin/matching/offers/{offer_id}", headers=super_admin_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["offer_id"] == offer_id
    assert data["ride_id"] == ride_id
    assert data["driver_id"] == driver_id
    assert data["status"] == "PENDING"
    assert data["responded_at"] is None


def test_get_unknown_offer_returns_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.get(
        f"/api/v1/admin/matching/offers/{uuid.uuid4()}",
        headers=super_admin_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_get_offer_requires_matching_permission(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    _admin_id, phone = _create_employee_admin(api_client, super_admin_headers)
    employee_headers = _login_employee_admin(api_client, sms, phone)

    response = api_client.get(
        f"/api/v1/admin/matching/offers/{uuid.uuid4()}", headers=employee_headers
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# --- Driver Strike History (Admin Web §4.9, api-contracts.md §46.18) --
#
# Reuses the DRIVERS permission (this is driver data, not a new
# module). A plain read over `penalty.strikes` — immutable by
# construction, so the search-filter logic is thin enough that the
# service-level unit tests (tests/test_penalty_service.py) cover the
# real behavior; these confirm the HTTP layer wires it up correctly.


def _record_driver_strike_directly(
    driver_id: uuid.UUID, *, ride_id: uuid.UUID, reason: str = "DRIVER_CANCELLATION"
) -> None:
    """Direct-service-layer seed, same technique
    _record_penalty_directly() above already uses — no HTTP endpoint
    creates a strike on demand (BR-068 records one as a side effect of
    a real ride-cancellation flow, out of scope for this shape check).
    `ride_id` must be a real ride.rides row — a real FK, same caveat
    _record_penalty_directly()'s own docstring already gives."""
    db = SessionLocal()
    try:
        service = PenaltyService(
            penalties=SqlAlchemyPenaltyRepository(db),
            strikes=SqlAlchemyStrikeRepository(db),
        )
        service.record_driver_strike(
            driver_id=driver_id, ride_id=ride_id, reason=reason, now=datetime.now(UTC)
        )
        db.commit()
    finally:
        db.close()


def test_get_driver_strikes_returns_the_seeded_strike(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    driver_id, _driver_headers = _new_driver_with_profile(api_client, sms)
    _customer_id, customer_headers = _new_customer_with_profile(api_client, sms)
    ride = api_client.post(
        "/api/v1/rides",
        json={
            "pickup": {"latitude": 25.5941, "longitude": 85.1376},
            "destination": {"latitude": 25.6120, "longitude": 85.1580},
            "vehicle_category": "BIKE",
            "payment_method": "CASH",
        },
        headers={**customer_headers, "Idempotency-Key": f"test-{uuid.uuid4()}"},
    ).json()["data"]
    ride_id = uuid.UUID(ride["ride_id"])
    _record_driver_strike_directly(
        uuid.UUID(driver_id), ride_id=ride_id, reason="UNWILLING_TO_PROCEED"
    )

    response = api_client.get(
        f"/api/v1/admin/drivers/{driver_id}/strikes", headers=super_admin_headers
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["driver_id"] == driver_id
    assert items[0]["ride_id"] == str(ride_id)
    assert items[0]["reason"] == "UNWILLING_TO_PROCEED"
    assert "strike_id" in items[0]
    assert "created_at" in items[0]


def test_get_driver_strikes_is_empty_for_a_driver_with_none(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    driver_id, _driver_headers = _new_driver_with_profile(api_client, sms)

    response = api_client.get(
        f"/api/v1/admin/drivers/{driver_id}/strikes", headers=super_admin_headers
    )

    assert response.status_code == 200
    assert response.json()["data"]["items"] == []


def test_get_strikes_for_unknown_driver_returns_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)

    response = api_client.get(
        f"/api/v1/admin/drivers/{uuid.uuid4()}/strikes", headers=super_admin_headers
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_get_driver_strikes_requires_drivers_permission(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    driver_id, _driver_headers = _new_driver_with_profile(api_client, sms)
    _admin_id, phone = _create_employee_admin(api_client, super_admin_headers)
    employee_headers = _login_employee_admin(api_client, sms, phone)

    response = api_client.get(
        f"/api/v1/admin/drivers/{driver_id}/strikes", headers=employee_headers
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_employee_admin_with_drivers_view_can_read_strike_history(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    _, super_admin_headers = _login_admin(api_client, sms)
    driver_id, _driver_headers = _new_driver_with_profile(api_client, sms)
    _admin_id, phone = _create_employee_admin(
        api_client,
        super_admin_headers,
        permissions=[{"module": "DRIVERS", "access_level": "VIEW"}],
    )
    employee_headers = _login_employee_admin(api_client, sms, phone)

    response = api_client.get(
        f"/api/v1/admin/drivers/{driver_id}/strikes", headers=employee_headers
    )

    assert response.status_code == 200
