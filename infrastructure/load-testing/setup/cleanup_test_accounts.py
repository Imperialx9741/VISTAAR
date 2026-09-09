"""VISTAAR Load-Testing — removes every account mint_test_accounts.py
created (Phase 20, 2026-09-04).

Every synthetic account's phone number starts with the same fixed
prefix (_PHONE_PREFIX in mint_test_accounts.py) — this script only ever
deletes rows reachable from an identity.accounts row whose phone
matches that prefix, via the same foreign-key relationships every real
account has, never a broader "delete everything" sweep. Safe to run
repeatedly; a second run simply deletes nothing.

Usage (same venv/requirement as mint_test_accounts.py):

    cd apps/backend && source .venv/Scripts/activate
    python ../../infrastructure/load-testing/setup/cleanup_test_accounts.py \\
        --i-understand-this-is-not-production
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BACKEND_SRC = Path(__file__).resolve().parents[3] / "apps" / "backend" / "src"
sys.path.insert(0, str(_BACKEND_SRC))

from sqlalchemy import text  # noqa: E402

from core.database import SessionLocal  # noqa: E402

_PHONE_PREFIX = "+91700000"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--i-understand-this-is-not-production",
        action="store_true",
        dest="confirmed",
    )
    args = parser.parse_args()
    if not args.confirmed:
        print(
            "Refusing to run: pass --i-understand-this-is-not-production.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    db = SessionLocal()
    try:
        account_ids = [
            row[0]
            for row in db.execute(
                text(
                    "SELECT id FROM identity.accounts WHERE phone LIKE :prefix"
                ),
                {"prefix": f"{_PHONE_PREFIX}%"},
            ).fetchall()
        ]
        if not account_ids:
            print("Nothing to clean up (no synthetic load-test accounts found).")
            return

        ids = [str(i) for i in account_ids]
        # Children before parents, matching real FK dependency order —
        # deliberately explicit rather than relying on ON DELETE CASCADE
        # (not every one of these tables declares it).
        db.execute(
            text(
                "DELETE FROM vehicle.documents WHERE vehicle_id IN "
                "(SELECT id FROM vehicle.vehicles "
                "WHERE driver_id = ANY(CAST(:ids AS uuid[])))"
            ),
            {"ids": ids},
        )
        db.execute(
            text(
                "DELETE FROM vehicle.vehicles "
                "WHERE driver_id = ANY(CAST(:ids AS uuid[]))"
            ),
            {"ids": ids},
        )
        db.execute(
            text(
                "DELETE FROM driver.documents "
                "WHERE driver_id = ANY(CAST(:ids AS uuid[]))"
            ),
            {"ids": ids},
        )
        db.execute(
            text(
                "DELETE FROM wallet.transactions "
                "WHERE driver_id = ANY(CAST(:ids AS uuid[]))"
            ),
            {"ids": ids},
        )
        db.execute(
            text(
                "DELETE FROM wallet.wallets WHERE driver_id = ANY(CAST(:ids AS uuid[]))"
            ),
            {"ids": ids},
        )
        db.execute(
            text("DELETE FROM driver.drivers WHERE id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": ids},
        )
        db.execute(
            text(
                "DELETE FROM customer.customers WHERE id = ANY(CAST(:ids AS uuid[]))"
            ),
            {"ids": ids},
        )
        db.execute(
            text(
                "DELETE FROM admin.audit_logs "
                "WHERE admin_id = ANY(CAST(:ids AS uuid[]))"
            ),
            {"ids": ids},
        )
        db.execute(
            text("DELETE FROM admin.users WHERE id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": ids},
        )
        db.execute(
            text("DELETE FROM identity.accounts WHERE id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": ids},
        )
        db.commit()
        print(f"Deleted {len(ids)} synthetic load-test accounts and their rows.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
