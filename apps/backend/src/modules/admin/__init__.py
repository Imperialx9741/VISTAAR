"""VISTAAR Admin module — Admin Foundation & Driver/Vehicle Approval
(Phase 2 / Task 2.7A).

Owns admin identity/authorization records and the administrative audit
trail, per docs/03-architecture/technical-architecture.md §4 (domain #17
of 18) and docs/04-database/database-design.md §3 (`admin` schema) / §33
(Admin Tables). Does NOT own driver/vehicle approval itself —
`ApproveDriver`/`RejectDriver` (domain-design.md §7.4) and
`ApproveVehicle`/`RejectVehicle` (§8.3) are Driver-domain and
Vehicle-domain commands respectively, implemented in
`modules/driver/service.py` and `modules/vehicle/service.py`. This
module's router composes with those (and with modules.identity for phone
display, modules.verification for document review visibility) at the API
layer only — same pattern used throughout this codebase.

See docs/14-decisions/ADR-0009-admin-approval-scope-and-open-items.md and
docs/14-decisions/ADR-0040-admin-permission-model.md for the design
decisions this module implements. Summary:

- `require_admin` (modules.identity, Task 2.1) gates account-type access;
  `AdminService.require_permission()` additionally requires a real,
  `ACTIVE` `admin.users` row, and — for an employee (non-Super-Admin)
  account — a matching `admin.permissions` row at the required access
  level (ADR-0040/BR-126/BR-127, 2026-08-26). `require_active_admin()`
  (the active-status check alone, no module/level) still exists for the
  one route that needs it without a specific module — Get My Admin
  Profile (`GET /api/v1/admin/me`).
- Two admin roles now (`admin.users.role`, still a plain VARCHAR — see
  below): `SUPER_ADMIN` (implicit full access to every module, no
  `admin.permissions` rows ever written) and `ADMIN` (an "employee
  admin," access entirely determined by their own permission rows).
  `ADMIN_MANAGEMENT`/`SETTINGS` module access is never grantable to an
  employee admin — BR-126's own rule.
- No self-service registration HTTP endpoint for the *Super Admin*
  level, ever (BR-127) — `admin.users` rows with `role=SUPER_ADMIN` are
  provisioned exclusively via `apps/backend/scripts/provision_admin.py
  --role super_admin`, an ops-only script run directly against the
  database by someone who already holds deployment/infrastructure
  access — the same trust level already required to run `alembic
  upgrade head`. No credential is generated, printed, or hard-coded by
  the script; the resulting account still authenticates through the
  existing OTP flow. *Employee* admins, by contrast, now have a real
  HTTP endpoint (`POST /api/v1/admin/admins`, Super-Admin-only) —
  BR-126/BR-127 resolved the "who is allowed to grant admin status"
  question ADR-0009 originally left unresolved.
- `admin.users.role`/`.status` are plain strings, never a DB-level
  CHECK-constrained enum — `security.md` §7's original fixed-role
  example list (SAFETY_ADMIN/FINANCE_ADMIN/SUPER_ADMIN-as-account-
  types) is now formally superseded by BR-126's actual answer (one
  Super Admin level + granular per-module permissions, not a fixed role
  set); the closed set (`SUPER_ADMIN`/`ADMIN`) is enforced at the
  application layer (`domain/entities.py`'s `AdminRole`), same
  convention `status` already used before this ADR.
- `admin.audit_logs` is built exactly as database-design.md §33.2
  specifies — no `actor_role`/`ip_address` columns, despite security.md
  §46 listing them (ADR-0009 conflict 2). Every driver/vehicle approval
  or rejection writes one row, in the same DB transaction as the
  mutation itself (so a failed audit write rolls back the approval).
- Approval/rejection apply NO document/verification-case precondition —
  ADR-0009 point C records this as an explicitly unresolved business
  decision, not a silently-decided rule. Document/verification-case
  state is surfaced on Driver Review for display only.
- Approval never changes `operational_status` (driver stays `OFFLINE`,
  vehicle stays `INACTIVE`) — only `verification_status`.

Phase 16 (Admin, ADR-0023) extended this module's router with 5 more
routes, all read-only except one: Search Rides, Get Ride (admin), Admin
Wallet View (composing modules.ride/modules.pricing/modules.wallet the
same one-directional way Driver/Vehicle Review already compose
modules.driver/modules.vehicle), and Search Penalties / Resolve Penalty
(composing modules.penalty — the only one of the five that mutates and
is audited). See ADR-0023 for the full reasoning behind which of Phase
16's 17 roadmap-listed admin capabilities are/aren't buildable.

Explicitly out of scope for this module (do not extend without a new
task): Vehicle Review (GET), any pending-review list/search endpoint,
driver eligibility/Go-Online-Offline (Task 2.7B), driver suspension/
reactivation, matching, GPS, notifications, any external verification
provider, AI/OCR, WhatsApp/SMS, Kafka publishing of `driver.approved`/
`vehicle.approved` (event-contracts.md §19/§20 define the payloads;
publishing them is unused here, same precedent as Task 2.4's unpublished
`vehicle.*` events), Redis state, full Admin Web dashboard, Customer
management, Promotion/Referral administration, Dispute dashboard, GPS
evidence review, Pricing configuration, Safety/Support dashboards,
Advertisement management, Audit viewer, Payment monitoring, Settlements
— none of these has any documented HTTP shape anywhere in
api-contracts.md (ADR-0023 Decision 5).

Layering mirrors every other module:

    domain/         pure business logic — no FastAPI/SQLAlchemy imports
    ports.py        AdminRepository Protocol
    models.py       SQLAlchemy ORM models (infrastructure)
    repositories.py SQLAlchemy-backed implementation of the port
    service.py      application service (use cases)
    schemas.py      Pydantic request DTO
    dependencies.py FastAPI DI wiring (reuses modules.identity's
                    require_admin as-is — no new auth code here)
    router.py       FastAPI routes under /api/v1/admin
"""
