ADR-0040 — Admin Permission Model

Status: Implemented (2026-08-26, following the owner's "continue" after
this design was reviewed — the earlier "DO NOT IMPLEMENT YET"
instruction was scoped to the Admin Web frontend plan specifically, not
this backend design once separately confirmed).

Implementation note: `require_permission()` (Decision 4) ended up as a
plain `AdminService` method called from inside each route's own try
block — not a separate FastAPI `Depends()` chain as originally sketched
below. This matches the existing router's own convention for every
other DB-backed authorization check (`require_active_admin()` was
already built the same way) more closely than a new dependency-
injection pattern would have; the effect (server-side enforcement on
every request) is identical. Migration `5150fb4352b4`; 46 new tests
across the domain, service, and real-Postgres API integration layers,
including dedicated permission-enforcement cases (an employee admin
with no grant gets a real 403, VIEW doesn't satisfy MANAGE, etc.) — see
the roadmap's own checkpoint for the exact before/after count.

Date recorded: 2026-08-26.
Deciders: Project owner (Super Admin + granular permissions, no fixed
roles — resolving business-rules.md §43's "Admin roles"/"Permission
hierarchy" TBD markers, see BR-126/BR-127). The specific schema/
endpoint shape below is this task's own engineering-judgment proposal,
not yet owner-approved — flagged as such throughout.

1. Context

`admin.users` currently has `{id, role, status}`, where `role` has only
ever held the literal string `"ADMIN"` — there is no permission
granularity, no Super Admin concept, and no way to create an admin
account except `scripts/provision_admin.py`, an ops-only script with no
HTTP endpoint at all (ADR-0009 point B, by deliberate design — "who is
allowed to grant admin status" was exactly the unresolved question).
BR-126/BR-127 now answer that question; this ADR designs the schema and
endpoints it implies.

2. Decision 1 — `admin.users.role` becomes `'SUPER_ADMIN' | 'ADMIN'`,
   no new column

`role` is already a free-text VARCHAR(40) with no enum/CHECK constraint
(database-design.md §33.1) — reused rather than adding a parallel
column. `'SUPER_ADMIN'` marks the one-or-more core-team accounts
BR-126 describes; every other admin account is `'ADMIN'` (an "employee
admin" in BR-126's terms) and has its access controlled entirely by the
new `admin.permissions` table below. A Super Admin implicitly has full
access to every module — no `admin.permissions` rows are written for a
Super Admin account, matching this codebase's existing "don't write
rows that would always evaluate to the same default" restraint.

3. Decision 2 — `admin.permissions`, one row per (admin, module) an
   employee admin has some access to

```
CREATE TABLE admin.permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_id UUID NOT NULL REFERENCES admin.users(id),
    module VARCHAR(40) NOT NULL,
    access_level VARCHAR(10) NOT NULL,  -- 'VIEW' | 'MANAGE'
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_admin_permissions_admin_module
ON admin.permissions(admin_id, module);
```

Absence of a row for a given `(admin_id, module)` means no access — a
Super Admin granting access writes a row; revoking deletes it (or
lowers `access_level`), matching this codebase's existing preference
for "state is what's present" over a tri-state NONE/VIEW/MANAGE enum
value written for the common no-access case.

`module` is a plain string, not an enum with a DB constraint — the same
"no source document enumerates the full value set as a closed list, so
don't over-constrain it" reasoning `admin.users.role` itself already
uses (domain/entities.py's own docstring). The catalog is fixed at the
application layer instead: the 20 modules BR-126 names, exactly
matching the Admin Web's own navigation, defined once as a Python
`StrEnum` (`modules/admin/domain/entities.py`) both the permission-check
dependency and the admin-management endpoints import — one source of
truth, not duplicated between backend validation and frontend nav.

`access_level`: `VIEW` (read-only) or `MANAGE` (read + that module's own
mutating actions — e.g. MANAGE on Penalties/Strikes covers Resolve
Penalty, MANAGE on Fare Management covers publishing a new fare
version). This two-level granularity is proposed as a starting point,
not a ceiling — BR-126 itself notes finer per-action permissions can be
added later without a breaking schema change (a third `access_level`
value, or a second table keyed the same way, both fit without touching
existing rows).

"Admin Management" and "Settings" are never grantable via this table —
BR-126's own rule, enforced by the permission-check dependency (Decision
4) refusing to grant/check those two modules for anyone but a Super
Admin, not by a database constraint (consistent with `module` staying
an unconstrained string).

4. Decision 3 — New endpoints, Super-Admin-only

```
POST   /api/v1/admin/admins                      Create employee admin
GET    /api/v1/admin/admins                       List employee admins
GET    /api/v1/admin/admins/{admin_id}             Get one (incl. permissions)
PATCH  /api/v1/admin/admins/{admin_id}/permissions  Replace permission set
POST   /api/v1/admin/admins/{admin_id}/disable      Disable
POST   /api/v1/admin/admins/{admin_id}/enable       Re-enable
```

None of these are documented anywhere in api-contracts.md today — this
is the same "new public API contract" §0.3 stop condition this codebase
has hit repeatedly (Advertisement, Driver Suspension, Notification) —
flagged here rather than invented silently; api-contracts.md needs a
real new section for these before implementation, mirroring the shape
above. `Create employee admin` takes a phone number (reusing
`modules.identity`'s existing `AccountType.ADMIN` account-creation path,
the same one `scripts/provision_admin.py` already uses — no new
account-creation code) plus an initial permission list; the created
account still authenticates through the ordinary phone+OTP flow, same
as `provision_admin.py`'s own script does today, no credential
generated or emailed.

5. Decision 4 — Server-side enforcement: a new `require_permission()`
   dependency, `require_admin` kept for authentication only

`require_admin` (modules/identity/dependencies.py) stays exactly what
it is today — "is this an authenticated ADMIN-type account" — and
remains the first check on every admin route (unchanged). A new
`require_permission(module: AdminModule, level: AccessLevel)`
dependency factory is added alongside it: a Super Admin passes
automatically; an employee admin's `admin.permissions` row for that
module must exist and be at least the required level, or the request
gets `403 FORBIDDEN` — the same IDOR-safe-adjacent "authorization
enforced server-side, not just hidden in the frontend nav" principle
security.md §7 already states as a general rule. Every existing admin
route (Driver Review, Approve/Reject Driver/Vehicle, Search Rides,
Resolve Penalty, etc.) gets a `require_permission()` call added for its
own module — a mechanical follow-up once this design is approved, not
a redesign of any of those routes' own logic.

6. Decision 5 — Bootstrapping stays an ops script, not an endpoint

The very first Super Admin for a given environment has no account yet
to call the new endpoints with — `scripts/provision_admin.py` is
extended with a `--role super_admin|admin` flag (default `admin`,
matching its current behavior exactly for anyone not passing the new
flag) rather than replaced. This is BR-127's own rule: bootstrapping
requires deployment/infrastructure access, the same trust level
`alembic upgrade head` already requires — never a public or
authenticated-but-self-service HTTP path.

7. Explicitly out of scope for this ADR

- Escalation rules / fraud investigation workflow — business-rules.md
  §43 still marks both genuinely TBD; BR-126/BR-127 do not address
  them, and neither does this ADR.
- Finer-than-VIEW/MANAGE per-action permissions — noted as a compatible
  future extension (Decision 3), not built now.
- The actual migration, model, repository, service, and router code —
  this ADR is the design; implementation is a separate task once
  reviewed, per the owner's explicit instruction.
