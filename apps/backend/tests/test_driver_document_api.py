"""Integration tests: real HTTP layer (TestClient) + real Postgres,
exercising POST and GET /api/v1/drivers/me/documents end-to-end,
authenticated via a real OTP login through modules.identity — same
pattern as tests/test_driver_api.py.

GET was added by ADR-0072 (2026-09-04), closing the gap
docs/14-decisions/ADR-0007 originally left open — see that ADR for the
full account. tests/test_vehicle_document_api.py covers the equivalent
new vehicle-document endpoints.

Skips (not fails) when Postgres is genuinely unreachable.
"""

from __future__ import annotations

import secrets
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from core.database import SessionLocal
from main import app
from modules.identity.dependencies import get_sms_provider_dependency


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


def _create_driver_profile(api_client: TestClient, headers: dict[str, str]) -> None:
    api_client.patch(
        "/api/v1/drivers/me", json={"full_name": "Ravi Kumar"}, headers=headers
    )


def test_submit_document_before_profile_exists_returns_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "DRIVER")

    response = api_client.post(
        "/api/v1/drivers/me/documents",
        json={"document_type": "DRIVING_LICENSE"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_submit_document_succeeds_and_matches_documented_response_shape(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "DRIVER")
    headers = {"Authorization": f"Bearer {access_token}"}
    _create_driver_profile(api_client, headers)

    response = api_client.post(
        "/api/v1/drivers/me/documents",
        json={
            "document_type": "driving_license",
            "document_number": "XY1234",
            "evidence_uri": "uploaded-file-reference",
        },
        headers=headers,
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["document_type"] == "DRIVING_LICENSE"
    assert data["document_number"] == "XY1234"
    assert data["evidence_uri"] == "uploaded-file-reference"
    assert data["verification_status"] == "PENDING"
    assert data["expires_at"] is None
    assert "document_id" in data
    assert "created_at" in data
    assert "updated_at" in data
    # Phase 2 / Task 2.6, ADR-0008 items 1/9: evidence_uri was supplied,
    # so a verification case must have been created.
    assert data["verification_case_id"] is not None


def test_submit_document_with_evidence_uri_creates_a_verification_case(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "DRIVER")
    headers = {"Authorization": f"Bearer {access_token}"}
    _create_driver_profile(api_client, headers)

    response = api_client.post(
        "/api/v1/drivers/me/documents",
        json={"document_type": "DRIVING_LICENSE", "evidence_uri": "ref-1"},
        headers=headers,
    )
    data = response.json()["data"]

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT status, subject_type, subject_id FROM verification.cases "
                "WHERE id = :id"
            ),
            {"id": data["verification_case_id"]},
        ).fetchone()
        assert row is not None
        assert row[0] == "PENDING"
        assert row[1] == "DRIVER_DOCUMENT"
        assert str(row[2]) == data["document_id"]
    finally:
        db.close()


def test_submit_document_without_evidence_uri_creates_no_verification_case(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "DRIVER")
    headers = {"Authorization": f"Bearer {access_token}"}
    _create_driver_profile(api_client, headers)

    response = api_client.post(
        "/api/v1/drivers/me/documents",
        json={"document_type": "DRIVING_LICENSE"},
        headers=headers,
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["evidence_uri"] is None
    assert data["verification_case_id"] is None

    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT id FROM verification.cases WHERE subject_id = :id"),
            {"id": data["document_id"]},
        ).fetchone()
        assert row is None
    finally:
        db.close()


def test_submit_document_with_blank_type_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "DRIVER")
    headers = {"Authorization": f"Bearer {access_token}"}
    _create_driver_profile(api_client, headers)

    response = api_client.post(
        "/api/v1/drivers/me/documents",
        json={"document_type": "   "},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_resubmitting_same_document_type_creates_a_second_record(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """No versioning/replacement rule exists — see ADR-0007."""
    access_token = _login(api_client, sms, "DRIVER")
    headers = {"Authorization": f"Bearer {access_token}"}
    _create_driver_profile(api_client, headers)

    first = api_client.post(
        "/api/v1/drivers/me/documents",
        json={"document_type": "DRIVING_LICENSE"},
        headers=headers,
    ).json()["data"]
    second = api_client.post(
        "/api/v1/drivers/me/documents",
        json={"document_type": "DRIVING_LICENSE"},
        headers=headers,
    ).json()["data"]

    assert first["document_id"] != second["document_id"]


def test_unauthenticated_request_is_rejected(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/drivers/me/documents", json={"document_type": "DRIVING_LICENSE"}
    )
    assert response.status_code == 401


def test_customer_account_cannot_submit_driver_document(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "CUSTOMER")

    response = api_client.post(
        "/api/v1/drivers/me/documents",
        json={"document_type": "DRIVING_LICENSE"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 403


def test_document_persists_across_requests_via_postgres(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "DRIVER")
    headers = {"Authorization": f"Bearer {access_token}"}
    _create_driver_profile(api_client, headers)

    api_client.post(
        "/api/v1/drivers/me/documents",
        json={"document_type": "DRIVING_LICENSE", "document_number": "PERSIST-TEST"},
        headers=headers,
    )

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT document_number FROM driver.documents "
                "WHERE document_number = :n"
            ),
            {"n": "PERSIST-TEST"},
        ).fetchone()
        assert row is not None
    finally:
        db.close()


# --- List My Driver Documents (ADR-0072, 2026-09-04) ---------------------


def test_list_documents_is_empty_before_any_submission(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "DRIVER")
    headers = {"Authorization": f"Bearer {access_token}"}
    _create_driver_profile(api_client, headers)

    response = api_client.get("/api/v1/drivers/me/documents", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["documents"] == []


def test_list_documents_returns_newest_first_with_no_verification_case_id(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "DRIVER")
    headers = {"Authorization": f"Bearer {access_token}"}
    _create_driver_profile(api_client, headers)

    first = api_client.post(
        "/api/v1/drivers/me/documents",
        json={"document_type": "GOVERNMENT_ID", "evidence_uri": "ref-1"},
        headers=headers,
    ).json()["data"]
    second = api_client.post(
        "/api/v1/drivers/me/documents",
        json={"document_type": "DRIVING_LICENSE", "evidence_uri": "ref-2"},
        headers=headers,
    ).json()["data"]

    response = api_client.get("/api/v1/drivers/me/documents", headers=headers)

    assert response.status_code == 200
    documents = response.json()["data"]["documents"]
    assert [d["document_id"] for d in documents] == [
        second["document_id"],
        first["document_id"],
    ]
    # List reads never report a verification_case_id — only the POST
    # response that actually created one does (see this endpoint's own
    # docstring).
    assert all(d["verification_case_id"] is None for d in documents)


def test_list_documents_only_returns_the_callers_own(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    mine_token = _login(api_client, sms, "DRIVER")
    mine_headers = {"Authorization": f"Bearer {mine_token}"}
    _create_driver_profile(api_client, mine_headers)
    api_client.post(
        "/api/v1/drivers/me/documents",
        json={"document_type": "GOVERNMENT_ID"},
        headers=mine_headers,
    )

    other_token = _login(api_client, sms, "DRIVER")
    other_headers = {"Authorization": f"Bearer {other_token}"}
    _create_driver_profile(api_client, other_headers)

    response = api_client.get("/api/v1/drivers/me/documents", headers=other_headers)

    assert response.status_code == 200
    assert response.json()["data"]["documents"] == []


def test_list_documents_unauthenticated_is_rejected(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/drivers/me/documents")
    assert response.status_code == 401


def test_list_documents_customer_account_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "CUSTOMER")

    response = api_client.get(
        "/api/v1/drivers/me/documents",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 403
