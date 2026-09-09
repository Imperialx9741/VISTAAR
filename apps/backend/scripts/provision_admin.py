"""Ops-only admin provisioning script.

Phase 2 / Task 2.7A. See
docs/14-decisions/ADR-0009-admin-approval-scope-and-open-items.md point B.

ADR-0040/BR-126/BR-127 (2026-08-26) resolved business-rules.md §43's
"Admin roles"/"Permission hierarchy" TBD markers: one Super Admin level
(controlled by the core team) can create/manage employee ADMIN accounts
over a real HTTP endpoint (POST /api/v1/admin/admins) — but the Super
Admin level itself still has no self-service registration path (BR-127:
"the same 'who is allowed to grant admin status' restraint ADR-0009
already applied"). This script is that bootstrap, for either role: run
directly against the database by someone who already holds deployment/
infrastructure access — the same trust level already required to run
`alembic upgrade head` or exec into the Postgres container. No new
privilege boundary is invented; this script is not reachable over HTTP
and is not imported by any FastAPI route.

It creates (or reuses) the target identity.accounts row with
account_type=ADMIN using the existing identity repository — no new
account-creation code — then inserts one admin.users row (role=ADMIN or
SUPER_ADMIN per --role, status="ACTIVE"). It generates, prints, or
hard-codes no credential: the resulting account still authenticates
through the existing phone+OTP flow like any other account, the same
way a DRIVER or CUSTOMER account does. This script only grants the
admin.users record itself — an employee ADMIN provisioned this way
starts with zero module permissions (admin.permissions), same as one
created via the HTTP endpoint with an empty `permissions` list; a Super
Admin needs none (ADR-0040 Decision 1: implicit full access).

Usage (from apps/backend/, with the project's virtualenv active and
DATABASE_URL pointing at the target environment):

    python scripts/provision_admin.py --phone +919999999999
    python scripts/provision_admin.py --phone +919999999999 --role super_admin

Refuses to run if an admin.users row already exists for the resolved
account (use a database console directly for role/status changes to an
existing admin — not this script's job).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Standalone script, not part of the FastAPI application package — put
# src/ on sys.path so `core.*`/`modules.*` imports resolve the same way
# they do for the app and the test suite (pyproject.toml's
# [tool.pytest.ini_options] pythonpath = ["src"]).
_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from core.database import SessionLocal  # noqa: E402
from modules.admin.models import AdminUserORM  # noqa: E402
from modules.identity.domain.entities import AccountType  # noqa: E402
from modules.identity.domain.errors import InvalidPhoneNumberError  # noqa: E402
from modules.identity.domain.phone_number import PhoneNumber  # noqa: E402
from modules.identity.repositories import SqlAlchemyAccountRepository  # noqa: E402


def provision_admin(phone_raw: str, *, role: str = "admin") -> None:
    admin_role = "SUPER_ADMIN" if role == "super_admin" else "ADMIN"
    try:
        phone = str(PhoneNumber.parse(phone_raw))
    except InvalidPhoneNumberError as exc:
        print(f"error: invalid phone number: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    db = SessionLocal()
    try:
        accounts = SqlAlchemyAccountRepository(db)
        account = accounts.get_by_phone(phone)
        if account is None:
            account = accounts.create(account_type=AccountType.ADMIN, phone=phone)
            print(f"created identity.accounts row: {account.id} ({phone})")
        elif account.account_type is not AccountType.ADMIN:
            print(
                f"error: {phone} already exists as account_type="
                f"{account.account_type.value}, not ADMIN. Refusing to "
                "reuse a non-admin account.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        else:
            print(f"reusing existing ADMIN identity.accounts row: {account.id}")

        existing_admin_user = db.get(AdminUserORM, account.id)
        if existing_admin_user is not None:
            print(
                f"error: admin.users already exists for {account.id} "
                f"(role={existing_admin_user.role!r}, "
                f"status={existing_admin_user.status!r}). Refusing to "
                "overwrite — use a database console directly for "
                "role/status changes to an existing admin.",
                file=sys.stderr,
            )
            raise SystemExit(1)

        admin_user = AdminUserORM(id=account.id, role=admin_role, status="ACTIVE")
        db.add(admin_user)
        db.commit()
        print(
            f"provisioned admin.users row for {account.id} "
            f"(role={admin_role}, status=ACTIVE)"
        )
        print(
            "no credential was generated — this account authenticates via "
            "the normal phone+OTP flow."
        )
    except SystemExit:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phone",
        required=True,
        help="Phone number of the account to provision as ADMIN (E.164 or "
        "bare 10-digit Indian mobile).",
    )
    parser.add_argument(
        "--role",
        choices=("admin", "super_admin"),
        default="admin",
        help="admin (default): an employee admin, starts with zero module "
        "permissions (grant them via PATCH /api/v1/admin/admins/{id}/"
        "permissions once a Super Admin exists). super_admin: full "
        "implicit access to every module, per ADR-0040.",
    )
    args = parser.parse_args()
    provision_admin(args.phone, role=args.role)


if __name__ == "__main__":
    main()
