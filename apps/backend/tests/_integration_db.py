"""Shared test-database infrastructure for the Postgres-backed integration
tests (test_vehicle_document_integration.py, test_verification_integration.py)
and, via tests/conftest.py, for the whole suite.

Task 2.7B test-isolation correction. Root cause (confirmed before this
module was added): every DB-backed test — not just the two "integration"
files — ran against the long-lived development database
(docker-compose.dev.yml's `vistaar_db`, backed by a persistent Docker
volume) because no test overrides the `get_db` dependency and no test
DB was ever configured. Rows committed by prior runs (e.g.
vehicle.vehicles, via test_vehicle_document_integration.py's
`_create_vehicle()`) were never cleaned up, and that helper's random
`registration_number` suffix only had 9,999 possible values. With
enough accumulated rows, a freshly generated value eventually collided
with one from an earlier run and tripped `uq_vehicles_registration_number`
— a UniqueViolation unrelated to any Task 2.7B behavior (Task 2.7B is
driver go_online/go_offline; it does not touch vehicles or
registration_number at all).

This isolation covers `pytest` only. A one-off script that imports
`core.database.SessionLocal()` directly (outside `pytest`) still talks
to the real dev database with no cleanup — see README.md's "Manual
diagnostic scripts and the dev database" (added 2026-09-08, during a
Super Admin console audit that traced ~1,800 identity.accounts rows,
mostly from 2026-08-21/22, back to this exact pre-isolation gap) for
the convention to follow when one is genuinely needed.

This module provides:
  - `resolve_test_database_url()` — the URL every test should use,
    switched to a dedicated `vistaar_test_db` so tests never touch the
    development database. tests/conftest.py calls this and sets
    `DATABASE_URL` in os.environ before anything imports
    core.config/core.database, since core.config.settings reads that
    env var exactly once, at import time.
  - `ensure_database_exists()` / `run_migrations()` — create the test
    database and bring it to the current migration head if needed.
  - `truncate_integration_tables()` — an FK-ordered DELETE (see its own
    comment for why not TRUNCATE) covering every table those two files'
    data could transitively touch, so each test starts from an empty
    slate instead of relying on ever-larger random values to avoid
    collisions. Deliberately NOT a transaction/savepoint rollback
    scheme, and deliberately not applied to the rest of the suite — see
    those two files' local `_clean_integration_tables` fixture, the only
    place this is called from.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import sqlalchemy
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

# Matches core/config.py's own default so this module works standalone
# (it must not import core.config — that would trigger the DATABASE_URL
# read this module exists to redirect first).
_DEFAULT_DEV_DATABASE_URL = "postgresql://db_user:db_password@127.0.0.1:5433/vistaar_db"
_TEST_DATABASE_NAME = "vistaar_test_db"


def resolve_test_database_url() -> str:
    """The DATABASE_URL value tests should run with.

    Honors an explicit TEST_DATABASE_URL override if set. Otherwise
    derives it from DATABASE_URL (or the documented default) by
    swapping only the database name, so host/port/credentials still
    match the local docker-compose Postgres instance."""
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit

    base = os.environ.get("DATABASE_URL", _DEFAULT_DEV_DATABASE_URL)
    parts = urlsplit(base)
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            f"/{_TEST_DATABASE_NAME}",
            parts.query,
            parts.fragment,
        )
    )


def ensure_database_exists(test_database_url: str) -> bool:
    """Creates the dedicated test database if it doesn't already exist.

    Connects to the server's `postgres` maintenance database using the
    same host/port/credentials. Returns False without raising if
    Postgres itself is unreachable — the individual integration test
    files already skip (rather than fail) in that case via their own
    `_infra_available()` checks, so this must not turn "Postgres is
    off" into a hard error for the rest of the suite."""
    parts = urlsplit(test_database_url)
    maintenance_url = urlunsplit((parts.scheme, parts.netloc, "/postgres", "", ""))
    db_name = parts.path.lstrip("/")

    try:
        maintenance_engine = sqlalchemy.create_engine(
            maintenance_url, isolation_level="AUTOCOMMIT"
        )
        try:
            with maintenance_engine.connect() as conn:
                exists = conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": db_name},
                ).first()
                if exists is None:
                    # Database names cannot be bound parameters; db_name
                    # comes from our own derived/overridden URL, not
                    # external input.
                    conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        finally:
            maintenance_engine.dispose()
    except OperationalError:
        return False
    return True


def run_migrations() -> None:
    """Brings the test database to the current Alembic head.

    Idempotent — safe to call every test session even when already at
    head. Uses absolute paths so it works regardless of pytest's cwd."""
    from alembic import command
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parents[1]  # apps/backend
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))
    command.upgrade(cfg, "head")


def ensure_admin_settings_seeded(test_database_url: str) -> None:
    """Called once, unconditionally, at conftest.py's module (import)
    level — not just from inside truncate_integration_tables().

    run_migrations() above is a no-op once the test database is
    already at head (alembic only replays a migration's upgrade() body
    the first time a revision is applied), so it does NOT by itself
    repair admin.settings if some earlier session's
    truncate_integration_tables() run wiped it (ADR-0048 has no Create
    endpoint, so unlike every other admin config table, nothing else
    in the test suite can put those two rows back on its own — see
    `_reseed_admin_settings_baseline()`'s own docstring). Calling the
    same idempotent (ON CONFLICT DO NOTHING) reseed here too closes
    that gap for any test file whose settings-dependent tests happen
    to run before the first truncate call of the session. Tolerates
    Postgres being unreachable the same way ensure_database_exists()
    does — the individual test files' own `_infra_available()` checks
    are what actually skip in that case."""
    engine = sqlalchemy.create_engine(test_database_url)
    try:
        with engine.connect() as conn:
            _reseed_admin_settings_baseline(conn)
            conn.commit()
    except OperationalError:
        pass
    finally:
        engine.dispose()


# Every table in the schema, ordered child -> parent. Broader than just
# the tables the two integration test files write to directly: since the
# whole test database is shared for the session (see resolve_test_
# database_url()/conftest.py), API tests in other files (test_admin_api.py,
# test_customer_api.py, etc. — none of which override the `get_db`
# dependency) may have already inserted rows that transitively reference
# identity.accounts (e.g. admin.users, customer.customers) before these
# two files' tests run. identity.accounts can't be cleared while any of
# those still reference it, so every table in that FK graph must be
# included here, confirmed against information_schema against a fully
# migrated test database:
#   admin.audit_logs -> admin.users -> identity.accounts; admin.
#     permissions -> admin.users too (added Admin Permission Model,
#     ADR-0040/BR-126/BR-127 — same class of gap again)
#   customer.preferences -> customer.customers -> identity.accounts
#   driver.documents, vehicle.vehicles -> driver.drivers -> identity.accounts
#   vehicle.documents -> vehicle.vehicles
#   identity.sessions, identity.otp_challenges, identity.mfa_credentials
#     -> identity.accounts (mfa_credentials added Admin MFA, ADR-0051 —
#     same class of gap again)
#   verification.evidence, verification.results -> verification.cases
#     (verification.cases has no FK to identity.accounts — subject_id is
#     a polymorphic reference, not an enforced foreign key)
#   ride.state_history, ride.gps_verifications, ride.ride_otps,
#     ride.early_drop_requests, ride.gps_disputes -> ride.rides ->
#     customer.customers, driver.drivers, vehicle.vehicles; ride.gps_
#     dispute_evidence -> ride.gps_disputes; ride.gps_disputes also ->
#     ride.gps_verifications (ride.rides added Phase 3 / Task 3.1;
#     gps_verifications/ride_otps added Phase 06/07, ADR-0028, used by
#     tests/test_ride_lifecycle_api.py; early_drop_requests added Phase
#     08, ADR-0030, used by tests/test_early_drop_api.py; gps_disputes/
#     gps_dispute_evidence added BR-124/BR-125, ADR-0032, used by
#     tests/test_gps_dispute_api.py — same class of gap this whole
#     mechanism exists to catch; see database-design.md §9.1/§9.2/§12.1/
#     §13.1/§14.1/§14.2/§14.3)
#   matching.ride_offers -> ride.rides, driver.drivers, vehicle.vehicles
#     (added Phase 3 / Task 3.2 — same class of gap again; see
#     database-design.md §10.1)
#   wallet.transactions -> ride.rides (nullable), driver.drivers; wallet.wallets
#     -> driver.drivers (added Minimal Wallet Foundation — same class of gap
#     again; see database-design.md §17)
#   promotion.usage, promotion.reservations -> promotion.entitlements,
#     ride.rides; promotion.entitlements -> customer.customers (added
#     Phase 12 / Growth, ADR-0019 — same class of gap again; see
#     database-design.md §24). promotion.entitlements also -> promotion.
#     campaigns (nullable campaign_id) and promotion.campaign_eligible_
#     customers -> promotion.campaigns, customer.customers; promotion.
#     campaigns -> admin.users (added Coupon/Campaign Schema, ADR-0041 —
#     same class of gap again; entitlements must clear before campaigns,
#     which must clear before admin.users, same as admin.audit_logs/
#     admin.permissions above)
#   referral.driver_bonus_rules, referral.customer_reward_rules ->
#     admin.users (added Referral Reward Configuration, ADR-0043 - same
#     class of gap again; both must clear before admin.users)
#   referral.rewards -> referral.referrals -> referral.codes (no FK to
#     identity.accounts/customer.customers/driver.drivers — owner_id/
#     referrer_id/referred_id are plain UUID columns, not enforced
#     foreign keys, so these three have no ordering constraint relative
#     to the rest of the graph; see database-design.md §25)
#   pricing.fare_quotes -> ride.rides (added Phase 04's "Initial fare
#     quote" task, ADR-0020 — same class of gap again; see
#     database-design.md §15.2). pricing.fare_rules is deliberately NOT
#     in this list — it's seeded reference/config data (migration
#     61a5a80a044e), not per-test row data; clearing it every test would
#     break PricingService.calculate_fare() for every subsequent test in
#     the same session. pricing.platform_fee_rules (added Platform Fee
#     Management, ADR-0045) does NOT get the same exemption, despite
#     also being seeded reference/config data — unlike fare_rules it has
#     a real `created_by` FK to admin.users, so it must clear before
#     admin.users (same reasoning as referral.driver_bonus_rules/
#     customer_reward_rules below), not because its own rows need
#     resetting.
#   ride.change_requests -> ride.rides, pricing.fare_quotes (both
#     old_fare_quote_id/new_fare_quote_id, both nullable) (added Ride
#     Modifications, ADR-0033, used by tests/test_pickup_change_api.py —
#     same class of gap again; see database-design.md §11.1). Must be
#     cleared before pricing.fare_quotes above, not merely before
#     ride.rides — it has FK edges to both.
#   notification.deliveries, notification.preferences have no foreign
#     keys to any user table (user_id is a bare UUID across both —
#     database-design.md §32.1/§32.2, same "no single users table"
#     reasoning penalty.penalties.user_id already established) — added
#     Notification Domain Foundation, ADR-0034, used by tests/
#     test_notification_service.py and the notification assertions in
#     tests/test_matching_api.py/test_ride_lifecycle_api.py. No ordering
#     constraint relative to the rest of the graph; listed early only for
#     readability, not correctness. notification.deliveries DOES now
#     have one real FK, though (template_version_id -> notification.
#     templates, added Notification Template Management, ADR-0044) — it
#     must clear before notification.templates, which is why
#     notification.templates is listed separately, much further down,
#     right before admin.users (same reasoning as
#     referral.driver_bonus_rules/customer_reward_rules below).
#   notification.templates -> admin.users (added Notification Template
#     Management, ADR-0044 — same class of gap again; must clear before
#     admin.users, and after notification.deliveries above).
#   safety.events -> safety.incidents -> ride.rides (nullable); support.
#     messages -> support.cases -> ride.rides (nullable) (added Phase 14
#     / Safety & Support, ADR-0022 — same class of gap again; see
#     database-design.md §28/§30)
#   admin.settings -> admin.users (added Admin Settings, ADR-0048 — same
#     class of gap again: a real `updated_by` FK to admin.users, so it
#     must clear before admin.users, same reasoning as pricing.
#     platform_fee_rules above). Unlike every other config table listed
#     here, admin.settings has NO Create endpoint at all (ADR-0048
#     Decision 3: closed vocabulary, PATCH-only) — so once this DELETE
#     wipes its two seeded rows, no test can bring them back on its
#     own the way a platform-fee-rule test creates a fresh row for
#     itself. truncate_integration_tables() therefore re-inserts the
#     seeded baseline immediately after the DELETE loop below (see
#     `_reseed_admin_settings_baseline()`) instead of leaving the table
#     empty for the rest of the session.
#
# Cleared with DELETE, not TRUNCATE: Postgres's TRUNCATE refuses to
# truncate a table that *any* other table has a live FK constraint
# pointing to, even an already-empty one — truncating "cases"
# individually fails as long as "evidence"/"results" merely reference
# it, regardless of row order. DELETE enforces referential integrity at
# the row level instead, so deleting child rows before parent rows (this
# order) never hits that restriction. These tables use UUID primary
# keys, so there's no sequence to reset either way.
_CLEAR_ORDER: tuple[str, ...] = (
    "shared.outbox_events",
    "notification.deliveries",
    "notification.preferences",
    "admin.audit_logs",
    "admin.permissions",
    "customer.preferences",
    "verification.evidence",
    "verification.results",
    "verification.cases",
    "driver.documents",
    "vehicle.documents",
    "matching.ride_offers",
    "wallet.transactions",
    "penalty.penalties",
    "penalty.strikes",
    "advertisement.payouts",
    "advertisement.driver_campaigns",
    "advertisement.campaigns",
    "referral.rewards",
    "referral.referrals",
    "referral.codes",
    "promotion.usage",
    "promotion.reservations",
    "ride.change_requests",
    "pricing.fare_quotes",
    "safety.events",
    "safety.incidents",
    "support.messages",
    "support.cases",
    "ride.state_history",
    "ride.gps_dispute_evidence",
    "ride.gps_disputes",
    "ride.gps_verifications",
    "ride.ride_otps",
    "ride.early_drop_requests",
    "ride.rides",
    "vehicle.vehicles",
    "wallet.wallets",
    "promotion.entitlements",
    "promotion.campaign_eligible_customers",
    "promotion.campaigns",
    "referral.driver_bonus_rules",
    "referral.customer_reward_rules",
    "notification.templates",
    "notification.broadcasts",
    "pricing.platform_fee_rules",
    "admin.settings",
    "admin.users",
    "customer.customers",
    "driver.drivers",
    "identity.sessions",
    "identity.otp_challenges",
    "identity.mfa_credentials",
    "identity.accounts",
)


_SETTINGS_SEED = {
    "welcome_discount_percent": (
        "50",
        "PROMOTION_DEFAULT",
        "Discount percentage applied by the welcome coupon granted to "
        "a newly registered customer.",
    ),
    "welcome_total_uses": (
        "3",
        "PROMOTION_DEFAULT",
        "Number of times the welcome coupon entitlement may be "
        "redeemed before it is exhausted.",
    ),
}


def _reseed_admin_settings_baseline(conn: sqlalchemy.engine.Connection) -> None:
    """Re-inserts the two admin.settings rows migration f2c6a819e3b4
    seeds (ADR-0048). Unlike referral.driver_bonus_rules/
    customer_reward_rules/pricing.platform_fee_rules — which get a
    fresh row from their own Create endpoint whenever a test needs
    one — admin.settings has no Create endpoint at all (ADR-0048
    Decision 3: closed vocabulary, PATCH-only): once DELETE FROM
    admin.settings runs above, the only way these two keys come back
    is if this function puts them back, so it must. Reuses the same
    synthetic-system-admin fallback the migration itself uses, since
    the DELETE loop above also just cleared admin.users."""
    admin_id = conn.execute(
        text("SELECT id FROM admin.users WHERE role = 'SUPER_ADMIN' LIMIT 1")
    ).scalar()
    if admin_id is None:
        system_account_id = "00000000-0000-0000-0000-000000000001"
        conn.execute(
            text(
                "INSERT INTO identity.accounts (id, account_type, phone, status) "
                "VALUES (:id, 'ADMIN', '+910000000001', 'ACTIVE') "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"id": system_account_id},
        )
        conn.execute(
            text(
                "INSERT INTO admin.users (id, role, status) "
                "VALUES (:id, 'SUPER_ADMIN', 'ACTIVE') "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"id": system_account_id},
        )
        admin_id = system_account_id

    for key, (value, category, description) in _SETTINGS_SEED.items():
        conn.execute(
            text(
                "INSERT INTO admin.settings "
                "(key, value, category, description, updated_by) "
                "VALUES (:key, CAST(:value AS jsonb), :category, "
                ":description, :admin_id) "
                "ON CONFLICT (key) DO NOTHING"
            ),
            {
                "key": key,
                "value": value,
                "category": category,
                "description": description,
                "admin_id": str(admin_id),
            },
        )


def truncate_integration_tables(engine: Engine) -> None:
    """Wipes every table the driver/vehicle-document and verification
    integration tests touch, in FK-safe order. Called before each test
    function in those two files only (see their local
    `_clean_integration_tables` autouse fixture) — not applied
    suite-wide, and not a transaction/savepoint rollback scheme."""
    with engine.connect() as conn:
        for table in _CLEAR_ORDER:
            conn.execute(text(f"DELETE FROM {table}"))
        _reseed_admin_settings_baseline(conn)
        conn.commit()
