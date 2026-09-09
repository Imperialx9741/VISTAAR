ADR-0018 — Advertisement Domain Scope and Open Items

Status: Decision 1 Accepted. Items 2-3 explicitly deferred, not decided
here.
Date recorded: 2026-08-24
Deciders: Approved under the owner's phase-level autonomy grant (VISTAAR
session, 2026-08-24) — mandatory stop conditions (roadmap §0.3/§0.4)
still apply and are respected below where they genuinely bite.

1. Context

Phase 17 — Advertisements (8 roadmap tasks) was assessed in
VISTAAR_AUTONOMOUS_EXECUTION_PLAN.md as "fully completable using
patterns already established elsewhere." Building it surfaced two gaps
that assessment missed: `api-contracts.md` documents zero Advertisement
endpoints anywhere (no path, no request/response shape — unlike every
other module built so far, which had at least a documented endpoint to
implement against), and technical-architecture.md §55 names a specific
external verification partner, Admoto, with no credentials, onboarding
process, or approval recorded anywhere. Domain-design.md §22 and
database-design.md §31, by contrast, are fully specified — commands,
schema, and the exact 80/20 payout split are all documented and
unambiguous.

2. Decision 1 — Build the domain/service/repository layer in full;
   do not build a router or integrate Admoto

The commands domain-design.md §22.3 documents (CreateCampaign,
AssignDriver, SubmitInstallationProof, VerifyAdvertisement,
CalculatePayout, SettlePayout) and the schema database-design.md §31
documents are both unambiguous enough to implement completely as a
domain/service/repository module — the same layering every other
module in this codebase uses — with real fake-based and real-Postgres
integration test coverage. What's deliberately NOT built:

- An HTTP router. No endpoint path or request/response shape is
  documented anywhere for Advertisement — inventing one would be
  exactly the "new public API contract" §0.3 flags as a mandatory stop
  condition. Unlike every prior task (which had at least a path and a
  body shape to implement against, even when a response example was
  missing), there is nothing here to implement against without
  inventing it outright.
- Admoto integration. technical-architecture.md §55 names it as the
  verification partner, but no requirement/candidate list/credential
  plan/data-exchange documentation exists (§0.4's required steps before
  integrating any external provider). `VerifyAdvertisement` is
  implemented instead as a manual admin decision (approve/reject) —
  the same treatment this codebase already gives document verification
  everywhere else (driver/vehicle documents are approved/rejected by an
  admin action today; AI/OCR and equivalent automated verification are
  consistently deferred external-provider decisions throughout this
  project, not just here).
- Wiring `WalletService.credit()` (ADVERTISEMENT_PAYOUT, already in the
  transaction-type enum) and outbox event publication
  (`advertisement.campaign_assigned`/`verified`/`payout_issued`,
  event-contracts.md §24) into a live composition — both are the
  router/composition layer's job in this codebase's established
  architecture (e.g. modules/ride/router.py composing wallet + penalty
  for cancellation), and there is no router yet to put that composition
  in. Proven instead by one integration test that manually performs the
  same sequence a future router would (`calculate_payout()` →
  `WalletService.credit()` → `mark_payout_paid()`), documented as
  exactly that — a demonstration of the intended composition, not a
  permanent part of this module.

3. Decision 2 — Campaign/driver-campaign status values are an
   engineering completion, not an invented business rule

Neither document enumerates the full set of values `campaigns.status`,
`driver_campaigns.status`, or `driver_campaigns.verification_status`
may take (database-design.md §31 gives only `driver_campaigns.status`'s
default, `'ASSIGNED'`). This mirrors the same "no canonical enum
documented" situation already handled elsewhere in this codebase (e.g.
`modules.ride.domain.entities.validate_cancellation_reason` — only
shape is validated, no enum invented) — but here a state machine is
unavoidable, since the six documented commands imply an ordering
(assign → prove → verify → calculate → settle). The values chosen:
`campaigns.status`: `ACTIVE` (a campaign is immediately usable once
created — nothing documents a draft/approval step before that).
`driver_campaigns.status`: `ASSIGNED → PROOF_SUBMITTED → VERIFIED |
REJECTED → PAID`. `driver_campaigns.verification_status`:
`PENDING | APPROVED | REJECTED` — reused verbatim from
`driver.documents`/`vehicle.documents`' own verification_status values
already established in this codebase, for consistency rather than
inventing a parallel vocabulary. `payouts.status`: `PENDING → PAID`
(matches database-design.md's own documented default and the roadmap's
own task names, "Payout pending"/"Payout processing").

4. Item 2 — The HTTP API contract: deferred, not decided here

A future task needs to specify: which endpoints exist (admin-only
campaign/assignment management? a driver-facing "my campaigns"/proof-
upload surface? both?), their request/response shapes, and error codes
— genuinely a product/API design decision, not something this ADR can
resolve on engineering judgment alone.

5. Item 3 — Admoto (or any) external verification provider: deferred,
   not decided here

Per §0.4: identify the exact requirement, list candidate providers
(Admoto is named, but not confirmed as selected/approved — it appears
only in technical-architecture.md's narrative, not the Decision
Register or Business Rules), identify credentials, document data
exchanged, record the selection in an ADR, then integrate. None of
that has happened yet.

6. Consequences — documents updated alongside this ADR

- `docs/VISTAAR_IMPLEMENTATION_ROADMAP.md` updated: this task marked
  complete for the scope above, with Items 2-3 recorded as the
  reasons the remaining roadmap tasks (which presuppose an HTTP surface
  and/or Admoto) are not done.
- `docs/VISTAAR_AUTONOMOUS_EXECUTION_PLAN.md` corrected: Phase 17 was
  assessed as fully completable; it is not, for the reasons in §1.
- No content changed in `business-rules.md`, `domain-design.md`,
  `event-contracts.md`, `state-machines.md`, or `database-design.md` —
  the domain/schema built matches what's documented exactly; the status
  vocabulary added (Decision 2) is a completion, not a change, of an
  already-implied state machine.
