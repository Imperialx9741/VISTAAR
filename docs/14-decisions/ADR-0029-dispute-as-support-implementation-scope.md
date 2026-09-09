ADR-0029 — Dispute-as-Support Implementation Scope (Phase 13)

Status: Decided and implemented (2026-08-25)
Deciders: Project owner (via ADR-0028's domain-placement decision) +
this record's own scoping of what that decision authorizes to build.

1. Context

ADR-0028 resolved ADR-0002's open question ("is Dispute a domain of its
own?") in favor of Option B: Support/Admin capability, no new `dispute.*`
domain/schema/service. That decision alone does not specify what to
build — ADR-0002 §5 is explicit that resolving the domain-placement
question is only the first of several steps ("api-contracts.md needs the
corresponding endpoints... event-contracts.md needs the corresponding
event family... state-machines.md needs the corresponding state
machine") before implementation. This record does that scoping work and
implements exactly what it authorizes — nothing beyond it.

Two, and only two, canonical mentions of "dispute" exist anywhere in the
documentation set (confirmed by the same document sweep ADR-0002 already
did, re-verified here):

- business-rules.md BR-121 ("Ride Fare Disputes"): "Because ride fares
  may be paid directly to drivers, ride-fare disputes require a
  support/admin process." No new endpoint, table, or state implied — it
  names an existing process (Support) as the mechanism.
- domain-design.md §17.3 (Penalty Domain commands): `DisputePenalty`,
  listed alongside the already-implemented `ResolvePenalty`
  (`POST /api/v1/admin/penalties/{id}/resolve`, action: "WAIVE" —
  api-contracts.md §48, ADR-0023). No request/response shape, no new
  `PenaltyStatus` value, and no dedicated endpoint is documented
  anywhere for `DisputePenalty` itself.

Everything else "dispute"-shaped in this documentation set — the
GPS-verification-dispute workflow described at length in security.md
§11-15 and testing-strategy.md §20-23/§89-90 (evidence upload, a
72-hour window, admin APPROVE/REJECT, "GPS override") — is exactly what
ADR-0002 §3 already classified as "an implementation concept that has
not been formally established": it was written directly into the
security/testing/implementation-readiness documents without ever passing
through business-rules.md → technical-architecture.md → domain-design.md
→ database-design.md → api-contracts.md → event-contracts.md →
state-machines.md, the source-of-truth chain business-rules.md §44/45
itself requires. ADR-0028's domain-placement decision does not retroactively
ratify that specific, elaborate, never-authored business rule — deciding
"where disputes live" is a different question from "what a GPS dispute's
evidence window and admin-override mechanics are," and only the former
was ever put to the project owner.

2. Decision

Phase 13 ("Dispute-as-Support") is implemented as the composition of two
already-built capabilities, matching exactly what BR-121 and
domain-design.md §17.3 authorize — no new domain, table, endpoint, or
state:

Decision 1 — Ride Fare Disputes (BR-121) are Support Cases.
`POST /api/v1/support/cases` (already built, ADR-0022) already accepts
`ride_id` + free-text `category` (api-contracts.md §44: "`category` has
no canonical enum documented anywhere"). This record documents
`"RIDE_FARE_DISPUTE"` as the category convention for exactly this BR-121
process — no code change, a documentation-only convention on an already-
generic field, the same treatment `document_type` values already get
elsewhere.

Decision 2 — DisputePenalty is a Support Case that references the
disputed penalty; ResolvePenalty (already built) is how it is decided.
A customer files a dispute the same way they file any other support
case — `POST /api/v1/support/cases` with `category: "PENALTY_DISPUTE"`
and the disputed penalty's `ride_id` (support.cases already carries
`ride_id`, ADR-0022 Decision 1 — no new column). An admin reviewing that
case already has everything needed to act: the case's `ride_id` and the
customer's account id (`GET /api/v1/support/cases/{case_id}`, already
built) resolve to a specific `penalty.penalties` row via the already-
built `GET /api/v1/admin/penalties?user_id=...` (ADR-0023) — the two are
never ambiguous today, since `penalty.penalties` currently only ever
holds customer cancellation penalties (BR-047/048;
`record_customer_cancellation()` is its only writer — no-show charges,
BR-050-052, remain unbuilt) and `uq_penalties_ride_penalty_type`
guarantees at most one per (ride, type). Deciding the dispute is then
literally the already-built, already-documented `POST /api/v1/admin/
penalties/{penalty_id}/resolve` (`action: "WAIVE"`, api-contracts.md
§48) for a dispute upheld — state-machines.md §40's OUTSTANDING → WAIVED
transition already exists and already means exactly "the penalty is
reversed by an authorized/verified admin process," which is BR-121's own
wording almost verbatim. A dispute an admin decides against the customer
has no state-machine action to take (the penalty stays OUTSTANDING) —
only the support case itself is resolved (already-built `resolve_case()`
service method).

This makes domain-design.md §17.3's `DisputePenalty` command real
without inventing a `PenaltyStatus.DISPUTED` state, a dedicated
`/disputes` endpoint, or a `dispute.*` schema/event family — none of
which any canonical document has ever specified, consistent with the
same "invent nothing beyond what's documented" discipline this session
has followed for every other §0.3-gated gap (Advertisement's missing
HTTP endpoint, ADR-0018; Driver Suspend/Reactivate's missing HTTP
endpoint, ADR-0021; Support's own missing Assign/Resolve/PostMessage
endpoints, ADR-0022).

Decision 3 — one small, additive traceability field: `charge.penalty_id`
on the Customer Cancellation response (api-contracts.md §19). Today a
customer who receives a `charge` object from `POST /api/v1/rides/
{ride_id}/cancel` has no way to learn their own penalty's id — the
service already holds it (`penalty.id`, used internally for the
`penalty.applied` outbox event's `aggregate_id`) but the HTTP response
never returns it. Without it, Decision 2's dispute flow is directionally
right but practically useless: the customer can name the disputed
*ride*, but never the specific *penalty*, forcing the admin to guess
which OUTSTANDING/SETTLED row for that ride+user is meant even though
today that guess is unambiguous (see Decision 2's own reasoning) — it
will not stay unambiguous once no-show charges (BR-050-052) are ever
built and a ride can carry more than one penalty type. Adding
`penalty_id` now costs nothing (an existing in-memory value, appended to
an existing response dict, backward-compatible) and is the same kind of
minor completing-a-gap addition ADR-0015 §4 already made for this same
response (`expires_at`/`amount` were similarly filled in for the
amount-0/grace cases, not new business rules).

Decision 4 — the GPS-verification-dispute workflow (evidence upload,
72-hour window, admin APPROVE/REJECT, GPS override) remains explicitly
OUT OF SCOPE, not deferred by oversight. ADR-0002 already found it has no
origin in any canonical document; nothing about ADR-0028's domain
decision changes that finding. Building it now would mean inventing a
business rule and API surface from whole cloth — exactly the §0.3
mandatory-stop condition this session has consistently respected
elsewhere. If the project owner wants this workflow, it needs its own
business-rules.md entry and the full source-of-truth chain ADR-0002 §5
describes, the same as any other new capability.

Decision 5 — no new Assign/Resolve-Support-Case or PostMessage HTTP
endpoint. ADR-0022 Decision 6 already declined to build these
(`SupportService.resolve_case()`/`assign_case()`/`post_message()` exist
and are tested, with no documented HTTP shape) — that gap is unchanged
by this record. An admin resolving a dispute today still ultimately acts
through `POST /api/v1/admin/penalties/{id}/resolve` (Decision 2) for the
financial outcome; formally closing the underlying support case itself
still has no HTTP endpoint, same pre-existing, already-flagged gap.

3. What this implements (code)

- `charge.penalty_id` added to `POST /api/v1/rides/{ride_id}/cancel`'s
  response (`modules/ride/router.py`'s `_post_acceptance_cancellation_
  charge()`), present whenever a real `penalty.penalties` row exists
  (i.e., every post-acceptance cancellation outside the 2-minute grace
  period — including the ₹0 first-qualifying case, which still gets a
  real row per ADR-0015 Decision 2), `null`/absent only for the
  grace-period and SEARCHING-cancellation cases where no row is created.
- No other code change. `POST /api/v1/support/cases` and `POST /api/v1/
  admin/penalties/{id}/resolve` already fully support the flows above;
  this record only documents the convention connecting them and confirms
  it via tests (a new integration test exercising the full customer-
  disputes → admin-resolves flow end-to-end through both existing
  endpoints).

4. Consequences

- Phase 13 ("Dispute-as-Support") and domain-design.md §17.3's
  `DisputePenalty` command are now genuinely implemented, closing the
  last unimplemented item in the Penalty Domain's command list.
- modules/penalty/__init__.py's docstring, which previously stated
  "`DisputePenalty` (also §17.3) is NOT implemented — it belongs to the
  still-unresolved Dispute-domain question (ADR-0002)," is corrected.
- The GPS-verification-dispute workflow question ADR-0002 raised remains
  genuinely open for a future task — this record does not close it, only
  the narrower BR-121/`DisputePenalty` question ADR-0028 actually
  decided.
