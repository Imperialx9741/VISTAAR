ADR-0009 — Admin Approval Scope and Open Items

Status: Points A, B, and C Accepted (approved business/architecture
decisions; point C via business-rules.md BR-123, added 2026-08-21, and
enforced in code by Phase 2 / Task 2.6C — see §3.C). The two
documentation conflicts in §2 remain Decision required — NOT decided by
this record.
Date recorded: 2026-08-21 (point C updated 2026-08-21, Task 2.6C)
Deciders: Approved via the "VISTAAR — Phase 2 / Task 2.7A — Admin
Foundation & Approval" planning and decision-resolution exchange,
resolving several of the open questions that task's research surfaced.
This record itself implements no code, schema, or provider integration —
see §5.

1. Context

Tasks 2.3, 2.4, and 2.6 each explicitly deferred admin approval of
drivers/vehicles as "Admin domain, later task." Researching Task 2.7A
found the `admin` domain/schema fully specified
([database-design.md §33](../04-database/database-design.md),
`admin.users`/`admin.audit_logs`) and exactly 3 admin routes documented
([api-contracts.md §46](../05-api/api-contracts.md)): Driver Review
(GET), Approve Driver (POST), Approve Vehicle (POST). Several integration
and scope questions were not resolved by that documentation alone:

- Should Reject Driver/Reject Vehicle get HTTP endpoints, given
  `RejectDriver`/`RejectVehicle` are documented domain commands
  ([domain-design.md §7.4/§8.3](../04-domain-design/domain-design.md))
  but no API route for either is documented anywhere?
- How does the first (or any) `admin.users` row come to exist, given no
  admin-registration endpoint is documented anywhere?
- Must a driver's/vehicle's documents or verification cases reach some
  approved/valid state before admin approval is allowed?

Two genuine documentation conflicts were also found along the way (§2).

2. Documentation conflicts found (Decision required — NOT decided)

**Conflict 1 — Admin role taxonomy.**
[security.md §7](../08-security/security.md) states "Supported roles
include: CUSTOMER, DRIVER, ADMIN, SAFETY_ADMIN, FINANCE_ADMIN,
SUPER_ADMIN" — concrete role names.
[business-rules.md §43](../02-business/business-rules.md) ("Items Still
TBD") lists "Admin roles," "Permission hierarchy," and "Escalation
rules" as explicitly unfinalized. These conflict on whether the admin
role taxonomy is actually settled. **Not resolved by this ADR.** Task
2.7A's implementation works around it rather than resolving it: it only
ever uses the one role name both documents implicitly agree exists and
that task actually needs — `"ADMIN"` — and builds no
SAFETY_ADMIN/FINANCE_ADMIN/SUPER_ADMIN-differentiated authorization.

**Conflict 2 — Audit field list vs. actual audit table schema.**
[security.md §46](../08-security/security.md) ("Audit Log Fields") lists
`actor_role` and `ip_address` as minimum fields. The actual documented
`admin.audit_logs` schema
([database-design.md §33.2](../04-database/database-design.md)) has
neither column. **Not resolved by this ADR.** Task 2.7A's implementation
builds `admin.audit_logs` exactly as §33.2 specifies — no `actor_role`,
no `ip_address` — rather than inventing columns to satisfy security.md's
list.

Minor, non-blocking note: security.md §45's "Audit Logging" required-
actions list names "Vehicle approval" and "Document approval" but not
"Driver approval." api-contracts.md §46's blanket "every admin mutation
creates an audit log" is treated as the controlling rule for Task 2.7A —
both Approve Driver and Approve Vehicle (and their new Reject
counterparts, point A) are audited.

3. Decisions

**A. Reject Driver / Reject Vehicle HTTP endpoints (Accepted).**
`POST /api/v1/admin/drivers/{driver_id}/reject` and
`POST /api/v1/admin/vehicles/{vehicle_id}/reject` are added to the
documented contract as an explicit Task 2.7A addition — the same
"flag the gap, propose the minimum addition, get explicit approval"
precedent already used for vehicle GET-single/PATCH
([ADR-0006](ADR-0006-vehicle-lifecycle-single-active-vehicle.md) §5) and
driver document endpoints
([ADR-0007](ADR-0007-document-type-and-endpoint-scope.md)). Both use the
existing `DriverService.reject_driver()`/`VehicleService.reject_vehicle()`
logic (mirroring `approve_driver()`/`approve_vehicle()`'s shape exactly),
require an active admin via the same authorization gate as approval, and
create the same transactional audit record shape as approval — `reason`
populated instead of null, no field invented beyond what
`admin.audit_logs.reason` already documents. `api-contracts.md` §46 is
updated accordingly (this record's companion documentation change).

**B. Admin bootstrap mechanism (Accepted).** No public admin-registration
HTTP endpoint is built, ever — self-service registration as `ADMIN` is
explicitly rejected as a design. Instead, initial (and any subsequent)
`admin.users` provisioning happens via a standalone, ops-only script
(`apps/backend/scripts/provision_admin.py`, built as part of Task 2.7A's
implementation) run directly against the database by someone who already
holds deployment/infrastructure access — the same trust level already
required to run `alembic upgrade head` or exec into the Postgres
container. No new privilege boundary is invented. The script creates (or
reuses) the target `identity.accounts` row with `account_type=ADMIN`
using the existing identity repository — no new account-creation code —
then inserts one `admin.users` row (`role="ADMIN"`, `status="ACTIVE"`).
It generates, prints, or hard-codes no credential — the resulting account
still authenticates through the existing OTP flow like any other
account; the script only grants the `admin.users` record itself. Who is
authorized to *run* the script is an organizational/process decision
outside this codebase's scope, same as who is authorized to run existing
deployment/migration commands today — this ADR does not attempt to
answer that.

**C. Document/verification-case gate on approval (Accepted — resolved by
business-rules.md BR-123).** This was genuinely unresolved when this ADR
was first recorded — no source document stated it either way, and per
[ADR-0008](ADR-0008-verification-case-scope-and-open-items.md) items 5/9,
`verification.cases.status`, `driver.documents`/`vehicle.documents.verification_status`,
and `driver.drivers`/`vehicle.vehicles.verification_status` were already
three independent, unreconciled status systems, so adding a gate here
would have meant inventing a fourth relationship without authorization.
An explicit business decision has since been made and recorded as
**BR-123 — Document/Verification Gate on Admin Approval**: an admin must
not approve a driver or vehicle while any required document or
verification case for that driver/vehicle is `PENDING`, `REJECTED`,
`EXPIRED`, or otherwise not in an approved/valid state.

This resolves the *yes/no* gate question. Task 2.6B built the lifecycle
mechanism (`CompleteManualReview` → write-back — see ADR-0008 item 5,
updated), and **Task 2.6C wires BR-123's check into
`DriverService.approve_driver()`/`VehicleService.approve_vehicle()`
directly** (`modules.driver.domain.required_documents`/
`modules.vehicle.domain.required_documents`) — approval is now rejected
(reusing the existing `DRIVER_NOT_ELIGIBLE`/`VEHICLE_NOT_ELIGIBLE`
codes) if any required document is missing, or present but not
`APPROVED` and unexpired. Rejecting a driver/vehicle is not gated.

Still unresolved:
- **Automatic triggering of the document-approval mechanism itself** —
  no HTTP endpoint or scheduled trigger calls
  `complete_manual_review()`/`apply_verification_outcome()`; today only
  tests exercise it. Whether/how an admin-facing surface should trigger
  it remains undecided — this is a separate question from BR-123's gate
  being enforced (which it now is); it's about how a document *reaches*
  `APPROVED` in the first place.
- **The required-document list's final ratification** —
  business-rules.md §43 still marks "Final KYC document list" as
  provisional. Task 2.6C's enforced set (Government ID, Driving Licence;
  RC, Insurance — Vehicle Photo deliberately excluded, see business-rules.md
  BR-123) is the working set, carrying the same "subject to final
  compliance review" caveat BR-097 itself states.

4. What this ADR does NOT do

- Does not create the `admin` PostgreSQL schema, any migration, the
  `modules/admin/` module, or `scripts/provision_admin.py` — those
  remain a separate, not-yet-implemented step per the approved Task 2.7A
  plan.
- Does not resolve conflict 1 (role taxonomy) or conflict 2 (audit field
  list).
- Point C's *rule* is resolved (BR-123) and its code enforcement has
  since been added by Phase 2 / Task 2.6C — this ADR record itself
  implements neither; both were done by the tasks referenced. The
  document-verification lifecycle mechanism (Task 2.6B) and the
  required-document list's final regulatory ratification remain as
  described above.
- Does not integrate any external provider or request any API key.
- Does not modify `driver.drivers`/`vehicle.vehicles`/document/
  verification tables.

5. Consequences

- Task 2.7A's implementation can proceed against points A and B without
  re-litigating them: 5 admin routes (Driver Review, Approve/Reject
  Driver, Approve/Reject Vehicle), the `admin` schema exactly as
  database-design.md §33 specifies, and the ops-only provisioning script.
- Point C's rule is now settled (BR-123); enforcing it requires Task
  2.6B (document verification lifecycle: `CompleteManualReview`, the
  write-back between `verification.cases.status` and
  `driver.documents`/`vehicle.documents.verification_status`, and the
  `all_required_documents_approved()` check called from
  `approve_driver()`/`approve_vehicle()`) — planned, not yet
  implemented or authorized.
- Conflict 1 and conflict 2 remain open. Closing conflict 1 requires an
  explicit business-rules.md decision finalizing (or formally deferring)
  the admin role taxonomy and permission hierarchy. Closing conflict 2
  requires either updating security.md §46's field list to match the
  actual schema, or an explicit database-design.md change adding
  `actor_role`/`ip_address` to `admin.audit_logs`.
- Any future task touching admin roles/permissions, audit log fields, or
  the approval/verification relationship should link back to this ADR
  rather than re-deciding ad hoc.

Conflict 1 RESOLVED (2026-08-26): BR-126/BR-127 finalize the admin role
taxonomy (Super Admin + granular per-module permissions on employee
ADMIN accounts, no fixed role enum) and the permission hierarchy (Super
Admin sole authority, enforced server-side). See ADR-0040 for the
schema/endpoint design. Conflict 2 (audit field mismatch) remains open —
untouched by this resolution.
