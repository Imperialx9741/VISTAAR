# VISTAAR — Implementation Roadmap

Version: 2.0
Date: 2026-08-22
Status: **Superseded** — 2026-08-22

> **This file is no longer the canonical roadmap.** The canonical roadmap is
> now [docs/VISTAAR_IMPLEMENTATION_ROADMAP.md](docs/VISTAAR_IMPLEMENTATION_ROADMAP.md).
> Two roadmap documents at different granularity had begun drifting out of
> sync with each other and with the repository — see that file's
> "Reconciliation note" for what was corrected. This file is kept for its
> historical Phase 1–10 narrative and open-decision detail, but is not
> updated going forward; do not treat anything below as current without
> cross-checking the canonical file first.

Scope: apps/backend, apps/customer-mobile, apps/driver-mobile, apps/admin-web, services/*, packages/*, infrastructure/*

## 0. How to read this document

This roadmap sequences the work that turns the completed VISTAAR design
documentation (docs/01-product through docs/11-implementation) into a
working product. It does not restate business rules, API shapes, database
schemas, or state machines — those remain authoritative in their own
documents. This file only answers: **what gets built, in what order, and
what has to be true before each phase can be considered done.**

Phase numbering follows [docs/11-implementation/implementation-readiness.md §61](docs/11-implementation/implementation-readiness.md)
("Implementation Order"). This is v2.0 of this roadmap — v1.0 (2026-08-20)
was written before any backend module existed; this revision reconciles it
against the actual repository state after Phase 2 completed in full and
Phase 3 began, and against ADR-0004 through ADR-0011 (recorded during that
work — see §7).

**Governing rules for every phase below** (from
[business-rules.md §44-45](docs/02-business/business-rules.md) and
[implementation-readiness.md §74](docs/11-implementation/implementation-readiness.md)),
unchanged since v1.0 and confirmed by practice across every task so far:

- PRD.md and business-rules.md remain authoritative. A phase must not invent
  a business value that those documents mark TBD.
- If implementation hits a genuine unresolved business question: **stop**,
  identify the exact ambiguity, ask a focused question, record the answer
  (an ADR, per the pattern ADR-0004 through ADR-0011 established), update
  the relevant document, then continue. Do not silently assume.
- A change to an approved business rule requires updating the business-rules
  document first, then the affected architecture/API/event/database/test
  documents, before code changes.
- Historical/completed transactions (fares, penalties, promotions) must
  retain the rule version that was actually applied, even after a later
  rule change.
- A documented request/response contract with no worked example (e.g. a
  route listed with no sample JSON) is an under-specification gap, not
  permission to invent freely — fill it in explicitly and record it (ADR-0011
  Decision 4 is the template), the same as a TBD business value.

## 1. Current status (as of this roadmap's date)

**Phase 1 — Foundation: complete.** Git is initialized (3 commits on
`main`); the v1.0 blocker is cleared. Backend boots and serves `/`,
`/health`, `/health/db`, `/health/redis`, `/health/kafka`.

**Phase 2 — Identity, Customer, Driver, Vehicle: complete.**

| Task | Scope | Status |
|---|---|---|
| 2.1 | Identity & Authentication (phone+OTP, sessions, refresh) | ✅ |
| 2.2 | Customer Profile | ✅ |
| 2.3 / 2.3A | Driver Profile + Design Clarification | ✅ (ADR-0004, ADR-0005) |
| 2.4 / 2.4A | Vehicle Management + Lifecycle/API Clarification | ✅ (ADR-0006) |
| 2.5 | Driver & Vehicle Documents | ✅ (ADR-0007) |
| 2.6 / 2.6B / 2.6C | Verification Foundation, completion, BR-123 enforcement | ✅ (ADR-0008) |
| 2.7A | Admin Foundation & Approval | ✅ (ADR-0009) |
| 2.7B | Driver Eligibility & Online/Offline | ✅ |

RBAC (`require_customer`/`require_driver`/`require_admin`) is enforced
server-side on every authenticated route. All Phase 2 exit criteria below
are met.

**Phase 3 — Ride, Matching: in progress.**

| Task | Scope | Status |
|---|---|---|
| 3.1 | Create Ride Request | ✅ (ADR-0010) |
| 3.2 | Driver Location Tracking & Matching (offer create/expire/reject) | ✅ (ADR-0011) |
| 3.3 | Customer Ride Cancellation (SEARCHING only) | ✅ (ADR-0012) |
| 3.4 | Accept Offer / Ride ACCEPTED | 🛑 blocked on Wallet (Phase 5) — see §2 |
| 3.5 | Driver Cancellation (ACCEPTED → CANCELLED), rematching | 🛑 blocked on 3.4 |

**Infrastructure built along the way, available to every later phase:**
PostGIS (dev + dedicated test database), `shared.idempotency_keys`
(generic Idempotency-Key handling), `shared/geo.py` (Redis GEO index),
`shared/geometry.py` (dependency-free PostGIS column type), a dedicated
test database with FK-safe cleanup (`tests/_integration_db.py`) separate
from the long-lived dev database.

**Phases 4-10:** not started. See §3 below — unchanged in shape from v1.0,
updated only where Phase 3 work changed what's actually available to build
against.

Verified directly, repeatedly, throughout: `ruff format --check`, `ruff
check`, `mypy` all clean; the full test suite (421 tests as of Task 3.3)
passes from a freshly-dropped test database, run 3× consecutively with no
reset between runs, exit code 0 every time.

## 2. Blockers

The v1.0 git blocker is cleared. Remaining blockers are business decisions
only (do not invent values for these — see §6 for the complete register):

- Exact fare model (base fare, ₹/km, ₹/minute, waiting rate, minimum fare,
  toll/tax treatment) — blocks full Phase 5, and blocks Task 3.1's `fare`
  field staying `null` (ADR-0010 Decision 1) from ever becoming real.
- **Wallet** (platform-fee debit, balance check) does not exist yet —
  confirmed by Task 3.2/ADR-0011 Decision 3 to be the specific, concrete
  blocker for Task 3.4 (Accept Offer), not just a general Phase 5
  dependency as v1.0 described it. `state-machines.md` §5's
  `SEARCHING → ACCEPTED` requires "Required platform fee secured" — no
  amount of matching/ride work can satisfy that without at least a minimal
  Wallet (account + balance + debit + ledger).
- Exact pickup-change rate (discussed range ₹10–₹20/km, not approved) —
  blocks full Phase 4/5.
- Exact GPS arrival/completion/early-drop radius — blocks full Phase 4.
- Whether "Dispute" is a formal domain, per
  [ADR-0002](docs/14-decisions/ADR-0002-dispute-domain-status.md) —
  blocks Phase 7 entirely until decided.
- Payment gateway selection — blocks full Phase 5.
- Promotional discount cap, custom fare-increase limit, driver/customer
  abuse-strike thresholds — blocks parts of Phases 4, 5, 6, and BR-031's
  "no driver accepts → retry/increase fare" flow (custom-increase limit).
- **The NO_DRIVER ride-state conflict** (`domain-design.md` §9.3 and
  `technical-architecture.md` §12 list it; `state-machines.md` §3.1 — the
  authoritative state-machine document — does not). Flagged, not resolved,
  in both ADR-0010 Item 6 and ADR-0011 Item 5. Blocks whichever future task
  implements BR-031 (no driver accepts → customer sees Retry/Increase
  Fare) — that task must resolve this conflict first, not pick a side
  silently.

These do not block starting the phases/tasks that don't depend on them
(e.g. Task 3.3, most of Phase 6, Phase 9) — only the specific items listed.

## 3. Phase-by-phase roadmap

Each phase lists: goal, backend scope, client scope (customer-mobile /
driver-mobile / admin-web, where applicable), dependencies, and exit
criteria. Exit criteria are drawn from and kept consistent with
implementation-readiness.md's per-phase Definition-of-Done sections; items
gated by an open business decision are marked ⚠ and must not be checked off
with an invented value.

### Phase 2 — Identity, Customer, Driver, Vehicle — ✅ COMPLETE

Backend: `identity`, `customer`, `driver`, `vehicle` modules exactly as
scoped in v1.0 of this roadmap, extended with document management
(`driver.documents`/`vehicle.documents`, ADR-0007), verification case
tracking (`verification` module, ADR-0008), admin approval gated on
required-document validity (BR-123, ADR-0009), and driver online/offline
eligibility (Task 2.7B).

Client work for Phase 2 (customer/driver app registration, profile,
document upload, admin review queues) is **not started** — every task so
far has been backend-only; see §3's client columns below as the still-open
work once client development begins.

Exit criteria (implementation-readiness.md §63) — all met:
- [x] Authentication (OTP request/verify, session, refresh, logout)
- [x] Customer profile
- [x] Driver profile
- [x] Vehicle profile (multi-vehicle support, BR-099–BR-102, BR-122)
- [x] Driver eligibility computed correctly (approved + documents valid + vehicle approved/active)
- [x] Document status tracking (BR-103–BR-105's expiry-based ineligibility; expiry *notifications* are Phase 8's Notification module, not yet built)
- [x] RBAC enforced server-side for every authenticated route

### Phase 3 — Ride, Matching — ⏳ IN PROGRESS

**Goal:** a customer can request a ride, get matched to the nearest eligible
driver, and the driver can accept/reject within the timer.

**Task 3.1 — Create Ride Request — ✅ COMPLETE (ADR-0010).**
`POST /api/v1/rides` creates `ride.rides` directly in `SEARCHING`
(fare/promotion not calculated — Pricing/Promotion don't exist; response
`fare` is `null`), with `ride.state_history` and `Idempotency-Key` handling
via the new `shared.idempotency_keys` infrastructure.

**Task 3.2 — Driver Location Tracking & Matching — ✅ COMPLETE (ADR-0011).**
`POST /api/v1/drivers/me/location` (Redis GEO), nearest-eligible-driver
dispatch on ride creation, `GET .../ride-offers` and `.../reject` with
lazy 20-second expiry (no background worker exists — evaluated on every
read/reject instead, ADR-0011 Decision 2) and rematch-to-next-driver
(BR-029/030). `ride.rides` gained `requested_vehicle_category`
(ADR-0011 Decision 1, resolving a gap ADR-0010 §8 had flagged and
deferred). Accept Offer is explicitly **not** implemented (ADR-0011
Decision 3) — see Task 3.4.

**Task 3.3 — Customer Ride Cancellation (SEARCHING only) — ✅ COMPLETE (ADR-0012).**
`POST /api/v1/rides/{ride_id}/cancel`, `SEARCHING → CANCELLED` only
(`ACCEPTED`/`ARRIVED → CANCELLED`, state-machines.md §11, aren't reachable
yet — no ride ever leaves `SEARCHING` until Task 3.4 exists). Cancels any
outstanding `PENDING` matching offer for the ride (the first real use of
`OfferStatus.CANCELLED`). BR-046–049's 2-minute-grace/₹0-first/₹15-
subsequent penalty framework presupposes a driver was assigned (a
platform fee to refund) — ADR-0012 Decision 1 records that it doesn't
apply here by its own terms: a `SEARCHING` cancellation is
unconditionally ₹0 and not counted toward that counter (`charge` is
always `null` in the response, same `null`-for-not-yet-applicable
pattern as `fare` in Task 3.1).

**Task 3.4 — Accept Offer / Ride ACCEPTED — blocked on Wallet.**
`POST /api/v1/drivers/me/ride-offers/{offer_id}/accept`,
`technical-architecture.md` §18's atomic accept transaction (lock wallet
row → validate offer/ride/eligibility → debit platform fee → assign
driver → `Ride ACCEPTED`). Cannot be honestly implemented until a minimal
Wallet exists (account, balance, debit, immutable ledger entry — the
"ready to build as specified" half of Phase 5's wallet scope, per §6's
register; the fare-formula half is separately blocked and irrelevant
here since the platform fee table, Bike ₹10/Auto ₹20/Cab ₹20, is already
approved). **Recommendation for whoever picks this up next:** pull just
the Wallet foundation forward out of Phase 5 (its own small task) rather
than waiting for all of Phase 5, since nothing else in Task 3.4 is
blocked.

**Task 3.5 — Driver Cancellation, Rematching — blocked on 3.4.**
`POST /api/v1/rides/{ride_id}/driver-cancel` (`ACCEPTED → CANCELLED`,
₹30 penalty + strike, or the changed-pickup-pass exception, BR-070/071) —
needs `ACCEPTED` to exist first.

Depends on: Phase 2 (✅ met).

Exit criteria (implementation-readiness.md §64):
- [x] Ride creation
- [x] Driver matching (nearest eligible driver)
- [x] Offer generation
- [x] 20-second expiry enforced server-side (lazy evaluation, ADR-0011 Decision 2 — client clock cannot bypass it either way, since expiry is always re-checked server-side against `expires_at`)
- [x] Offer rejection → next eligible driver, no penalty
- [ ] Atomic acceptance (concurrent accept attempts: exactly one wins, `RIDE_ALREADY_ASSIGNED` for the rest) — Task 3.4, blocked
- [x] Ride state machine enforces all valid/invalid transitions reachable so far (`SEARCHING` only)
- [x] Cancellation, `SEARCHING` only (Task 3.3) — driver cancellation and `ACCEPTED`/`ARRIVED` customer cancellation need Task 3.4/3.5

### Phase 4 — GPS Verification, Ride Start, Completion, Location Changes

**Goal:** the full in-progress ride lifecycle — arrival, OTP start,
pickup/destination changes, early drop, GPS-verified completion.

⚠ **Partially blocked**, unchanged from v1.0: GPS arrival/completion/
early-drop radius and the exact pickup-change rate are not approved (§2).
Build the verification and pickup-change logic against a **named,
server-side configuration value** (not a hard-coded literal — the same
pattern `MATCHING_SEARCH_RADIUS_KM`/`MATCHING_OFFER_TTL_SECONDS`
established in Task 3.2 for an analogous "documented as configurable, no
approved number" case) so the real figures can be substituted the moment
they're approved, without a code change. Do not ship this phase to
production with a placeholder radius/rate.

🛑 **Also depends on Task 3.4 existing** (ARRIVED/STARTED both require
`ACCEPTED` first) — cannot start meaningfully before Phase 3 finishes.

Backend: `verification` module extended (GPS arrival/completion/early-drop
checks — note a `verification` module already exists from Phase 2, Task 2.6,
for document verification; this is the same module gaining a second,
GPS-verification responsibility per domain-design.md, not a naming
collision to resolve later), OTP module (ride-start OTP, invalidate-on-
regenerate per BR-084), `ride.change_requests` handling for pickup change
(≤250m passthrough, >250m PROCEED/PASS per BR-071–BR-078) and destination
change (within-route / beyond-destination-₹8/km / different-route per
BR-079–BR-082), early-drop flow (BR-088–BR-090).

Customer app: navigation/active-ride screen, OTP entry, pickup/destination
change UI with mandatory fare-confirmation dialog (no silent charges, per
BR-077/BR-082), early-drop request.
Driver app: arrival screen, OTP prompt, pickup/destination-change
accept/pass decision, early-drop confirmation.

Depends on: Task 3.4 (ride state machine reaching ACCEPTED).

Exit criteria (implementation-readiness.md §65, adjusted to reflect open
decisions — do not check off the ⚠ items with an invented number):
- [ ] ⚠ Arrival GPS verification enforced against a configured (not yet
      approved) radius
- [ ] OTP ride start
- [ ] ⚠ Completion GPS verification enforced against a configured (not yet
      approved) radius
- [ ] Early drop (fare remains at original amount per BR-090)
- [ ] ⚠ Early-drop GPS verification enforced against a configured radius
- [ ] Configured GPS retry limit enforced before opening manual review
      (limit itself not established in PRD/business-rules — treat as an
      engineering/security configuration choice per
      [implementation-readiness.md §75](docs/11-implementation/implementation-readiness.md),
      not a business decision, unless product says otherwise)
- [ ] Pickup change (250m threshold is approved; ⚠ PROCEED charge rate is not)
- [ ] Destination change (₹8/km extension is approved and can be built as-is)

### Phase 5 — Pricing, Payments, Wallet, Penalties

**Goal:** real fares, online and offline payment, driver wallet, cancellation
and no-show penalties.

⚠ **Significantly blocked**, unchanged in substance from v1.0, but now with
a concrete forcing function: **Task 3.4 (Phase 3) needs Wallet's
foundation sooner than the rest of this phase** (see §2/Phase 3 above) —
whoever picks up Wallet should build the account/balance/debit/ledger
piece as a standalone deliverable Task 3.4 can consume, rather than
waiting for all of Phase 5 to be scheduled together.

- **Ready to build as specified:** wallet ledger and concurrency
  (technical-architecture.md §16-19), platform fee table (Bike ₹10 / Auto
  ₹20 / Cab ₹20 — already used as a constant, unenforced, everywhere Task
  3.2's eligibility checks reference "the platform fee" conceptually),
  minimum recharge ₹200, online/offline payment split architecture,
  cash-confirmation exact-match rule (BR-040-042), cash settlement +
  outstanding-settlement recovery (BR-043-045), destination extension
  ₹8/km, customer/driver cancellation penalties (₹0 first / ₹15 subsequent,
  ₹30 driver + strike — the exact rules Task 3.3 will find itself
  deliberately *not* applying yet, since no driver/fee exists in
  `SEARCHING`), no-show ₹30, all with their approved 30-day expiries.
- **Blocked, build behind configuration only:** the fare formula itself
  (base fare, ₹/km, ₹/minute, waiting rate, minimum fare, toll, tax — all
  explicitly TBD per PRD.md §62/business-rules.md §43 — this is exactly
  why Task 3.1's `fare` response field is `null`, ADR-0010 Decision 1), the
  payment gateway integration (provider TBD), the pickup-change rate
  (carried over from Phase 4 if not yet resolved).

Backend: `pricing` module (fare_quotes, versioned fare revisions — schema
already exists, `pricing.fare_quotes`/`pricing.fare_rules`, unused by any
code yet), `payment` module (payment intent, gateway webhook handling —
provider-agnostic interface until gateway is chosen), `wallet` module
(ledger, recharge, platform-fee debit, cash settlement), `penalty` module
(cancellation/no-show penalties, strikes).

Customer app: fare estimate, payment method selection, online payment flow,
offline cash-payment display, outstanding-charges screen, rating.
Driver app: cash-payment confirmation screen (exact-amount match, BR-040),
wallet screen (balance, recharge, transaction history), earnings
transparency screen (BR — "Driver Earnings Transparency" section).
Admin web: wallet/transaction monitoring, payment dispute review, pricing
configuration screen (writes to server-side config, never hard-coded).

Depends on: Phase 2 (✅), Phase 3 (ride state to hang payment/penalty
events off of — partially met; Wallet's foundation is itself now a
dependency *of* finishing Phase 3, see above — build it early).

Exit criteria (implementation-readiness.md §66, with the fare-formula and
gateway items marked):
- [ ] ⚠ Server fare calculation (formula itself pending business decision —
      build the pipeline against configuration, not a literal fare)
- [ ] ⚠ Online payment (pending payment gateway selection — build against a
      provider-agnostic interface)
- [ ] Offline payment
- [ ] Driver confirmation (exact-match enforcement)
- [ ] Wallet ledger
- [ ] Outstanding settlement
- [ ] Recharge recovery
- [ ] Penalties (cancellation, no-show, driver cancellation + strike)

### Phase 6 — Promotion, Referral

**Goal:** welcome offer, customer referral, driver referral, with abuse
prevention.

Unchanged from v1.0 — mostly ready to build as specified: welcome (3 rides
× 50%), customer referral (3 + 2 rides × 50%), driver referral (₹100 +
₹100), all with 30-day expiry, idempotent reward issuance (the
`shared.idempotency_keys` infrastructure Task 3.1 built is directly
reusable here — see §4), promotion reservation/consume/restore per ride
cancellation timing. ⚠ One open item: the maximum rupee value of the 50%
discount (business-rules BR-063) and the exact early/late promotional-
cancellation boundary (BR-065/066) are TBD — build the cap and boundary as
configuration, default unset/unlimited only for non-production testing,
and do not launch without them set.

Backend: `promotion` module (entitlements, reservations, usage), `referral`
module (codes, attribution, qualification, reward issuance, anti-self-
referral checks).
Customer app: promotions screen, referral code screen/sharing.
Admin web: promotion monitoring, referral monitoring, fraud flags.

Depends on: Phase 2 (✅), Phase 3 (ride completion/cancellation events to
trigger consumption/restoration — Task 3.3's cancellation and, later, ride
completion in Phase 4).

Exit criteria (implementation-readiness.md §67):
- [ ] Promotion reservation
- [ ] Promotion consumption
- [ ] Promotion restoration (qualifying early cancellation)
- [ ] 30-day expiry enforced
- [ ] Referral qualification (customer: register/login; driver: verified +
      approved)
- [ ] Referral reward issued exactly once per qualifying event

### Phase 7 — Dispute, Evidence, Admin Review, Audit

**Goal:** admin can review and decide GPS-verification disputes, penalty
disputes, and ride-fare disputes with a full audit trail.

🛑 **Do not start this phase until
[ADR-0002](docs/14-decisions/ADR-0002-dispute-domain-status.md) is
resolved** — unchanged from v1.0; no work since has touched this decision.
Before this phase can begin: product/architecture must decide whether
Dispute is its own domain or a capability of an existing one (Verification
is the most likely home for GPS disputes, Support/Admin for ride-fare
disputes per BR-121), and domain-design.md, database-design.md,
api-contracts.md, event-contracts.md, and state-machines.md must be
updated accordingly.

Once unblocked — backend: dispute creation, evidence upload, evidence-window
enforcement (window length also TBD — see §6), admin APPROVE/REJECT, GPS
override, full audit trail.
Admin web: dispute review queue, evidence viewer, decision recording.

Exit criteria (implementation-readiness.md §68, unchanged pending the
domain decision):
- [ ] Dispute creation
- [ ] Evidence upload
- [ ] ⚠ Evidence window enforced (length not established in PRD/business-rules)
- [ ] Admin review
- [ ] APPROVE / REJECT
- [ ] GPS override
- [ ] Audit logs

### Phase 8 — Notifications, Safety, Support

**Goal:** push/SMS notifications, SOS, lost-and-found, human + AI support.

Unchanged from v1.0. Mostly ready to build as specified (SOS incident
capture, lost-and-found workflow, support case lifecycle are all fully
defined in business-rules and state-machines). ⚠ Emergency-service
integration and notification provider are TBD — build against
provider-agnostic interfaces. This is also where BR-103's document-expiry
*notifications* (Phase 2 already computes the underlying eligibility
correctly, per BR-104/105 — only the proactive warning is deferred here)
and offer/ride push notifications finally get wired up — no outbox/Kafka
producer exists yet anywhere in this codebase (Task 3.1/3.2 both
deliberately deferred `ride.requested`/`matching.offer_*` publication for
exactly this reason, ADR-0010 Decision 3 / ADR-0011 discussion) — this
phase is the natural place `shared.outbox_events` (already fully specified
in database-design.md §34, unused) finally gets a first real consumer.

Backend: `notification` module (event-driven, consumes Kafka topics per
[event-contracts.md §22](docs/06-events/event-contracts.md)), `safety` module
(SOS, incidents), `support` module (cases, AI escalation with confidence
threshold, human handoff).
Customer app: SOS button, ride-sharing link, lost-and-found reporting,
support chat.
Driver app: SOS button, lost-and-found response.
Admin web: safety incident queue, support case queue.

Depends on: Phase 3+ (ride context for SOS/notifications to attach to — ✅
met, rides exist since Task 3.1).

Exit criteria (implementation-readiness.md §69):
- [ ] Push notifications
- [ ] SMS integration
- [ ] SOS
- [ ] Support (case creation, human escalation)
- [ ] AI escalation (confidence-threshold routing; AI restricted from
      irreversible financial/safety/suspension actions per
      [technical-architecture.md §54](docs/03-architecture/technical-architecture.md))
- [ ] Background workers (notification delivery, retry, DLQ — the first
      actual worker process in this codebase; Task 3.2 deliberately used
      lazy evaluation instead of a worker for offer expiry, ADR-0011
      Decision 2, specifically because none existed yet)

### Phase 9 — Advertisement

**Goal:** ad-campaign assignment, installation-proof verification, 80/20
driver/VISTAAR payout.

Unchanged from v1.0 — fully specified, ready to build as-is: 80% driver /
20% VISTAAR split is approved (business-rules §51). Partner integration
details (Admoto) are an external-integration detail, not a blocked
business decision. Depends on Wallet existing (payout via wallet
`CREDIT_AD_PAYOUT`) — sequence after Phase 5, or after Task 3.4's
Wallet-foundation pull-forward if that lands first.

Backend: `advertisement` module (campaigns, driver assignment, proof
submission/review, payout via wallet `CREDIT_AD_PAYOUT`).
Driver app: campaign assignment screen, proof upload.
Admin web: advertisement management.

Exit criteria (implementation-readiness.md §70):
- [ ] Advertisement assignment
- [ ] Proof upload
- [ ] Review
- [ ] Approval/rejection
- [ ] Payout
- [ ] Payout idempotency (no duplicate payout per assignment — reuse
      `shared.idempotency_keys`, same as Task 3.1)

### Phase 10 — Security Hardening, Performance, End-to-End Testing, Production Readiness

**Goal:** the system is ready to launch.

- Full security regression suite (docs/08-security/security.md §77-78,
  §91-92) — authentication, authorization, IDOR/BOLA, rate limits,
  injection, wallet/payment concurrency, admin permission boundaries.
- Load/stress/soak testing (testing-strategy.md §75-78).
- Full E2E suites for every critical flow (testing-strategy.md §82-90).
- Payment reconciliation jobs, backup/restore drills, disaster-recovery
  drills.
- Monitoring and alerting wired to the metrics list in
  implementation-readiness.md §52.
- Final admin-console hardening: reports, complaint management, fraud
  review, least-privilege role matrix (admin role hierarchy itself is TBD
  per business-rules §43 — must be finalized here at the latest).
- Resolve every remaining ⚠ item from earlier phases, **and the NO_DRIVER
  state conflict (§2)** if the task that implements BR-031 hasn't already
  forced its resolution earlier: this is the last point at which a TBD
  business value or an unresolved documentation conflict can still be
  shipped as configuration/deferred — it cannot go to production
  undecided.
- Migrate every "lazy evaluation instead of a worker" and "no outbox yet"
  decision made in earlier phases (Task 3.2's offer expiry, ADR-0011
  Decision 2; Task 3.1/3.2's undelivered domain events, ADR-0010 Decision
  3) to real background workers/event publication once Phase 8's worker
  infrastructure exists — confirm none of these were silently left as
  the permanent production design by accident.

Exit criteria (implementation-readiness.md §71, plus the
["Critical Business Acceptance Checklist"](docs/10-testing/testing-strategy.md)
— every ⚠-flagged line in that checklist must have its placeholder value
replaced with an approved figure before this phase closes):
- [ ] Security audit
- [ ] Load testing
- [ ] Concurrency testing
- [ ] Payment reconciliation
- [ ] Backup/restore test
- [ ] Disaster recovery test
- [ ] Monitoring
- [ ] Alerting
- [ ] Production smoke test
- [ ] Rollback plan
- [ ] Every TBD business value in §6 below has been resolved and the
      relevant documents (PRD/business-rules/database-design/security/
      testing-strategy) updated to reflect the approved figure, not a
      placeholder

## 4. Cross-cutting workstreams (run throughout, not a single phase)

- **Documentation upkeep.** Every phase that touches an API, event, state
  transition, or database table must update the corresponding contract
  document in the same change, per
  [implementation-readiness.md §59](docs/11-implementation/implementation-readiness.md)
  ("Documentation Rule") — practiced consistently through ADR-0004–0011,
  each pairing a code change with the doc updates it required.
- **Idempotency.** Every financial or state-changing mutation listed in
  [api-contracts.md §5](docs/05-api/api-contracts.md) needs its
  `Idempotency-Key` handling built alongside the operation itself, not
  retrofitted later. **No longer purely aspirational** — `shared/
  idempotency.py` + `shared.idempotency_keys` (built for Task 3.1, ADR-0010
  Decision 5) is real, generic, reusable infrastructure now. Every future
  phase whose endpoints document an `Idempotency-Key` header (Payment,
  Wallet recharge, Advertisement payout, ...) should reuse it directly
  rather than reinventing per-module dedup logic.
- **Outbox pattern.** Any phase that publishes a domain event must use the
  transactional outbox (event-contracts.md §2, §27-28) from the start —
  retrofitting this after data has been written directly is far more
  costly than building it in early. **Still not built anywhere** —
  `shared.outbox_events` is fully specified (database-design.md §34) but
  has zero rows written to it by any code as of Task 3.2; `ride.requested`
  and every `matching.offer_*` event remain undelivered by design (ADR-0010
  Decision 3, ADR-0011 discussion), since no consumer exists yet either.
  Phase 8 (Notifications) is the natural first real consumer — see that
  phase's entry above.
- **Testing discipline.** Per
  [testing-strategy.md §103](docs/10-testing/testing-strategy.md), test
  coverage priority order is: Wallet → Payment → Ride state machine →
  Matching/offer acceptance → Fare calculation → GPS verification →
  Penalties → Promotions → Authorization → Admin actions. Each phase above
  should write its tests in that relative priority, not defer them to
  Phase 10. Practiced so far as: real-Postgres integration tests for every
  API endpoint, a dedicated test database isolated from the dev database
  (`tests/_integration_db.py`), unit tests against in-memory fakes for
  every service, and a full-suite regression run (currently 421 tests)
  after every task.
- **Admin capability growth.** Admin-web work is not confined to a single
  phase — driver/vehicle review ships in Phase 2 (✅ backend; admin-web
  client itself not started), financial/wallet monitoring in Phase 5,
  promotion/referral monitoring in Phase 6, dispute review in Phase 7,
  safety/support queues in Phase 8, advertisement management in Phase 9.
  Phase 10 only hardens and completes the role matrix.
- **Client apps have not started.** Every task through Task 3.3 has been
  backend-only. `apps/customer-mobile`, `apps/driver-mobile`, and
  `apps/admin-web` remain at their Phase 1 skeleton state. This isn't a
  blocker for continuing backend work, but it means none of Phase 2/3's
  backend capability is usable end-to-end by an actual user yet — worth
  surfacing explicitly rather than letting backend-only progress read as
  more "done" than it is.

## 5. Milestone summary

| Phase | Name | Backend modules | Status |
|---|---|---|---|
| 1 | Foundation | (infra/tooling only) | ✅ Complete |
| 2 | Identity / Customer / Driver / Vehicle | identity, customer, driver, vehicle, verification, admin | ✅ Complete |
| 3 | Ride / Matching | ride, matching | ⏳ In progress (3.1, 3.2, 3.3 done; 3.4/3.5 blocked on Wallet) |
| 4 | GPS, Ride Start/Completion, Location Changes | verification (extended), ride (extended) | ⚠ GPS radii + pickup rate TBD; 🛑 also blocked on Task 3.4 |
| 5 | Pricing, Payments, Wallet, Penalties | pricing, payment, wallet, penalty | ⚠ Fare formula + payment gateway TBD; wallet foundation now needed earlier (see Task 3.4) |
| 6 | Promotion / Referral | promotion, referral | ⚠ Discount cap + cancellation boundary TBD |
| 7 | Dispute, Evidence, Admin Review | (domain TBD — see ADR-0002) | 🛑 Blocked until ADR-0002 resolved |
| 8 | Notifications, Safety, Support | notification, safety, support | ⚠ Emergency integration + notification provider TBD |
| 9 | Advertisement | advertisement | ⚠ Needs Wallet (payout) |
| 10 | Security, Performance, E2E, Production Readiness | (cross-cutting) | 🛑 Blocked until every ⚠ above is resolved |

## 6. Open business-decision register

Every value below is explicitly TBD in PRD.md and/or business-rules.md and
must be resolved by an explicit product/business decision — not invented
during implementation. This consolidates the individual mentions across
§2–§3 above into one list for tracking. Items resolved since v1.0 of this
roadmap have been removed (vehicle_category's missing `ride.rides` column,
ADR-0011 Decision 1/§8; the ride-schema-vs-technical-architecture.md
conflict, ADR-0010 Decision 7; whether a pre-acceptance `SEARCHING`
cancellation counts toward the progressive-penalty counter, ADR-0012
Decision 1 — it doesn't).

| Item | Source | Blocks |
|---|---|---|
| Base fare, ₹/km, ₹/minute, waiting rate, minimum fare, toll treatment, tax treatment | PRD.md §62, business-rules.md §43 | Phase 5; keeps Task 3.1's `fare` response `null` |
| Wallet foundation not yet built (account/balance/debit/ledger) | technical-architecture.md §16-19 | Task 3.4 specifically, ahead of the rest of Phase 5 |
| Pickup-change rate (discussed range ₹10–₹20/km) | business-rules.md BR-076, PRD.md §20/§62 | Phase 4, 5 |
| GPS arrival radius | PRD.md §62, business-rules.md §43 | Phase 4 |
| GPS completion radius | PRD.md §62, business-rules.md §43 | Phase 4 |
| GPS retry count, evidence-window length | not established in PRD/business-rules at all | Phase 4, 7 |
| Whether "Dispute" is a formal domain | [ADR-0002](docs/14-decisions/ADR-0002-dispute-domain-status.md) | Phase 7 |
| Payment gateway provider | PRD.md §62 | Phase 5 |
| Promotional discount cap (max ₹ value of 50% off) | business-rules.md BR-063 | Phase 6 |
| Early/late promotional-cancellation boundary | business-rules.md BR-065/066 | Phase 6 |
| Custom fare-increase maximum | business-rules.md §43 | Phase 3's BR-031 "no driver found" flow (not yet built — also needs the NO_DRIVER conflict resolved first) |
| Driver/customer abuse strike thresholds, suspension duration | business-rules.md §43 | Phases 4, 5 |
| **NO_DRIVER ride-state conflict** — `domain-design.md`/`technical-architecture.md` list it, `state-machines.md` (authoritative) doesn't | ADR-0010 Item 6, ADR-0011 Item 5 | Whichever future task implements BR-031 |
| Emergency-service integration | PRD.md §62 | Phase 8 |
| Notification provider | PRD.md §62 | Phase 8 |
| Admin role hierarchy / permission matrix | PRD.md §62, security.md §89 | Phase 10 |
| Data retention periods (location, documents, backups) | database-design.md §47/§55, security.md §89 | Phase 10 |
| Launch city, launch date, initial scale | PRD.md §60 | Not a code blocker — needed for capacity planning ahead of Phase 10 |

## 7. Architecture Decision Records recorded so far

| ADR | Topic | Status |
|---|---|---|
| [0001](docs/14-decisions/ADR-0001-backend-and-client-technology-stack.md) | Backend and client technology stack | Accepted |
| [0002](docs/14-decisions/ADR-0002-dispute-domain-status.md) | Dispute domain status | Decision required (blocks Phase 7) |
| [0003](docs/14-decisions/ADR-0003-documentation-numbering-reconciliation.md) | Documentation folder numbering reconciliation | Accepted (filing only) |
| [0004](docs/14-decisions/ADR-0004-driver-profile-creation-semantics.md) | Driver profile creation semantics | Accepted |
| [0005](docs/14-decisions/ADR-0005-br097-driver-onboarding-schema-reconciliation.md) | BR-097 driver onboarding vs. schema | Partially decided |
| [0006](docs/14-decisions/ADR-0006-vehicle-lifecycle-single-active-vehicle.md) | Single active vehicle per driver (BR-122) | Accepted |
| [0007](docs/14-decisions/ADR-0007-document-type-and-endpoint-scope.md) | Document type vocabulary & endpoint scope | Partially decided |
| [0008](docs/14-decisions/ADR-0008-verification-case-scope-and-open-items.md) | Verification case scope | Mostly accepted, 2 items open |
| [0009](docs/14-decisions/ADR-0009-admin-approval-scope-and-open-items.md) | Admin approval scope (incl. BR-123) | Mostly accepted, 2 items open |
| [0010](docs/14-decisions/ADR-0010-ride-creation-scope-and-open-items.md) | Ride creation (Task 3.1) scope | Accepted, 1 item deliberately open (Item 6, NO_DRIVER) |
| [0011](docs/14-decisions/ADR-0011-matching-scope-and-open-items.md) | Matching (Task 3.2) scope | Accepted, 1 item deliberately open (Item 5, NO_DRIVER) |
| [0012](docs/14-decisions/ADR-0012-searching-cancellation-scope-and-open-items.md) | Customer cancellation (Task 3.3) scope | Accepted, 1 item deliberately open (Item 3, post-acceptance cancellation) |

## 8. Document Status

Version: 2.0
Status: Draft
Derived from: PRD v2.0, Business Rules v1.0, Technical Architecture v2.0,
Domain Design v1.0, Database Design v1.0, API Contracts v1.0, Event
Contracts v1.0, State Machines v1.0, Security v1.0, Testing Strategy v1.0,
Implementation Readiness v1.0, ADR-0001 through ADR-0012.

This roadmap should be updated whenever a phase completes, a blocker
clears, or a business decision in §6 is resolved — practiced for this
revision by reconciling it against Tasks 2.3 through 3.2 and ADR-0004
through ADR-0012 in one pass, rather than letting it drift further out of
date.
