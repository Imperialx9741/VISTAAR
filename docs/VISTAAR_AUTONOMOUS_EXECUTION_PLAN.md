VISTAAR — Autonomous Execution Plan (Phase Completability Assessment)

Companion to `VISTAAR_IMPLEMENTATION_ROADMAP.md`, not a replacement for it. That
file remains the authoritative task breakdown and execution-control document. This
file answers one specific question the project owner asked: of the 21 phases /
280 tasks, how many can be completed autonomously (no per-task review, per the
owner's phase-level-autonomy grant) versus how many will still force a stop —
and exactly why.

Methodology: "Blocked" here means the roadmap's own §0.3 mandatory-stop
conditions apply — a genuinely TBD business value, a credential/provider that
doesn't exist yet, or an explicit ADR-controlled decision gate. It does not mean
"not built yet" (everything not yet built is, by definition, not yet built — that
alone is never a reason to stop). Where a phase is blocked on one specific value
or provider but the surrounding engineering is sound, that is called out
precisely rather than writing the whole phase off.

Status date: 2026-08-24 (updated after Phase 04's Tasks 3.5/3.6 completed).
Reconcile against the actual repository before trusting this file in a future
session, same as the master roadmap's own §1 warns.

SUMMARY

Of 21 phases: 3 are fully or almost-fully completable with no blocker, 10 are
mostly completable with one or a few specific tasks blocked, and 8 have their
core value blocked by a real external decision (most of a phase, not just one
task, is unbuildable without it). Updated 2026-08-24 as work actually progressed
(Phases 02 and 18 both moved from the first bucket to the second once deeper
research turned up genuine, specific blockers within them — not a change in
overall completability, just more precision than the original pass had.)

Fully/mostly completable (no real blocker): 04, 05*, 19, 20
Mostly completable (1-3 tasks blocked, rest sound): 01, 02, 03, 11, 12, 14, 16, 17, 18
Core value blocked (most of the phase needs an external decision): 06, 07, 08, 09, 10, 13, 15, 21

(Corrected 2026-08-24 — Phase 04 moved from the second bucket to the first: its one
previously-blocked task, Initial fare quote, is now resolved (ADR-0020); its only
remaining item, GET ride status, is unblocked, just not yet built — zero genuinely
blocked tasks left in this phase.)

(Corrected 2026-08-25 — Phase 10's classification changes character, not just
degree, per ADR-0025 (Approved P2P Payment Model, documentation-only): it isn't
"core value blocked by a real external decision" in the sense every other phase
in that bucket is (where the value exists and a decision would unlock it) — most
of Phase 10's value doesn't exist to unlock, because VISTAAR never collects the
ride fare. Left in this bucket for now rather than reclassified, since a narrow
genuine gateway decision (wallet-recharge) does still block a small residual
piece — see its own PHASE-BY-PHASE entry below for the full reconciliation. This
summary list and bucket counts are otherwise a 2026-08-24 snapshot and have not
been fully re-audited against every phase completed since — see the roadmap's
own §2.0 and this file's RECOMMENDED EXECUTION ORDER section for the current,
maintained record of what's actually done.)

(*05 — Matching is already COMPLETE per the master roadmap's §2.0/§8; listed here
only for completeness of the 21-phase sweep.)

(Corrected 2026-08-25 — Phases 06 and 07 both move out of "core value
blocked": the project owner resolved the GPS radius/retry-count and
Dispute-domain questions, and ADR-0028 implements the full ACCEPTED →
CLOSED ride lifecycle and GPS verification foundation. Both are now
DONE, not merely unblocked — see the roadmap's §2.0/§13/§14 and this
file's RECOMMENDED EXECUTION ORDER item 13. Phase 08 (Early Drop) also
loses its transitive GPS blocker but stays in the "core value blocked"
bucket's neighborhood only nominally — it is genuinely unblocked now,
simply not yet started as its own task (see its own PHASE-BY-PHASE entry
above). This summary list and bucket counts are otherwise a 2026-08-24
snapshot and have not been fully re-audited against every phase
completed since — see the roadmap's own §2.0 and this file's RECOMMENDED
EXECUTION ORDER section for the current, maintained record of what's
actually done.)

(Corrected 2026-08-25, same day, again — Phase 13 also moves out of "core
value blocked": immediately after Phase 06/07, the project owner asked
for Dispute-as-Support specifically, and ADR-0029 implements exactly what
BR-121/domain-design.md §17.3 authorize — see this file's RECOMMENDED
EXECUTION ORDER item 14. Only the much larger, never-ratified
GPS-verification-dispute evidence/admin-override workflow within Phase
13 remains genuinely blocked, and it is blocked on a business-rules.md
decision that was never made, not on engineering time.)

(Corrected 2026-08-25, same day, a third time — Phase 08 (Early Drop)
moves from "genuinely unblocked, not yet built" to fully DONE: continuing
autonomously, ADR-0030 found the apparent GPS-tolerance blocker never
actually required an owner decision (BR-088/api-contracts.md §27/
technical-architecture.md §43 already establish GPS/location as recorded
evidence, not a verified threshold) and implements RequestEarlyDrop/
ConfirmEarlyDrop in full — see this file's RECOMMENDED EXECUTION ORDER
item 15.)

That is 13 of 21 phases where autonomous work is genuinely productive right now,
and 8 where the honest answer is "very little can be finished without your
input first," no matter how much time is spent. (As of 2026-08-25, with
Phase 06/07 now DONE and Phase 08 reclassified to genuinely-unblocked, the
practical count of phases still waiting on a real project-owner decision has
fallen to 6 — see the correction immediately above; the "13/8" split in this
paragraph is left as the original 2026-08-24 snapshot, not restated, matching
this file's own established idiom of layering corrections rather than
rewriting prior counts in place. Falls to 5 as of the same day's second
correction, immediately above — Phase 13 is now also DONE for its
documented scope. Phase 08 itself is also now fully DONE, not merely
unblocked, per the third correction immediately above — the practical
count of phases genuinely waiting on the project owner stays at 5, since
Phase 08 had already been counted as unblocked rather than blocked.)

PHASE-BY-PHASE

01 — Foundation (19 tasks)

Already complete: 1-16, 19 (per roadmap §4).
Object storage foundation: RESOLVED and IMPLEMENTED (ADR-0031, 2026-08-25) —
the project owner selected AWS S3, not MinIO (MinIO was only ever a
candidate). No longer blocked.
Background worker foundation: RESOLVED and IMPLEMENTED (ADR-0039,
2026-08-26) — the project owner approved Celery ("Use Celery for
background workers"). Redis (already provisioned) serves as broker and
result backend, no new infrastructure. No longer blocked.
Corrected 2026-08-25 — this section previously claimed driver document
uploads (`evidence_uri`) still used the opaque placeholder pattern,
not yet retrofitted onto real object storage. Re-checked against the
actual code before suggesting it as a next task: `POST /api/v1/drivers/
me/documents`'s `evidence_uri` IS already S3-backed — ADR-0031 Decision
2's `POST /api/v1/drivers/me/uploads` presigned-URL endpoint explicitly
serves both `profile_photo_uri` (PATCH /me) and `evidence_uri` (POST
.../documents), unchanged shape either way (see modules/driver/
router.py's own docstring). Only vehicle documents remain outside this
— not because they are still on a placeholder, but because no HTTP
endpoint exists for vehicle-document submission at all (ADR-0007's own,
already-recorded, separate scope decision); there is no "placeholder"
to retrofit there, only a documented decision not to build the
endpoint. Nothing in this phase's own 19 tasks is workaround-blocked
any longer.
Verdict: COMPLETE. Zero remaining tasks in this phase (down from 2
blocked — object storage resolved, ADR-0031; background-worker
foundation resolved, ADR-0039).

02 — Identity (17 tasks)

Substantially implemented (customer/driver auth, OTP, tokens, profiles,
admin authentication — all via the same OTP flow, already complete).
Corrected 2026-08-24 (this section originally called the whole phase fully
completable — deeper research found two of the remaining items are
genuinely blocked, not just soft caveats):
- Admin RBAC / a fine-grained admin role hierarchy: BLOCKED. security.md
  §7/§9 lists specific roles (SAFETY_ADMIN, FINANCE_ADMIN, SUPER_ADMIN)
  with example permissions, but business-rules.md §43 explicitly lists
  "Admin roles / Permission hierarchy / Escalation rules" as deliberately
  TBD (ADR-0009 already flagged this exact conflict) — and per the
  roadmap's own §0.1 source-of-truth hierarchy, Business Rules outranks
  Security Design, so the TBD marker wins. Building a permission-check
  *framework* with only the one real role (ADMIN) to plug into it would be
  speculative infrastructure with no real caller — the same anti-pattern
  ADR-0013 explicitly avoided for Wallet's credit() until Task 3.5 gave it
  one.
- Admin MFA: BLOCKED. Not on a provider or credential — TOTP is genuinely
  self-contained — but api-contracts.md, database-design.md, and
  technical-architecture.md have zero mention of MFA anywhere: no
  documented enrollment/verify endpoint shape, no schema for a stored
  secret. Building it now means inventing a new public API contract,
  which is its own explicit §0.3 mandatory-stop condition, independent of
  the TOTP mechanism itself being simple.
  RESOLVED and IMPLEMENTED (ADR-0051, 2026-08-28) — the owner supplied
  the mechanism ("TOTP authenticator app") and the ADR supplied the
  endpoint shape this §0.3 gate was waiting on.
Corrected again 2026-08-25 — this section previously listed OTP abuse
protection's IP dimension as "genuinely unblocked and not yet built."
Re-checked against the actual code before suggesting it as a next task:
it is already fully built — `RedisOtpRateLimiter.check_and_increment_
request_ip()`/`check_and_increment_verify_attempt_ip()`
(modules/identity/rate_limit.py), wired end-to-end from
`modules/identity/router.py`'s `_client_ip()` helper through
`IdentityService.request_otp()`/`verify_otp()`, both checked before the
per-phone dimension (security.md §5), configured via
`OTP_REQUEST_RATE_LIMIT_PER_IP_PER_HOUR`/`OTP_VERIFY_RATE_LIMIT_PER_IP_
PER_HOUR`, and covered by `tests/test_identity_service.py`. Only the
device/session dimension remains deferred (needs a new `device_id`
request field api-contracts.md doesn't document, so it stays alongside
MFA).
Resource-ownership authorization: DONE (ADR-0037, 2026-08-26) — audited
every router endpoint with a resource-ID path parameter (`ride`,
`vehicle`, `safety`/SOS, `support` case; `admin` excluded, since an
admin is authorized to see every resource by design). All but one
already had both the correct ownership check and a regression test
covering it; the one real gap — `POST .../destination-change` and
`.../destination-change/confirm` had the correct ownership check in
`RideService` (verified: same `RideNotFoundError` for "missing" and
"not yours," matching every other module) but no test covering it,
unlike its sibling `pickup-change` and every other recently-added ride
sub-resource — is now fixed with two new IDOR regression tests in
`tests/test_destination_change_api.py`.
Corrected again 2026-08-26 — Admin RBAC is no longer blocked: the owner
gave the exact decision this section's own analysis said business-
rules.md §43 was missing (BR-126/BR-127, ADR-0040) — one Super Admin
level plus granular per-module permissions, not the fixed SAFETY_ADMIN/
FINANCE_ADMIN/SUPER_ADMIN role list security.md §7 originally sketched
(now corrected there too). Fully implemented — see item 26 below.
Admin MFA remains blocked, unaffected by this — still no documented
endpoint shape anywhere for it, a separate §0.3 gate.
Verdict: mostly complete; 1 of the remaining items blocked (Admin MFA);
resource-ownership authorization and Admin RBAC now both DONE.

03 — Driver Operations (10 tasks)

Substantially implemented (Task 2.3-2.7B), and now driver suspension/
reactivation too (ADR-0021, 2026-08-24): `DriverService.suspend_driver()`/
`reactivate_driver()` built at the service layer, concurrency-safe (same
row-lock pattern as go_online()/go_offline()), proven by unit + real-Postgres
integration + concurrency tests. Turned out less "pure engineering" than
originally assessed here — no HTTP endpoint is documented anywhere for it
(unlike Approve/Reject Driver), so building one would be a new public API
contract (§0.3), the same gate ADR-0018 hit for Advertisement; the service
methods exist and are tested, ready for whichever future task gets a real
endpoint to compose them into.
Blocked: final document-verification provider integration (provider TBD,
Decision Register).
Verdict: mostly complete; 1 of 10 tasks blocked. (Corrected 2026-08-24 — this
entry previously called driver suspension/reactivation "not blocked, just not
built... pure engineering"; building it surfaced the missing HTTP contract
this assessment missed, the same class of correction Phase 02/Phase 17 already
needed this session.)

04 — Ride Booking (9 tasks)

Complete: create ride, pickup/destination validation, vehicle category,
SEARCHING creation/history, all customer/driver cancellation variants
(Tasks 3.3/3.5/3.6, ADR-0012/0015/0016 — done since this file was first
written; the Minimal Penalty Foundation + `WalletService.credit()` this
needed are both built), and now Initial fare quote too (ADR-0020,
2026-08-24 — the owner supplied a real, approved fare table mid-session;
`CalculateFare`/`ApplyPromotionDiscount` compose into ride creation,
resolving `fare: null` and closing ADR-0019 Item 6 in the same change).
GET ride status: DONE too (ADR-0024, 2026-08-25) — `GET /api/v1/rides/{ride_id}`.
Verdict: COMPLETE. Zero remaining tasks in this phase. (Corrected 2026-08-24
— Initial fare quote was BLOCKED when this section was last written; it
isn't anymore, see above. Corrected again 2026-08-25 — GET ride status,
this entry's last remaining item, is also now built.)

05 — Matching (12 tasks)

COMPLETE (Task 3.2 + Task 3.4/ADR-0014). Background expiry worker and event
publication are out of scope by design (lazy-expiry chosen instead of a
worker — ADR-0011 Decision 2; no Kafka producer infra exists anywhere yet,
see Phase 18), not blocked, not owed.
Verdict: complete.

06 — Ride Lifecycle (10 tasks)

RESOLVED and IMPLEMENTED (ADR-0028, 2026-08-25). Complete: SEARCHING →
ACCEPTED (Task 3.4); ACCEPTED → ARRIVED → STARTED → COMPLETED → CLOSED
(this task) — the owner approved the previously-TBD GPS radius (50m
arrival / 100m completion, 3 attempts before manual review), removing
the cascading blocker described below (kept for the historical record,
not because it still applies): "Arrival verification and Completion
verification both need the exact GPS radius, which is explicitly TBD
(roadmap §9/Important — "must not hard-code a 50m rule unless formally
approved"). state-machines.md §6 requires "GPS verification = PASS" to
even *enter* ARRIVED — so ACCEPTED → ARRIVED itself cannot be
meaningfully completed until the radius is resolved, not just the
verification step. STARTED → COMPLETED has the same dependency via
Completion verification." Ride-start OTP, COMPLETED → CLOSED,
Invalid-transition protection, and Ride state history — already
genuinely unblocked before this ADR — are also now implemented as part
of this same task.
Verdict: DONE for the core lifecycle. Early Drop (Phase 08's own row)
and Dispute-as-Support (Phase 13, decided by this ADR but not built)
remain separate, not-yet-started work.

07 — GPS & Verification (9 tasks)

RESOLVED and IMPLEMENTED (ADR-0028, 2026-08-25) for the verification
foundation. Complete: GPS point storage, Server GPS distance calculation
(Haversine, `haversine_distance_meters()`), Arrival verification,
Completion verification, Retry-counter protection (3 attempts before
manual review) — the owner-approved radius and retry count removed the
blocker described below (kept for the historical record): "Arrival
verification, Completion verification, Early-drop GPS verification (all
need the TBD radius), Additional retries, Retry-counter protection (both
need the TBD retry count — Decision Register)." GPS anomaly detection
and Server-time validation remain as previously assessed (pure
engineering, not touched by this task specifically since neither was
blocked). Early-drop GPS verification remains unbuilt — Phase 08 (Early
Drop) itself hasn't started; only the two verification types it doesn't
need (ARRIVAL, COMPLETION) were in this task's scope.
Verdict: DONE for the foundation, and now also DONE for the manual-review
workflow itself (BR-124/BR-125, ADR-0032, 2026-08-25) — a terminal
GPS_VERIFICATION_FAILED outcome auto-opens a `ride.gps_disputes` row,
customer/driver may submit evidence within a 24-hour window, and an admin
resolves via `GET`/`POST /api/v1/admin/gps-disputes*` (Search Disputes,
Resolve Dispute). See this file's RECOMMENDED EXECUTION ORDER item 17.

08 — Early Drop (9 tasks)

RESOLVED and IMPLEMENTED (ADR-0030, 2026-08-25). Re-examined once thought
"independently buildable" — closer reading found the GPS-proof step was
never actually a threshold-verification step at all: BR-088, api-contracts.md
§27, and technical-architecture.md §43 all describe GPS/location as
RECORDED evidence, with only state-machines.md §19-21 (lower-ranked in
this documentation set's own source-of-truth hierarchy) adding an
unratified verification-gate/PASS-FAIL/REVIEW mechanic — the same shape
of downstream addition ADR-0002 already found for the GPS-dispute
workflow. No owner decision was ever needed; the apparent blocker
(security.md §12's "final radius... requires an explicit decision,"
state-machines.md §63's "exact early-drop GPS tolerance") dissolves once
the higher-ranked documents are read against the lower-ranked one instead
of in isolation. Implements RequestEarlyDrop/ConfirmEarlyDrop
(domain-design.md §9.4): `ride.early_drop_requests` (plus one additive
`reason` column); `POST .../early-drop`, `POST .../early-drop/confirm`;
`ride.early_drop_confirmed` (event-contracts.md §10.7); STARTED →
EARLY_DROP_REQUESTED → (both confirm) → COMPLETED → CLOSED, reusing
COMPLETED rather than inventing an eighth ride status; `confirmed: false`
realizes both reject paths, no separate endpoint; no fare recalculation
(BR-090).
Verdict: DONE.

09 — Ride Modifications (22 tasks)

RESOLVED and IMPLEMENTED for Pickup Change (BR-072-078, ADR-0033,
2026-08-25). Re-reading business-rules.md §22-23 while scoping this task
found the phase's own "roughly half needs a TBD rate" characterization
below (kept for the historical record) was itself imprecise: BR-076
(pickup-change) genuinely was TBD, but BR-080 (destination-extension)
already had a ratified ₹8/km flat rate with a worked example, no TBD
marker anywhere near it. The owner resolved BR-076 as "the ride's own
base per-km fare rate," not a new flat number. Implements
RequestPickupChange/ConfirmPickupChange: the ≤250m case applies
immediately; the >250m case creates a pending `ride.change_requests` row
(database-design.md §11.1's already-documented table — a research miss
initially led to inventing a separate table before this was caught and
corrected, see ADR-0033 Decision 4), the driver PROCEED (computes the
charge, customer must confirm) or PASS (no ₹30 penalty/strike, same
exemption `driver_cancel_ride()` already had for this reason — the ride
resets to SEARCHING and re-dispatches near the new pickup, resolving the
same rematch-design ambiguity ADR-0016 Item 2 left open for normal
driver cancellation specifically, which stays unresolved).
Verdict: DONE — both Pickup Change and Destination Change (BR-079-082,
ADR-0033 Decision 9, 2026-08-25) are implemented, closing out Phase 09
entirely. Destination Change needed two engineering-judgment calls
first (the route-deviation classification tolerance, and "current
location" for the full-recalculation case — no live per-ride GPS
tracking exists anywhere in this codebase), both recorded in the ADR
rather than guessed past silently.

(Historical record — the original assessment below, superseded above:)
The phase's own "Critical governance" note already flags this: pickup-change
and destination-extension charge *values* are illustrative only and must not
become code silently (roadmap §12). The ≤250m threshold itself is documented,
but the *rate* charged beyond it is TBD (Decision Register). Distance-based
mechanics (pickup-change detection, driver PROCEED/PASS branching,
rematch-after-PASS) are buildable as pure engineering; the charge/
confirmation/pricing-history tasks are not.
Original verdict: core value blocked — roughly half the phase needs a TBD
rate. (Corrected 2026-08-24 — this entry previously said "Historical pricing
version" also presupposes a not-yet-built Pricing domain; Pricing now exists
(ADR-0020) with `CalculateFare`/`ApplyPromotionDiscount` built — this phase's
`CreateFareRevision`/`CalculatePickupChangeCharge`/
`CalculateDestinationChangeFare` commands specifically remain unbuilt because
Phase 09 itself hasn't started and the extension rate is still TBD, not
because Pricing is missing.)

10 — Payments (17 tasks)

RECONCILED (ADR-0025, 2026-08-25 — approved P2P Payment Model, documentation
only, no code changed): the analysis below was written assuming VISTAAR
would eventually collect the ride fare via gateway/offline settlement — the
project owner has since ruled that out entirely. VISTAAR does not collect
the ride fare, in any form; the customer pays the driver directly, and the
platform fee is charged only to the driver's wallet at ride acceptance
(already built, ADR-0014). Most of this phase's 17 tasks (online payment
creation, signature verification, webhook handling, refunds, reconciliation,
payment confirmation state) describe a flow that no longer applies and
should not be built. The phase is not "blocked pending a gateway decision"
in the sense originally meant here — it is largely N/A.

UPDATED (ADR-0026, 2026-08-26, Option A — also documentation-only): "largely
N/A" was too strong. The project owner resolved the one open question
ADR-0025 left (BR-055, customer outstanding-penalty collection): a valid
cancellation/no-show penalty is surfaced — not collected — at the customer's
next ride booking, then settled as a genuinely separate "Customer → VISTAAR"
charge (never through the driver's wallet, never bundled with the P2P ride
fare). [Superseded 2026-09-03, ADR-0066: the penalty is now bundled with
the ride fare and paid to the driver directly, with VISTAAR recovering its
share through the driver's wallet at ride completion — the opposite of
this entry's original framing. Historical log entry, not corrected in
place.] This revives a narrow slice of "Refund"/"Duplicate-payment
protection"/"Payment confirmation state" above, scoped to penalty collection
only. Two genuine decision gates survive, both narrower than the original
17-task scope: driver wallet-recharge gateway selection (Phase 11) and
customer outstanding-penalty-collection gateway selection (new).

As originally written (superseded):

"Payment gateway selection is a formal decision gate" (roadmap §13, explicit).
Every task in this phase — signature verification, webhook handling, refunds,
reconciliation — is meaningless without a real gateway's actual contract shape
to build against. Domain-level scaffolding (payment state machine, DTOs) could
be sketched the way Wallet's domain layer was built before it had a caller,
but the phase's real value cannot be delivered.
Verdict: core value blocked on a single, explicit decision gate.

11 — Financial (19 tasks)

Complete: driver wallet, ledger, debit, credit, atomic transaction,
negative-balance prevention, concurrency tests (Minimal Wallet Foundation,
ADR-0013/0015). Driver cancellation penalty, Driver strike, Customer
subsequent/first-qualifying cancellation penalty, Customer grace period,
Penalty idempotency — all done since this file was first written, as part
of Phase 04's Tasks 3.5/3.6 (ADR-0015/0016). Financial audit trail — done
too (ADR-0024, 2026-08-25): `GET /api/v1/drivers/me/wallet/transactions`.
Reconciled (ADR-0025, 2026-08-25): Outstanding balance/recovery are N/A, not
blocked — they named the driver-side `wallet.outstanding_settlements`
concept (VISTAAR settling its own charge out of cash the driver collected on
its behalf), which cannot occur once the platform fee is always collected
from the driver's wallet at acceptance, before the ride happens. Recharge
remains genuinely blocked, on the wallet-recharge gateway specifically (the
one payment-gateway decision ADR-0025 preserves — BR-016: "payment must be
verified before the wallet is credited"). Pickup PASS penalty exemption —
needs Phase 09's pickup-change flow, itself blocked. Penalty expiry
*collection/enforcement* is stamped at creation (`expires_at`) but nothing
yet acts on an expired row — same lazy-evaluation gap as offer expiry
elsewhere in this codebase.
Verdict: mostly complete; roughly 2 of 19 tasks genuinely blocked (Recharge,
Pickup PASS exemption) — down from ~4, since Outstanding balance/recovery are
now N/A rather than blocked and Financial audit trail is done.

12 — Growth (14 tasks)

Built (ADR-0019, 2026-08-24): the full Promotion/Referral domain, service,
repository, and schema layer (creation, eligibility, reservation, consumption,
restoration, duplicate-protection, qualification, anti-self-referral, reward,
duplicate-reward-protection) — unlike Advertisement, this phase turned out to
have real documented HTTP endpoints (api-contracts.md §37-38: Get Promotions,
Get Referral Code, Attach Referral), all three implemented. `GrantWelcomePromotion`
composes into `GET /api/v1/customers/me`'s first-access auto-provision;
`QualifyDriverReferral` + the ₹100/₹100 wallet reward compose into driver
approval. `ReservePromotion` now also composes into ride creation (ADR-0020,
2026-08-24 — Pricing produced a real fare to apply a discount against, unblocking
api-contracts.md §72's flow). `ConsumePromotion`/`RestorePromotion` remain
uncomposed — ride cancellation/completion still have no real fare-driven
`discount_amount` to consume/restore. [Superseded 2026-08-28, ADR-0049,
reconfirmed 2026-09-04: BR-063's discount cap is resolved — 50% off,
₹100/ride cap, for welcome/referral entitlements — no longer NULL/TBD.
Historical log entry, not corrected in place.] [Also superseded
2026-09-04, ADR-0070: `ConsumePromotion`/`RestorePromotion` are now
composed into ride completion/cancellation — the "no real fare" blocker
had already been resolved and simply wasn't acted on for these two
commands until this task.]
Verdict: complete for the genuinely unblocked scope; ride-cancellation/completion
composition remains blocked on a real fare at those specific points, not on more
engineering time. (Corrected 2026-08-24 — ReservePromotion was blocked on Pricing
when this section was last written; it isn't anymore, see above.)

13 — Disputes (16 tasks)

RESOLVED and IMPLEMENTED for its documented scope (ADR-0028 + ADR-0029,
2026-08-25). The whole-phase decision gate this entry previously
described — "the formal Dispute-domain decision must be aligned with the
current ADR record before implementation" (roadmap §16) — is now
satisfied: ADR-0028 decided Dispute is a Support/Admin capability, not a
new domain, and ADR-0029 implements exactly what BR-121 (ride-fare
disputes) and domain-design.md §17.3 (DisputePenalty) actually authorize
— both realized as ordinary Support Cases decided via the already-built
Resolve Penalty endpoint, no new domain/table/endpoint/state. Genuinely
NOT built: the much larger 16-task "Dispute Module" implementation-
readiness.md §16/§61/§68 describes (evidence upload, 72-hour window,
admin GPS-override APPROVE/REJECT) — ADR-0002 already found that specific
workflow was never ratified through business-rules.md → architecture →
domain-design → database-design → api-contracts → event-contracts →
state-machines, and ADR-0029 reaffirms that finding still holds; building
it would mean inventing a business rule and API surface from nothing, the
same §0.3 gate this session has respected everywhere else.
Verdict: DONE for the two documented dispute concepts. The elaborate
GPS-dispute-evidence workflow was a genuinely separate, unratified
question at the time this entry was written — it has since gone through
business-rules.md properly: the project owner reviewed a drafted BR-124/
BR-125 (with one explicit correction, a 24-hour evidence window rather
than the 72-hour figure implementation-readiness.md §16/§61/§68 had
described) and approved them, and ADR-0032 (2026-08-25) implements
exactly that ratified scope — auto-opened disputes, evidence submission,
admin APPROVE/REJECT. Now also DONE — see this file's RECOMMENDED
EXECUTION ORDER item 17 and Phase 07's own entry above.

14 — Safety & Support (11 tasks)

Built (ADR-0022, 2026-08-24): full Safety (`safety.incidents`/`events`) and
Support (`support.cases`/`messages`) domain/service/repository/schema layer,
matching database-design.md §28/§30 exactly plus one additive column
(`support.cases.ride_id`). All 3 buildable documented HTTP endpoints
implemented (`POST /api/v1/rides/{ride_id}/sos`, `POST`/`GET
/api/v1/support/cases`). SOS creation/location/ride-context, safety
workflow/escalation, support case/assignment/conversation/resolution are all
built — "Support assignment" and "Human escalation" collapse into one
command, `assign_case()` (this codebase has no AI actor to escalate *from*).
`escalate_incident()` never contacts a real emergency service (BR-112's
integrations stay TBD, unchanged). AI escalation is transitively BLOCKED —
it presupposes AI Support (`POST /api/v1/support/ai/message`), which needs a
real LLM; no provider/credential exists anywhere in this environment (§0.4),
not stubbed. Acknowledge/Escalate/Resolve SOS and Assign/Resolve/PostMessage
Support Case have no documented HTTP endpoint anywhere — proven by tests
instead of an invented one.
Verdict: complete for the genuinely unblocked scope; only AI Support and
emergency-service integration remain blocked, exactly as originally assessed
— one of the few phases this session's prior analysis got right on the
first pass.

15 — Notifications (10 tasks)

Every delivery channel (push, SMS, WhatsApp, email) needs a real provider —
none were integrated when this section was first written (§25.0: SMS/
WhatsApp both explicitly "NOT YET INTEGRATED", and the existing OTP flow
already ran against a test double, not a real SMS provider). The
notification *domain model* (retry logic, delivery-tracking states,
per-event trigger points) is buildable without a live provider, but the
phase's actual purpose — delivering a notification — cannot be.
(Corrected 2026-08-25 — SMS specifically is no longer unprovisioned: MSG91
was selected and wired in (ADR-0031), but only behind modules.identity.
sms's existing OTP seam — no general-purpose Notification domain exists
yet to route ride-lifecycle events (driver assigned, arrived, etc.)
through it, and push/WhatsApp/email remain fully unprovisioned. This phase
stays core-value-blocked as a whole; MSG91 only removes SMS specifically
as a blocker for whichever future task builds the actual Notification
domain and its per-event triggers.)

(Corrected again 2026-08-25, same day — ADR-0034 builds the Notification
Domain Foundation itself: `NotificationService.send()` real for IN_APP/
SMS (SMS now generalized beyond OTP-only, MSG91's Flow API), composed
into two proof-of-concept trigger points (ride.accepted, ride.arrived).
Three real gaps kept this from being "fully done": (1) no HTTP endpoint
exists anywhere in api-contracts.md for Notification — the same §0.3
stop condition ADR-0018/ADR-0021 already hit, so the service layer is
composed directly at other routers instead of exposed; (2) Push (FCM,
owner-approved) has no device-token data source anywhere in this
codebase — registering one is itself a new, undocumented endpoint, so
`Channel.PUSH` raises `ChannelNotAvailableError` rather than being faked;
(3) no Kafka consumer exists anywhere in this codebase (Phase 18's own
"remain undone") — technical-architecture.md §46 describes Notification
as consuming events over Kafka, so only 2 of its full documented event
list are actually wired as proof-of-concept, the rest deferred as a
repeatable follow-up. WhatsApp: no BSP chosen, no code written, per the
owner's explicit instruction — a separate requirements analysis was
delivered instead.)
(Corrected again 2026-08-26 — ADR-0038 builds the real Kafka consumer
this entry's own previous correction called "a separate, larger task":
`modules/notification/consumer.py`'s `NotificationConsumer`, the first
real Kafka consumer anywhere in this codebase, additively wires four
more events on top of the existing synchronous `ride.accepted`/`ride.
arrived` — `ride.started`, `ride.completed`, `ride.cancelled`,
`penalty.applied` — each explicitly named as a Notification consumer in
event-contracts.md's own per-event list, not just loosely inferred. The
rest of the documented event list is deliberately deferred, not a
hidden remainder: SOSTriggered's recipient is a genuine, safety-
sensitive judgment call left unmade; PromotionActivated's closest real
event means something narrower ("reserved," not "activated");
FareChanged's closest real events already tell the same actor the new
fare in that same request's own HTTP response; PaymentRequired/
PaymentConfirmed are N/A under ADR-0025; WalletLow/PromotionExpiring/
DocumentExpiring have no triggering event anywhere (would need a
scheduled job — Background Worker Foundation, still unapproved); and
SupportEscalated has no real corresponding event at all.)
(Corrected again 2026-08-26 — the owner approved Celery (ADR-0039),
resolving the "Background Worker Foundation, still unapproved" reason
PromotionExpiring/DocumentExpiring were deferred above.
`modules/notification/tasks.py` adds both as real Celery Beat periodic
tasks — a daily scan warns a customer/driver before a promotion/
document expires, 3 days out by default, using the same
NotificationService.send() dispatch the Kafka consumer already uses.
WalletLow stays deferred, but on reflection for a better reason than
"no worker exists": a balance crossing a threshold is naturally an
event at the moment of a debit, not something scheduling helps with.)
Verdict: DONE for the foundation (in-app + SMS, both real), DONE for a
real Kafka consumer covering 4 of the documented event list's items
(ADR-0038), and DONE for 2 more via real scheduled tasks (ADR-0039).
Still blocked/deferred: Push (device-token endpoint, itself a new
public API contract), WhatsApp (BSP pick), email (never discussed,
still fully open), WalletLow (better done reactively, not scheduled),
SOSTriggered/PromotionActivated/FareChanged/SupportEscalated (each
deferred for its own explicit reason, see above).

16 — Admin (17 tasks)

Buildable now, backed by already-complete domains: customer management,
driver management, vehicle management, ride monitoring, wallet monitoring,
audit viewer (queries the existing `admin.audit_logs` table). GPS evidence
review (Phase 07) is now also DONE (BR-124/BR-125, ADR-0032, 2026-08-25):
`GET /api/v1/admin/gps-disputes` + `POST .../resolve`. Still coupled to
other blocked/partial phases: payment monitoring (Phase 10), dispute
dashboard (Phase 13), pricing configuration (no admin surface over
`pricing.fare_rules` exists yet — not blocked, values are resolved per
ADR-0020, just not yet built), promotion/referral administration (Phase
12's partial mechanism), safety/support dashboards (Phase 14's partial
scope).
Verdict: mostly completable; roughly half the dashboard surface is backed by
domains that are themselves complete, half by domains that are blocked or
partial.

17 — Advertisements (8 tasks)

Built (ADR-0018): the full domain/service/repository layer — all six
domain-design.md §22.3 commands, the exact 80/20 driver/VISTAAR split
(§22.4), and `uq_payouts_driver_campaign` as a real database-level
idempotency guard. `WalletService.credit()` (`ADVERTISEMENT_PAYOUT`,
already in the transaction-type enum) composes cleanly, proven by one
real-Postgres integration test.
Corrected 2026-08-24 (this section originally called the whole phase
fully completable; building it surfaced two gaps that assessment
missed):
- No HTTP endpoint: BLOCKED. `api-contracts.md` documents zero
  Advertisement endpoints anywhere — no path, no request/response
  shape, unlike every other module built so far (which had at least a
  documented endpoint to implement against). Inventing one would be
  the same "new public API contract" §0.3 stop condition Admin MFA
  (Phase 02) hit.
- Automated ad verification: BLOCKED. technical-architecture.md §55
  names Admoto as the intended partner, but no requirement/candidate
  list/credential plan is documented anywhere (§0.4's required steps
  before integrating any external provider). Implemented instead as a
  manual admin decision (`verify_advertisement()`), the same treatment
  this codebase already gives document verification everywhere else.
Verdict: complete at the domain layer; the two remaining gaps need a
product/API design decision and an external-provider decision
respectively, not more engineering time.

18 — Event & Background (11 tasks)

Built (ADR-0017): event schemas, Kafka producer, outbox table, outbox publisher
(as an in-process asyncio loop, not the still-blocked Background Worker
Foundation/Celery — ADR-0017 Decision 1), and real publication for every
already-built domain transition (ride.requested/accepted/cancelled, wallet.
debited/credited, penalty.applied/strike_recorded).
Corrected 2026-08-24 (deeper research while building this found two items
were less "buildable as pure engineering" than first assessed):
- Event retry: only PARTIALLY buildable — event-contracts.md §30's specific
  backoff sequence needs per-row attempt-count/next-retry-at columns the
  documented shared.outbox_events schema does not have. Built instead: a
  simpler fixed-interval re-poll (ADR-0017 Decision 2), with the backoff
  schema addition flagged as a follow-up, not silently added.
- Dead-letter handling and consumer-side event idempotency (shared.
  processed_events): NOT built — both depend on the attempt-tracking Event
  Retry defers, and event idempotency additionally has no real consumer
  module to serve yet (Notification, Analytics, etc. don't exist) — building
  it now would be speculative infrastructure with no caller.
- Kafka consumer: NOT built — every documented consumer belongs to a module
  that doesn't exist yet.
Still blocked: "Background worker process" (Celery unapproved, Phase 01);
"Scheduled expiry jobs"/"Payment reconciliation" transitively (behind that
worker and Phase 10 respectively).
Corrected 2026-08-26 — "every documented consumer belongs to a module
that doesn't exist yet" is no longer true: Notification exists (ADR-0034)
and now has a real consumer (ADR-0038), `modules/notification/consumer.
py`'s `NotificationConsumer` — the first real Kafka consumer in this
codebase, covering 4 events. Dead-letter handling and
`shared.processed_events`-style consumer-side idempotency tracking
remain not built, but for a narrower reason now: this consumer's own
idempotency is instead satisfied by `notification.deliveries`'
`uq_notification_deliveries_dedup` constraint (event_id is one of its
columns) — the same "unique constraints, event IDs" mechanism event-
contracts.md §9 itself describes as sufficient, not a gap this task left
open.
Corrected again 2026-08-26 — "Background worker process" and
"Scheduled expiry jobs" are no longer blocked: the owner approved
Celery (ADR-0039). `shared/celery_app.py` is the worker foundation
itself (Redis broker/backend, no new infrastructure); `modules/
notification/tasks.py`'s two periodic tasks are the first real
scheduled expiry jobs. "Payment reconciliation" remains blocked, but on
Phase 10 (a real gateway) specifically, not on the worker technology —
approving Celery does not by itself unblock it.
Verdict: mostly complete for what's genuinely unblocked; a first real
Kafka consumer (ADR-0038) and a first real background-worker foundation
with two scheduled jobs (ADR-0039) now exist; the rest needs either a
schema decision (backoff columns), a second real consumer module
(Analytics, Payment), or Phase 10's payment gateway — not just more
engineering time.

19 — Security (12 tasks)

JWT security, RBAC enforcement, rate limiting, object-level authorization,
input validation, audit logging, security headers, dependency scanning, and
admin MFA are all code-level practices with no external dependency — largely
already followed throughout this codebase's existing modules (IDOR-safe
errors, server-side ownership checks on every resource). HTTPS/TLS and
production-grade secret management are development-complete (self-signed
certs, `.env` locally) but need a real domain/cloud provider for their
*production* form — that's Phase 21's territory, not a new blocker here.
Security headers and dependency scanning: DONE (ADR-0036, 2026-08-25) —
`SecurityHeadersMiddleware` (security.md §64's five headers, CSP exempted
only on `/docs`/`/redoc`/`/openapi.json`) and a `pip-audit` CI step scoped
to `[project].dependencies`. Admin MFA remains blocked — same §0.3 "new
public API contract" gate Phase 02 already hit, no documented enrollment/
verify endpoint shape exists anywhere.
Corrected 2026-08-26 — "RBAC enforcement... blocked" is no longer true:
BR-126/BR-127/ADR-0040 resolved it (Phase 02's own updated entry has the
full write-up) — one Super Admin level, granular per-module permissions,
every existing admin route now actually enforcing them, not just the
single undifferentiated ADMIN role this section originally described.
Verdict: mostly/fully completable at the code level; production hardening
naturally sequenced behind Phase 21; security headers, dependency
scanning, and fine-grained RBAC now all DONE; admin MFA remains blocked
on its own separate §0.3 gate.

20 — Testing (15 tasks)

Unit, integration, contract, state-machine, idempotency, and security testing
are an ongoing practice already followed on every task in this project (real
Postgres integration tests, real-concurrency tests for every financial/
exclusive-transition operation — established since Task 2.7B). GPS boundary
tests and payment tests are naturally sequenced behind Phases 07 and 10
respectively, not blocked by anything new. E2E/load/failure-recovery testing
scale up as more of the system exists.
Verdict: fully completable as an ongoing discipline, with 2 tasks naturally
sequenced behind other phases' own blockers.

21 — Deployment (13 tasks)

Every task needs a real cloud provider, domain, and TLS. The provider is
now chosen — DigitalOcean Kubernetes, per technical-architecture.md §64
and ADR-0035, 2026-08-25 (this section originally described the provider
as entirely undecided; §25.0 of the roadmap now reads "CHOSEN, NOT YET
DEPLOYED"). CI/CD pipeline definitions and deployment scripts have been
authored as code (the way `docker-compose.dev.yml` already exists for
local dev) without live infrastructure to run them against — a hardened
production `Dockerfile`, `infrastructure/kubernetes/` manifests, an
`infrastructure/terraform/digitalocean/` module, and
`.github/workflows/deploy-do.yml` all exist and are syntax/schema-
validated — but standing up staging/production, verified backups, and
monitoring still cannot happen without a real DigitalOcean account;
none exists in this environment.
Verdict: DONE for the config/script-authorship slice (ADR-0035) — the
domain name, TLS contact email, container registry, and the account
itself remain the owner's decisions/resources; applying any of this
against a live cluster is the part still blocked.

RECOMMENDED EXECUTION ORDER FOR THE UNBLOCKED WORK

Dependency-aware, not phase-numeric order:

1. DONE — Minimal Penalty Foundation + `WalletService.credit()`
   (ADR-0015), Phase 04's Customer/Driver cancellation (Tasks 3.5/3.6,
   ADR-0015/0016), and Phase 11's remainder that fell out of that same
   build (penalty idempotency, driver/customer penalty logic). Not done:
   Phase 04's "GET ride status" (small, unblocked, not yet built) and
   Phase 11's "Financial audit trail" (also unblocked, not yet built).
2. DONE — Phase 02's genuinely unblocked remainder: resource-ownership
   authorization (audited — already enforced everywhere, nothing to
   build) and OTP abuse protection's IP dimension. Admin RBAC and Admin
   MFA are BLOCKED, not done (see Phase 02's entry above for why) — no
   further Phase 02 work is possible without an owner decision.
3. DONE — Phase 18's genuinely unblocked scope: event schemas, Kafka
   producer, outbox table, in-process outbox publisher, and real
   publication for every already-built domain transition. Kafka
   consumers, Dead Letter Topics, and consumer idempotency remain
   undone (need a real consumer module or a schema decision, not more
   engineering time — see Phase 18's entry above). [Superseded
   2026-08-26 by ADR-0038 (Kafka consumer) and 2026-09-04 by ADR-0071
   (Dead Letter Topics, consumer idempotency, and retry/backoff) — all
   three are now implemented. Historical log entry, not corrected in
   place.]
4. DONE — Phase 17's domain/service/repository layer (ADR-0018). No
   HTTP endpoint and no Admoto integration remain undone — both need a
   product/external-provider decision, not more engineering time (see
   Phase 17's entry above).
5. DONE — Phase 12 (Growth, ADR-0019): full Promotion/Referral domain,
   service, repository, and schema layer; all 3 documented HTTP
   endpoints; GrantWelcomePromotion composed into GET
   /api/v1/customers/me; QualifyDriverReferral + the ₹100/₹100 wallet
   reward composed into driver approval. [Superseded 2026-08-28,
   ADR-0049, reconfirmed 2026-09-04: BR-063's discount cap is resolved
   — 50% off, ₹100/ride — no longer NULL/TBD. Historical log entry, not
   corrected in place.] ReservePromotion's ride-creation composition
   was deferred here (no Fare Quote step existed yet) — see item 5b.
5b. DONE — Pricing Foundation (Phase 04's "Initial fare quote" task,
    ADR-0020, 2026-08-24): triggered by the owner supplying a real,
    approved fare table mid-session (not originally scheduled — pulled
    forward out of order because the input arrived). `pricing.fare_
    rules`/`fare_quotes` built and seeded; `CalculateFare` (+
    `ApplyPromotionDiscount`) composes into `POST /api/v1/rides`,
    resolving `fare: null` — and, in the same change, unblocks and
    composes item 5's deferred `ReservePromotion`, closing ADR-0019
    Item 6. CAB gained three owner-approved sub-tiers (Eco/Premium/
    Premium+), customer-selected at booking, matching-aware
    (`matching_category_key()`). BR-011's platform fee updated to
    match the same table (Bike ₹2/Auto ₹5/Cab ₹10, was ₹10/₹20/₹20).
    604 passed, 5 skipped, 0 failed (was 569) — see the roadmap's
    §2.0/§7/§15 for the full write-up.
6. Phase 19 (Security hardening) and Phase 20 (Testing depth) — best done
   continuously alongside the above, not as a separate pass at the end.
7. DONE — Phase 03's driver suspension/reactivation (ADR-0021, 2026-08-24):
   `DriverService.suspend_driver()`/`reactivate_driver()`, concurrency-safe,
   proven by unit + real-Postgres integration + concurrency tests. No HTTP
   endpoint — api-contracts.md documents none, the same §0.3 gate ADR-0018
   hit for Advertisement (turned out less "small" than assessed — see
   Phase 03's entry above). 616 passed, 5 skipped, 0 failed (was 604) —
   see the roadmap's §2.0/§6 for the full write-up.
8. DONE — Phase 14's internal safety/support workflow (ADR-0022,
   2026-08-24): full Safety/Support domain/service/repository layer, all
   3 documented HTTP endpoints (SOS, Create/Get Support Case). No HTTP
   endpoint for Acknowledge/Escalate/Resolve SOS or Assign/Resolve/
   PostMessage Support Case — same §0.3 gate as Phase 03/Advertisement.
   AI Support BLOCKED (§0.4, no LLM provider/credential). 667 passed,
   5 skipped, 0 failed (was 616) — see the roadmap's §2.0/§17 for the
   full write-up.
9. DONE — Phase 16's genuinely unblocked scope (ADR-0023, 2026-08-25):
   reconciled the roadmap's 17-bullet "Admin" task list against
   api-contracts.md §46-48, the only canonical Admin HTTP contract.
   Driver/Vehicle management (mutations) were already done (Task 2.7A).
   Newly built: Search Rides / Get Ride (`GET /api/v1/admin/rides`
   [+`/{id}`]), Admin Wallet View (`GET /api/v1/admin/wallets/{driver_id}`),
   Search Penalties / Resolve Penalty (`GET /api/v1/admin/penalties` +
   `POST .../resolve`, action: "WAIVE" only — reaches
   state-machines.md §40's previously-unreached WAIVED status; the
   "reversal/waiver record" api-contracts.md §48 asks for reuses
   admin.audit_logs rather than a new table). This codebase's first list
   endpoint, so a shared `shared/pagination.py` (§50's envelope) and a new
   `MAX_PAGE_SIZE` setting were added (renamed from `ADMIN_MAX_PAGE_SIZE`
   in item 10 below once a non-admin endpoint needed it too). The other
   12 roadmap bullets
   (Admin dashboard, Customer management, Payment monitoring, Settlements,
   Promotion/Referral administration, Dispute dashboard, GPS evidence
   review, Pricing configuration, Safety/Support dashboards, Advertisement
   management, Audit viewer) have zero HTTP shape anywhere in
   api-contracts.md — same §0.3 gate as Advertisement/Driver Suspend/
   Safety-Support's non-HTTP commands — flagged, not built. 708 passed,
   5 skipped, 0 failed (was 667) — see the roadmap's §2.0/§19 for the full
   write-up.
10. DONE — Phase 04's "GET ride status" and Phase 11's "Financial audit
    trail" (ADR-0024, 2026-08-25): `GET /api/v1/rides/{ride_id}`
    (customer/driver-ownership-restricted, IDOR-safe, composes
    modules.driver/modules.vehicle/modules.pricing for the
    driver/vehicle/fare sub-objects, `payment` always `null` — no
    Payment domain exists, Phase 10 blocked) and `GET
    /api/v1/drivers/me/wallet/transactions` (the driver's own paginated
    ledger, reusing `shared/pagination.py`/`MAX_PAGE_SIZE` from item 9).
    Closes out Phase 04 entirely (all 9 tasks now COMPLETE). 727 passed,
    5 skipped, 0 failed (was 708) — see the roadmap's §2.0/§7/§14 for
    the full write-up.
11. DONE (documentation-only, no code/schema/provider change; baseline
    unchanged at 727 passed) — Approved P2P Payment Model (ADR-0025,
    2026-08-25): the project owner formally recorded that VISTAAR does
    not collect the customer's ride fare in any form — the customer
    pays the driver directly, and the platform fee is charged only to
    the driver's wallet at ride acceptance (exactly what ADR-0014
    already implemented). Reconciled every affected canonical document
    (business-rules.md, api-contracts.md, database-design.md,
    domain-design.md, state-machines.md, technical-architecture.md,
    implementation-readiness.md) with inline "SUPERSEDED" annotations,
    not deletions, resolving a long-standing internal contradiction
    between this already-implemented model and a second, never-built
    "VISTAAR collects the fare via gateway or bundled offline cash"
    model both had documented. Phase 10 (Payments) is now largely N/A,
    not blocked — see the roadmap's §13. Driver wallet recharge (Phase
    11) remains the one genuinely blocked payment-gateway need,
    unaffected. NOT resolved: whether customer outstanding-penalty
    charges (BR-055) can still be paid via a VISTAAR-facing flow —
    flagged for the project owner. See the roadmap's §2.0 for the full
    write-up.
12. DONE (documentation-only, no code/schema/provider change; baseline
    unchanged at 727 passed) — Customer Outstanding Penalty Collection /
    Split Settlement, Option A (ADR-0026, 2026-08-26): resolves item 11's
    one open question. A valid customer cancellation/no-show penalty
    creates an OUTSTANDING liability (already exactly how
    `penalty.penalties` works — no change needed there); VISTAAR does not
    collect it immediately, but surfaces it, combined with the ride fare
    as an informational total, at the customer's next ride booking
    (api-contracts.md §12 gains a documented, not-yet-implemented
    `outstanding_penalty`/`total_payable` response shape). The ride fare
    stays P2P; the penalty is settled as a genuinely separate "Customer →
    VISTAAR" charge, never through the driver's wallet. Partially
    un-supersedes content ADR-0025 had marked fully dead: business-
    rules.md §12 (BR-037/038, revived with corrected mechanics),
    database-design.md §20's `payment.payments`/`payment.allocations`
    (may be the right schema for penalty collection specifically — its
    `VISTAAR_PENALTY` allocation type appears to have anticipated this).
    Phase 10 regains one real, still-blocked task accordingly. NOT
    resolved: the actual payment provider/mechanism for penalty
    collection (same open gap as wallet recharge). See the roadmap's
    §2.0 for the full write-up.
13. DONE — GPS Verification Foundation & Ride Lifecycle (Phase 06/07,
    ADR-0028, 2026-08-25): the project owner answered the "ok ask the
    queries you have doubt" round's top questions — GPS radius = 50m
    arrival / 100m completion, 3 attempts before manual review; Dispute
    domain = Support/Admin capability, no new domain (closes ADR-0002 in
    favor of Option B). Implements the full ACCEPTED → ARRIVED → STARTED
    → COMPLETED → CLOSED chain: `ride.gps_verifications`/`ride.ride_otps`
    (already fully specified, migration 9d0f47a4fe18); `POST .../arrived`,
    `POST .../otp/refresh`, `POST .../start`, `POST .../complete`
    (api-contracts.md §17/§18/§28); `ride.arrived`/`ride.started`/
    `ride.completed` outbox events (event-contracts.md §10.3/10.4/10.8);
    COMPLETED → CLOSED automatic/immediate in the same request (no
    documented precondition or event gates it separately). One design
    correction made mid-build: the OTP is only ever persisted as its
    HMAC, so the plaintext can only ever be returned by `otp/refresh`'s
    own response, never recovered later via GET Ride — corrected in both
    the ADR and api-contracts.md §18. Dispute-as-Support itself (Phase
    13, evidence/admin review) is decided but deliberately NOT built by
    this task. 767 passed, 5 skipped, 0 failed (was 727) — see the
    roadmap's §2.0/§13/§14 for the full write-up.
14. DONE — Dispute-as-Support (Phase 13, ADR-0029, 2026-08-25),
    immediately following item 13 at the project owner's request. Scopes
    and implements exactly what BR-121 and domain-design.md §17.3
    authorize: ride-fare disputes and DisputePenalty both realized as
    ordinary Support Cases (`POST /api/v1/support/cases`, already built,
    ADR-0022; `category: "RIDE_FARE_DISPUTE"`/`"PENALTY_DISPUTE"`,
    documentation-only conventions) decided via the already-built `POST
    /api/v1/admin/penalties/{id}/resolve` (`action: "WAIVE"` = dispute
    upheld). One real code change: Customer Cancellation's `charge`
    response gains `penalty_id` (api-contracts.md §19) so the customer
    has something to reference. No new domain, table, endpoint, or state
    — the GPS-verification-dispute evidence/admin-override workflow
    (security.md/testing-strategy.md) stays explicitly out of scope,
    ADR-0002's "never ratified" finding reaffirmed, not overridden. 768
    passed, 5 skipped, 0 failed (was 767) — see the roadmap's §2.0/§13
    for the full write-up.
15. DONE — Early Drop (Phase 08, ADR-0030, 2026-08-25), continuing
    autonomously per the phase-level-autonomy agreement immediately after
    item 14. Re-examined the apparent GPS-tolerance blocker (state-
    machines.md §63, security.md §12) and found it dissolves without a
    new owner decision: BR-088/api-contracts.md §27/technical-
    architecture.md §43 all describe GPS/location as recorded evidence,
    never a verified threshold — only state-machines.md §19-21 (lower-
    ranked) adds an unratified verification-gate mechanic, the same shape
    of finding ADR-0002 already made for the GPS-dispute workflow.
    Implements RequestEarlyDrop/ConfirmEarlyDrop: `ride.early_drop_
    requests` (plus one additive `reason` column); `POST .../early-drop`,
    `POST .../early-drop/confirm`; `ride.early_drop_confirmed`; STARTED →
    EARLY_DROP_REQUESTED → (both confirm) → COMPLETED → CLOSED (no new
    ride status); no fare recalculation (BR-090). Also stabilized a
    genuine, pre-existing (not caused by this task) test-isolation gap in
    tests/test_get_ride_status_api.py (the same Redis-geo-index-never-
    cleaned issue items 13/14's own new test files already worked around)
    that was occasionally failing full-suite runs. 788 passed, 5 skipped,
    0 failed (was 768) — see the roadmap's §2.0/§8 for the full write-up.
16. DONE — MSG91 SMS Provider & AWS S3 Object Storage (ADR-0031,
    2026-08-25). The project owner answered two of the four remaining
    open provider questions (via AskUserQuestion). MSG91 wired in behind
    modules.identity.sms's already-prepared `get_sms_provider()` seam
    (`SMS_PROVIDER=msg91`, `dev` stays the default) — flagged, not
    claimed verified, since no live MSG91 account exists in this
    environment to test the exact API shape against. AWS S3: a new `POST
    /api/v1/drivers/me/uploads` returns a presigned S3 PUT URL; the
    already-documented document/profile-photo submission endpoints are
    completely unchanged. Scoped to driver-facing uploads only — vehicle
    documents still have no HTTP endpoint (ADR-0007), not expanded here.
    813 passed, 5 skipped, 0 failed (was 788) — see the roadmap's
    §2.0/§4 for the full write-up.
17. DONE — GPS Dispute Manual Review (BR-124/BR-125, ADR-0032,
    2026-08-25), continuing autonomously per the phase-level-autonomy
    agreement immediately after item 16. The project owner reviewed the
    drafted business rules (surfaced via a follow-up AskUserQuestion) and
    approved them for implementation as-is, resolving the one item item
    16 left explicitly open. A terminal GPS_VERIFICATION_FAILED outcome
    from mark_arrived()/complete_ride() now auto-opens a `ride.gps_
    disputes` row (same transaction as the failing verification);
    customer/driver may submit evidence within the approved 24-hour
    window via `POST .../evidence` (reusing item 16's S3 presigned-upload
    flow, or free text); an admin resolves via
    `POST /api/v1/admin/gps-disputes/{id}/resolve` — APPROVE performs the
    exact ride transition a real PASS would have, REJECT records the
    decision only. The 24-hour window is enforced lazily, no background
    worker, matching item 13's own precedent (ADR-0011 Decision 2). Two
    new events (`ride.gps_dispute_opened`, `ride.gps_dispute_resolved`)
    published to the outbox. 847 passed, 5 skipped, 0 failed (was 813) —
    see the roadmap's §2.0/§7 for the full write-up.
18. DONE — Ride Modifications: Pickup Change (BR-072-078, ADR-0033,
    2026-08-25) — SUPERSEDED 2026-08-31 by ADR-0056-pickup-change-
    simplification-hard-threshold.md (owner decision): the driver
    PROCEED/PASS flow and >250m charge described below were removed in
    favor of a flat 100m hard threshold with no driver decision and no
    charge; see that ADR for the full reconciliation. Kept below as the
    historical record of what this item originally shipped. Continuing
    autonomously per the phase-level-autonomy agreement immediately
    after item 17. The project owner resolved
    BR-076's TBD pickup-change rate (same as the ride's own base per-km
    fare, not a new flat number) via a follow-up AskUserQuestion — the
    real remaining gap, since BR-080's destination-extension rate turned
    out to already be ratified (₹8/km), not TBD as this file previously
    assumed. Implements RequestPickupChange/ConfirmPickupChange: a
    ≤250m change applies immediately; a >250m change creates a pending
    request, driver PROCEED (computes the charge via a new
    `PricingService.calculate_pickup_change_charge()`, customer must
    confirm) or PASS (no penalty/strike, ride resets to SEARCHING and
    re-dispatches near the new pickup — resolving the same rematch
    ambiguity ADR-0016 Item 2 left open for normal driver cancellation
    specifically, which stays unresolved). Mid-task, a research miss was
    caught and corrected: the implementation initially invented a new
    table before finding database-design.md §11's already-documented
    unified `ride.change_requests` table (shared with a future
    Destination Change); the project owner was asked and chose the
    rework. 862 passed, 5 skipped, 0 failed (was 847) — see the
    roadmap's §2.0/§9 for the full write-up.
19. DONE — Ride Modifications: Destination Change (BR-079-082, ADR-0033
    Decision 9, 2026-08-25), continuing autonomously immediately after
    item 18 — the one item that entry itself flagged as "not blocked,
    just not yet built." Implements RequestDestinationChange/
    ConfirmDestinationChange, classifying WITHIN_ROUTE (BR-079, no
    charge)/BEYOND_ORIGINAL (BR-080, flat ₹8/km, already ratified)/
    DIFFERENT_ROUTE (BR-081, full recalculation) and reusing item 18's
    `ride.change_requests` schema (`request_type=DESTINATION_CHANGE`,
    no new migration). Two engineering-judgment calls were needed and
    recorded in the ADR rather than guessed past silently: a 200m
    route-deviation classification tolerance (no document specified
    one), and "current location" for the recalculation case (no live
    per-ride GPS tracking exists anywhere in this codebase — `ride.
    current_pickup` is used instead). Closes out Phase 09 entirely.
    879 passed, 5 skipped, 0 failed (was 862) — see the roadmap's
    §2.0/§9 for the full write-up.
20. DONE (foundation only) — Notification Domain Foundation (ADR-0034,
    2026-08-25), continuing autonomously immediately after item 19.
    `NotificationService.send()` real for IN_APP (pure DB write) and SMS
    (MSG91's Flow API, generalized from `modules.identity.sms`'s
    existing OTP-only integration); composed synchronously into two
    proof-of-concept trigger points (ride.accepted, ride.arrived) rather
    than a real Kafka consumer, none of which exists anywhere in this
    codebase (Phase 18's own "remain undone"). No HTTP endpoint exists
    anywhere for Notification (api-contracts.md documents none) — the
    same §0.3 stop condition ADR-0018/ADR-0021 already hit, so the
    service layer is composed directly at other routers, not exposed.
    Push (FCM, owner-approved) is scoped out specifically: no device-
    token data source exists anywhere in this codebase, and registering
    one would itself be a new, undocumented endpoint — `Channel.PUSH`
    raises `ChannelNotAvailableError` rather than being faked. WhatsApp:
    no BSP chosen, no code written, per the owner's own explicit
    instruction — a requirements analysis was delivered instead of an
    implementation. 898 passed, 5 skipped, 0 failed (was 879) — see the
    roadmap's §2.0/§15 for the full write-up.

21. DONE (config/script layer only) — DigitalOcean Deployment Artifacts
    & Production Dockerfile Fixes (ADR-0035, 2026-08-25). **The
    DigitalOcean choice this item records was itself superseded
    2026-09-03 (ADR-0063) — the owner switched to AWS only, explicitly
    instructing "Do not use DigitalOcean." See ADR-0063 and the new
    `infrastructure/terraform/aws/` module; this entry is preserved
    below as the historical record of the choice made at the time, not
    the current plan.** Continuing
    autonomously immediately after item 20. Asked the owner for a cloud
    provider and was told AWS; found technical-architecture.md §64
    already documents DigitalOcean Kubernetes as the baseline while
    surveying existing infrastructure files immediately afterward —
    flagged before writing any AWS-specific IaC, and the owner chose to
    switch, overriding their own earlier pick. Wrote and validated (not
    applied — no DigitalOcean account credentials exist in this
    environment) a hardened multi-stage `apps/backend/Dockerfile`,
    `infrastructure/kubernetes/` manifests, and an
    `infrastructure/terraform/digitalocean/` module for DOKS + Managed
    PostgreSQL (PostGIS) + Managed Redis + a self-hosted Kafka Droplet +
    Spaces. Building the image for real (never done before — CI has no
    Docker step) surfaced two genuine pre-existing bugs: `httpx`,
    imported unconditionally by `modules/identity/sms.py`'s MSG91 calls,
    was declared only as a dev dependency (reproduced via `docker run`
    crashing with `ModuleNotFoundError: No module named 'httpx'`); and
    `pip install .`'s setuptools auto-discovery silently flattened
    `src/` into a second, divergent installed copy of the same code.
    Both fixed and re-verified the same way — `/health` returned 200 and
    the image's own `HEALTHCHECK` reported healthy. 898 passed, 5
    skipped, 0 failed (unchanged from item 20 — no application logic
    touched) — see the roadmap's §2.0/§21 for the full write-up.

22. DONE — Security Response Headers & CI Dependency Scanning
    (ADR-0036, 2026-08-25), continuing autonomously immediately after
    item 21. Closed the two Phase 19 gaps flagged in this session's very
    first exchange, before any of items 09/15/19/21/22's work began:
    `SecurityHeadersMiddleware` applies security.md §64's five response
    headers to every request, with a documented judgment call on the one
    real ambiguity — Content-Security-Policy is exempted only on
    `/docs`/`/redoc`/`/openapi.json`, since FastAPI's own Swagger/ReDoc
    pages load CDN assets a strict CSP would break, and this backend is
    a JSON API, not the browser-rendered "deployed frontend
    architecture" the document's own qualifier is actually about. A new
    `pip-audit` CI step, scoped to just `[project].dependencies` (not
    the whole environment, which also flags the CI runner's own
    unrelated `pip` version — confirmed via a real local run: 7 findings
    against bare `pip-audit`, 0 against the properly-scoped
    `pip-audit -r <resolved production deps>`). Neither item needed an
    owner decision or new vendor account. Verified with a real
    `docker build` + `docker run`: `/health` carried all five headers
    including CSP; `/docs` carried the other four but correctly no CSP,
    and visibly still loaded its CDN CSS. 905 passed, 5 skipped, 0
    failed (was 898) — see the roadmap's §2.0/§19 for the full write-up.

23. DONE — Resource-Ownership Authorization Audit (ADR-0037,
    2026-08-26), continuing autonomously immediately after item 22.
    Before starting, found this same list's own item 22 write-up — and
    Phase 02's OTP-IP-dimension claim two sections above — had gone
    stale (both already fully built, not reflected back into the
    narrative), so this task verified the audit's own premise against
    the actual code first rather than trusting the document. Audited
    every router endpoint with a resource-ID path parameter (ride,
    safety/SOS, support case, vehicle; admin excluded — an admin is
    authorized to see every resource by design). Every ownership check
    was already correctly implemented; found one real test-coverage
    gap — `destination-change`'s two endpoints had the right check
    (verified: same `RIDE_NOT_FOUND` for missing vs. not-yours) but no
    regression test, unlike every sibling ride sub-resource — fixed
    with two new tests. Also corrected Phase 01's stale "driver
    documents still use a placeholder" claim, written before ADR-0031
    actually retrofitted `evidence_uri` onto real S3. 907 passed, 5
    skipped, 0 failed (was 905) — see the roadmap's §2.0/§01/§02 for the
    full write-up.

24. DONE — Notification Kafka Consumer (ADR-0038, 2026-08-26),
    continuing autonomously immediately after item 23. Built
    `modules/notification/consumer.py`'s `NotificationConsumer` — the
    first real Kafka consumer anywhere in this codebase (Phase 15/18's
    own long-standing "no consumer exists" gap). Checked event-
    contracts.md's own per-event "Consumers:" lists directly (not just
    domain-design.md's looser §20.3 examples) before wiring anything:
    `ride.started`, `ride.completed`, `ride.cancelled`, `penalty.
    applied` are each explicitly named as Notification's own
    responsibility there, and each has an unambiguous recipient —
    wired, additively, alongside the existing synchronous `ride.
    accepted`/`ride.arrived` dispatch (left untouched). Every other
    documented event deliberately deferred with its own explicit reason
    (ADR-0038 Decision 3) rather than silently skipped. No live Kafka
    broker exists in this dev environment, so verified two ways
    instead: a real `docker build`+`docker run` smoke test confirmed
    both the outbox publisher and this new consumer retry their Kafka
    connections independently and indefinitely without blocking `/health`
    from serving 200s, and 9 new integration tests against a real
    Postgres test database (including the `ride.cancelled`
    no-driver-yet skip case and a same-envelope-twice idempotency check)
    exercise `handle_event()` directly. 916 passed, 5 skipped, 0 failed
    (was 907) — see the roadmap's §2.0/§15/§18 for the full write-up.

25. DONE — Celery Background Worker Foundation (ADR-0039, 2026-08-26),
    continuing autonomously after the owner approved Celery ("Use
    Celery for background workers"). `shared/celery_app.py` (Redis as
    broker/backend, no new infrastructure) closes Phase 01's own last
    remaining task. `modules/notification/tasks.py` adds the first two
    real scheduled jobs — `PromotionExpiring`/`DocumentExpiring`
    (ADR-0038's own deferred list, resolved here) — a daily scan
    warning a customer/driver before a promotion/document expires,
    reusing `NotificationService.send()`'s dispatch and idempotency
    exactly as the Kafka consumer does, keyed by a value derived from
    the entity's id *and* its current `expires_at` so a renewed entity
    that later approaches expiry again still gets a fresh warning
    (verified with a dedicated test). Also fixed a real, unrelated
    mypy regression this dependency surfaced: `celery[redis]` pulled in
    redis-py 6.x, whose `hset()` stub changed to a form mypy correctly
    flags as unsound to `await` — one scoped `type: ignore[misc]` in
    `shared/geo.py`, not a silenced whole-file exemption. Verified with
    a real `docker build`+`docker run` of the exact Kubernetes
    manifest's `celery worker --beat` command against the real Redis/
    Postgres containers — task registration, Beat scheduling, and a
    real task submission all confirmed live; also caught and fixed a
    genuine liveness-probe bug this same verification surfaced (`$(HOST
    NAME)` is never substituted in a Kubernetes exec probe, which runs
    without a shell) before it shipped. 7 new tests. 923 passed, 5
    skipped, 0 failed (was 916) — see the roadmap's §2.0/§01/§15/§18
    for the full write-up.

26. DONE — Admin Permission Model (ADR-0040, BR-126/BR-127,
    2026-08-26), continuing autonomously after the owner reviewed the
    VISTAAR Admin Web plan and said "continue," confirming this ADR.
    Resolves Phase 02's long-blocked "Admin RBAC" item — `admin.users.
    role` now distinguishes `SUPER_ADMIN` (implicit full access) from
    `ADMIN` (an employee admin, access entirely determined by a new
    `admin.permissions` table — one row per module, `VIEW` or
    `MANAGE`); a Super Admin creates employee admins and grants/revokes
    their permissions through real, Super-Admin-only endpoints (`POST/
    GET /api/v1/admin/admins` and its siblings); every *existing* admin
    route (Driver/Vehicle Review, Search Rides, Admin Wallet View,
    Search Penalties, Search GPS Disputes, and their mutations) was
    converted from bare account-type authentication to a real
    per-module permission check — 12 call sites. `security.md` §7's
    original fixed SAFETY_ADMIN/FINANCE_ADMIN/SUPER_ADMIN role list is
    corrected to match. Bootstrapping the very first Super Admin stays
    an ops-only script (`scripts/provision_admin.py --role
    super_admin`), never a public endpoint — BR-127's own rule. A real
    integration-test failure caught a genuine bug before it shipped: an
    earlier `# type: ignore[arg-type]` (written to silence a mismatch
    rather than fix it) had let `Permission.access_level` be stored as
    a raw string instead of the `AccessLevel` enum, crashing the first
    time a real permission was actually returned over HTTP — fixed
    properly instead of re-suppressed. 46 new tests (domain, service,
    and real-Postgres API integration, including dedicated permission-
    enforcement cases). 969 passed, 5 skipped, 0 failed (was 923) — see
    the roadmap's §2.0/§02/§19 for the full write-up.

Everything else (Push's device-token endpoint, WhatsApp's BSP pick,
the remaining Notification event-list items deferred under ADR-0038/
ADR-0039, Admin MFA (still no documented endpoint shape, unaffected by
ADR-0040), plus the specific blocked tasks called out within
03/10/11/12/14/16, and actually applying item 21's Terraform/
Kubernetes artifacts against a real DigitalOcean account) waits on the
project owner or a materially
larger piece of new infrastructure than a single bounded task. A payment
gateway selection covering two now-distinct
surfaces — driver wallet recharge (ADR-0025) and customer
outstanding-penalty collection (ADR-0026) — "SBI Bank" was named but
needs clarification (which SBI product/API, merchant credentials
available?) before it can move; or actually provisioning against
DigitalOcean. (Corrected 2026-08-25 — Phase 16 removed
from this list: ADR-0023 completed its genuinely unblocked scope, see
item 9 above; its remaining 12 admin capabilities are flagged as
undocumented API contracts, not a project-owner-level blocker like the
others in this list. Phase 10 moved into this list's own enumeration,
not removed from it — most of its scope is N/A per ADR-0025, but its
remaining need(s) — the wallet-recharge gateway, and, since ADR-0026,
penalty collection — are exactly this list's "payment gateway selection"
item, now correctly scoped as two surfaces. Item 10 above is now also
DONE — every item in this RECOMMENDED EXECUTION ORDER list is complete;
what remains is exclusively the project-owner-blocked list this
paragraph names. Updated again 2026-08-26 — item 12/ADR-0026 added.
Updated again 2026-08-25 — item 13/ADR-0028 added; Phase 06/07 removed
from the "waits on the project owner" list, now DONE; Phase 08
reclassified from transitively-blocked to genuinely-unblocked-but-
unstarted. Updated again 2026-08-25 — item 14/ADR-0029 added; Phase 13
removed from the "waits on the project owner" list for its documented
scope, now DONE; only the unratified GPS-dispute-evidence workflow
within Phase 13 remains genuinely blocked, on a business-rules.md
decision that was never made, not an engineering gap. Updated again
2026-08-25 — item 15/ADR-0030 added; Phase 08 removed from this list
entirely, now DONE. Updated again 2026-08-25 — item 16/ADR-0031 added;
notification provider and object-storage technology choice both removed
from this list, now DONE — the payment gateway item's own wording
updated to name the specific "SBI Bank" clarification still needed.
Updated again 2026-08-25 — item 17/ADR-0032 added; the GPS-dispute-
evidence workflow within Phase 13, called out above (item 14's own
update) as genuinely blocked on an unmade business-rules.md decision,
is now DONE — the project owner made that decision (BR-124/BR-125
approved), removing it from this "waits on the project owner" list
entirely. Nothing from item 13/Phase 06-07's original scope remains
outstanding. Updated again 2026-08-25 — item 19/ADR-0033 Decision 9
added (Destination Change); item 20/ADR-0034 added (Notification Domain
Foundation); item 21/ADR-0035 added (DigitalOcean deployment artifacts +
Dockerfile bug fixes) — "a cloud/deployment provider" reworded to
"actually provisioning against DigitalOcean" now that the provider
itself is chosen and the config/script layer for it is written; item
22/ADR-0036 added (security headers + CI dependency scanning); item
23/ADR-0037 added (resource-ownership authorization audit); item
24/ADR-0038 added (Notification Kafka consumer, the first real
consumer in this codebase); item 25/ADR-0039 added (Celery Background
Worker Foundation, owner-approved) — "a background-worker technology
choice" removed from the "waits on the project owner" list above, now
resolved; item 26/ADR-0040 added (Admin Permission Model, BR-126/
BR-127) — "Admin RBAC" removed from Phase 02's own blocked-item list,
now resolved, leaving only Admin MFA blocked there; every item in this
RECOMMENDED EXECUTION ORDER list is now complete.)
