ADR-0004 — Driver Profile Creation Semantics

Status: Accepted (implementation/API behavior — not a business-rule decision)
Date recorded: 2026-08-21
Deciders: Recorded from repository evidence during the Phase 2 / Task 2.3
follow-up (Driver Profile Design Clarification). Formalizes a design
decision already implemented in Task 2.3, per that task's own flagged
"Unresolved decisions" item.

1. Problem

`apps/backend/src/modules/customer/` (Task 2.2) auto-provisions a
`customer.customers` row on first access by either `GET` or `PATCH
/api/v1/customers/me`, because `customer.customers.full_name` is
nullable — a sensible empty profile can exist before the customer ever
sets a name.

`driver.drivers.full_name` is `NOT NULL`
([database-design.md §7.1](../04-database/database-design.md)). There is
no column anywhere the driver's name could default from —
`identity.accounts` ([database-design.md §5.1](../04-database/database-design.md))
only carries `phone`, `account_type`, and `status`. Auto-provisioning a
driver profile the same way Customer does would require inventing a
placeholder name, which this project's governance rules
([business-rules.md §44](../02-business/business-rules.md)) do not permit.

2. Documentation reviewed for an existing answer

- [api-contracts.md §9](../05-api/api-contracts.md) documents only `GET
  /api/v1/drivers/me` and `PATCH /api/v1/drivers/me` (plus `POST
  .../documents`, out of scope for Task 2.3). No `POST /api/v1/drivers`
  registration endpoint, and no description of create-vs-update
  semantics for either documented endpoint.
- [database-design.md §7.1](../04-database/database-design.md) defines
  the `NOT NULL` constraint but says nothing about how the row comes
  into being.
- [PRD.md §9](../01-product/PRD.md) and
  [business-rules.md BR-098](../02-business/business-rules.md) describe
  driver onboarding as a sequence — "Registered → Documents submitted →
  Verified → Approved" — at the product/business level, but neither
  specifies an API shape for the "Registered" step.
- [implementation-readiness.md](../11-implementation/implementation-readiness.md)
  has no "Driver Module" architecture section (unlike Ride, Matching,
  Wallet, etc.) that might have specified this.

None of these documents define an alternative creation flow. This ADR
therefore does not invent one — it records the interpretation already
required by the `NOT NULL` constraint, using only the two endpoints that
are actually documented.

3. Decision

- `GET /api/v1/drivers/me` does **not** auto-provision. If no
  `driver.drivers` row exists yet for the authenticated driver account,
  it returns `RESOURCE_NOT_FOUND`.
- `PATCH /api/v1/drivers/me` creates the profile on the first call for a
  given driver account, but only when `full_name` is present in that
  call. If the profile does not yet exist and `full_name` is absent, it
  returns `VALIDATION_FAILED` rather than creating a half-populated row.
- Once a profile exists, `PATCH` behaves as an ordinary partial update
  (`full_name`/`profile_photo_uri` optional, PATCH semantics), identical
  in shape to Customer's update endpoint.

This avoids ever writing a `NULL`/placeholder value into a `NOT NULL`
column, without adding any endpoint, field, or business rule that isn't
already implied by the documented schema constraint plus the two
documented endpoints.

4. Status of this decision

This is an **implementation/API behavior decision**, not a newly invented
business rule. It does not change what data VISTAAR collects, what a
driver must provide, or any approval/verification rule — it only decides
the mechanics of *when* the already-required `full_name` field must be
supplied relative to the two already-documented endpoints.

5. Consequences

- [api-contracts.md §9](../05-api/api-contracts.md) has been updated (in
  the same change as this ADR) to state this behavior explicitly and
  point back here, so it is no longer only inferable from code comments.
- A future dedicated registration endpoint (e.g., a `POST
  /api/v1/drivers` that captures `full_name` alongside other onboarding
  data in one call) is not precluded by this decision, but would require
  its own explicit API decision/documentation update — this ADR does not
  reserve or imply that shape.
- If `driver.drivers.full_name` is ever relaxed to nullable (a database
  schema change, not something this ADR does), this decision should be
  revisited — the constraint driving it would no longer exist.
