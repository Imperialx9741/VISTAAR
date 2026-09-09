"""Integration tests: real HTTP layer (TestClient) + real Postgres,
exercising POST/GET /api/v1/drivers/me/vehicles/{vehicle_id}/documents
end-to-end (ADR-0072, 2026-09-04 — the previously-missing vehicle-
document endpoints, closing docs/14-decisions/ADR-0007's flagged gap).
Same layered pattern as tests/test_vehicle_api.py/
tests/test_driver_document_api.py.

Skips (not fails) when Postgres is genuinely unreachable.
"""

from __future__ import annotations

import secrets
import uuid
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


def _random_registration() -> str:
    return "BR01" + "".join(str(secrets.randbelow(10)) for _ in range(6))


def _new_driver_with_profile(
    api_client: TestClient, sms: CapturingSmsProvider
) -> dict[str, str]:
    phone = _random_phone()
    request_response = api_client.post(
        "/api/v1/auth/otp/request",
        json={"phone": phone, "account_type": "DRIVER"},
    )
    challenge_id = request_response.json()["data"]["challenge_id"]
    otp = sms.sent[phone]
    tokens = api_client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "otp": otp},
    ).json()["data"]
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    api_client.patch(
        "/api/v1/drivers/me", json={"full_name": "Ravi Kumar"}, headers=headers
    )
    return headers


def _add_vehicle(api_client: TestClient, headers: dict[str, str]) -> str:
    response = api_client.post(
        "/api/v1/drivers/me/vehicles",
        json={
            "category": "CAB",
            "cab_tier": "ECO",
            "registration_number": _random_registration(),
        },
        headers=headers,
    )
    vehicle_id: str = response.json()["data"]["vehicle_id"]
    return vehicle_id


# --- Submit Vehicle Document -----------------------------------------------


def test_submit_document_succeeds_and_matches_documented_response_shape(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers = _new_driver_with_profile(api_client, sms)
    vehicle_id = _add_vehicle(api_client, headers)

    response = api_client.post(
        f"/api/v1/drivers/me/vehicles/{vehicle_id}/documents",
        json={
            "document_type": "rc",
            "document_number": "RC-1234",
            "evidence_uri": "uploaded-file-reference",
        },
        headers=headers,
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["document_type"] == "RC"
    assert data["document_number"] == "RC-1234"
    assert data["evidence_uri"] == "uploaded-file-reference"
    assert data["verification_status"] == "PENDING"
    assert data["expires_at"] is None
    assert "document_id" in data
    assert "created_at" in data
    # VehicleDocument has no updated_at column (unlike DriverDocument) —
    # see modules/vehicle/domain/entities.py::VehicleDocument's own
    # docstring; the response must not invent one.
    assert "updated_at" not in data
    assert data["verification_case_id"] is not None


def test_submit_document_without_evidence_uri_creates_no_verification_case(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers = _new_driver_with_profile(api_client, sms)
    vehicle_id = _add_vehicle(api_client, headers)

    response = api_client.post(
        f"/api/v1/drivers/me/vehicles/{vehicle_id}/documents",
        json={"document_type": "INSURANCE"},
        headers=headers,
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["evidence_uri"] is None
    assert data["verification_case_id"] is None


def test_submit_document_with_evidence_uri_creates_a_verification_case(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers = _new_driver_with_profile(api_client, sms)
    vehicle_id = _add_vehicle(api_client, headers)

    response = api_client.post(
        f"/api/v1/drivers/me/vehicles/{vehicle_id}/documents",
        json={"document_type": "RC", "evidence_uri": "ref-1"},
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
        assert row[1] == "VEHICLE_DOCUMENT"
        assert str(row[2]) == data["document_id"]
    finally:
        db.close()


def test_submit_document_for_another_drivers_vehicle_is_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    owner_headers = _new_driver_with_profile(api_client, sms)
    vehicle_id = _add_vehicle(api_client, owner_headers)

    other_headers = _new_driver_with_profile(api_client, sms)
    response = api_client.post(
        f"/api/v1/drivers/me/vehicles/{vehicle_id}/documents",
        json={"document_type": "RC"},
        headers=other_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_submit_document_unknown_vehicle_is_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers = _new_driver_with_profile(api_client, sms)

    response = api_client.post(
        f"/api/v1/drivers/me/vehicles/{uuid.uuid4()}/documents",
        json={"document_type": "RC"},
        headers=headers,
    )

    assert response.status_code == 404


def test_submit_document_with_blank_type_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers = _new_driver_with_profile(api_client, sms)
    vehicle_id = _add_vehicle(api_client, headers)

    response = api_client.post(
        f"/api/v1/drivers/me/vehicles/{vehicle_id}/documents",
        json={"document_type": "   "},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_submit_document_unauthenticated_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers = _new_driver_with_profile(api_client, sms)
    vehicle_id = _add_vehicle(api_client, headers)

    response = api_client.post(
        f"/api/v1/drivers/me/vehicles/{vehicle_id}/documents",
        json={"document_type": "RC"},
    )

    assert response.status_code == 401


# --- List Vehicle Documents --------------------------------------------


def test_list_documents_is_empty_before_any_submission(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers = _new_driver_with_profile(api_client, sms)
    vehicle_id = _add_vehicle(api_client, headers)

    response = api_client.get(
        f"/api/v1/drivers/me/vehicles/{vehicle_id}/documents", headers=headers
    )

    assert response.status_code == 200
    assert response.json()["data"]["documents"] == []


def test_list_documents_returns_newest_first_with_no_verification_case_id(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers = _new_driver_with_profile(api_client, sms)
    vehicle_id = _add_vehicle(api_client, headers)

    first = api_client.post(
        f"/api/v1/drivers/me/vehicles/{vehicle_id}/documents",
        json={"document_type": "RC", "evidence_uri": "ref-1"},
        headers=headers,
    ).json()["data"]
    second = api_client.post(
        f"/api/v1/drivers/me/vehicles/{vehicle_id}/documents",
        json={"document_type": "INSURANCE", "evidence_uri": "ref-2"},
        headers=headers,
    ).json()["data"]

    response = api_client.get(
        f"/api/v1/drivers/me/vehicles/{vehicle_id}/documents", headers=headers
    )

    assert response.status_code == 200
    documents = response.json()["data"]["documents"]
    assert [d["document_id"] for d in documents] == [
        second["document_id"],
        first["document_id"],
    ]
    assert all(d["verification_case_id"] is None for d in documents)


def test_list_documents_for_another_drivers_vehicle_is_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    owner_headers = _new_driver_with_profile(api_client, sms)
    vehicle_id = _add_vehicle(api_client, owner_headers)

    other_headers = _new_driver_with_profile(api_client, sms)
    response = api_client.get(
        f"/api/v1/drivers/me/vehicles/{vehicle_id}/documents", headers=other_headers
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_list_documents_unauthenticated_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers = _new_driver_with_profile(api_client, sms)
    vehicle_id = _add_vehicle(api_client, headers)

    response = api_client.get(
        f"/api/v1/drivers/me/vehicles/{vehicle_id}/documents"
    )

    assert response.status_code == 401
