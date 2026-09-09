"""Integration tests: real HTTP layer (TestClient) + real Postgres,
exercising GET /api/v1/customers/me/referral and POST /api/v1/referrals/
attach end-to-end (api-contracts.md §38), plus the two ADR-0019
Decision 4 composition points:

- The customer flow's promotion grants, composed directly inside
  POST /api/v1/referrals/attach.
- The driver flow's qualify + ₹100/₹100 wallet reward, composed into
  POST /api/v1/admin/drivers/{driver_id}/approve.

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
from modules.admin.models import AdminUserORM
from modules.identity.dependencies import get_sms_provider_dependency
from modules.identity.security import decode_access_token


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


def _new_customer_with_profile(
    api_client: TestClient, sms: CapturingSmsProvider
) -> tuple[dict, uuid.UUID]:
    access_token = _login(api_client, sms, "CUSTOMER")
    headers = {"Authorization": f"Bearer {access_token}"}
    profile = api_client.get("/api/v1/customers/me", headers=headers).json()["data"]
    return headers, uuid.UUID(profile["customer_id"])


def _new_driver_with_profile(
    api_client: TestClient, sms: CapturingSmsProvider
) -> tuple[dict, uuid.UUID]:
    access_token = _login(api_client, sms, "DRIVER")
    headers = {"Authorization": f"Bearer {access_token}"}
    profile = api_client.patch(
        "/api/v1/drivers/me", json={"full_name": "Ravi Kumar"}, headers=headers
    ).json()["data"]
    return headers, uuid.UUID(profile["driver_id"])


def _provision_admin(account_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        db.add(AdminUserORM(id=account_id, role="SUPER_ADMIN", status="ACTIVE"))
        db.commit()
    finally:
        db.close()


def _login_admin(api_client: TestClient, sms: CapturingSmsProvider) -> dict:
    access_token = _login(api_client, sms, "ADMIN")
    _provision_admin(_account_id_from_token(access_token))
    return {"Authorization": f"Bearer {access_token}"}


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
    for document_type in ("GOVERNMENT_ID", "DRIVING_LICENSE"):
        document_id = _submit_driver_document(api_client, driver_headers, document_type)
        _mark_driver_document_approved(document_id)


def _wallet_balance(driver_id: uuid.UUID) -> float | None:
    db = SessionLocal()
    try:
        return db.execute(
            text("SELECT balance FROM wallet.wallets WHERE driver_id = :id"),
            {"id": str(driver_id)},
        ).scalar()
    finally:
        db.close()


# --- Get Referral Code ---------------------------------------------------


def test_get_my_referral_code_provisions_one(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers, _ = _new_customer_with_profile(api_client, sms)

    response = api_client.get("/api/v1/customers/me/referral", headers=headers)

    assert response.status_code == 200
    code = response.json()["data"]["code"]
    assert len(code) == 8


def test_get_my_referral_code_is_stable_across_calls(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers, _ = _new_customer_with_profile(api_client, sms)

    first = api_client.get("/api/v1/customers/me/referral", headers=headers)
    second = api_client.get("/api/v1/customers/me/referral", headers=headers)

    assert first.json()["data"]["code"] == second.json()["data"]["code"]


def test_get_my_referral_code_unauthenticated_is_rejected(
    api_client: TestClient,
) -> None:
    response = api_client.get("/api/v1/customers/me/referral")
    assert response.status_code == 401


# --- Attach Referral: customer flow --------------------------------------


def test_attach_referral_activates_and_grants_promotions(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    referrer_headers, _ = _new_customer_with_profile(api_client, sms)
    code = api_client.get(
        "/api/v1/customers/me/referral", headers=referrer_headers
    ).json()["data"]["code"]
    referred_headers, referred_id = _new_customer_with_profile(api_client, sms)

    response = api_client.post(
        "/api/v1/referrals/attach", json={"code": code}, headers=referred_headers
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ACTIVATED"  # BR-060: immediate

    referred_promotions = api_client.get(
        "/api/v1/customers/me/promotions", headers=referred_headers
    ).json()["data"]["promotions"]
    referred_types = {p["type"]: p["remaining_uses"] for p in referred_promotions}
    assert referred_types["REFERRAL_REFERRED"] == 3  # BR-059
    assert referred_types["WELCOME"] == 3  # unaffected, still separate

    referrer_promotions = api_client.get(
        "/api/v1/customers/me/promotions", headers=referrer_headers
    ).json()["data"]["promotions"]
    referrer_types = {p["type"]: p["remaining_uses"] for p in referrer_promotions}
    assert referrer_types["REFERRAL_REFERRING"] == 2  # BR-060

    db = SessionLocal()
    try:
        referral_row = db.execute(
            text("SELECT id, status FROM referral.referrals WHERE referred_id = :id"),
            {"id": str(referred_id)},
        ).fetchone()
        assert referral_row is not None
        assert referral_row.status == "ACTIVATED"

        reward_count = db.execute(
            text("SELECT COUNT(*) FROM referral.rewards WHERE referral_id = :id"),
            {"id": str(referral_row.id)},
        ).scalar()
        assert reward_count == 2  # one audit row per side
    finally:
        db.close()


def test_attach_referral_rejects_unknown_code(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers, _ = _new_customer_with_profile(api_client, sms)

    response = api_client.post(
        "/api/v1/referrals/attach", json={"code": "NOSUCH01"}, headers=headers
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "REFERRAL_INVALID"


def test_attach_referral_rejects_self_referral(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers, _ = _new_customer_with_profile(api_client, sms)
    code = api_client.get("/api/v1/customers/me/referral", headers=headers).json()[
        "data"
    ]["code"]

    response = api_client.post(
        "/api/v1/referrals/attach", json={"code": code}, headers=headers
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "REFERRAL_INVALID"


def test_attach_referral_rejects_a_second_attach_for_the_same_referred_party(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    referrer_headers, _ = _new_customer_with_profile(api_client, sms)
    code = api_client.get(
        "/api/v1/customers/me/referral", headers=referrer_headers
    ).json()["data"]["code"]
    other_referrer_headers, _ = _new_customer_with_profile(api_client, sms)
    other_code = api_client.get(
        "/api/v1/customers/me/referral", headers=other_referrer_headers
    ).json()["data"]["code"]
    referred_headers, _ = _new_customer_with_profile(api_client, sms)
    api_client.post(
        "/api/v1/referrals/attach", json={"code": code}, headers=referred_headers
    )

    response = api_client.post(
        "/api/v1/referrals/attach",
        json={"code": other_code},
        headers=referred_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REFERRAL_ALREADY_ATTACHED"


def test_attach_referral_unauthenticated_is_rejected(api_client: TestClient) -> None:
    response = api_client.post("/api/v1/referrals/attach", json={"code": "ABCD1234"})
    assert response.status_code == 401


# --- Attach Referral + Approve Driver: driver flow (BR-022/023) ---------


def test_driver_cannot_fetch_own_referral_code(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Get Referral Code is customer-only (ADR-0019 Decision 5) — a
    driver has no documented way to fetch their own code over HTTP."""
    driver_headers, _ = _new_driver_with_profile(api_client, sms)

    response = api_client.get("/api/v1/customers/me/referral", headers=driver_headers)

    assert response.status_code == 403


def test_driver_referral_activates_and_pays_reward_on_approval(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    referrer_headers, referrer_id = _new_driver_with_profile(api_client, sms)
    referred_headers, referred_id = _new_driver_with_profile(api_client, sms)
    _make_driver_approvable(api_client, referred_headers)
    admin_headers = _login_admin(api_client, sms)

    # No driver-facing "get my code" endpoint exists (ADR-0019 Decision 5)
    # — reach the code the same way modules/referral/service.py's
    # get_or_create_code() would produce it, directly via SQL, matching
    # this codebase's established "reach a state no endpoint produces
    # yet" pattern. Randomized (not a fixed literal) so a repeated suite
    # run against the same un-truncated test database never collides
    # with uq_referral_codes_code, matching this codebase's established
    # convention (e.g. test_admin_api.py's _random_registration()).
    driver_code = "DR" + secrets.token_hex(3).upper()
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO referral.codes (id, owner_type, owner_id, code, status) "
                "VALUES (:id, 'DRIVER', :owner_id, :code, 'ACTIVE')"
            ),
            {
                "id": str(uuid.uuid4()),
                "owner_id": str(referrer_id),
                "code": driver_code,
            },
        )
        db.commit()
    finally:
        db.close()

    attach = api_client.post(
        "/api/v1/referrals/attach",
        json={"code": driver_code},
        headers=referred_headers,
    )
    assert attach.status_code == 200
    assert attach.json()["data"]["status"] == "ATTACHED"  # not yet activated

    approve = api_client.post(
        f"/api/v1/admin/drivers/{referred_id}/approve", headers=admin_headers
    )
    assert approve.status_code == 200

    db = SessionLocal()
    try:
        referral_row = db.execute(
            text("SELECT id, status FROM referral.referrals WHERE referred_id = :id"),
            {"id": str(referred_id)},
        ).fetchone()
        assert referral_row is not None
        assert referral_row.status == "ACTIVATED"

        reward_count = db.execute(
            text("SELECT COUNT(*) FROM referral.rewards WHERE referral_id = :id"),
            {"id": str(referral_row.id)},
        ).scalar()
        assert reward_count == 2
    finally:
        db.close()

    assert _wallet_balance(referrer_id) == 100
    assert _wallet_balance(referred_id) == 100


def test_driver_referral_bonus_uses_the_published_asymmetric_amounts(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """ADR-0043: referred_amount and referrer_amount are independent
    fields — this guards against the pre-fix bug where a single shared
    constant was credited to both sides regardless of which was which
    (modules/admin/router.py::approve_driver()). Publishing a rule here
    replaces the globally-active driver-bonus policy (there is only
    ever one), so the test restores the original 100/100 seed in a
    `finally` — other tests in this module (and any future run) depend
    on that being the active rule."""
    admin_headers = _login_admin(api_client, sms)

    def _publish_driver_bonus(referred: int, referrer: int) -> None:
        rule_id = api_client.post(
            "/api/v1/admin/referral-config/driver-bonus",
            json={"referred_amount": referred, "referrer_amount": referrer},
            headers=admin_headers,
        ).json()["data"]["rule_id"]
        api_client.post(
            f"/api/v1/admin/referral-config/driver-bonus/{rule_id}/publish",
            json={},
            headers=admin_headers,
        )

    _publish_driver_bonus(250, 75)
    try:
        referrer_headers, referrer_id = _new_driver_with_profile(api_client, sms)
        referred_headers, referred_id = _new_driver_with_profile(api_client, sms)
        _make_driver_approvable(api_client, referred_headers)

        driver_code = "DR" + secrets.token_hex(3).upper()
        db = SessionLocal()
        try:
            db.execute(
                text(
                    "INSERT INTO referral.codes "
                    "(id, owner_type, owner_id, code, status) "
                    "VALUES (:id, 'DRIVER', :owner_id, :code, 'ACTIVE')"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "owner_id": str(referrer_id),
                    "code": driver_code,
                },
            )
            db.commit()
        finally:
            db.close()

        attach = api_client.post(
            "/api/v1/referrals/attach",
            json={"code": driver_code},
            headers=referred_headers,
        )
        assert attach.status_code == 200

        approve = api_client.post(
            f"/api/v1/admin/drivers/{referred_id}/approve", headers=admin_headers
        )
        assert approve.status_code == 200

        assert _wallet_balance(referred_id) == 250
        assert _wallet_balance(referrer_id) == 75
    finally:
        _publish_driver_bonus(100, 100)


def test_driver_approval_without_a_referral_is_unaffected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """The common case: most drivers were never referred at all."""
    driver_headers, driver_id = _new_driver_with_profile(api_client, sms)
    _make_driver_approvable(api_client, driver_headers)
    admin_headers = _login_admin(api_client, sms)

    response = api_client.post(
        f"/api/v1/admin/drivers/{driver_id}/approve", headers=admin_headers
    )

    assert response.status_code == 200
    assert _wallet_balance(driver_id) is None  # no wallet row ever created
