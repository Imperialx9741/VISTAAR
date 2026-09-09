"""Integration tests: real Postgres, exercising AdvertisementService
against its real SQLAlchemy-backed repositories end to end — including
one worked example of the wallet-credit composition a future router
would perform (ADR-0018).

No HTTP router exists for this module (ADR-0018) — driver_id comes from
a real account created via the existing OTP-login HTTP flow (satisfying
driver.drivers.id's foreign key to identity.accounts), but
AdvertisementService itself is exercised directly, not through HTTP,
matching this file's "service tests... real PostgreSQL integration
tests" testing-policy category rather than an API integration test.

Skips (not fails) when Postgres is genuinely unreachable.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from core.database import SessionLocal
from main import app
from modules.advertisement.domain.errors import PayoutAlreadyCalculatedError
from modules.advertisement.repositories import (
    SqlAlchemyCampaignRepository,
    SqlAlchemyDriverCampaignRepository,
    SqlAlchemyPayoutRepository,
)
from modules.advertisement.service import AdvertisementService
from modules.identity.dependencies import get_sms_provider_dependency
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


def _new_driver_id(api_client: TestClient, sms: CapturingSmsProvider) -> uuid.UUID:
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
    profile = api_client.patch(
        "/api/v1/drivers/me", json={"full_name": "Ravi Kumar"}, headers=headers
    ).json()["data"]
    return uuid.UUID(profile["driver_id"])


def test_create_campaign_persists_in_postgres() -> None:
    db = SessionLocal()
    try:
        service = AdvertisementService(
            campaigns=SqlAlchemyCampaignRepository(db),
            driver_campaigns=SqlAlchemyDriverCampaignRepository(db),
            payouts=SqlAlchemyPayoutRepository(db),
        )
        campaign = service.create_campaign(
            partner_name="Admoto",
            payout_amount=Decimal("1000"),
            starts_at=None,
            ends_at=None,
            now=datetime.now(UTC),
        )
        db.commit()

        row = db.execute(
            text(
                "SELECT partner_name, status, payout_amount FROM "
                "advertisement.campaigns WHERE id = :id"
            ),
            {"id": str(campaign.id)},
        ).fetchone()
        assert row is not None
        assert row.partner_name == "Admoto"
        assert row.status == "ACTIVE"
        assert row.payout_amount == Decimal("1000.00")
    finally:
        db.close()


def test_full_campaign_to_payout_flow_composes_with_wallet_credit(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Worked example of the composition a future router would perform
    (ADR-0018/modules/advertisement/service.py's docstring):
    calculate_payout() -> WalletService.credit() -> mark_payout_paid(),
    all inside one transaction, same shape
    modules/ride/router.py's post-acceptance cancellation composition
    already established for a different pair of modules."""
    driver_id = _new_driver_id(api_client, sms)
    now = datetime.now(UTC)

    db = SessionLocal()
    try:
        ads = AdvertisementService(
            campaigns=SqlAlchemyCampaignRepository(db),
            driver_campaigns=SqlAlchemyDriverCampaignRepository(db),
            payouts=SqlAlchemyPayoutRepository(db),
        )
        wallet = WalletService(wallets=SqlAlchemyWalletRepository(db))

        campaign = ads.create_campaign(
            partner_name="Admoto",
            payout_amount=Decimal("1000"),
            starts_at=None,
            ends_at=None,
            now=now,
        )
        assignment = ads.assign_driver(
            campaign_id=campaign.id, driver_id=driver_id, now=now
        )
        ads.submit_installation_proof(
            assignment_id=assignment.id,
            driver_id=driver_id,
            proof_uri="ref-install-photo",
            now=now,
        )
        ads.verify_advertisement(assignment_id=assignment.id, approved=True, now=now)
        payout = ads.calculate_payout(assignment_id=assignment.id, now=now)

        transaction = wallet.credit(
            driver_id=driver_id,
            amount=payout.driver_amount,
            transaction_type="ADVERTISEMENT_PAYOUT",
            ride_id=None,
            idempotency_key=f"advertisement-payout:{payout.id}",
            now=now,
        )
        settled = ads.mark_payout_paid(payout_id=payout.id)
        db.commit()
    finally:
        db.close()

    assert settled.status.value == "PAID"
    assert transaction.amount == Decimal("800.00")

    db = SessionLocal()
    try:
        wallet_balance = db.execute(
            text("SELECT balance FROM wallet.wallets WHERE driver_id = :id"),
            {"id": str(driver_id)},
        ).scalar()
        assert wallet_balance == Decimal("800.00")

        ledger_row = db.execute(
            text(
                "SELECT transaction_type, direction, amount FROM "
                "wallet.transactions WHERE driver_id = :id"
            ),
            {"id": str(driver_id)},
        ).fetchone()
        assert ledger_row is not None
        assert ledger_row.transaction_type == "ADVERTISEMENT_PAYOUT"
        assert ledger_row.direction == "CREDIT"
        assert ledger_row.amount == Decimal("800.00")

        assignment_row = db.execute(
            text("SELECT status FROM advertisement.driver_campaigns WHERE id = :id"),
            {"id": str(assignment.id)},
        ).fetchone()
        assert assignment_row is not None
        assert assignment_row.status == "PAID"

        payout_row = db.execute(
            text("SELECT status FROM advertisement.payouts WHERE id = :id"),
            {"id": str(payout.id)},
        ).fetchone()
        assert payout_row is not None
        assert payout_row.status == "PAID"
    finally:
        db.close()


def test_calculate_payout_raises_on_second_call_against_real_postgres(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Proves uq_payouts_driver_campaign (migration 83c95d7eaf67) is a
    real database-level constraint, not just an application-level check."""
    driver_id = _new_driver_id(api_client, sms)
    now = datetime.now(UTC)

    db = SessionLocal()
    try:
        ads = AdvertisementService(
            campaigns=SqlAlchemyCampaignRepository(db),
            driver_campaigns=SqlAlchemyDriverCampaignRepository(db),
            payouts=SqlAlchemyPayoutRepository(db),
        )
        campaign = ads.create_campaign(
            partner_name="Admoto",
            payout_amount=Decimal("500"),
            starts_at=None,
            ends_at=None,
            now=now,
        )
        assignment = ads.assign_driver(
            campaign_id=campaign.id, driver_id=driver_id, now=now
        )
        ads.submit_installation_proof(
            assignment_id=assignment.id,
            driver_id=driver_id,
            proof_uri="ref-1",
            now=now,
        )
        ads.verify_advertisement(assignment_id=assignment.id, approved=True, now=now)
        ads.calculate_payout(assignment_id=assignment.id, now=now)
        db.commit()
    finally:
        db.close()

    db = SessionLocal()
    try:
        ads = AdvertisementService(
            campaigns=SqlAlchemyCampaignRepository(db),
            driver_campaigns=SqlAlchemyDriverCampaignRepository(db),
            payouts=SqlAlchemyPayoutRepository(db),
        )
        with pytest.raises(PayoutAlreadyCalculatedError):
            ads.calculate_payout(assignment_id=assignment.id, now=now)
    finally:
        db.close()
