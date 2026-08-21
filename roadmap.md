# VISTAAR — Implementation Roadmap

Version: 1.0
Date: 2026-08-20
Status: Draft
Scope: apps/backend, apps/customer-mobile, apps/driver-mobile, apps/admin-web, services/*, packages/*, infrastructure/*

## 0. How to read this document

This roadmap sequences the work that turns the completed VISTAAR design
documentation (docs/01-product through docs/11-implementation) into a
working product. It does not restate business rules, API shapes, database
schemas, or state machines — those remain authoritative in their own
documents. This file only answers: **what gets built, in what order, and
what has to be true before each phase can be considered done.**

Phase numbering follows [docs/11-implementation/implementation-readiness.md §61](docs/11-implementation/implementation-readiness.md)
("Implementation Order"), which is the one document in this repository
already written for this exact purpose and already carries a
Definition-of-Done checklist per phase. This roadmap consolidates that plan
with the actual current repository state, the three Architecture Decision
Records recorded during the most recent documentation reconciliation, and
the explicit list of business decisions that are still open.

**Governing rules for every phase below** (from
[business-rules.md §44-45](docs/02-business/business-rules.md) and
[implementation-readiness.md §74](docs/11-implementation/implementation-readiness.md)):

- PRD.md and business-rules.md remain authoritative. A phase must not invent
  a business value that those documents mark TBD.
- If implementation hits a genuine unresolved business question: **stop**,
  identify the exact ambiguity, ask a focused question, record the answer,
  update the relevant document, then continue. Do not silently assume.
- A change to an approved business rule requires updating the business-rules
  document first, then the affected architecture/API/event/database/test
  documents, before code changes.
- Historical/completed transactions (fares, penalties, promotions) must
  retain the rule version that was actually applied, even after a later
  rule change.

## 1. Current status (as of this roadmap's date)

**Phase 1 — Foundation: substantially complete.**

| # | Task | Status |
|---|---|---|
| 1 | Git Setup | ❌ NOT COMPLETED — see §2 blocker below |
| 2 | Backend Skeleton | ✅ Complete |
| 3A | Flutter Development Environment | ✅ Complete |
| 3 | Customer Mobile Skeleton | ✅ Complete (Flutter, no platform target scaffolded yet beyond the `web`/`windows` support added while verifying it runs) |
| 4 | Driver Mobile Skeleton | ✅ Complete |
| 5 | Admin Web Skeleton | ✅ Complete (Next.js default scaffold, unmodified) |
| 6 | Shared Packages Foundation | ✅ Complete (README-only stubs — no code yet) |
| 7 | Environment Configuration | ✅ Complete |
| 8 | Python Development Environment | ✅ Complete |
| 9 | Code Quality Tools | ✅ Complete (ruff, mypy) |
| 10 | Testing Foundation | ✅ Complete (pytest) |
| 11 | CI Foundation | ✅ Complete (.github/workflows/ci.yml) |
| 12 | Docker Foundation | ✅ Complete |
| 13 | Local Infrastructure | ✅ Complete (docker-compose.dev.yml) |
| 14 | PostgreSQL Foundation | ✅ Complete (connection layer only — no tables yet) |
| 15 | Backend Configuration | ✅ Complete |
| 16 | Redis Integration | ✅ Complete (connection layer only) |
| 17 | Kafka Integration | ✅ Complete (connection layer only) |
| 18 | API Contract Foundation | ✅ Complete (docs/05-api/api-contracts.md) |
| 19 | Event Contract Foundation | ✅ Complete (docs/06-events/event-contracts.md) |
| 20 | Domain Foundation | ✅ Complete (docs/04-domain-design/domain-design.md) |

Verified directly: the backend boots and serves `/`, `/health`,
`/health/db`, `/health/redis`, `/health/kafka`; the customer-mobile skeleton
renders correctly once given a platform target. No business logic, database
table, API route, domain model, or Kafka topic exists in code yet — Tasks
2–20 are entirely infrastructure, tooling, and documentation.

## 2. Blockers to clear before Phase 2 (business-logic implementation) starts

1. **Git Setup (Task 1).** No `.git` exists in this repository. CI workflow,
   `.gitignore`, and every phase's "commit reviewable work" expectation
   assume version control. implementation-readiness.md's own
   ["Final Pre-Coding Gate" §79](docs/11-implementation/implementation-readiness.md)
   lists "Repository initialized" and "All documentation committed to Git"
   as explicit gates before business logic is written. This should be the
   very first thing done in Phase 2, not deferred further.
2. **Open business decisions that block full completion of specific phases**
   (do not invent values for these — see §6 for the complete register):
   - Exact fare model (base fare, ₹/km, ₹/minute, waiting rate, minimum
     fare, toll/tax treatment) — blocks full Phase 5.
   - Exact pickup-change rate (discussed range ₹10–₹20/km, not approved) —
     blocks full Phase 4/5.
   - Exact GPS arrival/completion/early-drop radius — blocks full Phase 4.
   - Whether "Dispute" is a formal domain, per
     [ADR-0002](docs/14-decisions/ADR-0002-dispute-domain-status.md) —
     blocks Phase 7 entirely until decided.
   - Payment gateway selection — blocks full Phase 5.
   - Promotional discount cap, custom fare-increase limit, driver/customer
     abuse-strike thresholds — blocks parts of Phases 4, 5, 6.
   These do not block starting the phases that don't depend on them (e.g.
   Phase 2, most of Phase 3, most of Phase 6, Phase 9) — only the specific
   items listed.

## 3. Phase-by-phase roadmap

Each phase lists: goal, backend scope, client scope (customer-mobile /
driver-mobile / admin-web, where applicable), dependencies, and exit
criteria. Exit criteria are drawn from and kept consistent with
implementation-readiness.md's per-phase Definition-of-Done sections; items
gated by an open business decision are marked ⚠ and must not be checked off
with an invented value.

### Phase 2 — Identity, Customer, Driver, Vehicle

**Goal:** authenticated accounts, customer/driver profiles, vehicle
registration and verification status, admin RBAC skeleton.

Backend: `identity` module (phone+OTP auth, sessions, token refresh),
`customer` module, `driver` module, `vehicle` module (multi-vehicle-per-driver
support, per business-rules BR-099–BR-102), document upload/verification
status tracking, RBAC primitives (`require_customer`/`require_driver`/
`require_admin`/`require_permission`/`require_resource_owner` per
[implementation-readiness.md §33](docs/11-implementation/implementation-readiness.md)).

Customer app: registration/login (mobile + OTP), profile screen.
Driver app: login/OTP, driver onboarding flow (personal/identity/vehicle/
payment info per business-rules BR-097), document upload, vehicle
management (add/activate/deactivate, switch-while-offline-only per BR-102).
Admin web: driver review queue, vehicle approval queue, customer/driver
account management (per [implementation-readiness.md §38](docs/11-implementation/implementation-readiness.md)).

Depends on: §2 blocker #1 resolved (git init).

Exit criteria (implementation-readiness.md §63):
- [ ] Authentication (OTP request/verify, session, refresh, logout)
- [ ] Customer profile
- [ ] Driver profile
- [ ] Vehicle profile (multi-vehicle support)
- [ ] Driver eligibility computed correctly (approved + documents valid + vehicle approved/active)
- [ ] Document status tracking (including expiry notifications, BR-103–BR-105)
- [ ] RBAC enforced server-side for every authenticated route

### Phase 3 — Ride, Matching

**Goal:** a customer can request a ride, get matched to the nearest eligible
driver, and the driver can accept/reject within the timer.

Backend: `ride` module (ride creation, ride state machine per
[state-machines.md §3-11](docs/07-state-machines/state-machines.md)), `matching`
module (Redis GEO driver discovery, eligibility filtering, offer creation/
expiry, 20-second timer per BR-027), atomic accept-ride transaction (wallet
lock → fee debit → assignment, per [technical-architecture.md §18](docs/03-architecture/technical-architecture.md)).

Customer app: pickup/destination selection, vehicle category selection,
booking/searching screen, driver tracking, cancellation.
Driver app: ride request screen with 20s countdown, accept/reject, "cannot
go offline with pending offer" enforcement (BR-107).

Depends on: Phase 2 (driver eligibility, wallet account existing — wallet
itself is built in Phase 5, but the *account* and eligibility check needed
for matching should exist by end of this phase; sequence with Phase 5 as
needed if wallet balance checks are required before real fee amounts exist).

Exit criteria (implementation-readiness.md §64):
- [ ] Ride creation
- [ ] Driver matching (nearest eligible driver)
- [ ] Offer generation
- [ ] 20-second expiry enforced server-side (client clock cannot bypass)
- [ ] Offer rejection → next eligible driver, no penalty
- [ ] Atomic acceptance (concurrent accept attempts: exactly one wins,
      `RIDE_ALREADY_ASSIGNED` for the rest)
- [ ] Ride state machine enforces all valid/invalid transitions per
      state-machines.md §49-50
- [ ] Cancellation (customer/driver, pre-completion states only)

### Phase 4 — GPS Verification, Ride Start, Completion, Location Changes

**Goal:** the full in-progress ride lifecycle — arrival, OTP start,
pickup/destination changes, early drop, GPS-verified completion.

⚠ **Partially blocked.** GPS arrival/completion/early-drop radius and the
exact pickup-change rate are not approved (§2 blocker #2). Build the
verification and pickup-change logic against a **named, server-side
configuration value** (not a hard-coded literal) so the real figures can be
substituted the moment they're approved, without a code change. Do not ship
this phase to production with a placeholder radius/rate.

Backend: `verification` module (GPS arrival/completion/early-drop checks,
retry counting), OTP module (ride-start OTP, invalidate-on-regenerate per
BR-084), `ride.change_requests` handling for pickup change (≤250m passthrough,
>250m PROCEED/PASS per BR-071–BR-078) and destination change (within-route /
beyond-destination-₹8/km / different-route per BR-079–BR-082), early-drop
flow (BR-088–BR-090).

Customer app: navigation/active-ride screen, OTP entry, pickup/destination
change UI with mandatory fare-confirmation dialog (no silent charges, per
BR-077/BR-082), early-drop request.
Driver app: arrival screen, OTP prompt, pickup/destination-change
accept/pass decision, early-drop confirmation.

Depends on: Phase 3 (ride state machine, offers).

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

⚠ **Significantly blocked.** This is the phase with the most open business
decisions. Sequence it so the parts that ARE approved can be built and
tested now, and isolate the parts that aren't behind configuration:

- **Ready to build as specified:** wallet ledger and concurrency
  (technical-architecture.md §16-19), platform fee table (Bike ₹10 / Auto
  ₹20 / Cab ₹20), minimum recharge ₹200, online/offline payment split
  architecture, cash-confirmation exact-match rule (BR-040-042), cash
  settlement + outstanding-settlement recovery (BR-043-045), destination
  extension ₹8/km, customer/driver cancellation penalties (₹0 first / ₹15
  subsequent, ₹30 driver + strike), no-show ₹30, all with their approved
  30-day expiries.
- **Blocked, build behind configuration only:** the fare formula itself
  (base fare, ₹/km, ₹/minute, waiting rate, minimum fare, toll, tax — all
  explicitly TBD per PRD.md §62/business-rules.md §43), the payment gateway
  integration (provider TBD), the pickup-change rate (carried over from
  Phase 4 if not yet resolved).

Backend: `pricing` module (fare_quotes, versioned fare revisions), `payment`
module (payment intent, gateway webhook handling — provider-agnostic
interface until gateway is chosen), `wallet` module (ledger, recharge,
platform-fee debit, cash settlement), `penalty` module (cancellation/no-show
penalties, strikes).

Customer app: fare estimate, payment method selection, online payment flow,
offline cash-payment display, outstanding-charges screen, rating.
Driver app: cash-payment confirmation screen (exact-amount match, BR-040),
wallet screen (balance, recharge, transaction history), earnings
transparency screen (BR — "Driver Earnings Transparency" section).
Admin web: wallet/transaction monitoring, payment dispute review, pricing
configuration screen (writes to server-side config, never hard-coded).

Depends on: Phase 2 (accounts), Phase 3/4 (ride state to hang payment/
penalty events off of).

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

Mostly ready to build as specified: welcome (3 rides × 50%), customer
referral (3 + 2 rides × 50%), driver referral (₹100 + ₹100), all with
30-day expiry, idempotent reward issuance, promotion reservation/consume/
restore per ride cancellation timing. ⚠ One open item: the maximum rupee
value of the 50% discount (business-rules BR-063) and the exact early/late
promotional-cancellation boundary (BR-065/066) are TBD — build the cap and
boundary as configuration, default unset/unlimited only for non-production
testing, and do not launch without them set.

Backend: `promotion` module (entitlements, reservations, usage), `referral`
module (codes, attribution, qualification, reward issuance, anti-self-
referral checks).
Customer app: promotions screen, referral code screen/sharing.
Admin web: promotion monitoring, referral monitoring, fraud flags.

Depends on: Phase 2 (customer accounts), Phase 3 (ride completion/
cancellation events to trigger consumption/restoration).

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
resolved.** Search of the full documentation set found no canonical
domain, database schema, API contract, event family, or state machine for
"Dispute" as implementation-readiness.md describes it — only a narrow
`DisputePenalty` command inside the Penalty domain, and business-rules'
routing of ride-fare disputes through the existing Support/Admin process.
Building this phase against implementation-readiness.md's "Dispute Module"
as currently written would produce code with no corresponding
domain/database/API/event documentation behind it. Before this phase can
begin: product/architecture must decide whether Dispute is its own domain
or a capability of an existing one (Verification is the most likely home
for GPS disputes, Support/Admin for ride-fare disputes per BR-121), and
domain-design.md, database-design.md, api-contracts.md, event-contracts.md,
and state-machines.md must be updated accordingly.

Once unblocked — backend: dispute creation, evidence upload, evidence-window
enforcement (window length also TBD — see §2), admin APPROVE/REJECT, GPS
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

Mostly ready to build as specified (SOS incident capture, lost-and-found
workflow, support case lifecycle are all fully defined in business-rules
and state-machines). ⚠ Emergency-service integration and notification
provider are TBD — build against provider-agnostic interfaces.

Backend: `notification` module (event-driven, consumes Kafka topics per
[event-contracts.md §22](docs/06-events/event-contracts.md)), `safety` module
(SOS, incidents), `support` module (cases, AI escalation with confidence
threshold, human handoff).
Customer app: SOS button, ride-sharing link, lost-and-found reporting,
support chat.
Driver app: SOS button, lost-and-found response.
Admin web: safety incident queue, support case queue.

Depends on: Phase 3+ (ride context for SOS/notifications to attach to).

Exit criteria (implementation-readiness.md §69):
- [ ] Push notifications
- [ ] SMS integration
- [ ] SOS
- [ ] Support (case creation, human escalation)
- [ ] AI escalation (confidence-threshold routing; AI restricted from
      irreversible financial/safety/suspension actions per
      [technical-architecture.md §54](docs/03-architecture/technical-architecture.md))
- [ ] Background workers (notification delivery, retry, DLQ)

### Phase 9 — Advertisement

**Goal:** ad-campaign assignment, installation-proof verification, 80/20
driver/VISTAAR payout.

Fully specified, ready to build as-is: 80% driver / 20% VISTAAR split is
approved (business-rules §51). Partner integration details (Admoto) are an
external-integration detail, not a blocked business decision.

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
- [ ] Payout idempotency (no duplicate payout per assignment)

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
- Resolve every remaining ⚠ item from earlier phases: this is the last
  point at which a TBD business value can still be shipped as
  configuration rather than a decided number — it cannot go to production
  undecided.

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
  ("Documentation Rule").
- **Idempotency.** Every financial or state-changing mutation listed in
  [api-contracts.md §5](docs/05-api/api-contracts.md) needs its
  `Idempotency-Key` handling built alongside the operation itself, not
  retrofitted later.
- **Outbox pattern.** Any phase that publishes a domain event must use the
  transactional outbox (event-contracts.md §2, §27-28) from the start —
  retrofitting this after data has been written directly is far more
  costly than building it in from phase 3 onward.
- **Testing discipline.** Per
  [testing-strategy.md §103](docs/10-testing/testing-strategy.md), test
  coverage priority order is: Wallet → Payment → Ride state machine →
  Matching/offer acceptance → Fare calculation → GPS verification →
  Penalties → Promotions → Authorization → Admin actions. Each phase above
  should write its tests in that relative priority, not defer them to
  Phase 10.
- **Admin capability growth.** Admin-web work is not confined to a single
  phase — driver/vehicle review ships in Phase 2, financial/wallet
  monitoring in Phase 5, promotion/referral monitoring in Phase 6, dispute
  review in Phase 7, safety/support queues in Phase 8, advertisement
  management in Phase 9. Phase 10 only hardens and completes the role
  matrix.

## 5. Milestone summary

| Phase | Name | Backend modules | Fully unblocked? |
|---|---|---|---|
| 1 | Foundation | (infra/tooling only) | ⚠ Task 1 (git init) outstanding |
| 2 | Identity / Customer / Driver / Vehicle | identity, customer, driver, vehicle | ✅ Yes |
| 3 | Ride / Matching | ride, matching | ✅ Yes |
| 4 | GPS, Ride Start/Completion, Location Changes | verification, ride (extended) | ⚠ GPS radii + pickup rate TBD |
| 5 | Pricing, Payments, Wallet, Penalties | pricing, payment, wallet, penalty | ⚠ Fare formula + payment gateway TBD |
| 6 | Promotion / Referral | promotion, referral | ⚠ Discount cap + cancellation boundary TBD |
| 7 | Dispute, Evidence, Admin Review | (domain TBD — see ADR-0002) | 🛑 Blocked until ADR-0002 resolved |
| 8 | Notifications, Safety, Support | notification, safety, support | ⚠ Emergency integration + notification provider TBD |
| 9 | Advertisement | advertisement | ✅ Yes |
| 10 | Security, Performance, E2E, Production Readiness | (cross-cutting) | 🛑 Blocked until every ⚠ above is resolved |

## 6. Open business-decision register

Every value below is explicitly TBD in PRD.md and/or business-rules.md and
must be resolved by an explicit product/business decision — not invented
during implementation. This consolidates the individual mentions across
§2–§3 above into one list for tracking.

| Item | Source | Blocks |
|---|---|---|
| Base fare, ₹/km, ₹/minute, waiting rate, minimum fare, toll treatment, tax treatment | PRD.md §62, business-rules.md §43 | Phase 5 |
| Pickup-change rate (discussed range ₹10–₹20/km) | business-rules.md BR-076, PRD.md §20/§62 | Phase 4, 5 |
| GPS arrival radius | PRD.md §62, business-rules.md §43 | Phase 4 |
| GPS completion radius | PRD.md §62, business-rules.md §43 | Phase 4 |
| GPS retry count, evidence-window length | not established in PRD/business-rules at all | Phase 4, 7 |
| Whether "Dispute" is a formal domain | [ADR-0002](docs/14-decisions/ADR-0002-dispute-domain-status.md) | Phase 7 |
| Payment gateway provider | PRD.md §62 | Phase 5 |
| Promotional discount cap (max ₹ value of 50% off) | business-rules.md BR-063 | Phase 6 |
| Early/late promotional-cancellation boundary | business-rules.md BR-065/066 | Phase 6 |
| Custom fare-increase maximum | business-rules.md §43 | Phase 3 (no-driver-found flow) |
| Driver/customer abuse strike thresholds, suspension duration | business-rules.md §43 | Phases 4, 5 |
| Emergency-service integration | PRD.md §62 | Phase 8 |
| Notification provider | PRD.md §62 | Phase 8 |
| Admin role hierarchy / permission matrix | PRD.md §62, security.md §89 | Phase 10 |
| Data retention periods (location, documents, backups) | database-design.md §47/§55, security.md §89 | Phase 10 |
| Launch city, launch date, initial scale | PRD.md §60 | Not a code blocker — needed for capacity planning ahead of Phase 10 |

## 7. Document Status

Version: 1.0
Status: Draft
Derived from: PRD v2.0, Business Rules v1.0, Technical Architecture v2.0,
Domain Design v1.0, Database Design v1.0, API Contracts v1.0, Event
Contracts v1.0, State Machines v1.0, Security v1.0, Testing Strategy v1.0,
Implementation Readiness v1.0, ADR-0001, ADR-0002, ADR-0003.

This roadmap should be updated whenever a phase completes, a blocker
clears, or a business decision in §6 is resolved.
