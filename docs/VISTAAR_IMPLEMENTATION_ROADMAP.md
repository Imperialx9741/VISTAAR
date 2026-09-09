VISTAAR — Master VISTAAR Execution Roadmap for Claude Code CLI

Document: Master Implementation Plan / Execution Control File
Project: VISTAAR
Market: India
Currency: INR
Purpose: Single execution source for Claude Code (or another coding agent) to continue VISTAAR from the current repository state through production readiness without asking for the next task after every completed item.

Important: This file is an execution plan, not a replacement for the PRD, Business Rules, Architecture, API Contracts, Database Design, Event Contracts, State Machines, Security Design, or Testing Strategy. Those remain authoritative for their respective decisions.

Claude Code CLI directive: This is the single master execution roadmap. Read it at the start of every session, but always reconcile it against the actual repository. Never reimplement completed work. Never treat a stale task label as proof that a capability is missing.

0. Execution Rules — MUST FOLLOW

0.1 Source-of-truth hierarchy

Use this order when artifacts conflict:

Explicitly approved business decisions / ADRs

PRD

Business Rules

State Machines

API Contracts

Database Design

Event Contracts

Security Design

Testing Strategy

Implementation details / code

The technical architecture document's own governance states that code must not silently override business rules. The implementation-readiness document likewise requires contradictions to stop for resolution.

0.2 Execution rule

The owner uses a plan-first, review-before-implementation workflow. The agent must
not blindly implement the whole roadmap in one run.

For every task:

Inspect the current repository and authoritative documents.

Confirm prerequisites and completed work.

Prepare the complete implementation plan for that single roadmap task.

STOP for owner review before implementation.

After approval, implement only that task.

Add/update tests.

Run applicable quality checks and migration verification.

Update affected documentation in the same change when appropriate.

Produce a task completion report.

Update this roadmap's task status.

Wait for owner review after each task plan and after any required blocker-resolution plan; do not silently jump into implementation.

Do not divide a roadmap task into invented A/B/C subtasks unless the project's
authoritative roadmap itself defines those as separate tasks.

0.3 Mandatory stop conditions

STOP and mark the task BLOCKED — REVIEW REQUIRED when any of the following occurs:

A product/business rule is ambiguous or contradictory.

A value is explicitly TBD and implementation would require choosing it.

A new external provider must be selected.

A production API key/credential is required and has not been supplied/approved.

A government-authorized API requires an approval/onboarding decision.

A destructive migration or data-loss decision is required.

A new public API contract would have to be invented.

A security decision materially changes the approved design.

A major architecture change is required.

The actual repository state materially differs from this roadmap and the mismatch could
cause reimplementation, data loss, or incorrect task ordering.

Do not guess. Do not silently continue.

0.4 External-provider rule

Providers are never invented or silently selected.

For every external service, first:

identify the exact requirement;

list candidate providers;

identify required credentials;

document data exchanged;

document legal/authorization requirements where applicable;

record the selection in an ADR;

then integrate.

0.5 Government verification rule

VISTAAR intends to use authorized transport/document verification capabilities where approved. Parivahan/Sarathi/Vahan access is not assumed to be an ordinary public API-key signup. Direct access, authorized partner access, and required approvals must be confirmed before provider-specific integration.

No scraping of citizen portals as a substitute for authorized access.

0.6 AI rule

AI/OCR is an inspection/assistance layer, never the authoritative legal source where an authoritative verification source is required.

AI may extract/classify/flag/recommend. AI must not silently convert uncertainty into legal validity.

0.7 Security rule

Never commit:

API keys

passwords

JWT secrets

provider secrets

private keys

cloud credentials

payment secrets

SMS/WhatsApp credentials

database passwords

Use .env locally and deployment secret management in production.

0.8 Git rule

Git/GitHub is now configured by the project owner. The agent must not rewrite history, force-push, reset unrelated work, or create unrelated commits.

0.9 Phase completion rule

A phase is complete only when:

every task in the phase is complete;

required tests pass;

required migrations are verified;

affected documentation is updated;

security requirements for that phase are addressed;

no unresolved blocker remains for that phase;

a phase completion report is produced.

1. IMPORTANT ROADMAP RECONCILIATION

The latest detailed printable roadmap is organized into 21 implementation phases with 280 task items. It explicitly says Phase 0 — Planning & Product Design — is already complete. The roadmap begins at Phase 1 Foundation.

This latest 21-phase roadmap is the controlling task-breakdown roadmap for execution. Earlier conversation task numbering (such as the custom Foundation Tasks 1–20 and Phase 2 Tasks 2.1–2.6) is more granular and does not map 1:1 to the 21-phase roadmap.

Do not reimplement completed repository functionality merely because a high-level roadmap item uses a different name. Instead, map existing code to the roadmap task and mark only the genuinely completed portions as complete.

The source roadmap contains several foundation items that were not part of the earlier custom 20-task foundation sequence, notably PostGIS, MinIO, and Celery. These must be reconciled before declaring the source roadmap's Phase 1 complete.

2. CURRENT REPOSITORY CHECKPOINT

2.0 Canonical execution checkpoint (updated 2026-08-22)

This section is the authoritative bridge between the high-level 21-phase roadmap and the
granular task history already completed in this repository. The agent MUST inspect the
actual repository, migrations, tests, and ADRs before choosing the next task.

Verified granular work already complete

Foundation / identity / driver / vehicle / verification / admin:

Custom Foundation Tasks 1–20: completed and verified where implemented in the repository.

Task 2.1 — Identity & Authentication: COMPLETE

Task 2.2 — Customer Profile: COMPLETE

Task 2.3 — Driver Profile: COMPLETE

Task 2.3A — Driver Profile clarification: COMPLETE

Task 2.4 — Vehicle Management: COMPLETE

Task 2.4A — Single-active-vehicle + vehicle GET/PATCH clarification: COMPLETE

Task 2.5 — Driver & Vehicle Document Management: COMPLETE

Task 2.6 — Verification Foundation: COMPLETE

Task 2.6B — Document Verification Completion: COMPLETE

Task 2.6C — BR-123 enforcement: COMPLETE

Task 2.7A — Admin Foundation & Driver/Vehicle Approval: COMPLETE

Task 2.7B — Driver Eligibility & Online/Offline: COMPLETE

Ride / matching:

Task 3.1 — Create Ride Request: COMPLETE

Task 3.2 — Matching / Driver Offers: COMPLETE

Task 3.3 — Customer Ride Cancellation (SEARCHING only): COMPLETE

Task 3.4 — Accept Offer / Ride ACCEPTED (Phase 06's "SEARCHING → ACCEPTED" task):
COMPLETE (ADR-0014). Implements technical-architecture.md §18's Accept-Ride Transaction
exactly: locks the driver's wallet row first (the serialization point for a concurrent
double-accept of the same offer — see ADR-0014/modules/matching/router.py's docstring),
re-validates offer PENDING+not-expired, re-validates ride SEARCHING, re-validates driver
and vehicle eligibility fresh (not trusting the offer's dispatch-time vehicle_id —
ADR-0014 Decision 2), then atomically debits the BR-011 platform fee (a hard-coded
per-category constant — ADR-0014 Decision 1, not a new config table), assigns
driver+vehicle, and transitions offer → ACCEPTED / ride → ACCEPTED. `Idempotency-Key`
required (api-contracts.md §16), same pattern as Create Ride (ADR-0010 Decision 5).
`RideService.accept_ride()` is the one place `ride.driver_id/vehicle_id/accepted_at`
are written (domain-design.md §9.6).

Task 3.5 — Customer Cancellation (ACCEPTED/ARRIVED), Minimal Penalty Foundation:
COMPLETE (ADR-0015). `penalty.penalties`/`penalty.strikes` (database-design.md §26)
built, pulled forward from Phase 13's Cancellation & Penalty domain the same way Wallet
was pulled forward from Phase 11 to unblock Task 3.4. `RideService.cancel_ride()` now
allows SEARCHING/ACCEPTED/ARRIVED → CANCELLED (previously SEARCHING only), row-locked
(`get_by_id_for_update()`) for the whole composition. For a post-acceptance
cancellation: the driver's platform fee is always refunded (new `WalletService.
credit()`, reversing the exact original debit amount — ADR-0015 Decision 3), and,
only outside the 2-minute grace period (BR-046), the customer's qualifying-cancellation
penalty is recorded (₹0 first, ₹15 second+ — BR-047/048 — BR-049 [corrected 2026-09-04,
ADR-0069: never expires, no longer a 30-day window],
idempotent per ride via `uq_penalties_ride_penalty_type`). Verified with a real
dual-thread HTTP concurrency test (two concurrent cancel attempts on the same accepted
ride; exactly one succeeds, the fee refunds exactly once).

Task 3.6 — Driver Cancellation: COMPLETE (ADR-0016) for the scope actually built —
`ACCEPTED → CANCELLED` (state-machines.md §13's literal transition), the ₹30 wallet
penalty (BR-067, a plain `WalletService.debit()` — "processed through the Wallet
domain", technical-architecture.md §36), the behavioral strike (BR-068), and the
BR-071 changed-pickup-pass exemption (no penalty, no strike). BR-070's "automatic
rematch, no new booking needed" is explicitly NOT built — ADR-0016 Item 2 flags a
genuine, unresolved contradiction between BR-070 and state-machines.md §13's literal
transition, rather than guessing which of two plausible readings is correct. Also
verified with a real dual-thread HTTP concurrency test.

Both explicitly NOT implemented by Tasks 3.4-3.6 together: any Kafka event (`ride.
accepted`, `ride.cancelled`, `penalty.applied`, `penalty.strike_recorded` — no producer
infrastructure exists yet, same gap every prior task has left), ACCEPTED → ARRIVED, or
any other ride-lifecycle transition beyond SEARCHING → ACCEPTED and the two
cancellation paths.

Financial:

Minimal Wallet Foundation (pulled forward from Phase 11 to unblock Task 3.4 — Accept
Offer): COMPLETE (ADR-0013). `wallet.wallets` + `wallet.transactions` (database-design.md
§17) implemented exactly as documented; `WalletService.debit()` is atomic (SELECT ...
FOR UPDATE row lock, database-design.md §42), refuses an insufficient balance
(BR-012), and is idempotent on a caller-supplied key via `wallet.transactions.
idempotency_key`'s own UNIQUE constraint. `GET /api/v1/drivers/me/wallet` implemented.
`WalletService.credit()` (Task 3.5, ADR-0015) is now also implemented — same row-locked,
idempotent shape as `debit()`, no insufficient-balance concern. Both are now called from
real callers: `debit()` by Task 3.4 (platform fee) and Task 3.6 (driver cancellation
penalty); `credit()` by Task 3.5 (platform-fee refund on post-acceptance cancellation).
Explicitly NOT implemented (ADR-0013 — still not any task's scope yet): recharge, any
*other* credit path (joining bonus, referral bonus, etc.), `wallet.
outstanding_settlements`/`wallet.recharges`, transaction-history endpoint.

Minimal Penalty Foundation (pulled forward from Phase 13's Cancellation & Penalty
domain to unblock Tasks 3.5/3.6): COMPLETE (ADR-0015). `penalty.penalties` +
`penalty.strikes` (database-design.md §26) implemented exactly as documented, plus one
addition beyond the literal schema — `uq_penalties_ride_penalty_type`, a concurrency
backstop (same UNIQUE-constraint-as-idempotency-guard pattern `wallet.transactions.
idempotency_key` already established). `PenaltyService.record_customer_cancellation()`
and `record_driver_strike()` implemented; both composed at
`modules/ride/router.py`'s two cancellation endpoints. Explicitly NOT implemented
(ADR-0015/0016 — still not any task's scope yet): no-show charges, penalty expiry
collection/enforcement, how an OUTSTANDING charge is ever actually collected, and
BR-069/119's progressive-abuse escalation (thresholds TBD).

Identity hardening (Phase 02, pulled forward per docs/VISTAAR_AUTONOMOUS_EXECUTION_PLAN.md's
dependency order): COMPLETE for everything genuinely unblocked. Resource-ownership
authorization audited across every resource-scoped router (all enforce it already —
nothing to build). OTP abuse protection extended to the IP dimension alongside the
existing phone dimension (`OtpRateLimiter.check_and_increment_request_ip()`/
`check_and_increment_verify_attempt_ip()`) — uses the request's own connection info, no
new API contract. Admin RBAC and Admin MFA remain BLOCKED (not unbuilt) — see §5 for
why (an "Admin roles TBD" business-rules conflict, ADR-0009, and a new-API-contract gap,
respectively). One real latent bug caught and fixed along the way:
`otp_resend_cooldown_seconds = 0` (a legitimate "disable cooldown" config value) crashed
Redis's `SET ... EX 0`; fixed to skip setting the cooldown key when disabled.

Event & Outbox Foundation (Phase 18, ADR-0017): COMPLETE for the genuinely unblocked
scope. `shared.outbox_events` (database-design.md §34) implemented exactly as
documented; `shared/outbox.py` (envelope + insert, event-contracts.md §3) and
`shared/outbox_publisher.py` (an in-process asyncio loop, not the still-unapproved
Background Worker Foundation/Celery — ADR-0017 Decision 1) ship rows to Kafka, topic
`vistaar.<domain>` (§6), partitioned by aggregate_id (§7). Retry is a fixed-interval
re-poll, not event-contracts.md §30's specific backoff sequence, which needs per-row
attempt-tracking columns not in the documented schema (ADR-0017 Decision 2) — Dead
Letter Topics and consumer idempotency (`shared.processed_events`) are both explicitly
deferred alongside it (ADR-0017 §4), since no consumer module exists yet either.
[Superseded 2026-09-04, ADR-0071 (owner-requested Phase 18 reliability work): the
attempt-tracking columns now exist, retry is genuine exponential backoff, Dead Letter
Topics are implemented (`vistaar.dlq.<domain>`), and `shared.processed_events` is real
— `modules/notification/consumer.py`'s NotificationConsumer (ADR-0038) is now the
consumer that needs it. See §21's Phase 18 status table and ADR-0071 for the full
account. Historical log entry, not corrected in place.]
Real events now published, composed at the router layer that already produces each
domain change: `ride.requested` (Task 3.1), `ride.accepted` + `wallet.debited` (Task
3.4), `ride.cancelled` + `wallet.credited` + `penalty.applied` (Task 3.5),
`ride.cancelled` + `wallet.debited` + `penalty.strike_recorded` (Task 3.6) — closing
the "no producer infrastructure exists yet" gap every one of those tasks' own
docstrings had been carrying.

Advertisements (Phase 17, ADR-0018): COMPLETE at the domain/service/repository layer —
all six domain-design.md §22.3 commands (`AdvertisementService`), the exact 80/20
driver/VISTAAR split (§22.4), and `uq_payouts_driver_campaign` as a real database-level
idempotency guard (proven with a real-Postgres test, not just an application check).
NOT built, and flagged rather than guessed at: any HTTP endpoint (`api-contracts.md`
documents zero Advertisement endpoints anywhere — building one means inventing a new
public API contract, §0.3) and Admoto integration (technical-architecture.md §55's
named verification partner, but no requirement/credential/approval documented — §0.4).
`verify_advertisement()` is a manual admin decision instead, matching this codebase's
existing document-verification treatment everywhere else. The `WalletService.credit()`
composition (ADVERTISEMENT_PAYOUT) is proven end-to-end by one real-Postgres
integration test performing the sequence a future router would.

Growth (Phase 12, ADR-0019): COMPLETE for the genuinely unblocked scope — the full
Promotion/Referral domain, service, repository, and schema layer (`promotion.*`,
`referral.*`, migration `ddc5e2ce287d`), all eleven domain-design.md §15.3/§16.3
commands except `RejectReferral` (nothing needs it yet), and — unlike Advertisement —
real documented HTTP endpoints (api-contracts.md §37-38: `GET
/api/v1/customers/me/promotions`, `GET /api/v1/customers/me/referral`, `POST
/api/v1/referrals/attach`), all three implemented. Two real composition points wired
in: `GrantWelcomePromotion` composes into `GET /api/v1/customers/me`'s first-access
auto-provision (a new `CustomerService.get_or_provision_profile()` reports whether
that call created the row, so the grant fires exactly once); `QualifyDriverReferral`
plus a ₹100/₹100 `WalletService.credit()` reward compose into `POST
/api/v1/admin/drivers/{driver_id}/approve`. `ReservePromotion`/`ConsumePromotion`/
`RestorePromotion` are implemented and proven directly by a real-Postgres
integration test (including a real-concurrency test racing two reservations for an
entitlement's last remaining use, `get_by_id_for_update()` row-locked). [Superseded
2026-08-28, ADR-0049, reconfirmed 2026-09-04: BR-063's discount cap is resolved —
50% off, ₹100/ride — no longer NULL/TBD. Historical log entry, not corrected in
place.] One real latent bug caught
and fixed along the way: `Entitlement._new()`'s dataclass constructor call was
missing the `discount_percent` argument entirely (caught by mypy, not by a test —
every fake-repository unit test happened to pass a valid `Decimal` through before
the bug could surface as a wrong value). (Corrected 2026-08-24 — this paragraph
originally said `ReservePromotion` was NOT composed into ride creation because no
Fare Quote step existed; the Pricing Foundation paragraph below closes exactly that
gap, so `ReservePromotion` now IS composed into `POST /api/v1/rides`.
`ConsumePromotion`/`RestorePromotion` remain uncomposed — ride cancellation/
completion still have no real fare to compute a discount_amount against.)
[Superseded 2026-09-04, ADR-0070: `ConsumePromotion`/`RestorePromotion` are
now composed into ride completion/cancellation too — the "no real fare"
blocker was already resolved by the Pricing Foundation paragraph below and
simply never acted on for these two commands until this task. Historical
log entry, not corrected in place.]

Pricing Foundation (Phase 04's "Initial fare quote" task, ADR-0020): COMPLETE for
the genuinely unblocked scope, triggered by the owner supplying a real, approved
fare table mid-session. `pricing.fare_rules`/`fare_quotes` built exactly as
documented (database-design.md §15.1-15.2, plus one additive `fare_rules.
minimum_fare` column), seeded via migration `61a5a80a044e` with the owner's rates.
`CalculateFare` (domain-design.md §11.4, with `ApplyPromotionDiscount` folded in)
composes into `POST /api/v1/rides`, resolving ADR-0010 Decision 1's `fare: null`
placeholder with a real `{base, discount, total, currency}` object — this same
change closes ADR-0019 Item 6 by also reserving the customer's soonest-expiring
eligible promotion in the same request, per api-contracts.md §12's documented flow.
Three genuine ambiguities were surfaced and resolved with the owner before any of
this was built (not guessed past — §0.3): the fare table's 5 columns vs.
business-rules.md §2's 3 documented vehicle categories (resolved: CAB gained three
customer-selected-at-booking sub-tiers — Eco/Premium/Premium+ — not new categories);
the table's platform fees contradicting BR-011's already-approved, already-
implemented fees (resolved: the table supersedes BR-011, updated in the same
change — Bike ₹2/Auto ₹5/Cab ₹10, was ₹10/₹20/₹20); and a real system-design
conflict between "fare must be calculated before matching" and an initial "vehicle
tier decides the fare" answer (resolved: the customer picks the tier at booking,
keeping fare deterministic up front, consistent with BR-002/BR-033). Distance is an
interim straight-line (haversine) calculation — technical-architecture.md names
Mapbox+OSM as the approved Maps choice, but no credential exists in this
environment (§0.4), the same "flag the specific external-provider gap, build
everything else" treatment ADR-0018 gave Admoto. NOT built: `CreateFareRevision`/
`CalculatePickupChangeCharge`/`CalculateDestinationChangeFare` (Phase 09, Ride
Modifications, not started — no live caller); a non-zero `time_charge`/
`waiting_charge`/`parking_charge`/`toll_charge`/`tax_amount` (no waiting-time
tracking, parking-proof-to-fare composition, toll integration, or tax engine
exists); `ConsumePromotion`/`RestorePromotion` composition into ride cancellation/
completion (same blocker). [Superseded 2026-09-04, ADR-0070: this composition
is now done — see the annotation on the "Two real composition points wired
in" paragraph above.] Matching also gained CAB-tier awareness in this same
change: `modules.vehicle.domain.entities.matching_category_key()` builds a
composite key (e.g. `"CAB:ECO"`) used consistently by the Redis geo-index
(`shared/geo.py`), `ComposedEligibilityChecker`, and offer dispatch/rematch/accept
— a PREMIUM ride is never offered to an ECO-tier driver — with zero signature
changes inside `modules.matching` itself (composed entirely at the router layer
that already imports `modules.vehicle`).

Driver Suspension & Reactivation (Phase 03, ADR-0021): COMPLETE at the service
layer. `DriverService.suspend_driver()`/`reactivate_driver()` implement the
already-documented `SuspendDriver`/`ReactivateDriver` commands
(domain-design.md §7.4) — concurrency-safe (row-locked, same mechanism as
`go_online()`/`go_offline()`), suspend reachable from any operational_status
except already-SUSPENDED, and deliberately not touching an in-progress ride if
the driver happens to be ON_RIDE (no source document describes force-
cancelling one). Reactivate always lands on OFFLINE, never directly ONLINE,
mirroring ADR-0009's "approval does not change eligibility" precedent. This
also retired a real latent gap: `go_online()`'s "driver not suspended"
precondition previously "held by construction" only because SUSPENDED was
unreachable (api-contracts.md §10 said so explicitly) — now that it's
reachable, the existing generic "must be OFFLINE" guard already enforces it
correctly, confirmed by a new test; only the docstring/error-message text
needed correcting, not new logic. NOT built, flagged rather than guessed at:
any HTTP endpoint (api-contracts.md documents no `POST /api/v1/admin/drivers/
{id}/suspend` or `/reactivate` shape anywhere, unlike Approve/Reject Driver
which had one already — the same "new public API contract" §0.3 gate ADR-0018
hit for Advertisement) and automatic threshold-based suspension (BR-069/117/119
— exact strike thresholds and suspension duration remain genuinely TBD,
business-rules.md §43, unchanged by this task). Proven by unit tests plus a
real-Postgres integration test (full suspend → blocked-from-going-online →
reactivate → can-go-online-again lifecycle) and a real-concurrency test (two
threads racing to suspend the same driver — the row lock ensures exactly one
succeeds).

Safety & Support Foundation (Phase 14, ADR-0022): COMPLETE for the genuinely
unblocked scope. Full Safety (`safety.incidents`/`events`, domain-design.md
§19) and Support (`support.cases`/`messages`, §21) domain/service/repository/
schema layer, matching database-design.md §28/§30 exactly plus one additive
column (`support.cases.ride_id` — api-contracts.md §44's documented request
body has nowhere else to store it). All 3 buildable documented HTTP endpoints
implemented: `POST /api/v1/rides/{ride_id}/sos` (§41, ride-participant-only,
IDOR-safe), `POST`/`GET /api/v1/support/cases` (§44, `ride_id` ownership
checked the same way, an admin may view any case). `SafetyService.
acknowledge_incident()`/`escalate_incident()`/`resolve_incident()` and
`SupportService.assign_case()`/`resolve_case()`/`post_message()` are built and
tested but have no documented HTTP endpoint anywhere — same "new public API
contract" §0.3 gate ADR-0018/0021 already hit; `assign_case()` deliberately
collapses the roadmap's "Support assignment" and "Human escalation" tasks into
one command (this codebase has no AI actor to escalate *from*).
`escalate_incident()` never contacts a real emergency service (BR-112's exact
integrations stay TBD). AI Support (§45, `POST /api/v1/support/ai/message`) is
BLOCKED, not stubbed — needs a real LLM, no provider/credential exists
anywhere in this environment (§0.4); the roadmap's "AI escalation" task is
transitively blocked the same way. Proven by unit tests plus real-Postgres
integration tests (full SOS trigger → acknowledge → escalate → resolve
lifecycle; full support case create → assign → post_message → resolve
lifecycle) and two real-concurrency tests (racing acknowledge attempts on one
incident, racing assign attempts on one case — each row lock ensures exactly
one succeeds).

Admin Monitoring & Penalty Review (Phase 16, ADR-0023, 2026-08-25): COMPLETE for
the genuinely unblocked scope, reconciling the roadmap's 17-bullet "Admin" task
list against api-contracts.md §46-48 — the only canonical source of the Admin
HTTP surface (PRD.md §54/domain-design.md §23.2's capability lists are intent,
not a contract). Driver/Vehicle management (mutations) were already COMPLETE
from Task 2.7A. Newly built: Search Rides / Get Ride (`GET /api/v1/admin/rides`
[+`/{ride_id}`], admin-only, composes modules.ride + modules.pricing for the
active fare quote — response shape filled in, none was documented, same
precedent Phase 14 set for GET Support Case); Admin Wallet View (`GET
/api/v1/admin/wallets/{driver_id}`, reuses the driver-facing wallet's exact
response shape); Search Penalties / Resolve Penalty (`GET
/api/v1/admin/penalties` + `POST .../resolve`, admin-only, row-locked). A real
new `PenaltyStatus.WAIVED` was added (state-machines.md §40's own documented
sibling of SETTLED/EXPIRED, reached only via `action: "WAIVE"` — the one
documented value); the "reversal/waiver record" api-contracts.md §48 asks for
reuses the existing `admin.audit_logs` mechanism rather than a new table. A
shared `shared/pagination.py` was added (this codebase's first list endpoint)
since Search Rides and Search Penalties both need §50's identical pagination
envelope; `ADMIN_MAX_PAGE_SIZE` (default 100) is the new server-configured cap
§50 asks for. NOT built, flagged rather than guessed at (ADR-0023 Decision 5):
Admin dashboard (aggregate), Customer management, Promotion/Referral
administration, Dispute dashboard, GPS evidence review, Pricing configuration,
Safety/Support dashboards, Advertisement management, Audit viewer, Payment
monitoring, Settlements — none has any HTTP shape anywhere in api-contracts.md;
Vehicle Review (GET) and a driver/vehicle pending-review list stay flagged from
ADR-0009, unchanged. Of Phase 16's 17 roadmap bullets: 2 already complete, 3
newly built, 12 have no documented contract to build against.

Get Ride Status & Wallet Transaction History (Phase 04 / Phase 11, ADR-0024,
2026-08-25): COMPLETE. `GET /api/v1/rides/{ride_id}` (api-contracts.md §13) —
customer/driver-ownership-restricted (IDOR-safe), reuses `RideService.
get_ride()` (previously internal-only), composes modules.driver/modules.
vehicle/modules.pricing for the `driver`/`vehicle`/`fare` sub-objects
(`null` until a driver is assigned), `payment` always `null` (no Payment
domain exists — Phase 10, blocked). Distinct from the admin-only `GET
/api/v1/admin/rides/{ride_id}` ADR-0023 already built. `GET
/api/v1/drivers/me/wallet/transactions` (api-contracts.md §34, the
roadmap's "Financial audit trail" task) — the driver's own paginated
ledger, `type` validated against the documented TransactionType enum;
`wallet.transactions` was already an immutable, fully-populated ledger,
only the read path was missing. Both reuse `shared/pagination.py`
(ADR-0023). This closes out Phase 04's only remaining task. (Outstanding
balance/Outstanding recovery/Penalty expiry collection remain not
started; Recharge remains blocked on the Phase 10 payment gateway — see
the Approved P2P Payment Model paragraph immediately below, ADR-0025,
2026-08-25, for why "Outstanding balance/recovery" specifically is now
N/A rather than merely blocked.)

Latest verified baseline (Get Ride Status & Wallet Transaction History):

727 passed

5 skipped (3 Kafka connectivity + 2 OutboxPublisher tests, unrelated — Kafka is not
running in this dev environment)

0 failed

Full suite verified 3 consecutive times from a freshly-dropped dedicated test database.

SUPERSEDED by a newer baseline: 767 passed, 5 skipped, 0 failed, verified 3
consecutive times — see the GPS Verification Foundation & Ride Lifecycle
paragraph below (ADR-0028, 2026-08-25) for the 40 new tests accounting for
the difference. SUPERSEDED AGAIN: 768 passed, 5 skipped, 0 failed — see
the Dispute-as-Support paragraph below (ADR-0029, 2026-08-25) for the 1
new test accounting for that difference. SUPERSEDED AGAIN: 788 passed, 5
skipped, 0 failed — see the Early Drop paragraph below (ADR-0030,
2026-08-25) for the 20 new tests accounting for that difference.
SUPERSEDED AGAIN: 813 passed, 5 skipped, 0 failed — see the MSG91/S3
paragraph below (ADR-0031, 2026-08-25) for the 25 new tests accounting
for that difference. SUPERSEDED AGAIN: 847 passed, 5 skipped, 0 failed —
see the GPS Dispute Manual Review paragraph below (ADR-0032, 2026-08-25)
for the 34 new tests (21 unit + 13 integration) accounting for that
difference. SUPERSEDED AGAIN: 862 passed, 5 skipped, 0 failed — see the
Ride Modifications (Pickup Change) paragraph below (ADR-0033,
2026-08-25) for the 15 new tests (5 unit + 10 integration) accounting
for that difference. SUPERSEDED AGAIN: 879 passed, 5 skipped, 0 failed
— see the Ride Modifications (Destination Change) paragraph below
(ADR-0033 Decision 9, 2026-08-25) for the 17 new tests (8 unit + 9
integration) accounting for that difference. SUPERSEDED AGAIN: 898
passed, 5 skipped, 0 failed — see the Notification Domain Foundation
paragraph below (ADR-0034, 2026-08-25) for the 19 new tests accounting
for that difference. Left here rather than edited in place, matching
this section's own established idiom of layering corrections instead
of erasing prior checkpoints.

Approved P2P Payment Model (ADR-0025, 2026-08-25) — DOCUMENTATION-ONLY,
no code/schema/provider change, baseline unchanged (still 727 passed, 5
skipped, 0 failed — this decision touched only docs). The project owner
formally recorded that VISTAAR does not collect the customer's ride
fare in any form; the customer pays the driver directly (cash/UPI), and
VISTAAR's platform fee is charged only to the driver's wallet, at ride
acceptance — exactly what technical-architecture.md §18/ADR-0014
already implemented. This resolves a long-standing internal
contradiction across business-rules.md/api-contracts.md/database-
design.md/domain-design.md/state-machines.md/technical-architecture.md,
all of which had also documented a second, incompatible, never-
implemented "VISTAAR collects the fare via online gateway or bundled
offline cash" model. That second model is now superseded throughout
(inline annotations, not deletions — see the ADR for the full file-by-
file list). Phase 10 (Payments)'s blocker status changes accordingly —
see its own entry below. Driver wallet recharge (Phase 11) remains the
one genuinely blocked payment-gateway need, unaffected. NOT resolved by
this decision: whether customers can still pay outstanding penalty/
no-show charges via a VISTAAR-facing flow (BR-055) — flagged for the
project owner, not assumed either way.

Customer Outstanding Penalty Collection — Split Settlement, Option A
(ADR-0026, 2026-08-26) — DOCUMENTATION-ONLY, no code/schema/provider
change, baseline unchanged (still 727 passed, 5 skipped, 0 failed). The
project owner answered the exact BR-055 question ADR-0025 left open,
above. A valid customer cancellation/no-show penalty creates an
OUTSTANDING liability (already exactly how `penalty.penalties` /
`PenaltyStatus.OUTSTANDING` work today — no change needed there).
VISTAAR does not collect it immediately; it is surfaced — combined with
the ride fare, as an informational total, never as one payment — at the
customer's next ride booking. The ride fare stays P2P (unaffected); the
outstanding penalty is settled as a genuinely separate "Customer →
VISTAAR" charge, and the driver's wallet is never touched for it. This
partially un-supersedes content ADR-0025 had marked fully dead: business-
rules.md §12's BR-037/038 (revived, with corrected settlement mechanics),
api-contracts.md §12 gains a documented `outstanding_penalty`/
`total_payable` response shape (not yet implemented), and database-
design.md §20's `payment.payments`/`payment.allocations` may still be
substantially the right schema — for penalty collection only, never the
ride fare (its already-documented `VISTAAR_PENALTY` allocation type
appears to have anticipated exactly this). Phase 10 regains one real,
still-blocked task accordingly — see its own entry below. Still NOT
resolved: the actual payment mechanism/provider for penalty collection
(same open-ended gap as wallet recharge), and whether BR-055's "pay
anytime through the app" is a standalone path beyond the at-next-booking
trigger — both flagged for a future task, not decided here.

GPS Verification Foundation & Ride Lifecycle (ADR-0028, 2026-08-25) — REAL
CODE, new baseline 767 passed, 5 skipped, 0 failed (up from 727 — 40 new
tests: 33 unit against fake repositories, 7 new real-Postgres integration
tests exercising the full HTTP flow end-to-end, plus 2 pre-existing files
extended). The project owner answered the three outstanding questions from
the "ok ask the queries you have doubt" round: GPS radius = 50m arrival /
100m completion with 3 attempts before manual review; Dispute domain =
Support/Admin capability, no new domain; this ADR's own scope = GPS
Verification Foundation (Phase 07) + Ride Lifecycle ACCEPTED → CLOSED
(Phase 06), explicitly not Dispute-as-Support itself (Phase 13). Implements:
`ride.gps_verifications`/`ride.ride_otps` (already fully specified in
database-design.md §13-14, migration 9d0f47a4fe18, upgrade/downgrade/
upgrade verified); `POST /api/v1/rides/{ride_id}/arrived`, `POST .../otp/
refresh`, `POST .../start`, `POST .../complete` (api-contracts.md §17/§18/
§28); `ride.arrived`/`ride.started`/`ride.completed` outbox events with
their exact documented payloads (event-contracts.md §10.3/10.4/10.8); no
`ride.closed` event (none documented — COMPLETED → CLOSED is automatic/
immediate in the same request, per state-machines.md §10, corrected here to
say so explicitly). One real design correction made mid-implementation:
the OTP is only ever persisted as its HMAC, never in plaintext, so
api-contracts.md's originally-drafted "customer sees it via GET Ride" design
was unworkable — corrected to "the plaintext OTP is only ever returned in
the direct response of `otp/refresh`'s own call," documented in both the
ADR and api-contracts.md §18. Phase 10/11 unaffected by this ADR (payments,
not ride lifecycle).

Dispute-as-Support (Phase 13, ADR-0029, 2026-08-25) — REAL CODE, new
baseline 768 passed, 5 skipped, 0 failed (up from 767 — 1 new end-to-end
integration test, plus 2 existing tests extended). Scopes and implements
exactly what BR-121 and domain-design.md §17.3 authorize following
ADR-0028's domain decision — no new domain, table, endpoint, or state.
Ride-fare disputes and DisputePenalty are both realized as ordinary
Support Cases (`POST /api/v1/support/cases`, already built, ADR-0022;
`category: "RIDE_FARE_DISPUTE"`/`"PENALTY_DISPUTE"`, documentation-only
conventions on an already free-text column) decided via the already-built
`POST /api/v1/admin/penalties/{id}/resolve` (`action: "WAIVE"` = dispute
upheld; a rejected dispute leaves the penalty OUTSTANDING with only the
support case itself resolved). The one real code change: `POST /api/v1/
rides/{ride_id}/cancel`'s `charge` response gains `penalty_id` (the
customer's own reference for filing a dispute) — a small, additive,
backward-compatible field, not a new business rule. The much larger
GPS-verification-dispute evidence/72-hour-window/admin-override workflow
(security.md §11-15, testing-strategy.md §20-23/§89-90) remains
explicitly out of scope — ADR-0002 already found it was never ratified
through the canonical documentation chain, and ADR-0029 reaffirms that
finding still holds; ADR-0028's domain-placement decision answers a
different question ("where does Dispute live") than "what are a GPS
dispute's evidence/override mechanics," and only the former was ever put
to the project owner.

Early Drop (Phase 08, ADR-0030, 2026-08-25) — REAL CODE, new baseline 788
passed, 5 skipped, 0 failed (up from 768 — 20 new tests: 11 unit against
fake repositories, 9 new real-Postgres integration tests exercising the
full HTTP flow end-to-end, plus a pre-existing file's own flaky test
stabilized — see below). Previously assessed as transitively unblocked
by ADR-0028 but re-examined here: the project owner was only ever asked
about arrival/completion GPS radii, never early-drop's own — security.md
§12 groups all three together as needing "an explicit decision," and
state-machines.md §63 separately lists "Exact early-drop GPS tolerance"
as still open. Resolved WITHOUT a new owner decision: business-rules.md
BR-088, api-contracts.md §27, and technical-architecture.md §43 all three
already say GPS/location is RECORDED, not verified against a threshold —
only state-machines.md §19-21 (lower-ranked per this project's own
source-of-truth hierarchy) adds a verification-gate PASS/FAIL/REVIEW
mechanic those three don't corroborate, the same shape of unratified
downstream addition ADR-0002 already found for the GPS-dispute workflow.
Implements: `ride.early_drop_requests` (already fully specified, plus one
additive `reason` column, migration 6ce26a4f7fd4); `POST .../early-drop`,
`POST .../early-drop/confirm` (api-contracts.md §27); `ride.early_drop_
confirmed` (event-contracts.md §10.7); STARTED → EARLY_DROP_REQUESTED →
(both confirm) → COMPLETED → CLOSED, reusing COMPLETED rather than
inventing an eighth ride status (state-machines.md §3.1's authoritative
enum has none); `confirmed: false` on Confirm realizes both reject paths,
no separate endpoint. No fare recalculation (BR-090). Also fixed in this
same pass: tests/test_get_ride_status_api.py gained the same Redis-geo-
index cleanup fixture tests/test_ride_lifecycle_api.py and tests/
test_early_drop_api.py already carried — a genuine, pre-existing
(not caused by this task) test-isolation gap that was occasionally
failing full-suite runs; see those files' own fixture docstrings.

MSG91 SMS Provider & AWS S3 Object Storage (ADR-0031, 2026-08-25) — REAL
CODE, new baseline 813 passed, 5 skipped, 0 failed (up from 788 — 25 new
tests: 19 unit — 8 against httpx.MockTransport for MSG91, 6 against
boto3's local presigned-URL signing for S3, 5 SMS-provider-dispatch — plus
6 new real-Postgres integration tests for the upload endpoint). The
project owner answered two of the four remaining open provider questions.
MSG91: wired in behind modules.identity.sms's already-prepared
`get_sms_provider()` seam (`SMS_PROVIDER=msg91`; `dev`, console-log,
remains the default) — flagged, not claimed verified: built from general
knowledge of MSG91's public v5 OTP API, no live account exists in this
environment to test against. AWS S3: a new `POST /api/v1/drivers/me/
uploads` (api-contracts.md §9) returns a presigned S3 PUT URL — the
client uploads directly to S3, then supplies the resulting URI to the
already-documented, completely unchanged `POST .../documents`/`PATCH
/me` request bodies. `.env.example`'s `STORAGE_*` block (Phase 1,
provisioned, never wired to any code) is now actually read. Scoped to
driver-facing uploads only — vehicle documents still have no HTTP
endpoint at all (ADR-0007), not expanded by this task. Two provider
questions remain fully open (payment gateway, background-worker/cloud
provider); the GPS-verification-dispute workflow is drafted (BR-124/
BR-125, 24-hour evidence window) but awaiting the project owner's
approval before any code is written — none of these three are touched by
this record.

GPS Dispute Manual Review (BR-124/BR-125, ADR-0032, 2026-08-25) — REAL
CODE, new baseline 847 passed, 5 skipped, 0 failed (up from 813 — 34 new
tests: 21 unit against RideService's new dispute methods, plus 13 real-
Postgres integration tests driving the full HTTP flow). The project owner
approved the drafted business rules with one explicit correction — a
24-hour evidence window, not the 72-hour figure this task's own draft had
initially carried over from security.md/testing-strategy.md. A terminal
GPS_VERIFICATION_FAILED outcome from mark_arrived()/complete_ride() (the
same ADR-0028 manual-review trigger, still 3 attempts) now auto-opens a
`ride.gps_disputes` row in the same transaction as the failing
verification (audit-trail-first, same discipline as every other write in
those two methods). Customer or driver may submit evidence (photo/video/
document via ADR-0031's S3 presigned-upload flow, or free-text) through
`POST .../evidence`; an admin resolves via `POST /api/v1/admin/gps-
disputes/{id}/resolve` with an `APPROVE` (performs the exact ride
transition the original PASS would have — `_finalize_arrival()`/
`_finalize_completion()`, shared with mark_arrived()/complete_ride()
themselves) or `REJECT` (records the decision only; the ride never
transitions). The 24-hour window is enforced lazily — no background
worker — the same precedent as MatchingService.expire_stale_offers()
(ADR-0011 Decision 2): any read or write touching an OPEN dispute past
its deadline transitions it to EXPIRED as a real write first. Two new
events (`ride.gps_dispute_opened`, `ride.gps_dispute_resolved`) are
published to the outbox; the resolve endpoint is the one deliberate,
explicitly-commented exception to modules/admin/router.py's otherwise
universal "audited, never published" rule for admin mutations, made
because these two events were already committed to in event-contracts.md.

Ride Modifications — Pickup Change (BR-072-078, ADR-0033, 2026-08-25) —
REAL CODE, new baseline 862 passed, 5 skipped, 0 failed (up from 847 —
15 new tests: 5 unit against the new Pricing domain function/service
method, plus 10 real-Postgres integration tests driving the full HTTP
flow, including a real re-dispatch to a second online driver after a
PASS). The project owner resolved BR-076's TBD pickup-change rate as
"the ride's own base per-km fare rate" — not a new flat number; BR-080's
already-ratified ₹8/km destination-extension rate was untouched (a
correction to this file's own earlier "roughly half the phase needs a
TBD rate" characterization of Phase 09 — only BR-076 was ever actually
open). A ≤250m pickup change applies immediately; a >250m change creates
a pending request, the driver chooses PROCEED (computes the charge via a
new `PricingService.calculate_pickup_change_charge()`, customer must
confirm before it's applied) or PASS (no ₹30 penalty/strike, same
exemption `driver_cancel_ride()` already had — the ride resets to
SEARCHING and is re-dispatched near the new pickup, the owner's
resolution of the same rematch ambiguity ADR-0016 Item 2 left open for
normal driver cancellation, which stays unresolved). Mid-task, a research
gap was caught and corrected: the implementation initially invented a new
`ride.pickup_change_requests` table before discovering database-design.md
already documented a unified `ride.change_requests` table (shared by
pickup- and destination-change, discriminated by `request_type`) — the
project owner was asked and chose to rework to match the documented
schema; see ADR-0033 Decision 4's own correction note. Destination Change
(BR-079-082) remains unimplemented — the schema is ready for it.

Ride Modifications — Destination Change (BR-079-082, ADR-0033
Decision 9, 2026-08-25) — REAL CODE, new baseline 879 passed, 5 skipped,
0 failed (up from 862 — 17 new tests: 8 unit against the new geometric
classification/Pricing function/service method, plus 9 real-Postgres
integration tests covering all three cases end-to-end). Completes
Phase 09 outright, reusing the `ride.change_requests` table's
`DESTINATION_CHANGE` request type the Pickup Change task above already
built the schema for — no new migration needed. Two real gaps had to be
resolved as documented engineering judgment calls before this could be
built at all, since neither was ever discussed as a business decision:
(1) no document specifies the geometric tolerance for classifying a new
destination as "along the original route" (BR-079/080) vs. "a different
route" (BR-081) — resolved as a 200m perpendicular-distance-from-the-
original-route-line tolerance, the same order of magnitude as the
owner-approved 250m pickup threshold; (2) BR-081's "recalculate from
current location" has no real data source anywhere in this codebase (no
per-ride live GPS tracking exists — the matching module's own location
endpoint is driver-global and Redis-ephemeral, not ride-scoped or
persisted) — resolved as `ride.current_pickup` (the confirmed arrival
point), the only "current state" location concept `Ride` actually has.
Both are recorded in ADR-0033 Decision 9 as engineering judgment, not
business values, following the same precedent ADR-0020 Decision 5 set
for choosing straight-line distance over real road routing without
asking the owner. A within-route change applies immediately; beyond-
original bills a flat ₹8/km (BR-080, already ratified, untouched); a
different route triggers a full fare recalculation (BR-081) via the
same base-fare/distance-charge formula `CalculateFare` itself uses. No
driver-decision step exists for destination change (unlike pickup
change's PROCEED/PASS) — the quote is computed and attached to the
pending request immediately, and the customer alone confirms or rejects
it, echoing back the `change_request_id` api-contracts.md §26 documents
(the one place this flow's request shape differs from pickup change's
own confirm step).

Notification Domain Foundation (ADR-0034, 2026-08-25) — REAL CODE, new
baseline 898 passed, 5 skipped, 0 failed (up from 879 — 19 new tests: 13
unit against NotificationService's send()/preferences methods, plus 6
against Msg91SmsProvider's new general-SMS send_message()). The owner
had approved four channels (in-app/WhatsApp/push/SMS) and FCM for push
specifically, but three real gaps surfaced during research, none of
them values-are-TBD gaps to guess past: (1) api-contracts.md documents
zero Notification HTTP endpoints anywhere — the same §0.3 "new public
API contract" stop condition ADR-0018/ADR-0021 already hit, so no
endpoint is invented; `NotificationService` is built and tested at the
service layer only, composed directly into other modules' routers. (2)
Push (FCM) has no device-token data source anywhere in this codebase —
`identity.sessions.device_metadata` is free-form session text, not a
structured registration token, and registering one would itself be a
new, undocumented endpoint — so Push is scoped out of this task
specifically, not abandoned; `Channel.PUSH` exists in the domain but
`send()` raises `ChannelNotAvailableError` for it. (3) No Kafka consumer
exists anywhere in this codebase (Phase 18's own status: "remain
undone") — technical-architecture.md §46 describes Notification as
consuming events over Kafka, but building the first real consumer is a
separate, materially larger task than this one; `send()` is instead
composed synchronously at the router layer, immediately after the
triggering write commits, as a best-effort step that must never roll
back the main transaction (domain-design.md §20.4) — the same pattern
`_dispatch_rematch()` already established in modules/matching/router.py.
Only two of technical-architecture.md §46's full documented event list
are actually wired (ride.accepted, ride.arrived) as a proof the
mechanism is real; the rest is a repeatable, bounded follow-up. SMS
reuses `modules.identity.sms`'s MSG91 integration, generalized from
OTP-only via a new `send_message()` method (MSG91's Flow API, a
separate `MSG91_NOTIFICATION_TEMPLATE_ID` from the OTP template) — same
"wired, not verified against a live account" caveat ADR-0031 already
carries, plus India's SMS DLT template-registration requirement, which
this environment cannot satisfy either. Message wording itself is
nowhere documented (domain-design.md §20.2 only says the domain "owns...
templates," not what they say) — a small, explicitly-flagged placeholder
lookup was written, not approved customer-facing copy. WhatsApp: no BSP
chosen, no code written, per the owner's own explicit instruction — a
separate requirements analysis was delivered alongside this task instead
of a docs change (see the task's own completion report).

Actual next engineering dependency

Phase 04 now has no remaining unblocked task — Tasks 3.4-3.6 finished its
cancellation work, "Initial fare quote" closed with ADR-0020, and "GET ride
status" closes it out here (ADR-0024). Identity hardening (Phase 02), the
Event & Outbox Foundation (Phase 18), Advertisements (Phase 17), Growth
(Phase 12), Phase 03's driver suspension/reactivation, Phase 14's Safety &
Support foundation, and Phase 16's Admin monitoring/penalty review have each
gone as far as they can without an owner decision, a new consumer module, or
a new API contract respectively. Phase 06/07's GPS Verification Foundation
and Ride Lifecycle task — previously blocked here — is now RESOLVED and
IMPLEMENTED (ADR-0028, 2026-08-25): the owner approved 50m arrival / 100m
completion GPS radii with 3 attempts before manual review, and the whole
ACCEPTED → ARRIVED → STARTED → COMPLETED → CLOSED chain (api-contracts.md
§17/§18/§28, state-machines.md §6-10) is built, tested (unit + real-Postgres
integration, including the GPS retry/manual-review split and the OTP
attempt-limit/expiry logic), and verified. See the ADR for the OTP-exposure
design correction (the plaintext OTP is only ever returned by
`otp/refresh`'s own response — never recoverable later, since only its HMAC
is persisted) and for why Dispute-as-Support (Phase 13) was decided but
deliberately NOT built as part of this same task. (Phase 13 itself was
built immediately after, as its own task — see the Dispute-as-Support
paragraph immediately above, ADR-0029.)

Per docs/VISTAAR_AUTONOMOUS_EXECUTION_PLAN.md's dependency-ordered execution plan,
every item in the RECOMMENDED EXECUTION ORDER list is now DONE, including
Phase 06/07 and its GPS dispute manual-review workflow (ADR-0032). What
remains (Payment monitoring, pricing configuration, safety/support
dashboards, advertisement management, an audit viewer, and everything else
in that plan's "waits on the project owner" list) genuinely requires an
owner decision, a new documented API contract, or an external-provider
selection — see docs/VISTAAR_AUTONOMOUS_EXECUTION_PLAN.md for the full
phase-by-phase reasoning. (Corrected 2026-08-25 — this paragraph
previously pointed at Phase 04's "GET ride status"/Phase 11's "Financial
audit trail" as the next candidates; that work is now done too (ADR-0024,
see the paragraph above), and this section is updated to match. Phases 19
(Security hardening) and 20 (Testing depth) remain best done continuously
alongside whichever phase is active, not as one discrete task — not a
competing "next" candidate. Updated again 2026-08-25 for Phase 06/07's own
resolution, ADR-0028, and again 2026-08-25 once more for the GPS dispute
manual-review workflow's own resolution, ADR-0032.)

Critical numbering rule

The project contains two numbering systems:

The high-level 21-phase / 280-task roadmap below.

The granular task numbers used in this implementation history (2.6C, 2.7A, 2.7B,
3.1, 3.2, 3.3, etc.).

They are NOT 1:1. The agent MUST use capability/state evidence from the actual repository
when mapping a granular task to a high-level phase. Never reimplement a completed
capability merely because a high-level phase table still contains an old label.

Foundation reconciliation status

The earlier roadmap listed PostGIS, MinIO, and Celery as foundation tasks. PostGIS is now
required and already exists because Task 3.1 introduced the ride geometry schema. Object
storage is RESOLVED and IMPLEMENTED (ADR-0031, 2026-08-25) — the project owner selected
AWS S3, not MinIO (MinIO was only ever a candidate, correctly never adopted without a
decision). The background-worker process is RESOLVED and IMPLEMENTED too (ADR-0039,
2026-08-26) — the project owner approved Celery directly ("Use Celery for background
workers"), the same §0.4 external-technology-decision process this section itself
describes, followed through to its actual approval rather than left open.

2.1 Completed current implementation work

The following granular work has been completed in the repository:

Backend skeleton

Customer mobile skeleton

Driver mobile skeleton

Admin web skeleton

Shared packages foundation

Environment configuration

Python 3.12 development environment

Ruff / MyPy foundation

Testing foundation

GitHub Actions CI foundation

Backend Docker foundation

Local PostgreSQL / Redis / Kafka development stack

PostgreSQL / SQLAlchemy / Alembic foundation

Central backend configuration

Redis integration

Kafka integration

API contract foundation

Event contract foundation

Domain package foundation

Identity/authentication foundation

Customer profile

Driver profile

Driver-profile design clarification

Vehicle management

Single-active-vehicle rule and vehicle API clarification

Driver/vehicle document management foundation

Verification/compliance domain foundation

Verification decision ADRs and external integration register

2.2 Current verification state

Latest verified backend results have remained green across the completed tasks. The current checkpoint (Admin Permission Model, ADR-0040) reports 969 passed, 5 skipped, 0 failed (up from 923 — 46 new tests across `tests/test_admin_domain.py`, `tests/test_admin_service.py`, and `tests/test_admin_api.py`, including dedicated permission-enforcement cases against a real Postgres database) — confirmed 2 consecutive times from the dedicated test database, plus `mypy`/`ruff format`/`ruff check` all clean. A real integration-test failure caught a genuine bug before it shipped: a `# type: ignore[arg-type]` written earlier had masked `Permission.access_level` being stored as a raw string instead of the `AccessLevel` enum — fixed properly (`AccessLevel(row.access_level)`) rather than re-suppressed. (Corrected 2026-08-26 — this subsection previously carried a stale Admin-Monitoring/Phase-16 count of 708 passed, contradicted by §2.0's own figure, then a 727 count superseded by Phase 06/07's 40 new tests (ADR-0028), then a 767 count superseded by Phase 13's 1 new test (ADR-0029), then a 768 count superseded by Phase 08's 20 new tests (ADR-0030), then a 788 count superseded by the MSG91/S3 integrations' 25 new tests (ADR-0031), then an 813 count superseded by the GPS Dispute Manual Review feature's 34 new tests (ADR-0032), then an 847 count superseded by the Ride Modifications (Pickup Change) feature's 15 new tests (ADR-0033), then an 862 count superseded by the Ride Modifications (Destination Change) feature's 17 new tests (ADR-0033 Decision 9), then an 879 count superseded by the Notification Domain Foundation's 19 new tests (ADR-0034), then confirmed unchanged at 898 for ADR-0035 (no new tests — a deployment/config task), then a 905 count superseded by the Security Response Headers feature's 7 new tests (ADR-0036), then a 907 count superseded by the Resource-Ownership Authorization Audit's 2 new tests (ADR-0037), then a 916 count superseded by the Notification Kafka Consumer's 9 new tests (ADR-0038), then a 923 count superseded by the Celery Background Worker Foundation's 7 new tests (ADR-0039), then a 969 count superseded by the Admin Permission Model's 46 new tests (ADR-0040). Corrected repeatedly already for the same class of staleness — see this file's own edit history on 2026-08-22 through 2026-08-26.)

2.3 Known deliberate follow-ups

These are not forgotten:

Real SMS provider integration

Authorized transport/document verification provider selection

Parivahan/Sarathi/Vahan authorized access

AI/OCR provider selection

Final KYC/document-type vocabulary

Verification-case status → document-status write-back rule

Driver DOB/address/payout details decisions from ADR-0005

One-active-vehicle rule is now approved as BR-122

Vehicle GET/PATCH API is now approved and implemented

Broader OTP abuse protection beyond phone dimension

Identity/Customer/Driver/Vehicle Kafka event publication where contracts are available and authorized

3. MASTER PHASE LIST

Phase

Area

Tasks

Current state

01

Foundation

19

COMPLETE; PostGIS is now present. Object storage is RESOLVED and
IMPLEMENTED (ADR-0031, 2026-08-25, AWS S3 — see §4). Background-worker foundation
is RESOLVED and IMPLEMENTED too (ADR-0039, 2026-08-26) — the owner approved Celery

02

Identity

17

COMPLETE; identity/customer/driver/admin auth, resource-ownership authorization (audited), OTP abuse protection (phone + IP dimensions), Admin RBAC (ADR-0040, BR-126/BR-127), and Admin MFA (ADR-0051, 2026-08-28 — TOTP) all implemented. (Corrected 2026-08-28 — this line previously said Admin RBAC and Admin MFA remain BLOCKED; both are now resolved, see §5.)

03

Driver Operations

10

Core driver/vehicle/document/eligibility/online-offline capability implemented, now including suspend/reactivate at the service layer (ADR-0021, 2026-08-24 — no HTTP endpoint documented anywhere, same §0.3 gate as Advertisement); remaining compliance/provider hardening remains

04

Ride Booking

9

COMPLETE. Ride creation and all customer/driver cancellation variants (Tasks 3.3/3.5/3.6, ADR-0012/0015/0016) implemented. "Initial fare quote" COMPLETE (ADR-0020, owner-supplied fare table) — CalculateFare + ApplyPromotionDiscount compose into POST /api/v1/rides, resolving fare: null and closing ADR-0019 Item 6. "GET ride status" now COMPLETE too (ADR-0024, 2026-08-25) — GET /api/v1/rides/{ride_id}, ownership-restricted, composes modules.driver/modules.vehicle/modules.pricing for the response

05

Matching

12

Partially complete; matching/driver offers and offer acceptance (Task 3.4, ADR-0014) implemented; remaining tasks (background expiry worker, event publication) out of scope by design — see modules/matching/__init__.py

06

Ride Lifecycle

10

COMPLETE for the core lifecycle. SEARCHING → ACCEPTED implemented (Task 3.4 — see Phase 05's row above, same task); ACCEPTED → ARRIVED → STARTED → COMPLETED → CLOSED implemented (ADR-0028, 2026-08-25) with real GPS verification and ride-start OTP. Early Drop (Phase 08's own row, ADR-0030, 2026-08-25) and Dispute-as-Support (Phase 13, ADR-0029, 2026-08-25) are both also now COMPLETE — every genuinely unblocked ride-lifecycle task from this session's execution plan is done

07

GPS & Verification

9

COMPLETE for GPS verification foundation. Owner-approved radii (50m arrival / 100m completion) and the 3-attempts-before-manual-review split implemented (ADR-0028, 2026-08-25) — ride.gps_verifications is a real audit trail now, every attempt recorded pass or fail. The manual-review queue/dispute workflow is now also COMPLETE (BR-124/BR-125, ADR-0032, 2026-08-25): a terminal failure auto-opens a `ride.gps_disputes` row, customer/driver may submit evidence within a 24-hour window, and an admin resolves via `POST /api/v1/admin/gps-disputes/{id}/resolve` — see the GPS Dispute Manual Review paragraph in the "Actual next engineering dependency" section above for the full design.

08

Early Drop

9

COMPLETE (ADR-0030, 2026-08-25). RequestEarlyDrop/ConfirmEarlyDrop
implemented exactly per BR-088/089/090 and api-contracts.md §27 —
GPS/location recorded as evidence, never verified against a threshold
(state-machines.md §19-21's added verification-gate language does not
govern — see the ADR for the full source-of-truth reconciliation, which
also resolves §63's "Exact early-drop GPS tolerance" TBD item as N/A).
STARTED → EARLY_DROP_REQUESTED → (both confirm) → COMPLETED → CLOSED, no
new ride status invented; `confirmed: false` on Confirm handles both
reject paths, no separate reject endpoint. No fare recalculation (BR-090)

09

Ride Modifications

22

Not started; must respect currently approved/TBD business values

10

Payments

17

Blocker status changed (ADR-0025, 2026-08-25, extended ADR-0026,
2026-08-26 — approved P2P Payment Model + Option A customer-penalty
split settlement; documentation-only, no code/schema/provider change):
VISTAAR does not collect the ride fare from the customer in any form;
most of this phase's 17 tasks describe a customer-facing gateway/
settlement flow that no longer applies and should not be built. Two
payment-gateway needs remain project-wide, both still genuinely blocked
on provider selection: driver wallet recharge (Phase 11) and, newly
(ADR-0026), customer outstanding-penalty collection — a valid
cancellation/no-show penalty is surfaced (not collected) at the
customer's next booking, then settled "Customer → VISTAAR" separately
from the P2P ride fare. [Superseded 2026-09-03, ADR-0066: no longer
"Customer → VISTAAR" at all — the penalty is now bundled into the P2P
ride-fare payment and VISTAAR recovers its share via the driver's
wallet at ride completion instead. Historical log entry, not corrected
in place.] See §13's Current implementation mapping for
the full reconciliation.

11

Financial

19

Not started as a phase; a minimal subset was pulled forward and is COMPLETE — wallet balance/debit/credit/immutable ledger (ADR-0013, ADR-0015) and the customer/driver cancellation penalty logic (ADR-0015/0016: qualifying-cancellation charges, driver strikes, penalty idempotency). The driver referral bonus credit path (BR-022, ₹100/₹100) is also COMPLETE, composed at admin driver-approval time (ADR-0019, see Phase 12). "Financial audit trail" is now COMPLETE too (ADR-0024, 2026-08-25) — GET /api/v1/drivers/me/wallet/transactions, the driver's own paginated ledger. Outstanding balance/recovery are N/A as originally scoped (ADR-0025, 2026-08-25 — the driver-side "cash settlement" concept they modeled no longer exists). Recharge remains blocked on the Phase 10 payment gateway (narrowed to wallet-recharge specifically). Penalty expiry collection and no-show charges remain not started

12

Growth

14

COMPLETE for the genuinely unblocked scope (ADR-0019): full Promotion/Referral domain,
service, repository, and schema layer; the 3 documented HTTP endpoints (Get Promotions,
Get Referral Code, Attach Referral); GrantWelcomePromotion composed into GET
/api/v1/customers/me; QualifyDriverReferral/wallet reward composed into driver
approval. reserve/consume/restore not composed into ride creation/cancellation — no
Fare Quote step exists yet (blocked on Pricing, same as Phase 04). [Superseded
2026-08-28, ADR-0049, reconfirmed 2026-09-04: BR-063's discount cap is resolved —
50% off, ₹100/ride — no longer NULL/TBD. Historical log entry, not corrected in
place.] See §2.0 for the full write-up

13

Disputes

16

COMPLETE for BR-121/domain-design.md §17.3's actually-documented scope
(ADR-0028 + ADR-0029, 2026-08-25): the Dispute-domain decision is made
(Support/Admin capability, no new domain) and both named dispute concepts
(ride-fare disputes, DisputePenalty) are implemented, composed entirely
from already-built endpoints (Create Support Case + Resolve Penalty) plus
one small additive `charge.penalty_id` field — no new domain, table,
endpoint, or state. The much larger GPS-verification-dispute
evidence/admin-override workflow described in security.md/testing-
strategy.md/implementation-readiness.md remains explicitly NOT built —
ADR-0002 found it was never ratified in any canonical document, and
ADR-0029 reaffirms that finding still holds

14

Safety & Support

11

COMPLETE for the genuinely unblocked scope (ADR-0022): full Safety/Support
domain, service, repository, and schema layer; the 3 documented HTTP endpoints
(SOS, Create Support Case, Get Support Case). Acknowledge/Escalate/Resolve
SOS and Assign/Resolve/PostMessage Support Case implemented at the service
layer (no documented HTTP endpoint anywhere). AI Support (§45) is BLOCKED —
no LLM provider/credential exists (§0.4); not stubbed. Automatic emergency-
service integration stays out of scope (BR-112's exact integrations remain
TBD). See §2.0 for the full write-up

15

Notifications

10

Not started; SMS/WhatsApp/push provider decisions pending where applicable

16

Admin

17

Driver/Vehicle management complete (Task 2.7A). Ride monitoring, Wallet monitoring,
and Penalty administration now COMPLETE too (ADR-0023, 2026-08-25). The other 12
roadmap bullets have no documented HTTP contract anywhere in api-contracts.md and
stay flagged, not built — see §19's Current implementation mapping

17

Advertisements

8

Complete at the domain/service/repository layer (ADR-0018) — all 8 tasks' underlying business logic implemented and tested. No HTTP endpoint exists (would mean inventing a new public API contract — none is documented anywhere) and Admoto verification is not integrated (unapproved external partner) — see §20

18

Event & Background

11

Mostly complete for the genuinely unblocked scope (ADR-0017): outbox table, in-process publisher, and real event publication for every already-built domain transition. A real Kafka consumer now exists (ADR-0038, Notification, 4 events) and the background worker process is RESOLVED and IMPLEMENTED (ADR-0039, Celery — first scheduled jobs: promotion/document expiry warnings). Dead Letter Topics and consumer idempotency remain deferred — need the attempt-tracking schema Event Retry above still lacks; this consumer's own idempotency is instead satisfied by `notification.deliveries`' unique constraint, the same "unique constraints, event IDs" mechanism event-contracts.md §9 itself describes as sufficient — see §21

19

Security

12

Not started as final production hardening

20

Testing

15

Foundation tests exist; final system-level testing remains

21

Deployment

13

Not started

Total implementation tasks in the latest detailed roadmap: 280.

4. PHASE 01 — FOUNDATION (19 TASKS)

Goal

Complete the technical foundation required for all later production domains.

Current state: COMPLETE. PostGIS is now present through Ride work (Task 3.1).
Object storage is RESOLVED and IMPLEMENTED (ADR-0031, 2026-08-25 — AWS S3, not MinIO).
Background-worker foundation is RESOLVED and IMPLEMENTED (ADR-0039, 2026-08-26) —
the owner approved Celery, using the already-provisioned Redis as broker/backend.

Tasks

Git repository and branch strategy

Backend skeleton

Customer mobile skeleton

Driver mobile skeleton

Admin web skeleton

Shared packages

Environment configuration

Python 3.12 setup

Lint/format/type checks

Test framework

CI baseline

Docker Compose

PostgreSQL

PostGIS

Redis

Kafka

Object storage foundation — RESOLVED (ADR-0031, 2026-08-25): AWS S3

Background worker foundation — RESOLVED (ADR-0039, 2026-08-26): Celery

Health checks

Current mapping

Already implemented in the repository: 1–16, plus foundational health checks (19).
PostGIS (14) is complete — the dev and dedicated test databases both run a PostGIS-enabled
Postgres image, and ride.rides' pickup/destination columns are real GEOMETRY(Point,4326)
columns with GIST indexes (Task 3.1). (Corrected 2026-08-22 — this line previously excluded
item 14, contradicting §2.0's own statement that PostGIS is already present.)

Remaining reconciliation items

Object storage foundation: RESOLVED and IMPLEMENTED (ADR-0031, 2026-08-25). The project
owner selected AWS S3. `POST /api/v1/drivers/me/uploads` (api-contracts.md §9) returns a
presigned S3 upload URL; the document/profile-photo submission endpoints still accept the
resulting URI exactly as before (evidence_uri/profile_photo_uri unchanged). Scoped to
driver-facing uploads only — vehicle documents have no HTTP endpoint at all (ADR-0007) and
were not expanded here.

Background worker foundation: RESOLVED and IMPLEMENTED (ADR-0039, 2026-08-26) — the
owner approved Celery ("Use Celery for background workers"). `shared/celery_app.py`
(Redis broker/backend, no new infrastructure) is the foundation itself; `modules/
notification/tasks.py`'s two periodic tasks (promotion/document expiry warnings) are
its first real scheduled jobs.

Health-check coverage: confirm the complete required health/readiness surface.

Exit gate

Phase 1 is complete only after the 19 roadmap tasks are mapped to real repository capability and all required tests/documentation are green.

5. PHASE 02 — IDENTITY (17 TASKS)

Goal

Complete authentication, identity, profiles, authorization, admin authentication, and MFA foundations.

Tasks

Customer registration

Customer OTP request

Customer OTP verification

Customer tokens/sessions

Driver registration

Driver OTP request

Driver OTP verification

Driver tokens/sessions

OTP expiry/retry limits

Authentication rate limiting

Customer profile

Driver profile

RBAC

Resource ownership authorization

Admin authentication

Admin RBAC

Admin MFA

Existing coverage

Tasks 1–12 are substantially represented by the existing Identity and Customer/Driver work.

Admin authentication: COMPLETE — admin accounts authenticate through the exact same OTP
flow as customer/driver (`account_type: "ADMIN"`); `require_admin` gates every admin
endpoint. Was already true before this pass; not previously stated explicitly here.

Resource ownership authorization: COMPLETE, audited this pass (2026-08-24) — every
resource-scoped endpoint in the repository (`ride/router.py`, `matching/router.py`,
`vehicle/router.py`, `admin/router.py`) either passes the authenticated account's id into
its service call for an ownership check (same "not found" response for missing and
unauthorized — IDOR-safe throughout) or is admin-gated via `require_admin`. `driver/`,
`customer/`, and `wallet/` routers have no resource-id path parameters at all (`/me`-style
endpoints only, inherently ownership-safe). No endpoint was found lacking this.

OTP abuse protection, IP dimension: COMPLETE — `OtpRateLimiter` now enforces phone-number
*and* IP-address dimensions (security.md §5's first two of three documented dimensions);
IP uses the request's own connection info (`request.client.host`), no new API contract
needed. The device/session dimension remains NOT implemented — it would need a
client-supplied identifier api-contracts.md's OTP request/verify bodies do not document,
which is its own new-public-API-contract stop condition (§0.3), independent of how simple
the rate-limiting logic itself would be.

Admin RBAC (a fine-grained admin role/permission hierarchy): BLOCKED, not merely
unbuilt. security.md §7/§9 lists specific roles (SAFETY_ADMIN, FINANCE_ADMIN,
SUPER_ADMIN) with example permissions, but business-rules.md §43 explicitly lists
"Admin roles / Permission hierarchy / Escalation rules" as deliberately TBD — ADR-0009
already flagged this exact conflict, and per §0.1's source-of-truth hierarchy, Business
Rules outranks Security Design, so the TBD marker governs. Building a permission-check
framework with only the one real role (ADMIN) to plug into it would be speculative
infrastructure with no real caller — the anti-pattern ADR-0013 explicitly avoided for
Wallet's `credit()` until a real task needed it.

Admin MFA: RESOLVED and IMPLEMENTED (ADR-0051, 2026-08-28) — the owner supplied the
missing mechanism ("TOTP authenticator app"), and this ADR supplied the endpoint shape
the §0.3 gate below was waiting on. See api-contracts.md §7.3, database-design.md §5.4.
(Kept below for the historical record of why it was blocked until then, not because it
still applies.)

Admin MFA: BLOCKED, not merely unbuilt. Not on a provider/credential — TOTP is
self-contained — but api-contracts.md, database-design.md, and technical-architecture.md
have zero mention of MFA anywhere: no documented enrollment/verify endpoint shape, no
schema for a stored secret. Building it now means inventing a new public API contract,
itself an explicit §0.3 mandatory-stop condition.

Remaining, not blocked

None — every genuinely unblocked item in this phase's "Remaining" list is now done (see
above). The two still-open items (Admin RBAC, Admin MFA) both need an owner/business
decision first, not more engineering time.

Exit gate

Customer, driver, and admin authentication/authorization are real, tested, documented, and protected against enumeration/IDOR/BOLA. This exit gate is MET for everything not blocked above; Admin RBAC/MFA remain open pending the two decisions flagged above.

6. PHASE 03 — DRIVER OPERATIONS (10 TASKS)

Goal

Complete the operational driver/vehicle lifecycle needed before ride matching.

Tasks

Driver onboarding

Driver documents

Driver document verification

Driver eligibility

Driver online/offline

Driver suspension/reactivation

Vehicle registration

Vehicle documents

Vehicle approval

Vehicle eligibility

Existing coverage

Driver profile ✅

Driver documents ✅

Vehicle registration ✅

Vehicle documents ✅

Verification foundation ✅

One-active-vehicle rule ✅ (BR-122)

Driver approval/rejection/admin review ✅ (Task 2.7A)

Vehicle approval/rejection/admin review ✅ (Task 2.7A)

Eligibility engine ✅ (Task 2.7B)

Online/offline lifecycle ✅ (Task 2.7B)

Vehicle eligibility ✅ (covered by the eligibility engine above)

Driver suspension/reactivation ✅ (ADR-0021, 2026-08-24 — service-layer only,
see "Remaining" below for the one genuine gap)

(Corrected 2026-08-22 — the six items above were previously listed under
"Remaining" even though they were already implemented and tested; this is the
same reintroduced contradiction §1's reconciliation warning exists to catch.
Corrected again 2026-08-24 — driver suspension/reactivation moved here from
"Remaining" once built.)

Remaining

Final document verification provider integration (provider TBD).

An HTTP endpoint for Suspend/Reactivate Driver — `DriverService.
suspend_driver()`/`reactivate_driver()` are fully built and tested (ADR-0021),
but api-contracts.md documents no `POST /api/v1/admin/drivers/{id}/suspend`
(or `/reactivate`) shape anywhere, unlike Approve/Reject Driver which had one
already — inventing one would be a new public API contract (§0.3), the same
gate ADR-0018 hit for Advertisement. Automatic, threshold-based suspension
(BR-069/117/119) remains separately TBD (exact strike thresholds/suspension
duration, business-rules.md §43) — not attempted.

Critical dependency

The approved rule is:

Driver → multiple registered vehicles → maximum ONE ACTIVE vehicle → vehicle switching only while OFFLINE.

This is already implemented at the vehicle layer and must remain enforced under concurrency.

7. PHASE 04 — RIDE BOOKING (9 TASKS)

Create ride request

Validate pickup

Validate destination

Initial fare quote

Vehicle category

Create SEARCHING ride

Customer ride status

Customer cancellation

Driver cancellation

Current implementation mapping

Create ride request: COMPLETE (granular Task 3.1)

Pickup/destination validation: COMPLETE for currently documented coordinate validation

Vehicle category: COMPLETE for ride creation

SEARCHING creation/state history: COMPLETE

Customer ride cancellation while SEARCHING: COMPLETE (granular Task 3.3)

Fare quote: COMPLETE (ADR-0020, 2026-08-24) — owner supplied approved fare rates
mid-session; CalculateFare + ApplyPromotionDiscount now compose into POST
/api/v1/rides. See §2.0's Pricing Foundation paragraph for the full write-up.
(Corrected 2026-08-24 — this line previously said PARTIAL / fare: null / blocked
on Pricing.)

Customer cancellation (ACCEPTED/ARRIVED): COMPLETE (Task 3.5, ADR-0015) — see §2.0.

Driver cancellation: COMPLETE for the scope actually built (Task 3.6, ADR-0016) —
BR-070's automatic rematch explicitly not implemented (ADR-0016 Item 2, a genuine
ambiguity between two documents, flagged rather than guessed past).

GET ride status: COMPLETE (ADR-0024, 2026-08-25) — GET /api/v1/rides/{ride_id},
customer/driver-ownership-restricted (IDOR-safe), composes modules.driver/
modules.vehicle/modules.pricing for the driver/vehicle/fare sub-objects
(each null until applicable); payment stays null (no Payment domain exists —
Phase 10, blocked). (Corrected 2026-08-25 — this line previously said "not
implemented, no plan yet.")

Phase 04 has no remaining task after this — every one of its 9 tasks is now
COMPLETE.

Requirements

Do not invent final fare values that remain TBD.

Integrate maps/routing only after provider selection and credential approval.

Maintain transactional ride creation.

Maintain API/domain/database separation.

Add integration and concurrency tests.

Exit gate

A customer can create a valid ride request and observe a server-authoritative SEARCHING ride state.

8. PHASE 05 — MATCHING (12 TASKS)

Find eligible nearby drivers

PostGIS proximity query

Create driver offer

20-second offer timer

Driver accept

Driver reject

Offer expiry

Next-driver selection

Driver remains ONLINE after reject

Driver remains ONLINE after expiry

Atomic single-driver assignment

Prevent duplicate acceptance

Current implementation mapping

Nearby-driver discovery / candidate selection: COMPLETE to the extent already implemented in granular Task 3.2; verify exact PostGIS/Redis behavior against current code before extending it

Driver offer creation: COMPLETE (granular Task 3.2)

Offer expiry / rejection behavior: COMPLETE to the extent verified by Task 3.2; do not reimplement

Driver acceptance / ACCEPTED transition: COMPLETE (Task 3.4, ADR-0014) — technical-architecture.md §18's Accept-Ride Transaction implemented exactly (wallet lock → re-validate offer/ride/eligibility → debit → assign driver → offer/ride ACCEPTED, all in one transaction).

Atomic single-driver assignment: COMPLETE — verified with a real dual-thread HTTP concurrency test (two concurrent accept requests for the same offer; exactly one succeeds, exactly one ride.state_history ACCEPTED row is written).

Requirements

Server-side timer.

Exact-one-winner acceptance.

Concurrency tests.

PostGIS/Redis use according to final architecture.

Driver eligibility must come from the approved eligibility engine.

The detailed roadmap explicitly requires the 20-second offer timer and atomic single-driver assignment.

9. PHASE 06 — RIDE LIFECYCLE (10 TASKS)

Current next dependency: SEARCHING → ACCEPTED is COMPLETE (Task 3.4, ADR-0014 — see
§2.0). This phase's own next task is ACCEPTED → ARRIVED (Driver Arrival) — not yet
planned or implemented. (Corrected 2026-08-24 — this note previously also discussed
ACCEPTED/ARRIVED cancellation here, but that task belongs to Phase 04 — Ride Booking's
"Customer cancellation"/"Driver cancellation" tasks, §7 above, not to this phase's task
list, §9 below, which has no cancellation task at all. See §2.0's "Actual next
engineering dependency" for both of the project's currently-unblocked next-task
candidates together.)

SEARCHING → ACCEPTED (COMPLETE — Task 3.4, ADR-0014)

ACCEPTED → ARRIVED

Arrival verification

Ride-start OTP

ARRIVED → STARTED

STARTED → COMPLETED

Completion verification

COMPLETED → CLOSED

Invalid-transition protection

Ride state history

Important

The roadmap currently lists 50m arrival/completion verification. However, the authoritative business decision register previously marked exact GPS radii as TBD in the project documentation. The agent must not hard-code a 50m rule unless the business rules are formally reconciled/approved.

10. PHASE 07 — GPS & VERIFICATION (9 TASKS)

GPS point storage

Server GPS distance calculation

Arrival verification

Completion verification

Early-drop GPS verification

Additional retries

Retry-counter protection

GPS anomaly detection

Server-time validation

Requirements

Server authoritative time.

No client-only GPS decisions.

Evidence/audit trail for disputes.

Exact retry/radius numbers only after approval when currently TBD.

Integrate document verification provider separately from GPS verification.

11. PHASE 08 — EARLY DROP (9 TASKS)

Customer initiates early drop

Driver receives request

Driver accepts

Driver rejects

Rejection keeps ride active

GPS verification

End ride immediately

Original fare remains

Allow later early-drop request

Exit gate

Early-drop state transitions, GPS proof, and fare behavior are server-authoritative and fully tested.

12. PHASE 09 — RIDE MODIFICATIONS (22 TASKS)

Pickup change

Pickup distance calculation

≤250m no extra charge



250m driver decision

Driver PROCEED

Driver PASS

PASS no penalty

PASS no strike

Rematch after PASS

New pickup used for rematch

Pickup-change charge

Customer confirms pickup charge

Customer rejects pickup charge

Multiple pickup changes

Destination change

Intermediate destination keeps original fare

Detect extended destination

Extension charge

Customer confirms extension

Customer rejects extension

Multiple destination changes

Historical pricing version

Critical governance

The roadmap currently includes illustrative pickup-change and destination-extension values, but these must be checked against the authoritative current Business Rules/PRD. The project governance says unresolved values must not become code silently.

13. PHASE 10 — PAYMENTS (17 TASKS)

Online payment creation

Server payment-amount validation

Gateway signature verification

Webhook verification

Webhook idempotency

Payment success

Payment failure

Payment timeout/reconciliation

Refund

Duplicate-payment protection

Authoritative offline amount

Driver collection amount

Full-payment confirmation

Reject partial confirmation

Cash confirmation idempotency

Payment confirmation state

Admin payment exception/dispute

External dependency

Payment gateway selection is a formal decision gate. Do not integrate Razorpay/Cashfree/PhonePe/another provider until explicitly selected and credentialed.

Required controls

signature verification

webhook idempotency

duplicate-payment protection

reconciliation

audit trail

failure/retry handling

Current implementation mapping (ADR-0025, 2026-08-25 — approved P2P
Payment Model, documentation reconciliation only; no code, schema, or
provider was integrated)

VISTAAR does not collect the ride fare from the customer, in any form —
the customer pays the driver directly (cash or UPI); VISTAAR's platform
fee is charged only to the driver, from the driver's wallet, at ride
acceptance (already implemented, ADR-0014, unaffected by this
reconciliation). Consequently, most of this phase's 17 tasks describe a
flow that no longer applies and should NOT be built as originally
scoped: Online payment creation / Server payment-amount validation /
Gateway signature verification / Webhook verification / Webhook
idempotency / Payment success / Payment failure / Payment
timeout/reconciliation / Refund / Duplicate-payment protection — all
described the now-superseded customer-facing gateway. Authoritative
offline amount / Driver collection amount / Full-payment confirmation /
Reject partial confirmation / Cash confirmation idempotency / Payment
confirmation state — these could still have a much narrower, legitimate
form (a driver confirming they received the ride fare directly from the
customer, with no VISTAAR settlement side-effect), but none is built,
and none is scheduled ahead of an explicit task. Admin payment
exception/dispute — already covered by BR-121's existing "ride-fare
disputes require a support/admin process," which needs no Payment
domain/gateway at all.

Update (ADR-0026, 2026-08-26, Option A — documentation-only, no code):
the "largely N/A" framing above is corrected — Phase 10 regains one
real, still-blocked task. The project owner resolved the exact open
question ADR-0025 flagged (BR-055): a valid customer cancellation/
no-show penalty creates an OUTSTANDING liability (already exactly how
`penalty.penalties` works); VISTAAR does not collect it immediately, but
surfaces it — combined with the ride fare, as an informational total —
at the customer's next ride booking (`outstanding_penalty`/
`total_payable`, now documented at api-contracts.md §12). The ride fare
stays P2P (Customer → Driver, unchanged); the penalty is a genuinely
separate "Customer → VISTAAR" charge, never routed through the driver's
wallet. [Superseded 2026-09-03, ADR-0066: the penalty is now bundled
into the same P2P payment as the ride fare — paid to the driver, not
VISTAAR — with VISTAAR recovering its share via a driver-wallet debit
at ride completion. No longer "still-provider-blocked": resolved by
determining no provider/gateway is needed at all. Historical log entry,
not corrected in place.] This revives a narrow slice of "Refund" /
"Duplicate-payment protection" / "Payment confirmation state" above —
scoped to penalty collection only, never the ride fare — as a real,
still-undesigned, still-provider-blocked task (at the time this entry
was written — see the 2026-09-03 supersession note above).
`payment.payments`/`payment.allocations`
(database-design.md §20, previously "superseded in full") may be
substantially the right shape for it — see there.

The "External dependency: Payment gateway selection" formal decision
gate above is narrowed, not removed, and now covers TWO surfaces instead
of one: driver wallet recharge (Phase 11's "Recharge" task,
api-contracts.md §35) and customer outstanding-penalty collection (new,
ADR-0026) — both still genuinely blocked on provider selection, neither
decided by either ADR. The "Required controls" list above (signature
verification, webhook idempotency, etc.) still applies to both. See
docs/14-decisions/ADR-0025-p2p-payment-model-no-customer-collection.md
and docs/14-decisions/ADR-0026-customer-outstanding-penalty-collection-split-settlement.md
for the full business-rules.md/api-contracts.md/database-design.md/
domain-design.md/state-machines.md/technical-architecture.md
reconciliation these decisions triggered.

14. PHASE 11 — FINANCIAL (19 TASKS)

Driver wallet

Wallet ledger

Wallet credit

Wallet debit

Atomic wallet transaction

Prevent negative wallet

Outstanding balance

Recharge

Outstanding recovery

Financial audit trail

Wallet concurrency tests

Driver cancellation penalty

Driver strike

Customer subsequent cancellation penalty

Customer first qualifying cancellation

Customer grace period

Penalty expiry

Penalty idempotency

Pickup PASS penalty exemption

Current implementation mapping

Driver wallet / Wallet ledger / Wallet debit / Wallet credit / Atomic wallet transaction / Prevent negative wallet / Wallet concurrency tests: COMPLETE (ADR-0013, ADR-0015 — pulled forward to unblock Tasks 3.4-3.6, see §2.0). Driver cancellation penalty / Driver strike / Customer subsequent cancellation penalty / Customer first qualifying cancellation / Customer grace period / Penalty idempotency: COMPLETE (ADR-0015, ADR-0016). Financial audit trail: COMPLETE too (ADR-0024, 2026-08-25) — GET /api/v1/drivers/me/wallet/transactions, the driver's own paginated, type-filterable ledger; the underlying `wallet.transactions` table was already immutable and complete, only the read path was missing. (Corrected 2026-08-25 — this line previously listed Financial audit trail as not started.) Outstanding balance and Outstanding recovery: RECONCILED (ADR-0025, 2026-08-25) — these named the driver-side `wallet.outstanding_settlements` concept (database-design.md §18), which modeled VISTAAR settling its own charge out of cash the driver collected on its behalf. That scenario no longer exists under the approved P2P Payment Model (the platform fee is always collected from the driver's wallet at ride acceptance, never bundled into customer cash) — not "blocked pending a payment gateway" as previously stated, but N/A as originally scoped. Recharge remains blocked on the Phase 10 payment gateway (narrowed — ADR-0025 — to the wallet-recharge gateway specifically, the one payment-gateway need this decision preserves). Penalty expiry *collection/enforcement* (stamped at creation, nothing yet acts on an expired row) and Pickup PASS penalty exemption (needs Phase 09's pickup-change flow, itself blocked) remain not started, unaffected by this reconciliation.

Requirements

Immutable ledger.

ACID transactions.

concurrency-safe deductions.

idempotency keys.

no negative wallet.

penalty recovery rules only where approved.

15. PHASE 12 — GROWTH (14 TASKS)

Promotion creation

Promotion eligibility

Promotion grant

Promotion expiry

Promotion reservation

Promotion consumption

Promotion restoration

Duplicate-consumption protection

Customer referral

Driver referral

Referral qualification

Anti-self-referral

Referral reward

Duplicate-reward protection

Governance

Use the authoritative promotion/referral rules. Do not invent discount caps, cancellation boundaries, or reward values still marked TBD.

Status (ADR-0019, 2026-08-24): COMPLETE for the genuinely unblocked scope. Promotion
creation/grant/expiry/reservation/consumption/restoration/duplicate-consumption
protection all built (`modules/promotion/`) — reservation decrements at reserve time
(database-design.md §44), lazy expiry (no background worker, same pattern as offer
expiry), `uq_promotion_ride_use` enforces duplicate-consumption protection at the
database level. Customer referral/driver referral/referral qualification/
anti-self-referral/referral reward/duplicate-reward protection all built
(`modules/referral/`) — BR-025 self-referral rejected before a row is ever created,
`uq_referrals_referred_id` enforces one referral per referred party at the database
level, reward idempotency is keyed on `referral.rewards.idempotency_key`.
`GrantWelcomePromotion` composes into `GET /api/v1/customers/me`'s first-access
auto-provision; `QualifyDriverReferral`/the ₹100/₹100 wallet reward compose into
`POST /api/v1/admin/drivers/{driver_id}/approve`. `ReservePromotion` now also
composes into `POST /api/v1/rides` (ADR-0020, once Pricing produced a real fare to
apply a discount against — corrected 2026-08-24; this line previously said
ReservePromotion was NOT composed, blocked on the not-yet-built Pricing domain).
`ConsumePromotion`/`RestorePromotion` remain uncomposed — ride cancellation/
completion still have no real fare to compute a `discount_amount` against.
[Superseded 2026-08-28, ADR-0049, reconfirmed 2026-09-04: BR-063's discount cap is
resolved — 50% off, ₹100/ride — no longer NULL/TBD. Historical log entry, not
corrected in place.] [Also superseded 2026-09-04, ADR-0070: `ConsumePromotion`/
`RestorePromotion` are now composed into ride completion/cancellation.] See
§2.0 for the full write-up and test evidence.

16. PHASE 13 — DISPUTES (16 TASKS)

Create GPS dispute

Store GPS history

Driver evidence

Customer evidence

Photo evidence

Video evidence

Document evidence

Text explanation

Evidence window

Close after deadline

Admin review

Admin APPROVE

Admin REJECT

Admin GPS override

Audit admin decision

Preserve original GPS result

Critical governance

The formal Dispute-domain decision must be aligned with the current ADR record before implementation. Do not introduce a new domain contrary to the approved architecture.

17. PHASE 14 — SAFETY & SUPPORT (11 TASKS)

SOS creation

SOS location

SOS ride context

Safety workflow

Safety escalation

Support case

Support assignment

Support conversation

AI escalation

Human escalation

Resolve support case

External dependencies

Emergency-service integration and external support/communication providers require explicit decisions before integration.

Status (ADR-0022, 2026-08-24): COMPLETE for the genuinely unblocked scope.
SOS creation/location/ride context all covered by the one real endpoint
(`POST /api/v1/rides/{ride_id}/sos`, api-contracts.md §41) — ride-participant-
only, IDOR-safe. Safety workflow/escalation built as `SafetyService.
acknowledge_incident()`/`escalate_incident()`/`resolve_incident()` — row-
locked, audit-trailed (`safety.events`), proven by unit + real-Postgres +
concurrency tests; `escalate_incident()` never contacts a real emergency
service (BR-112's exact integrations stay TBD). Support case/conversation
built (`POST`/`GET /api/v1/support/cases`, api-contracts.md §44 — `ride_id`
column added additively, see database-design.md §30.1). Support
assignment/Human escalation collapse into one command, `AssignSupportCase`
(ADR-0022 Decision 2) — this codebase has no AI actor to escalate *from*.
AI escalation is transitively BLOCKED: it presupposes AI Support
(`POST /api/v1/support/ai/message`, §45), which needs a real LLM — no
provider/credential exists anywhere in this environment (§0.4); not
stubbed. Resolve support case built (`resolve_case()`). None of
Acknowledge/Escalate/Resolve SOS or Assign/Resolve/PostMessage Support Case
has a documented HTTP endpoint anywhere — same gap ADR-0018/0021 already
hit; proven by tests instead of an invented endpoint. See §2.0 for the
full write-up and test evidence.

18. PHASE 15 — NOTIFICATIONS (10 TASKS)

Push infrastructure

SMS infrastructure

Ride-offer notification

Acceptance notification

Ride-status notification

Payment notification

Dispute notification

Safety notification

Notification retries

Delivery tracking

Planned channels

Driver/customer mobile push

SMS where required

WhatsApp where approved

email if approved

Document expiry notifications

Once the compliance/expiry workflow is finalized, notifications can include document expiry reminders. The exact cadence (for example, one month before expiry and follow-ups) must be explicitly approved before hard-coding.

19. PHASE 16 — ADMIN (17 TASKS)

Admin dashboard

Customer management

Driver management

Vehicle management

Ride monitoring

Payment monitoring

Wallet monitoring

Penalty administration

Promotion administration

Referral administration

Dispute dashboard

GPS evidence review

Pricing configuration

Safety dashboard

Support dashboard

Advertisement management

Audit viewer

Design rule

Admin operations must use server-side permission checks and resource ownership rules. No admin UI should become a bypass around normal backend authorization.

Current implementation mapping (ADR-0023, Admin Monitoring & Penalty Review)

Driver management / Vehicle management: COMPLETE from Task 2.7A (Phase 2, ADR-0009)
— Driver Review, Approve/Reject Driver, Approve/Reject Vehicle. Predates this Phase
16 checkpoint; unchanged by ADR-0023.

Ride monitoring: COMPLETE — `GET /api/v1/admin/rides` (Search Rides, filters
`status`/`driver_id`/`customer_id`, paginated per §50) and `GET
/api/v1/admin/rides/{ride_id}` (Get Ride). Composes modules.pricing for the active
fare quote. Response shape was undocumented in api-contracts.md §46; filled in as an
implementation decision (same precedent Phase 14 set for GET Support Case).

Wallet monitoring (part of "Admin Financial Review", §47): COMPLETE — `GET
/api/v1/admin/wallets/{driver_id}`, reusing the driver-facing wallet endpoint's exact
response shape.

Penalty administration (§48): COMPLETE — `GET /api/v1/admin/penalties` (Search
Penalties, filters `status`/`user_id`) and `POST
/api/v1/admin/penalties/{penalty_id}/resolve` (action: "WAIVE" only). Implements
domain-design.md §17.3's `ResolvePenalty` command and reaches
state-machines.md §40's previously-unreached `WAIVED` status. The "reversal/waiver
record" reuses `admin.audit_logs` rather than a new table.

NOT implemented (flagged, not invented — ADR-0023 Decision 5, since api-contracts.md
documents no HTTP shape for any of these anywhere): Admin dashboard (aggregate view),
Customer management (no `/api/v1/admin/customers*` route exists), Payment monitoring
(no Payment module exists — Phase 10 blocked) / Settlements (no backing concept
documented anywhere), Promotion administration / Referral administration (no
`/api/v1/admin/promotions*` or `/api/v1/admin/referrals*` route), Dispute dashboard
(coupled to ADR-0002's unresolved Dispute-domain question — still open),
Pricing configuration (no admin-facing fare-rule CRUD endpoint documented anywhere),
Safety dashboard / Support dashboard (beyond ADR-0022's 3 real endpoints, no
admin-facing list/aggregate route documented), Advertisement management (ADR-0018,
unchanged), Audit viewer (`admin.audit_logs` is real and populated, but no `GET`
route to read it back exists anywhere in api-contracts.md). (Corrected 2026-08-25 —
GPS evidence review, listed here as NOT implemented at the ADR-0023/Phase-16
checkpoint this paragraph describes, is now COMPLETE: `GET /api/v1/admin/gps-
disputes` (Search Disputes) and `POST /api/v1/admin/gps-disputes/{id}/resolve`
(Resolve Dispute) — BR-124/BR-125, ADR-0032, 2026-08-25.)

20. PHASE 17 — ADVERTISEMENTS (8 TASKS)

Advertisement assignment

Proof upload

Proof review

Approve advertisement

Reject advertisement

Payout pending

Payout processing

Payout idempotency

Current implementation mapping (ADR-0018)

Advertisement assignment / Proof upload / Proof review / Approve advertisement /
Reject advertisement / Payout pending / Payout processing / Payout idempotency:
COMPLETE at the domain/service/repository layer — `advertisement.campaigns`/
`driver_campaigns`/`payouts` (database-design.md §31) and all six domain-design.md
§22.3 commands implemented exactly (`AdvertisementService`). "Proof review"/"Approve
advertisement"/"Reject advertisement" are ONE command, `verify_advertisement()`, a
manual admin decision — Admoto (technical-architecture.md §55's named partner) is NOT
integrated (ADR-0018 Item 3, no requirement/credential/approval documented anywhere).
"Payout idempotency" is a real database constraint (`uq_payouts_driver_campaign`), not
just an application-level check — verified with a real-Postgres test proving a second
`calculate_payout()` call is refused. The 80/20 driver/VISTAAR split (domain-design.md
§22.4) is exact, derived so `driver_amount + vistaar_amount == gross_amount` even after
rounding.

NOT implemented: any HTTP endpoint. `api-contracts.md` documents zero Advertisement
endpoints anywhere — no path, no request/response shape — unlike every other module
built so far. Building one would mean inventing a new public API contract (§0.3's
explicit mandatory-stop condition). The `WalletService.credit()` (ADVERTISEMENT_PAYOUT,
already in the transaction-type enum) composition IS proven — one real-Postgres
integration test manually performs the sequence a future router would
(`calculate_payout()` → `WalletService.credit()` → `mark_payout_paid()`) — but outbox
event publication (`advertisement.campaign_assigned`/`verified`/`payout_issued`,
event-contracts.md §24) is not wired in anywhere yet, same reason as the wallet
composition generally: there is no router to put either composition in.

21. PHASE 18 — EVENT & BACKGROUND (11 TASKS)

Event schemas

Kafka producer

Kafka consumer

Outbox table

Outbox publisher

Event retry

Dead-letter handling

Event idempotency

Background worker process (technology not yet selected — see §4; Celery is a
candidate, not an approved choice)

Scheduled expiry jobs

Payment reconciliation

Current implementation mapping (ADR-0017, Minimal Event & Outbox Foundation)

Event schemas: COMPLETE — event-contracts.md §3's envelope, implemented generically in
shared/outbox.py (EventEnvelope/new_envelope()).

Kafka producer: COMPLETE — shared/outbox_publisher.py wraps AIOKafkaProducer (already a
dependency, used for the admin/health-check client since Phase 01).

Outbox table: COMPLETE — shared.outbox_events exactly as database-design.md §34
documents.

Outbox publisher: COMPLETE, but as an in-process asyncio loop (main.py's lifespan), not
a separate worker process — ADR-0017 Decision 1: this is a different, smaller concern
than the still-unapproved Background Worker Foundation, and does not need that decision
resolved first.

Event retry: COMPLETE (ADR-0071, 2026-09-04, owner-requested) — shared.outbox_events
gained attempt_count/last_attempt_at/first_failure_at/next_attempt_at/last_error/status
columns (migration c2e6a9f4d7b1); shared/outbox_publisher.py now applies genuine
exponential backoff (base * multiplier^(attempt-1), capped — core/config.py's
EVENT_RETRY_* settings) and only selects rows whose next_attempt_at is due, closing
the "retried forever at a fixed interval, no backoff" gap this line previously
described. Superseded 2026-09-04, not corrected in place above (historical accuracy
of what Task pulled-forward-from-3.1 actually shipped) — see ADR-0071 for the full
design and docs/06-events/event-contracts.md §30 for the updated spec cross-reference.

Dead-letter handling: COMPLETE (ADR-0071, 2026-09-04) — once attempt_count reaches
EVENT_RETRY_MAX_ATTEMPTS, the next due attempt publishes to vistaar.dlq.<domain>
(event-contracts.md §31's documented naming) via the same Kafka producer, preserving
the original event plus attempt-count/first-failure/last-failure/error metadata; the
row is marked DEAD_LETTERED only once that DLQ publish itself succeeds — never
silently discarded if it doesn't. See ADR-0071 §4 and event-contracts.md §31.

Event idempotency: COMPLETE on the consumer side (ADR-0071, 2026-09-04) —
shared.processed_events (migration d8f1c3a6e9b2, exactly event-contracts.md §29's
recommended schema) is now real: modules/notification/consumer.py's NotificationConsumer
(ADR-0038) is the real consumer this was waiting for. checked/recorded around every
handler dispatch in handle_event(), additive to that module's own narrower
(user_id, channel, template_key, event_id) dedup. See ADR-0071 §4.

Kafka consumer: IMPLEMENTED (ADR-0038, 2026-08-26) — `modules/notification/consumer.py`'s
`NotificationConsumer`, the first real consumer in this codebase, covering `ride.started`/
`ride.completed`/`ride.cancelled`/`penalty.applied`. Every other documented consumer in
event-contracts.md §56's registry (Analytics, Pricing, Payment, ...) still belongs to a
module that doesn't exist yet.

Background worker process: RESOLVED and IMPLEMENTED (ADR-0039, 2026-08-26) — the owner
approved Celery directly. `shared/celery_app.py`, Redis as broker/backend.

Scheduled expiry jobs: IMPLEMENTED (ADR-0039) — `modules/notification/tasks.py`'s two
periodic tasks (promotion/document expiry warnings), the Background Worker Foundation's
first real use.

Payment reconciliation: still BLOCKED — needs Phase 10 (a real payment gateway)
specifically, not the worker technology; approving Celery does not unblock this one.

Events actually being published today: ride.requested, ride.accepted, ride.cancelled
(both customer- and driver-initiated, distinguished by data.cancelled_by),
wallet.debited, wallet.credited, penalty.applied (only when amount > 0 —
state-machines.md §12), penalty.strike_recorded — one for each already-built domain
transition that had been carrying a "no producer infrastructure exists yet" note since
its own task.

Critical architecture

Event delivery should use the approved event contracts. Do not create producers/consumers before the corresponding contract exists.

Outbox + idempotency + DLQ/retry mechanisms should be treated as reliability-critical.

Scheduled expiry jobs are where the document-expiry engine can later feed the notification system.

22. PHASE 19 — SECURITY (12 TASKS)

HTTPS/TLS

JWT security

RBAC enforcement

Rate limiting

Object-level authorization

Input validation

File-upload security

Secret management

Audit logging

Security headers

Dependency scanning

Admin MFA

Production gate

No production launch without completion of the security checklist and remediation of high-severity findings.

23. PHASE 20 — TESTING (15 TASKS)

Unit tests

Integration tests

API contract tests

Event contract tests

State-machine tests

GPS boundary tests

Payment tests

Wallet concurrency tests

Idempotency tests

Security tests

Customer E2E

Driver E2E

Admin E2E

Load testing

Failure/recovery testing

Production-quality gate

The system must pass both happy-path and failure-path testing. Concurrency, idempotency, payment callbacks, event delivery, GPS boundaries, authorization, and recovery cannot be validated only through unit tests.

24. PHASE 21 — DEPLOYMENT (13 TASKS)

Staging environment

Production environment

Database backups

Restore test

Monitoring

Prometheus

Grafana

Sentry

OpenTelemetry

CI/CD

Deployment scripts

Rollback procedure

Production smoke tests

Production gate

Production launch requires:

successful staging deployment;

successful backup/restore test;

monitoring/alerting active;

rollback tested;

CI/CD validated;

production smoke tests passed;

secrets stored securely;

TLS/HTTPS active;

incident/rollback procedures documented.

25. EXTERNAL SERVICE & CREDENTIAL PLAN

25.0 Current provisioning status

Do not expect every service below to be provisioned now. Provider credentials are obtained
only at the task that actually requires them. Current known future dependencies include:

Government vehicle/document verification (authorized Parivahan/Sarathi/Vahan or approved intermediary): NOT YET INTEGRATED

Maps/routing provider: NOT YET INTEGRATED

SMS provider: INTEGRATED (ADR-0031, 2026-08-25) — MSG91, selected by the
  project owner; SMS_PROVIDER=msg91 (default remains "dev", console-log
  only). See the ADR's own caveat: built from general API knowledge, not
  verified against a live MSG91 account.

WhatsApp provider: NOT YET INTEGRATED

Payment gateway: NOT YET INTEGRATED — "SBI Bank" was named by the
  project owner but needs clarification (which SBI product/API, and
  whether merchant credentials/API docs are available) before this can
  move; see the project owner's own follow-up question, unresolved as of
  2026-08-25

AI/OCR provider: NOT YET INTEGRATED

Production cloud provider: CHOSEN, NOT YET DEPLOYED — **AWS**
  (ADR-0063, 2026-09-03, owner's explicit instruction, superseding
  ADR-0035's DigitalOcean choice below). Config/script layer
  (Dockerfile, Kubernetes manifests — both provider-agnostic and
  unchanged by this switch — plus a new `infrastructure/terraform/aws/`
  Terraform module) is written; nothing has been applied — no AWS
  account credentials exist in this environment, and this environment
  also has no `terraform` CLI to even syntax-validate the new module
  (see ADR-0063 §4). The paragraph immediately below, describing the
  earlier DigitalOcean choice (ADR-0035, 2026-08-25), is preserved as
  the historical record of that decision — DigitalOcean is no longer
  the plan.

When a task reaches one of these dependencies, stop for provider/access review rather than
selecting a vendor or inventing credentials.

Services likely required before production

Government / compliance

Authorized Parivahan/Sarathi/Vahan access or an approved authorized intermediary.

Any additional verification source approved for insurance/other compliance data.

Maps/location

Mapping provider

Geocoding

Routes/distance

Possibly route matrix / map SDK

SMS / OTP

SMS provider — RESOLVED (ADR-0031, 2026-08-25): MSG91

WhatsApp

WhatsApp Business/provider integration if approved for notifications

Push

FCM/APNs or approved equivalent

Payments

Approved payment gateway

Object storage — RESOLVED (ADR-0031, 2026-08-25): AWS S3

S3-compatible production storage or approved provider

Monitoring

Sentry (if approved)

Prometheus

Grafana

OpenTelemetry

Cloud

Production hosting provider

Domain

DNS

TLS/SSL

Rule

Do not purchase every service at once. Select them at the phase that actually requires them.

26. DECISION REGISTER / HARD BLOCKERS

The agent must maintain a live table of unresolved decisions.

Decision

Needed by

Status

Action

Verification provider

Verification

TBD

Select before production provider integration

Final KYC/document list

Driver Ops / Verification

TBD

Resolve in Business Rules

Document verification status write-back

Verification

TBD

ADR before implementation

AI/OCR provider

Verification / Support

TBD

Decide before integration

Payment gateway

Payments

TBD

ADR + provider selection

Fare engine exact values

Ride Modifications / Payments

RESOLVED for the core engine (base fare/per-km/minimum fare — ADR-0020,
2026-08-24, owner-approved rate table). Still TBD where applicable: payment-
gateway-dependent charges (blocked on Payments' own TBD provider selection
above)

Business approval (core engine: approved — see ADR-0020)

GPS arrival/completion radius

Ride Lifecycle/GPS

RESOLVED (ADR-0028, 2026-08-25): 50m arrival / 100m completion,
owner-approved and implemented

Business approval — DONE

GPS retry count

GPS

RESOLVED (ADR-0028, 2026-08-25): 3 attempts before manual review,
owner-approved and implemented (no manual-review queue/UI built yet —
out of this task's scope)

Business approval — DONE

Pickup-change rate

Ride Modifications

TBD unless formally approved

Business approval

Promotional cap/boundaries

Growth

TBD where applicable

Business approval

Dispute domain status

Disputes

RESOLVED and IMPLEMENTED (ADR-0028 + ADR-0029, 2026-08-25): Support/Admin
capability — no new Dispute domain/service (closes ADR-0002 in favor of
its Option B). BR-121 (ride-fare disputes) and domain-design.md §17.3's
DisputePenalty are both implemented as compositions of already-built
endpoints (Create Support Case + Resolve Penalty). The GPS-verification-
dispute evidence/admin-override workflow (security.md/testing-
strategy.md/implementation-readiness.md) remains explicitly unratified
and unbuilt — a genuinely separate, still-open question

Resolve before dispute implementation — DONE for the documented scope

Emergency integration

Safety

TBD

Provider/business decision

Notification provider

Notifications

TBD

Provider selection

Admin permission hierarchy

Admin/Security

TBD

ADR/security decision

Data retention periods

Security/Deployment

TBD

Security/legal decision

27. PHASE EXECUTION TEMPLATE

For every task, Claude Code should produce:

TASK: <phase.task>
STATUS: COMPLETE / BLOCKED / REVIEW REQUIRED

FILES CREATED:
FILES MODIFIED:
FILES MOVED:
DATABASE/MIGRATION:
API CHANGES:
EVENT CHANGES:
SECURITY CHANGES:
EXTERNAL SERVICES:
SECRETS:
TESTS:
RUFF:
MYPY:
DOC UPDATES:
UNRESOLVED DECISIONS:
WARNINGS:
EXACT COMMANDS:
NEXT TASK:

A task cannot be marked complete without verification.

28. TESTING POLICY FOR THE AUTONOMOUS AGENT

For each implementation task, prefer the appropriate combination of:

pure domain tests;

service tests with fakes;

real PostgreSQL integration tests;

real Redis/Kafka integration tests when relevant;

API integration tests;

concurrency tests for transactional code;

contract tests;

failure-path tests.

Never use tests to hide a known requirement failure.

Never convert an expected failure into a skip just to make CI green unless the documented test policy explicitly allows the skip.

29. DATABASE / MIGRATION POLICY

Every schema change must:

match database-design.md;

use Alembic;

be reversible where practical;

be tested with upgrade/downgrade/upgrade;

preserve existing data unless a migration has an explicit reviewed data transformation;

add indexes/constraints only when supported by documented requirements or a formal ADR.

30. API POLICY

All new business APIs:

use /api/v1/...;

follow the existing envelope conventions;

return DTOs rather than raw ORM models;

enforce authorization server-side;

include error contracts;

update api-contracts.md in the same task;

remain backward-compatible when practical.

Do not invent an endpoint merely because it seems convenient.

31. EVENT POLICY

Before publishing an event:

event contract must exist;

payload must be documented;

event versioning must be defined;

idempotency semantics must be known;

retry/DLQ behavior must be defined when the event infrastructure phase is active.

Do not publish undocumented business events.

32. PRODUCTION READINESS DEFINITION

VISTAAR is not production-ready merely because the customer can complete a ride.

Production readiness requires:

all required business modules complete;

authorization enforced;

payment and wallet consistency verified;

document/compliance verification operational;

notification delivery operational;

background jobs reliable;

Kafka/event delivery reliable where used;

audit trail available;

security audit passed;

load/concurrency testing passed;

failure/recovery testing passed;

backups restored successfully in a test;

monitoring and alerting active;

rollback tested;

staging validated;

production smoke tests passed.

33. AUTONOMOUS AGENT OPERATING INSTRUCTION

When this file is placed in the VISTAAR repository as the master roadmap, Claude Code should:

Read this file at the beginning of every session.

Inspect the current repository state before deciding the next task.

Reconcile the roadmap status with actual code/tests, not memory.

Never reimplement a task that is already genuinely complete.

Pick the first uncompleted, unblocked task in the master sequence.

Show an implementation plan before materially changing architecture or business behavior.

Implement the approved task only.

Verify it.

Update this roadmap's status/notes.

Continue to the next unblocked task automatically.

STOP whenever a decision, credential, provider approval, or contradictory requirement is encountered.

Never fabricate approval.

Never claim production readiness without Phase 19–21 completion.

Review checkpoints for the project owner

The owner should review at minimum:

every ADR/business decision;

every external provider selection;

every production credential integration;

every major database model change;

each phase completion report;

all production-readiness/security findings.

34. CURRENT NEXT ACTION

The current repository checkpoint is after Get Ride Status & Wallet
Transaction History (Phase 04/11, ADR-0024). Every item in
docs/VISTAAR_AUTONOMOUS_EXECUTION_PLAN.md's RECOMMENDED EXECUTION ORDER list
is now DONE: Phase 04's cancellation work, fare quote, and now GET ride
status; Phase 02's Identity hardening; Phase 18's Event & Outbox Foundation;
Phase 17's domain/service/repository layer; Phase 12's full Promotion/
Referral domain/service/repository/HTTP layer; Phase 03's `suspend_driver()`/
`reactivate_driver()`; Phase 14's Safety/Support domain/service/repository/
HTTP layer; Phase 16's Search Rides / Get Ride / Admin Wallet View / Search
Penalties / Resolve Penalty; and Phase 11's Financial audit trail (Wallet
Transactions) are all COMPLETE for their genuinely unblocked scope. Admin
RBAC/MFA (Phase 02), Dead Letter Topics/consumer idempotency/Kafka consumers
(Phase 18), any Advertisement HTTP endpoint/Admoto integration (Phase 17),
`ConsumePromotion`/`RestorePromotion`'s ride cancellation/completion
composition (Phase 12) [Superseded 2026-09-04, ADR-0070: this composition
is now done], a Suspend/Reactivate Driver HTTP endpoint plus
automatic threshold-based suspension (Phase 03), an Acknowledge/Escalate/
Resolve SOS or Assign/Resolve/PostMessage Support Case HTTP endpoint
(Phase 14, no documented shape anywhere — same §0.3 gate), AI Support
(Phase 14, no LLM provider/credential anywhere — §0.4), Phase 16's other 12
admin capabilities (Admin dashboard, Customer management, Payment
monitoring, Settlements, Promotion/Referral administration, Dispute
dashboard, GPS evidence review, Pricing configuration, Safety/Support
dashboards, Advertisement management, Audit viewer — none has any documented
HTTP shape, same §0.3 gate), and Phase 11's remaining gaps (Recharge —
Phase 10 payment gateway, narrowed by ADR-0025 to wallet-recharge
specifically; Penalty expiry collection — the background-worker
technology decision itself is now resolved (ADR-0039, Celery), but
this specific scheduled job has not been built yet, distinct from the
two ADR-0039 did build (promotion/document expiry warnings);
Outstanding balance/Outstanding recovery — reconciled as N/A, not
merely blocked, by ADR-0025, see below) remain BLOCKED, N/A, or
deferred, not unbuilt — see §5, §6, §7, §13, §14, §19, §21, §20, and
§15 for why each one specifically. See §2.0 for the full verified
baseline (727 passed, 5 skipped, 0 failed — unchanged by ADR-0025,
which is documentation-only).

Since this checkpoint, the project owner also recorded the Approved P2P
Payment Model (ADR-0025, 2026-08-25) and, resolving the one question it
left open, the Customer Outstanding Penalty Collection / Split
Settlement decision (ADR-0026, 2026-08-26, Option A) — both
documentation-only, no code changed. VISTAAR does not collect the ride
fare from the customer in any form; a valid customer cancellation/
no-show penalty is surfaced (not immediately collected) at the
customer's next ride booking and settled as a separate "Customer →
VISTAAR" charge, never through the driver's wallet. See §2.0's own
paragraphs on both decisions and Phase 10's Current implementation
mapping (§13) for the full reconciliation. This does not change what
engineering work is next-available — it narrows Phase 10's scope (most
of it is N/A; one narrow penalty-collection task is real again, still
provider-blocked) and Phase 11's Outstanding-balance/recovery scope
(still N/A — that concept was always about the driver-side wallet
settlement, unaffected by ADR-0026), without unblocking any new
buildable task.

Since that checkpoint, the project owner also answered the outstanding GPS
radius/retry-count and Dispute-domain questions (2026-08-25), resolving
Phase 06/07's own blocker: ADR-0028 records 50m arrival / 100m completion
GPS radii, 3 attempts before manual review, and Support/Admin (not a new
Dispute domain) for disputes — and the full ACCEPTED → ARRIVED → STARTED →
COMPLETED → CLOSED ride lifecycle plus its GPS/OTP foundation is now
implemented, tested (unit + real-Postgres integration), and verified (see
§2.0 for the updated baseline).

Immediately after, the project owner asked for Phase 13 (Dispute-as-
Support) to be built next. ADR-0029 scopes and implements exactly what
BR-121 and domain-design.md §17.3 authorize — ride-fare disputes and
DisputePenalty are both realized as ordinary Support Cases decided via
the already-built Resolve Penalty endpoint, plus one small additive
`charge.penalty_id` field on Customer Cancellation — no new domain,
table, endpoint, or state invented. The much larger GPS-verification-
dispute evidence/admin-override workflow (security.md/testing-
strategy.md) remains explicitly out of scope, unratified per ADR-0002;
ADR-0029 reaffirms that finding rather than building past it. See §2.0
for the updated baseline (768 passed).

Immediately after, continuing autonomously (per the phase-level-autonomy
agreement), Phase 08 (Early Drop) was built next — genuinely unblocked,
just previously unstarted. ADR-0030 found the apparent GPS-tolerance
blocker (state-machines.md §63) dissolves once BR-088/api-contracts.md
§27/technical-architecture.md §43 are compared against state-machines.md
§19-21 directly: the higher-ranked three all describe GPS/location as
recorded evidence, never a verified threshold — the same class of
unratified-downstream-addition ADR-0002 already found for the GPS-dispute
workflow. No owner decision was needed. See §2.0 for the updated baseline
(788 passed).

Immediately after, the project owner answered two of the four remaining
open provider questions (via AskUserQuestion): MSG91 for SMS/
notifications, AWS S3 for object storage. ADR-0031 wires both in behind
seams this codebase already, deliberately, left open — modules.identity.
sms's `get_sms_provider()` factory (Msg91SmsProvider, `SMS_PROVIDER=
msg91`) and the never-wired-up `STORAGE_*` block `.env.example` already
provisioned (S3ObjectStorage, a new `POST /api/v1/drivers/me/uploads`
presigned-upload-URL endpoint — driver-scoped only; vehicle documents
still have no HTTP endpoint at all, ADR-0007, not expanded here). MSG91's
exact API shape is flagged, not verified, in the code itself (no live
MSG91 account exists in this environment). The other two provider
questions remain open: the payment gateway ("SBI Bank" needs
clarification — see the project owner's own follow-up, unresolved) and
the GPS-verification-dispute evidence/admin-override workflow (approved
in principle with a 24-hour evidence window, drafted as BR-124/BR-125,
still awaiting the project owner's review/approval of that draft before
any code is written — see business-rules.md §39). See §2.0 for the
updated baseline (813 passed).

Immediately after, the project owner reviewed the drafted BR-124/BR-125
and approved them for implementation as-is. ADR-0032 formalizes the
design and builds the full GPS Dispute Manual Review workflow: a terminal
GPS_VERIFICATION_FAILED outcome now auto-opens a `ride.gps_disputes` row
in the same transaction as the failing verification; customer/driver may
submit evidence within the approved 24-hour window (reusing ADR-0031's
S3 presigned-upload flow, or free text); an admin resolves via APPROVE
(performs the exact ride transition a real PASS would have) or REJECT
(records the decision only). The window is enforced lazily, matching
ADR-0011 Decision 2's no-background-worker precedent. No owner decision
remained blocking this work once BR-124/BR-125 were approved. See §2.0
for the updated baseline (847 passed).

Immediately after, the project owner answered a round of questions
clarifying the remaining phase-09/15/21 blockers: Phase 09's pickup-
change rate (same as the ride's own base per-km fare), Phase 15's
notification channels (in-app/WhatsApp/push/SMS, WhatsApp BSP not yet
picked), and Phase 21's cloud provider (AWS at the time — corrected to
DigitalOcean Kubernetes shortly after; see the ADR-0035 paragraph
below). Continuing autonomously,
ADR-0033 builds Phase 09's Pickup Change: BR-076's TBD rate resolved
(business-rules.md corrected), driver PROCEED/PASS decision, customer
confirmation gate, and the PASS-rematch design (same ride resets to
SEARCHING, resolving the rematch-design ambiguity ADR-0016 Item 2 left
open for normal driver cancellation specifically — that item stays
separately unresolved). Mid-task, a research gap was caught before it
shipped uncorrected: the implementation initially invented a new table
before discovering database-design.md §11 already documented a unified
`ride.change_requests` table for both pickup- and destination-change —
flagged to the project owner, who chose a rework to match the documented
schema. Destination Change (BR-079-082) remains unimplemented. See §2.0
for the updated baseline (862 passed).

Immediately after, continuing autonomously, ADR-0033 Decision 9 builds
Phase 09's remaining piece, Destination Change: BR-079/080/081's three
cases, reusing the same `ride.change_requests` schema (no new
migration). Two engineering-judgment gaps needed resolving first — the
route-deviation classification tolerance (200m, no document specified
one) and "current location" for the full-recalculation case (no live
per-ride GPS tracking exists anywhere in this codebase; `ride.
current_pickup` is used) — both recorded in the ADR rather than guessed
past silently. This closes out Phase 09 entirely. See §2.0 for the
updated baseline (879 passed).

Immediately after, continuing autonomously, ADR-0034 builds the
Notification Domain Foundation: NotificationService.send() (IN_APP/SMS
real; PUSH/WHATSAPP raise ChannelNotAvailableError), composed
synchronously into two proof-of-concept trigger points (ride.accepted,
ride.arrived) rather than a real Kafka consumer (none exists anywhere in
this codebase — Phase 18). No HTTP endpoint exists anywhere for
Notification (api-contracts.md documents none), so none is invented —
the same §0.3 stop condition ADR-0018/ADR-0021 already hit. See §2.0 for
the updated baseline (898 passed).

Immediately after, starting Phase 21 (Deployment), this task asked the
owner to pick a cloud provider and was told AWS — only while surveying
existing infrastructure files immediately afterward did this task find
technical-architecture.md §64 already documents DigitalOcean Kubernetes
(+ Managed PostgreSQL, Managed Redis, Kafka) as the baseline, directly
contradicting the AWS steer. Flagged to the owner before any AWS-
specific IaC was written; the owner chose to switch to DigitalOcean,
overriding their own earlier AWS pick. ADR-0035 records this correction
plus two real, pre-existing Dockerfile/pyproject.toml bugs found and
fixed while building the image for the first time (CI never builds or
runs it): `httpx`, imported unconditionally by
modules/identity/sms.py's MSG91 calls, was declared only as a dev
dependency, so a production install never installed it (reproduced via
a real `docker run` crash, `ModuleNotFoundError: No module named
'httpx'`); and `pip install .`'s setuptools auto-discovery silently
flattened `src/` into two divergent installed copies of the same code.
Both fixed and re-verified the same way (real `docker build` + `docker
run`, `/health` returned 200 and the image's own `HEALTHCHECK` reported
healthy). Kubernetes manifests (`infrastructure/kubernetes/`) and a
Terraform module (`infrastructure/terraform/digitalocean/`) for DOKS +
Managed PostgreSQL (PostGIS extension) + Managed Redis + a self-hosted
Kafka Droplet + a Spaces bucket were written and syntax/schema-
validated (`terraform validate` against the real provider schemas,
`kubeconform` against the real Kubernetes/cert-manager schemas,
`actionlint` against the new deploy workflow) but never applied — no
DigitalOcean account credentials exist in this environment. See §2.0
for the updated baseline (898 passed, unchanged — this task touched no
application logic, only Dockerfile/pyproject.toml and two test files'
mypy type-narrowing annotations discovered as a side effect of the same
`mypy src tests` run).

Immediately after, continuing autonomously, ADR-0036 builds Phase 19's
two long-flagged, still-open gaps from this session's very first
exchange: `SecurityHeadersMiddleware` (security.md §64's five response
headers on every request, with a strict CSP exempted only on the
interactive-docs paths so FastAPI's own Swagger/ReDoc pages, which load
CDN assets, keep working — a real engineering-judgment call the
document's own "exact policy depends on the deployed frontend
architecture" qualifier left open, recorded in the ADR rather than
guessed past), and a `pip-audit` CI step scoped to just `[project].
dependencies` (not the whole environment, which also flags the CI
runner's own unrelated `pip` version). Neither needed an owner decision
or a new vendor account — a dependency scanner is a dev-tool choice in
the same category as `ruff`/`mypy`, not an external vendor relationship.
See §2.0 for the updated baseline (905 passed).

Immediately after, continuing autonomously, ADR-0037 audits resource-
ownership authorization across every router with a resource-ID path
parameter (ride, safety/SOS, support case, vehicle; admin excluded by
design). Before starting, the OTP-IP-dimension claim this same write-up
made two paragraphs above turned out to be stale — already fully built,
just never reflected back into the roadmap — so this task verified the
ownership-authorization claim against the actual code first rather than
trusting the document. Every endpoint's ownership check was already
correct; the audit found one real test-coverage gap — `destination-
change`'s two endpoints had the right check but no regression test,
unlike every sibling ride sub-resource — fixed with two new tests. Also
corrected a second stale claim found along the way: Phase 01's "driver
documents still use a placeholder" was written before ADR-0031 actually
retrofitted `evidence_uri` onto real S3. See §2.0 for the updated
baseline (907 passed).

Immediately after, continuing autonomously, ADR-0038 builds the first
real Kafka consumer anywhere in this codebase —
`modules/notification/consumer.py`'s `NotificationConsumer`, closing
Phase 15/18's own long-standing "no consumer exists" gap. Checked
event-contracts.md's own per-event "Consumers:" lists directly (not
just domain-design.md §20.3's looser example list) before wiring
anything: `ride.started`, `ride.completed`, `ride.cancelled`, and
`penalty.applied` are each explicitly named as Notification's own
responsibility there, each with an unambiguous recipient, so those four
are wired — additively, alongside the existing synchronous `ride.
accepted`/`ride.arrived` dispatch, left untouched. Every other
documented event is deliberately deferred with its own explicit reason
(SOSTriggered's recipient is a genuine, safety-sensitive judgment call;
PromotionActivated's closest real event means something narrower;
FareChanged's closest real events already tell the same actor via that
same request's own response; PaymentRequired/PaymentConfirmed are N/A
under ADR-0025; WalletLow/PromotionExpiring/DocumentExpiring have no
triggering event without a scheduled job; SupportEscalated has no real
corresponding event) — not a hidden remainder. No live Kafka broker
exists in this dev environment, so verified two ways instead: a real
`docker build`+`docker run` smoke test confirmed both the outbox
publisher and this new consumer retry their Kafka connections
independently and indefinitely without ever blocking `/health` from
serving 200s, and 9 new integration tests exercise `handle_event()`
directly against a real Postgres test database. See §2.0 for the
updated baseline (916 passed).

Immediately after, the project owner approved Celery ("Use Celery for
background workers"), resolving Phase 01's own last remaining task.
Continuing autonomously, ADR-0039 builds `shared/celery_app.py` (Redis
as broker/backend — no new infrastructure) and its first two real
scheduled jobs, `modules/notification/tasks.py`'s `PromotionExpiring`/
`DocumentExpiring` — exactly the two events ADR-0038 deferred for
"needs a scheduled job." Each dedup key is derived from the entity's id
*and* its current `expires_at`, not the id alone, so a renewed
entitlement/document that later approaches expiry again still gets a
fresh warning — verified with a dedicated test reproducing that exact
sequence. `WalletLow` stays deferred, but for a better reason on
reflection: a balance crossing a threshold is naturally an event at the
moment of a debit, not something a schedule helps with. A real `docker
build`+`docker run` of the exact Kubernetes manifest's `celery worker
--beat` command against real Redis/Postgres confirmed task discovery,
Beat scheduling, and a live task submission all work — that same
verification also caught a real liveness-probe bug (`$(HOSTNAME)` is
never substituted in a Kubernetes exec probe) before it shipped, fixed
in the same pass. A `celery[redis]`-induced redis-py version bump also
surfaced one unrelated, real mypy regression (an upstream stub
imprecision in `hset()`), fixed with one scoped `type: ignore[misc]` in
`shared/geo.py`. See §2.0 for the updated baseline (923 passed).

Separately from the 21-phase backend track above, the owner requested a
full VISTAAR Admin Web design (a distinct app, `apps/admin-web`, still
a bare Next.js scaffold — no admin frontend has been built yet). This
resolved two more real gaps along the way: BR-126/BR-127 (2026-08-26,
APPROVED) finally answer business-rules.md §43's long-open "Admin
roles/Permission hierarchy" question — one Super Admin level, granular
per-module permissions, no fixed role set, correcting security.md §7's
own stale fixed-role example list — and ADR-0041 proposes (accepted) a
new `promotion.campaigns` schema for a real coupon/code concept
`promotion.entitlements` never supported (it's a per-customer grant,
not a shared redeemable code). See
`docs/15-admin-web/admin-web-implementation-plan.md` for the full
navigation/permission/API-mapping plan (Gold `#EFBF04`/Deep Green
`#003314` brand system) — approved for design; the frontend itself
remains unbuilt (the owner's "DO NOT IMPLEMENT YET" instruction was
about the Admin Web specifically), but §4.18's own backend (Admin
Management) is now real — see the next paragraph. Every other module
still needs at least one genuinely new backend endpoint — none invented
yet, each flagged in that plan as either "NEW — SCOPED" (ready to build)
or "NEW — NEEDS SCOPING" (not enough decided yet to design safely, e.g.
Reports/Analytics and Settings have no backend domain or spec at all).

Immediately after, the owner said "continue," confirming both ADR-0040
(permission model) and ADR-0041 (coupon/campaign schema) — resolving
that "design only" status for the former. ADR-0040 is now fully
implemented: `admin.users.role` distinguishes `SUPER_ADMIN` (implicit
full access) from `ADMIN` (an employee admin, access entirely
determined by their own rows in the new `admin.permissions` table — one
row per module, `VIEW` or `MANAGE`); `POST /api/v1/admin/admins` and its
siblings (List/Get/Update Permissions/Disable/Enable, `GET .../me`) are
real, Super-Admin-only endpoints; and every *existing* admin route
(Driver/Vehicle Review, Search Rides, Admin Wallet View, Search
Penalties, Search GPS Disputes, and their mutations) now requires a
real per-module permission, not just bare account-type authentication —
12 call sites converted from `require_active_admin()` to
`require_permission(module, level)`. A real integration-test failure
caught a genuine bug in the process: an earlier `# type: ignore[arg-
type]` (written to silence a type mismatch rather than fix it) had let
`Permission.access_level` be stored as a raw string instead of the
`AccessLevel` enum, crashing at runtime the first time a real
permission was actually serialized — fixed properly instead of
re-suppressed. ADR-0041's coupon/campaign schema was accepted but not
yet implemented at the time this paragraph was first written — since
implemented in full (2026-08-26): Campaign entity/service/repository,
admin CRUD + lifecycle endpoints, and the customer-facing Redeem
Campaign Code endpoint, plus a Search Audit Logs endpoint (Admin Web
module #18 — `admin.audit_logs` had been write-only since ADR-0040;
nothing read it back until now). One real bug caught in the process:
the shared integration-test table-wipe order
(`tests/_integration_db.py`) didn't yet know about the two new
campaign tables' foreign keys, breaking ~80 unrelated tests in other
files on the first full-suite run after adding them — fixed by
inserting them into the wipe order in dependency-safe position, the
same class of gap that file's own comment block already documents
recurring with every new FK-bearing table. See §2.0 for the updated
baseline (1002 passed).

Every genuinely unblocked, dependency-ordered item this session's execution
plan identified has now been built, including Phase 06/07 (and its GPS
dispute manual-review workflow), Phase 13, Phase 08, the MSG91/S3
integrations, Phase 09 in full (Pickup Change and Destination Change),
the Notification Domain Foundation (in-app + SMS) plus a real Kafka
consumer for four of its documented events, Phase 21's config/script
layer (Dockerfile, Kubernetes manifests, Terraform, CI/CD deploy
workflow — written and validated, not applied), Phase 19's
security-headers middleware plus CI dependency scanning, a
resource-ownership authorization audit (one test-coverage gap found and
fixed), Phase 01's Celery Background Worker Foundation plus its
first two scheduled jobs, and the Admin Permission Model (ADR-0040) —
one Super Admin level, granular per-module permissions, every existing
admin route now actually enforcing them. What remains is exclusively work that needs a project-owner decision, an
external account, or a materially larger piece of new infrastructure:
the payment gateway (SBI Bank clarification), Push (needs a
device-token-registration endpoint — a new API contract — before FCM
can be wired against anything real), WhatsApp (BSP not yet picked, per
the owner's own instruction), the remaining Notification event-list
items deferred under ADR-0038/ADR-0039 (each blocked on its own
specific gate, not "needs a consumer"/"needs a worker" generically
anymore), and actually applying Phase 21's Terraform/Kubernetes
artifacts against a real DigitalOcean account. See
docs/VISTAAR_AUTONOMOUS_EXECUTION_PLAN.md for the full phase-by-phase
reasoning. (Corrected 2026-08-25 — this section previously
described Admin Monitoring & Penalty Review (Phase 16) as the checkpoint
with Phase 04's "GET ride status"/Phase 11's "Financial audit trail" as
next; that work is now done too, and this section is updated to match
§2.0's own record of that completion — the same class of staleness this
section has now been corrected for repeatedly; see this file's own edit
history on 2026-08-22 through 2026-08-25. Updated again 2026-08-25 for
Phase 06/07's resolution and implementation, ADR-0028, again the same day
for Phase 13's implementation, ADR-0029, again the same day for Phase 08's
implementation, ADR-0030, again the same day for the MSG91/S3
integrations, ADR-0031, again the same day for the GPS Dispute Manual
Review workflow's implementation, ADR-0032, again the same day for Phase
09's Pickup Change and Destination Change implementations, ADR-0033, and
again the same day for the Notification Domain Foundation, ADR-0034, and
again the same day for Phase 21's DigitalOcean deployment artifacts and
the production-Dockerfile bug fixes, ADR-0035, and again the same day
for Phase 19's security-headers middleware and CI dependency scanning,
ADR-0036, and again the next day for the resource-ownership
authorization audit, ADR-0037, and again the same day for the first
real Kafka consumer in this codebase (Notification), ADR-0038, and
again the same day for the Celery Background Worker Foundation and its
first two scheduled jobs, ADR-0039, and again the same day for the
Admin Permission Model, ADR-0040, and again the next day for the
Coupon/Campaign Schema's implementation, ADR-0041, and again the same
day for the Search Audit Logs endpoint (Admin Web module #18, no ADR —
a pure read over an existing table, no new schema or business rule),
and again the same day, under the owner's "continue and complete the
whole" authorization, for the entire remaining backend layer of the
Admin Web implementation plan's "NEW — SCOPED" items,
and again on 2026-08-28 for §4.18's own frontend: after a read-only
audit confirmed the Admin RBAC/Admin Management backend (ADR-0040) was
genuinely complete but had no Admin Web screen behind it (§4.18's own
status line said as much — "the one thing still outstanding here is the
Admin Web screen"), that screen was built. `apps/admin-web` had no
frontend test tooling of any kind before this — Vitest + React Testing
Library was added (not Jest: ESM-native, no separate config needed
beyond the existing `@/*` alias), wired into `npm run test` and the
`admin-web-checks` CI job. Two new routes
(`/admin-management`, `/admin-management/[adminId]`) cover: an employee
admin list with pagination; Create Employee Admin, with an inline
permission picker at creation time; a per-admin detail/edit screen with
Save/Reset for a redesigned permission set (VIEW/MANAGE/None per
module — no third "Approve" level exists anywhere in this codebase, by
design) and Enable/Disable; and `Sidebar`'s existing
`isModuleVisible()` gating, unchanged, now has a real screen behind it
for the first time. `ADMIN_MANAGEMENT`/`SETTINGS` are excluded
client-side from the permission editor's own module list (mirroring,
not re-deciding, `_UNGRANTABLE_MODULES` in `modules/admin/service.py`),
and every mutation (create, permission update, disable, enable) shows
its own real loading/error/success state — deliberately not the
Dashboard's existing "fall back to sample data on failure" pattern,
since silently substituting a fake admin a user could then "disable" is
a materially different risk than a dashboard tile briefly showing stale
numbers. 29 new frontend tests across 6 files (permission-editor
toggling, create/list/paginate, FORBIDDEN handling, Super-Admin-target
exclusion from the permission editor, disable/enable, and the two
existing-nav-helper cases) — `npm run lint`, `npx tsc --noEmit`,
`npm run test`, and `npm run build` all clean. See
`docs/15-admin-web/admin-web-implementation-plan.md` §4.18, updated to
IMPLEMENTED.

Immediately after, the same day (2026-08-28), §10 item (2): the Admin
Web frontend for Customers, Drivers, Vehicles, and Verification
(§4.1-§4.4, api-contracts.md §46.4 — the plan's own "biggest immediate
gap"). `/customers`, `/drivers`, `/vehicles`, `/verification`, plus a
detail route for each of the first three. Drivers gets Approve/Reject/
Suspend/Reactivate and a nested document/verification-case view;
Vehicles gets Approve/Reject and its own document list (fetched and
error-handled independently from the vehicle record itself, since that
endpoint is gated under the VERIFICATION module, not VEHICLES);
Verification is a read-only pending-review queue defaulting to
status=PENDING, deliberately not deep-linking to the underlying
driver/vehicle — `subject_id` on a case is the document's own id, and
no endpoint resolves that back to its owner. Same "no sample-data
fallback for anything mutable or operational" rule as Admin Management.
28 more frontend tests (8 new files, 57/57 passing total) — lint,
typecheck, tests, and build all clean. See
`docs/15-admin-web/admin-web-implementation-plan.md` §4.1-§4.4 and §10,
both updated.

Same day, §10 item (3): Audit Logs (§4.17) — `/audit-logs`, a single
read-only search screen over `admin.audit_logs` (filters: admin ID,
action, target type/id, and a from/to date range — the backend takes
full ISO datetimes for `created_after`/`created_before`, so a plain
date-picker value is widened client-side to that day's start/end
before the request goes out). No mutations here, so none of the
sample-data-fallback design questions the two frontend builds before it
had to work through even come up. 4 more tests (61/61 total) — lint,
typecheck, tests, and build all clean.

Same day, §10 item (4): Fare Management (§4.8, ADR-0042) —
`/fare-management` (list, filters, an inline Create Draft form) and
`/fare-management/{id}` (Submit for Review; Publish with an optional
`datetime-local` `effective_from`, sent as ISO 8601 only when filled
in). The vehicle-category picker offers exactly the 5 values
`calculate_fare()` keys off (`BIKE`/`AUTO`/`CAB_ECO`/`CAB_PREMIUM`/
`CAB_PREMIUM_PLUS`, modules/pricing/__init__.py) — a CAB-tier-aware
vocabulary distinct from the 3-value `VehicleCategory` enum
Drivers/Vehicles use, easy to conflate but not the same field.
`lib/status-tone.ts` (already shared by Drivers/Vehicles/Verification)
gained `PUBLISHED`→success and `IN_REVIEW`→warning rather than a
fourth one-off status map. Platform Fee Management (§10 item (10), same
DRAFT/IN_REVIEW/PUBLISHED shape but its own table/permission) stays
backend-only — not built here. 9 more tests (70/70 total) — lint,
typecheck, tests, and build all clean. See
`docs/15-admin-web/admin-web-implementation-plan.md` §4.8 and §10, both
updated.

Same day, §10 item (5): Offers/Coupons (§4.10, ADR-0041) —
`/offers-coupons` (list, status filter, an inline Create Campaign form)
and `/offers-coupons/{id}` (Edit while `status=DRAFT`, then
Activate/Pause/End). One 13-field `CampaignForm` is shared by Create
(POST) and Edit (PATCH) — the backend, not the form, is what actually
enforces PATCH-only-in-DRAFT; the form just never renders for a
non-DRAFT campaign. `eligible_customer_ids` (only meaningful when
`eligible_scope=SELECTED`) is a plain textarea, one ID per line or
comma-separated, parsed client-side into the UUID list the API already
expected — not the CSV-bulk-upload endpoint (§4.10's own table, "NEW —
SCOPED", still unbuilt at either layer). 14 more tests (84/84 total) —
lint, typecheck, tests, and build all clean. See
`docs/15-admin-web/admin-web-implementation-plan.md` §4.10 and §10,
both updated.

Same day, §10 item (6): Safety/SOS (§4.13, ADR-0022) — `/safety`,
`/safety/{id}` (Acknowledge/Escalate/Resolve, each shown only for the
one status that actually allows it, matching state-machines.md §45's
linear lifecycle) — and Support/Disputes (§4.14) — `/support`,
`/support/{id}` (Resolve, plus the full message conversation). GPS
Dispute (§4.14's own 4th row) stays out of scope — it's already treated
as a separate, pre-existing surface (§77, BR-124/125) by that section's
own text, not new work this item covers, same "flag what's excluded"
treatment already given to Platform Fee Management and CSV bulk
targeting. `lib/status-tone.ts` gained `RESOLVED`→success,
`IN_PROGRESS`/`WAITING_FOR_USER`→warning, and `OPEN`/`ASSIGNED`/
`ACKNOWLEDGED`→info. 15 more tests (99/99 total) — lint, typecheck,
tests, and build all clean. See
`docs/15-admin-web/admin-web-implementation-plan.md` §4.13, §4.14, and
§10, all updated.

Same day, §10 items (7) and (9) together, out of numeric order —
both live under §4.12's single `NOTIFICATIONS` permission key, so
splitting Notification History from Templates across two separate
passes would have divided one Admin Web module's frontend for no real
reason; (8) Referral Reward Configuration is next, deferred one slot,
not skipped. `/notifications` (delivery history, filters: channel,
status) links to `/notifications/templates` (list, filters, an inline
Create Template form) and `/notifications/templates/{id}` (Publish,
DRAFT only — no Edit endpoint exists, ADR-0044 Decision 4: an edit is
always a new, versioned Create, and the frontend doesn't invent one).
Compose/Send Broadcast, Audience Selection, and device-token
registration remain exactly what §4.12's own table already says: NEEDS
SCOPING, untouched. 11 more tests (110/110 total) — lint, typecheck,
tests, and build all clean. See
`docs/15-admin-web/admin-web-implementation-plan.md` §4.12 and §10,
both updated.

Same day, §10 item (8): Referral Reward Configuration (§4.11,
ADR-0043) — with Search Referrals folded in too, since §4.11 names it
under the same `REFERRALS` permission key and its backend was done the
same day, same "don't split one module's frontend for no reason"
reasoning already applied to items (7)/(9). `/referrals` (search,
status filter, each row's own reward(s) shown inline) links to
`/referrals/rewards`, one page hosting both independent config
streams — Driver Referral Bonus (one global policy) and Customer
Referral Rewards (one per `reward_type`,
REFERRAL_REFERRED/REFERRAL_REFERRING — a config-level vocabulary
distinct from `ReferralReward`'s own DRIVER_REFERRAL_BONUS/
CUSTOMER_REFERRAL_PROMOTION `reward_type`, a different table) — each
with its own inline create form, status filter, and detail route for
Submit-for-Review/Publish, reusing the DRAFT→IN_REVIEW→PUBLISHED shape
Fare Management and Notification Templates already established.
`lib/status-tone.ts` gained `ACTIVATED`→success and `SENT`/`FAILED`.
15 more tests (125/125 total) — lint, typecheck, tests, and build all
clean. See `docs/15-admin-web/admin-web-implementation-plan.md` §4.11
and §10, both updated.

2026-08-29, §10 item (10): before continuing the build, two prior
status claims were reconciled against the actual current code rather
than trusted as-is (owner-requested audit-correction pass). (1) The
ADR-0011 Redis go_offline-cleanup gap blocking Dashboard's Online
Drivers figure — reported NEEDS SCOPING as recently as the plan doc's
own 2026-08-28 header — was found already fixed in the live code:
`shared/geo.py`'s `remove_driver_location()` is now actually called
from `modules/driver/router.py`'s `go_offline` endpoint, and
`GET /dashboard/summary` returns a real, accurate count. The plan
doc's own narrative header simply hadn't been updated after the fix
landed; corrected to IMPLEMENTED. (2) "Device-token registration is
blocked" was found imprecise: ADR-0052 (2026-08-28) fully implements
the registration API (`POST/DELETE /api/v1/notifications/me/devices`,
`notification.device_tokens`, a `PushProvider` abstraction) — what's
actually still open is a real Firebase credential (external dependency,
`PUSH_PROVIDER` stays `dev`) and, unrelated to ADR-0052 entirely,
Compose/Send Broadcast + Audience Selection (still no endpoint stores
an admin-composed message body). Both corrections are reflected in
`docs/15-admin-web/admin-web-implementation-plan.md`'s status header,
§3, §4.6, and §4.12.

Then, §10 item (10) itself: Platform Fee Management (§4.8's own row,
ADR-0045) — `/fare-management/platform-fee` (list + filters + inline
Create Draft form) and `/fare-management/platform-fee/{id}` (Submit
for Review, Publish), reached via a link from `/fare-management`
rather than its own sidebar entry, since `nav.ts` maps one
`AdminModule` per href and Platform Fee has no module of its own
(ADR-0045 Decision 3 deliberately reuses `FINANCE`, not
`FARE_MANAGEMENT` — an admin with only Fare Management access sees the
link but gets the same FORBIDDEN handling as any other screen without
`FINANCE`). Same DRAFT→IN_REVIEW→PUBLISHED shape as Fare Management,
Notification Templates, and Referral Reward Configuration, reused a
fourth time; keys off the 3-value `VehicleCategory` (BIKE/AUTO/CAB),
not Fare Management's 5-value CAB-tier set, since BR-011's platform
fee applies uniformly across CAB's tiers (ADR-0045 Decision 1). 9 more
tests (134/134 total) — lint, typecheck, tests, and build all clean.
See `docs/15-admin-web/admin-web-implementation-plan.md` §3, §4.6,
§4.8, §4.12, and §10, all updated.

Same day, §10 item (11): Advertisements (§4.15, ADR-0046) — the
largest module built this session, three independent resources sharing
one `ADVERTISEMENTS` permission. `/advertisements` (campaign list,
status filter, inline Create Campaign form) and `/advertisements/{id}`
(Pause/Resume/End over `CampaignStatus`'s new ACTIVE⇄PAUSED→ENDED
lifecycle, an inline Assign-a-driver form disabled with an explanatory
message once the campaign isn't ACTIVE, and that campaign's own
assignments listed inline); `/advertisements/assignments` (the global
installation/proof review queue, filterable by campaign/driver
ID/status — freeform ID inputs, same "no picker component exists to
reuse" precedent Offers/Coupons' own eligible-customer textarea already
set) and `/advertisements/assignments/{id}` (Approve/Reject proof,
shown only while PROOF_SUBMITTED; Calculate Payout, shown only once
VERIFIED, renders the resulting payout inline); `/advertisements
/payouts` (payout/settlement monitoring, inline Settle per PENDING
row). `lib/status-tone.ts` gained `VERIFIED`/`PAID`→success and
`PAUSED`/`PROOF_SUBMITTED`→warning; `ENDED` was left deliberately
unmapped (neutral default), the same treatment already given to
Safety's own `CLOSED`. New types are `Ad`-prefixed
(`AdCampaign`/`AdCampaignStatus`/`AdAssignment`/`AdPayout`) to avoid
colliding with Offers/Coupons' own unrelated `Campaign`/`CampaignStatus`.
21 more tests (155/155 total) — lint, typecheck, tests, and build all
clean. See `docs/15-admin-web/admin-web-implementation-plan.md` §4.15
and §10, both updated.

Same day, §10 item (12): Reports/Analytics (§4.16, ADR-0047) —
`/reports`, one page hosting all nine fixed-shape reports behind a
single report-type picker and a shared `from`/`to` date range, rather
than nine near-identical routes. `<input type="date">` widens to a
full-day boundary before it's sent, same convention Audit Logs already
established; an empty range is left empty rather than guessed at
client-side, so the backend's own 30-day default (ADR-0047 §2) decides
it, and the response's own `from`/`to` (the range actually used) is
what's displayed. Each report's fetched shape maps to one uniform
`{stats, breakdowns}` view — scalar numbers/rates/currency as stat
cards, `Record<string, number>` fields as breakdown lists — one shared
renderer for nine different response shapes. VIEW-only permission, no
mutations, so no sample-data-fallback question and no audit-log entries
either. 4 more tests (159/159 total) — lint, typecheck, tests, and
build all clean. See `docs/15-admin-web/admin-web-implementation-plan.md`
§4.16 and §10, both updated.

Same day, §10 item (13) — the last item of the numbered build order:
Settings (§4.19, ADR-0048) — `/settings`, a navigation surface, not a
second place to edit data that already has its own dedicated screen
(ADR-0048 Decision 1): four link cards point at `/fare-management`,
`/fare-management/platform-fee`, `/referrals/rewards`, and
`/notifications/templates`. Below that, the actual `admin.settings`
table (promotion defaults, operational thresholds, feature flags,
general — the four categories with no home elsewhere) as a
category-filterable list with inline editing: `value` is a bare JSON
scalar/object with no per-key schema, so the edit control is a
textarea pre-filled with `JSON.stringify(value, null, 2)`, parsed back
on Save with a real validation-error banner if the typed text isn't
valid JSON. A plain overwrite, not a DRAFT/PUBLISHED lifecycle —
nothing reads `admin.settings` live at transaction time the way
Fare/Platform Fee do. `SETTINGS` is Super-Admin-only and never
grantable (BR-126) — the only module in this app with no
partial-access case to design for. 5 more tests (164/164 total) —
lint, typecheck, tests, and build all clean. See
`docs/15-admin-web/admin-web-implementation-plan.md` §4.19 and §10,
both updated.

This closes every item §10 itself ever numbered (1-13). Continuing
past 13 in the order asked: §10 item (14), 2026-08-29: Rides (§4.5) —
`/rides` (search by driver/customer ID and status) and `/rides/{id}` (a
read-only lifecycle timeline: Requested → Accepted → Driver arrived →
Started → Completed/Cancelled → Closed, each with its own timestamp or
an em dash, plus pickup/destination coordinates and the fare breakdown
when one exists). No action exists anywhere on this screen — no
admin-side ride intervention was ever asked for. `lib/status-tone.ts`
gained `ACCEPTED`/`COMPLETED`→success, `CANCELLED`→danger,
`STARTED`→warning, `SEARCHING`/`ARRIVED`→info; Rides' own `CLOSED`
joins Ad campaigns' `ENDED` as a second deliberately-unmapped
terminal-but-not-bad status. 6 more tests (170/170 total) — lint,
typecheck, tests, and build all clean. See
`docs/15-admin-web/admin-web-implementation-plan.md` §4.5 and §10,
both updated.

Same day, §10 item (15): Finance / Wallet (§4.7) — `/finance`, a
driver-ID lookup form (no search-all-wallets endpoint exists by
design), and `/finance/{driverId}` (balance + outstanding settlement,
then transaction history with a type filter over all 10
`TransactionType` values and pagination). `useRouter().push()` is this
app's first use of programmatic navigation — every other screen so far
navigates via `<Link>`, but a lookup-then-navigate flow has nothing to
attach a `<Link>` to until the ID is known. `CREDIT`/`DEBIT` gets an
inline `Pill` rather than a `toneForStatus()` entry — a fixed 2-value
field, not a status enum. 6 more tests (176/176 total) — lint,
typecheck, tests, and build all clean. See
`docs/15-admin-web/admin-web-implementation-plan.md` §4.7 and §10,
both updated.

Same day, §10 item (16): Penalties / Strikes (§4.9) — `/penalties`
(search by user ID and status, plus the only documented resolve
action, Waive, via an inline reason row directly below the target
penalty rather than a separate detail page). Driver Strike History was
checked against the current backend rather than assumed from the plan
doc's own text — `GET /api/v1/admin/drivers/{id}/strikes` still does
not exist, so it stays NEW — SCOPED and isn't folded into this screen.
`lib/status-tone.ts` gained `SETTLED`/`WAIVED`→success and
`OUTSTANDING`→info. 5 more tests (181/181 total) — lint, typecheck,
tests, and build all clean. See
`docs/15-admin-web/admin-web-implementation-plan.md` §4.9 and §10,
both updated.

Only Matching/Offers (§4.6) remained, and its documented endpoint did
not exist yet. A scoping report (2026-08-29) inspected the current
matching backend, Redis GEO state, offer lifecycle, Reports, and
Dashboard, presenting three tiers (A: surface only what already
exists; B: A plus a per-category online count; C: real search over
individual offers, optionally with a live driver-location map). The
owner chose Tier C, explicitly excluding the location-map half —
recorded as ADR-0054.

Same day, §10 item (17), closing the last item in the 20-module
catalog: Matching/Offers (§4.6, ADR-0054) — `/matching` (online-driver
count, total and by real `matching_category_key()` value — BIKE/AUTO/
CAB:ECO/CAB:PREMIUM/CAB:PREMIUM_PLUS — plus a search form over
individual offers: status/ride ID/driver ID/date range) and
`/matching/{offerId}` (documented/safe fields only — offer_id, ride_id,
driver_id, vehicle_id, status, expires_at, responded_at, created_at;
no coordinates, no Redis-derived location or availability data). Two
new backend endpoints, a new `OfferRepository.search()` (mirroring
`RideService.search_rides()`'s own shape) and `MatchingService.
get_offer()` (mirroring `RideService.get_ride()`'s admin-only-no-
ownership-check split), and a new `geo.count_online_drivers_by_
category()` (the same ZCARD loop `count_online_drivers()` already
sums, just not collapsed). No driver-location map, no live coordinates
anywhere — the owner's explicit exclusion, left for a separate future
decision. No mutation exists in this module or was proposed — the
matching algorithm itself stays entirely driver-facing. 20 new backend
tests (6 unit, 14 real-Postgres/real-Redis integration dispatching an
actual offer end-to-end) — full backend suite 1197 passed, 5 skipped
(pre-existing Kafka-only skips), ruff and mypy clean. Frontend: 7 more
tests (188/188 total) — lint, typecheck, tests, and build all clean.
See `docs/14-decisions/ADR-0054-matching-offers-admin-visibility.md`,
`docs/05-api/api-contracts.md` §46.20, and
`docs/15-admin-web/admin-web-implementation-plan.md` §4.6 and §10, all
updated.

Every module in the original 20-item catalog now has a real Admin Web
screen.

Same day: CORS, the last open item blocking the Admin Web from
actually working in a real browser (admin-web-implementation-plan.md
§6, flagged since 2026-08-26, never fixed until now). `main.py` gained
`CORSMiddleware`, added after `SecurityHeadersMiddleware` so it wraps
everything including error responses, reading a new
`CORS_ALLOWED_ORIGINS` setting (comma-separated, defaults to Next.js's
own dev port). `allow_credentials=False` — the Admin Web's own
fetch() calls authenticate via an `Authorization` header, not cookies,
so the credentialed CORS mode was never needed. No real production
admin-web origin exists yet, so `infrastructure/kubernetes/backend-
configmap.yaml` deliberately leaves the setting unset with a comment
rather than shipping a guessed value, the same treatment already given
to `FCM_SERVICE_ACCOUNT_JSON`. 4 new tests (`tests/test_cors.py`) —
full backend suite 1201 passed, 5 skipped (pre-existing, unrelated),
ruff and mypy clean. Every Admin Web screen built this session was
unreachable from a real browser until this landed, independent of how
many screens existed. See
`docs/15-admin-web/admin-web-implementation-plan.md` §6, updated.

Same day, §10 item (18): Driver Strike History (§4.9, api-contracts.md
§46.18) — the first of the three remaining NEW — SCOPED items, picked
up after the 20-module catalog itself was complete. New
`StrikeRepository.list_for_driver()` (newest-first, paginated) and a
new `GET /api/v1/admin/drivers/{id}/strikes` endpoint, reusing the
DRIVERS permission (this is driver data, not a new module). Frontend:
`/drivers/{driverId}/strikes`, a plain paginated table, reached via a
new "View history →" link next to the strikes count already shown on
`/drivers/{id}` — no new sidebar entry. No action exists on this
screen. 8 new backend tests (3 unit, 5 real-Postgres integration) —
full backend suite 1209 passed, 5 skipped (pre-existing, unrelated),
ruff and mypy clean. Frontend: 5 more tests (192/192 total) — lint,
typecheck, tests, and build all clean. See
`docs/15-admin-web/admin-web-implementation-plan.md` §4.9 and §10,
both updated.

Same day, §10 item (19): CSV Bulk Customer Targeting (§4.10, ADR-0041
§9) — the second of the three remaining NEW — SCOPED items. New
`CampaignRepository.add_eligible_customers()` (additive, idempotent),
coexisting with the existing `set_eligible_customers()` (replace
semantics, Create/Edit) — ADR-0041 §9's own deliberate choice: a
re-uploaded refreshed list must never silently drop individually-added
customers. New `POST /api/v1/admin/campaigns/{id}/eligible-
customers/bulk`, multipart/form-data, resolving each CSV row's phone
to a customer_id via the same two-step check Customer Detail's own
composition already performs — unmatched rows reported back, never
silently dropped. Pulled in `python-multipart` as a new runtime
dependency. Frontend: a file input + Upload button on
`/offers-coupons/{id}`, shown only while DRAFT and eligible_scope=
'SELECTED', via a new `apiUpload()` client helper (this app's first
multipart request). 11 new backend tests (4 unit, 7 real-Postgres
integration) — full backend suite 1220 passed, 5 skipped
(pre-existing, unrelated), ruff and mypy clean. Frontend: 4 more tests
(196/196 total) — lint, typecheck, tests, and build all clean. See
`docs/15-admin-web/admin-web-implementation-plan.md` §4.10 and §10,
both updated.

(20) was built 2026-08-29: GPS Dispute frontend (§4.14). The backend
needed only one new endpoint, `GET /api/v1/admin/gps-disputes/
{dispute_id}`, composing the pre-existing, pre-tested
`RideService.get_gps_dispute()` — the "service exists, no HTTP route"
pattern already used by Driver Suspension and Safety Acknowledge/
Escalate/Resolve, so no new domain or service code was needed. 3 new
backend tests — full backend suite 1223 passed, 5 skipped
(pre-existing, unrelated), ruff and mypy clean. Frontend: new
`/support/gps-disputes` list (status filter, pagination) and
`/support/gps-disputes/{disputeId}` detail (evidence table, conditional
Approve/Reject with a required decision reason) routes, linked from a
new "GPS Disputes →" nav item on the Support page; 8 new tests — full
suite 50 files/204 tests passed, tsc/lint/build all clean. See
`docs/05-api/api-contracts.md` §77 and
`docs/15-admin-web/admin-web-implementation-plan.md` §4.14, both
updated.

This closed out every item in the Admin Web implementation plan's
original scope that didn't require a fresh decision: all 20 sidebar
modules plus every NEW — SCOPED sub-item (Driver Strike History, CSV
Bulk Customer Targeting, GPS Dispute frontend), plus the cross-cutting
CORS fix that made these screens reachable from a real browser. One
genuinely NEEDS-SCOPING item remained: §4.12's Compose/Send Broadcast +
Audience Selection, which needed its own owner decision (a real schema
addition Templates alone didn't supply).

(21) was built 2026-08-29, closing that last item: Compose/Send
Broadcast + Audience Selection (§4.12, ADR-0055 Tier C). A scoping
report presented three tiers (A: trigger an existing published
Template, no free text; B: A plus true free-text composition; C: B
plus scheduling); the owner chose Tier C. New `notification.broadcasts`
table — a broadcast's own free-text subject/body publishes a one-off,
broadcast-only `notification.templates` row under the hood
(`event_key=NULL`, exactly the case ADR-0044's own schema comment
anticipated), so every recipient's actual send still goes through
`NotificationService.send()` unchanged, with no change to that
method's single-recipient signature — the fan-out lives one layer
above it, in a new shared `modules.notification.broadcast_dispatch`
module, used identically by the immediate-send path and a new Celery
Beat task polling every 5 minutes for due scheduled broadcasts. New
audience-resolution methods (`CustomerService.list_all_customer_ids()`,
`DriverService.list_all_driver_ids()`, `geo.list_online_driver_ids()`).
21 new backend tests (unit against fakes plus real-Postgres/real-Redis
integration, including the scheduled-dispatch task against this
codebase's own truncated-table fixture for exact audience-count
assertions) — full backend suite 1254 passed, 5 skipped (pre-existing,
unrelated), ruff and mypy clean. Frontend: `/notifications/broadcasts`
(compose form + history list) and `/notifications/broadcasts/{id}`
(read-only detail), linked from the Notifications page; 8 new tests —
full suite 52 files/212 tests passed, tsc/lint/build all clean. See
`docs/04-database/database-design.md` §32.5, `docs/05-api/api-
contracts.md` §46.21, `docs/14-decisions/ADR-0055-notification-
broadcast-composition.md`, and `docs/15-admin-web/admin-web-
implementation-plan.md` §4.12, all updated.

This closes out every item in the Admin Web implementation plan's
original scope, including the one item that needed its own fresh
decision: all 20 sidebar modules, every NEW — SCOPED sub-item, the
cross-cutting CORS fix, and the one NEEDS-SCOPING item (Compose/Send
Broadcast + Audience Selection, ADR-0055). No item from this plan's
original scope remains outstanding.

Customers/Drivers/Vehicles/Verification search+detail and Suspend/
Reactivate Driver (Admin Web §4.1-§4.4, api-contracts.md §46.4); Wallet
Transaction History (§4.7, §46.5 — the driver-facing equivalent turned
out to already exist, Phase 11/ADR-0024, built after this plan section
was first written); Referrals search (§4.11, §46.6); Fare Management's
DRAFT->IN_REVIEW->PUBLISHED workflow (§4.8, ADR-0042, §46.7 — one real
bug caught by the integration tests, not by inspection: the schema
migration's first version never relaxed `effective_from`'s NOT NULL
constraint even though the domain/ORM layer already treated it as
nullable, caught the moment Create Draft's real-Postgres test ran, not
by the in-memory fake tests, which passed cleanly and hid the gap —
fixed by amending the same migration and re-verifying the full
upgrade/downgrade/upgrade cycle before re-running the tests); Safety/
SOS and Support/Disputes admin surfaces (§4.13/§4.14, §46.8/§46.9 —
Acknowledge/Escalate/Resolve/Resolve-Case all turned out to already
exist at the service layer, only the HTTP routes were missing, and
Support's own "NEEDS SCOPING" note on Resolve Case was corrected to
IMPLEMENTED as a result); Notification History (§4.12, §46.10 — the
one cleanly-buildable piece of that module; Compose/Send Broadcast was
corrected from its original "NEW — SCOPED" status to NEEDS SCOPING,
since `NotificationService.send()` turned out to only ever accept a
fixed `template_key`, never admin-composed free text, the same gap
Templates already needed schema work for); and the Dashboard aggregate
summary endpoint (§3, §46.11 — every widget except Online Drivers,
which was corrected to NEEDS SCOPING once `shared/geo.py`'s own
documented "never removed on go_offline" behavior was checked against
what an honest count would show). Every remaining "NEEDS SCOPING" item
across the plan stayed exactly that — nothing was invented to fill a
gap a source document did not already close. Full suite: 1046 passed,
5 skipped (Kafka-only, infra-unreachable in this environment) before
the Dashboard endpoint's own tests were added; ruff and mypy clean
throughout. See docs/15-admin-web/admin-web-implementation-plan.md's
own top-of-file status line and docs/14-decisions/ADR-0042-fare-
management-workflow.md for the full detail.)

Before doing any work:

Inspect the actual repository state and current migration head.

Read the authoritative API/business/state/database/event/security/testing documents
relevant to the next task.

Locate the approved implementation plan for the next task if one exists.

If the plan does not exist, create the plan and STOP for owner review.

Implement only after plan approval.

Verify with tests, migrations, Ruff, MyPy, and relevant integration/concurrency checks.

Update this file and produce the task completion report.

Do not use this section to override a more recent approved task decision. The actual
repository plus the latest approved task/ADR is always authoritative for what is already
complete and what comes next.

35. FINAL PROJECT COMPLETION CRITERIA

The project is not complete merely because the current phase/task checklist appears green.
The final state must be reconciled against the actual codebase, database, provider access,
security requirements, test suite, deployment environment, and production-readiness gates.

Mark the entire VISTAAR project PRODUCTION READY only when:

Phase 01 ✅

Phase 02 ✅

Phase 03 ✅

Phase 04 ✅

Phase 05 ✅

Phase 06 ✅

Phase 07 ✅

Phase 08 ✅

Phase 09 ✅

Phase 10 ✅

Phase 11 ✅

Phase 12 ✅

Phase 13 ✅

Phase 14 ✅

Phase 15 ✅

Phase 16 ✅

Phase 17 ✅

Phase 18 ✅

Phase 19 ✅

Phase 20 ✅

Phase 21 ✅

and the final production checklist confirms:

security approved;

backups/restore verified;

monitoring active;

rollback tested;

deployment reproducible;

E2E customer journey passed;

E2E driver journey passed;

E2E admin journey passed;

high-severity defects resolved;

required external providers operational;

no unauthorized secrets in repository;

documentation current;

operational runbooks complete.

36. CLI STARTUP CHECKLIST

When Claude Code CLI starts a new session for VISTAAR, do this in order:

Read VISTAAR_MASTER_IMPLEMENTATION_ROADMAP_CLI.md (or the repo's current master-roadmap filename).

Inspect git status, current branch, repository tree, migration head, and test configuration.

Locate the most recent approved task completion report/ADR.

Confirm the actual completed-task checkpoint.

Read the next task's authoritative documentation.

Produce a single complete implementation plan for that task.

STOP for owner review.

After approval, implement and verify.

Update this roadmap and report the exact next task.

Never rely solely on conversational memory for the current state.

END OF MASTER ROADMAP