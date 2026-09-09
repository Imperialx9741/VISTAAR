"""VISTAAR Load-Testing — safe test-account provisioning.

Phase 20 (owner-requested, 2026-09-04): "Complete all load-testing
preparation that can be done locally... safe test data/setup."

Creates N real Sarthi (driver) accounts and M real customer accounts,
each fully onboarded and ready to generate load (approved documents,
an ACTIVE approved vehicle, a funded wallet, for drivers), then mints
real access tokens for every one of them — the exact same
`issue_access_token()` the real login flow uses (modules/identity/
security.py) — and writes them to a JSON file the k6 scripts read.

Why this bypasses the real OTP/SMS login flow entirely, deliberately:
- It is the only way to provision thousands of accounts in minutes
  instead of thousands of real SMS sends (cost, and MSG91 rate limits
  would make this infeasible regardless).
- It never touches the real SMS provider, in any environment — the
  identity.accounts rows below are created directly, and
  issue_access_token() is called in-process; no OTP is ever requested
  or "faked" through the API.
- The resulting tokens are indistinguishable from a real login's
  tokens to every endpoint under test (same signing key, same claims,
  same expiry) — this measures real request-handling load, not a
  shortcut that skips work the real app would also skip.

SAFETY:
- Every phone number and full_name below is obviously synthetic
  (+91700000NNNN, "Load Test Driver N"/"Load Test Customer N") and
  namespaced under a single admin-provisioned batch — safe to bulk-
  delete afterward (see cleanup_test_accounts.py).
- Refuses to run unless DATABASE_URL/API_BASE_URL point somewhere the
  caller has explicitly confirmed via --i-understand-this-is-not-production
  (no default "just go" behavior) — this project's explicit standing
  rule is "do not run destructive/load testing against production."
- Never touches wallet.wallets for a real, non-synthetic driver — every
  row this script writes carries a phone number matching
  _PHONE_PREFIX, and cleanup only ever deletes rows matching that same
  prefix.

Usage (run from apps/backend's own virtualenv, so it can import the
real signing/DB code — this script is intentionally NOT a standalone
reimplementation of that logic):

    cd apps/backend && source .venv/Scripts/activate
    python ../../infrastructure/load-testing/setup/mint_test_accounts.py \\
        --drivers 200 --customers 300 \\
        --api-base-url http://127.0.0.1:8000 \\
        --i-understand-this-is-not-production \\
        --out ../../infrastructure/load-testing/tokens.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

# Runs from apps/backend's own venv (see module docstring) so these
# imports resolve exactly like they do for the backend process itself —
# no duplicated/guessed signing or schema logic.
_BACKEND_SRC = Path(__file__).resolve().parents[3] / "apps" / "backend" / "src"
sys.path.insert(0, str(_BACKEND_SRC))

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from core.database import SessionLocal  # noqa: E402
from modules.identity.domain.entities import AccountType  # noqa: E402
from modules.identity.security import issue_access_token  # noqa: E402

_PHONE_PREFIX = "+91700000"  # every synthetic account's phone starts here
_WALLET_STARTING_BALANCE = "5000.00"
_CONCURRENCY = 20  # simultaneous in-flight setup requests to the API


@dataclass
class MintedAccount:
    role: str  # "DRIVER" | "CUSTOMER" | "ADMIN"
    account_id: str
    token: str
    phone: str
    vehicle_id: str | None = None
    extra: dict[str, str] = field(default_factory=dict)


def _seed_account(phone: str, account_type: str) -> tuple[uuid.UUID, str]:
    """Direct insert (bypassing OTP entirely — see module docstring) +
    a real, correctly-signed access token via the same function the
    real login flow calls."""
    account_id = uuid.uuid4()
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO identity.accounts (id, account_type, phone, status) "
                "VALUES (:id, :account_type, :phone, 'ACTIVE')"
            ),
            {"id": str(account_id), "account_type": account_type, "phone": phone},
        )
        db.commit()
    finally:
        db.close()
    token, _jti, _expires_at = issue_access_token(
        account_id=account_id,
        account_type=AccountType(account_type),
        now=datetime.now(UTC),
    )
    return account_id, token


async def _approve_document_with_retry(*, table: str, document_id: str) -> None:
    """Marks one driver.documents/vehicle.documents row APPROVED,
    verifying the UPDATE actually matched a row (`rowcount`) and
    retrying briefly if not.

    Found and fixed 2026-09-04: running several `_provision_driver()`
    tasks concurrently (`asyncio.gather`, this module's own pattern)
    made this specific step genuinely flaky — a document occasionally
    stayed PENDING even though the exact same UPDATE, run in isolation
    immediately after its own POST, always succeeded on the first try.
    The concurrent-only reproducibility points at a read-visibility
    race between the backend server process's own request-handling
    commit and this script's separate process's next read/write — not
    a logic bug in the SQL itself. Rather than accept a data-seeding
    tool that silently produces wrong state some fraction of the time
    (worse than an outright failure — see this module's own "safe test
    data" framing), this retries a few times with a short delay instead
    of asserting the first attempt must succeed."""
    for attempt in range(5):
        db = SessionLocal()
        try:
            result = db.execute(
                text(
                    f"UPDATE {table} SET verification_status = 'APPROVED' "  # noqa: S608
                    "WHERE id = :id"
                ),
                {"id": document_id},
            )
            db.commit()
            if result.rowcount == 1:
                return
        finally:
            db.close()
        await asyncio.sleep(0.1 * (attempt + 1))
    raise RuntimeError(
        f"Could not mark {table} row {document_id} APPROVED after 5 attempts "
        "— the document row never became visible to this script's own "
        "database connection."
    )


def _seed_admin() -> tuple[uuid.UUID, str]:
    admin_id, token = _seed_account(f"{_PHONE_PREFIX}9999", "ADMIN")
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO admin.users (id, role, status) "
                "VALUES (:id, 'SUPER_ADMIN', 'ACTIVE')"
            ),
            {"id": str(admin_id)},
        )
        db.commit()
    finally:
        db.close()
    return admin_id, token


async def _provision_driver(
    client: httpx.AsyncClient, *, index: int, admin_token: str
) -> MintedAccount:
    """Mirrors tests/test_notification_consumer.py's own
    _accepted_ride()-style driver-provisioning sequence exactly
    (document submit -> admin-approve -> vehicle create -> admin-
    approve -> activate), just driven over real HTTP with a minted
    token instead of a real OTP login, and via the running server
    rather than in-process calls — this is what actually exercises the
    real endpoints under load-test-adjacent conditions during setup
    too."""
    phone = f"{_PHONE_PREFIX}{index:04d}"
    account_id, token = _seed_account(phone, "DRIVER")
    headers = {"Authorization": f"Bearer {token}"}
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    await client.patch(
        "/api/v1/drivers/me",
        json={"full_name": f"Load Test Driver {index}"},
        headers=headers,
    )

    for document_type in ("GOVERNMENT_ID", "DRIVING_LICENSE"):
        response = await client.post(
            "/api/v1/drivers/me/documents",
            json={"document_type": document_type, "evidence_uri": "load-test-ref"},
            headers=headers,
        )
        document_id = response.json()["data"]["document_id"]
        await _approve_document_with_retry(
            table="driver.documents", document_id=document_id
        )

    approve_driver_response = await client.post(
        f"/api/v1/admin/drivers/{account_id}/approve", headers=admin_headers
    )
    if approve_driver_response.status_code != 200:
        raise RuntimeError(
            f"Approving driver {account_id} failed: "
            f"{approve_driver_response.status_code} {approve_driver_response.text}"
        )

    vehicle_response = await client.post(
        "/api/v1/drivers/me/vehicles",
        json={
            "category": "CAB",
            "cab_tier": "ECO",
            "registration_number": f"LT{index:06d}",
        },
        headers=headers,
    )
    vehicle_id = vehicle_response.json()["data"]["vehicle_id"]

    # ADR-0072 (2026-09-04) added the real HTTP endpoint this previously
    # had no choice but to work around via raw SQL — submit through it
    # for real now, same as the driver-document loop above, then mark
    # each APPROVED the same raw-SQL way (approval itself is still an
    # admin-only action with no bulk HTTP endpoint).
    for document_type in ("RC", "INSURANCE"):
        response = await client.post(
            f"/api/v1/drivers/me/vehicles/{vehicle_id}/documents",
            json={"document_type": document_type, "evidence_uri": "load-test-ref"},
            headers=headers,
        )
        document_id = response.json()["data"]["document_id"]
        await _approve_document_with_retry(
            table="vehicle.documents", document_id=document_id
        )

    approve_vehicle_response = await client.post(
        f"/api/v1/admin/vehicles/{vehicle_id}/approve", headers=admin_headers
    )
    if approve_vehicle_response.status_code != 200:
        raise RuntimeError(
            f"Approving vehicle {vehicle_id} failed: "
            f"{approve_vehicle_response.status_code} {approve_vehicle_response.text}"
        )
    activate_response = await client.post(
        f"/api/v1/drivers/me/vehicles/{vehicle_id}/activate", headers=headers
    )
    if activate_response.status_code != 200:
        raise RuntimeError(
            f"Activating vehicle {vehicle_id} failed: "
            f"{activate_response.status_code} {activate_response.text}"
        )

    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO wallet.wallets (driver_id, balance) "
                "VALUES (:driver_id, :balance) "
                "ON CONFLICT (driver_id) DO UPDATE SET balance = :balance"
            ),
            {"driver_id": str(account_id), "balance": _WALLET_STARTING_BALANCE},
        )
        db.commit()
    finally:
        db.close()

    return MintedAccount(
        role="DRIVER",
        account_id=str(account_id),
        token=token,
        phone=phone,
        vehicle_id=vehicle_id,
    )


async def _provision_customer(index: int) -> MintedAccount:
    phone = f"{_PHONE_PREFIX}{50000 + index:05d}"
    account_id, token = _seed_account(phone, "CUSTOMER")
    return MintedAccount(
        role="CUSTOMER", account_id=str(account_id), token=token, phone=phone
    )


async def _run(args: argparse.Namespace) -> list[MintedAccount]:
    print("Seeding 1 admin account (for document/vehicle approvals)...")
    _admin_id, admin_token = _seed_admin()

    accounts: list[MintedAccount] = []
    async with httpx.AsyncClient(base_url=args.api_base_url, timeout=30.0) as client:
        semaphore = asyncio.Semaphore(_CONCURRENCY)

        async def _driver_task(i: int) -> MintedAccount:
            async with semaphore:
                return await _provision_driver(client, index=i, admin_token=admin_token)

        print(f"Provisioning {args.drivers} Sarthi accounts (documents, vehicle, "
              f"wallet — this calls the real API, so it takes a while)...")
        drivers = await asyncio.gather(*[_driver_task(i) for i in range(args.drivers)])
        accounts.extend(drivers)

    print(f"Provisioning {args.customers} customer accounts...")
    customers = await asyncio.gather(
        *[_provision_customer(i) for i in range(args.customers)]
    )
    accounts.extend(customers)

    return accounts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drivers", type=int, default=50)
    parser.add_argument("--customers", type=int, default=100)
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parent.parent / "tokens.json"),
    )
    parser.add_argument(
        "--i-understand-this-is-not-production",
        action="store_true",
        dest="confirmed",
        help=(
            "Required. This script writes real rows to whatever database "
            "the backend process (--api-base-url) is connected to — never "
            "point this at a production environment."
        ),
    )
    args = parser.parse_args()

    if not args.confirmed:
        print(
            "Refusing to run: pass --i-understand-this-is-not-production to "
            "confirm --api-base-url is a disposable/staging environment, "
            "never production.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    accounts = asyncio.run(_run(args))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "api_base_url": args.api_base_url,
                "accounts": [
                    {
                        "role": a.role,
                        "account_id": a.account_id,
                        "token": a.token,
                        "phone": a.phone,
                        "vehicle_id": a.vehicle_id,
                    }
                    for a in accounts
                ],
            },
            indent=2,
        )
    )
    print(f"Wrote {len(accounts)} accounts to {out_path}")


if __name__ == "__main__":
    main()
