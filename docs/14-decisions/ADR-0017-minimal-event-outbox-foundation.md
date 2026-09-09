ADR-0017 — Minimal Event & Outbox Foundation

Status: Accepted
Date recorded: 2026-08-24
Deciders: Approved under the owner's phase-level autonomy grant (VISTAAR
session, 2026-08-24) — mandatory stop conditions (roadmap §0.3) still
apply and are respected below where they genuinely bite. Follows the
same "flag before implementing" governance as ADR-0010 through ADR-0016.

1. Context

Every task since Task 3.1 has documented the same gap: no Kafka producer
infrastructure exists, so no domain event (`ride.requested`,
`ride.accepted`, `wallet.debited`, etc.) is ever published, despite
event-contracts.md fully specifying the envelope, topic strategy,
outbox pattern, retry policy, and DLQ naming for all of them.
Phase 18 — Event & Background is where the roadmap schedules this work.
Of its 11 tasks, "Background worker process" is explicitly blocked
(Celery is an unapproved candidate — roadmap §4/§0.4), and "Scheduled
expiry jobs"/"Payment reconciliation" are transitively gated behind it
or Phase 10. This ADR scopes the minimal foundation for everything else:
event schemas, a Kafka producer, the outbox table, and an outbox
publisher — pulled together as one build, the same "minimal X
foundation" pattern ADR-0013 and ADR-0015 already established for
Wallet and Penalty.

2. Decision 1 — The outbox publisher is an in-process asyncio task, not
   the (still-unapproved) Celery/background-worker foundation

event-contracts.md §28 describes the publisher as reading unpublished
outbox rows and shipping them to Kafka on a loop — it does not mandate
*how* that loop is scheduled. A dedicated Celery worker process is one
way to run it; a lightweight `asyncio` task started from FastAPI's own
lifespan (no new process, no new technology, using only `asyncio` and
`aiokafka`, both already present) is another. This ADR picks the
in-process loop specifically because it needs no decision on the
still-blocked "Background worker foundation" question (Phase 01/18) —
Celery is for independently-scalable, heavy background jobs (scheduled
notifications, reconciliation), a different and larger concern than
"periodically drain one small table." If/when the Background Worker
Foundation technology is chosen, the publisher's core logic
(`publish_pending()`) can be lifted into that system unchanged — only
its scheduling wrapper would move.

3. Decision 2 — Retry is "leave unpublished and re-poll," not
   event-contracts.md §30's specific backoff sequence

§30 documents a five-step backoff (5s → 30s → 2m → 10m → 30m) before a
message reaches the Dead Letter Topic. That requires per-event attempt
tracking (an attempt count and a next-eligible-retry timestamp) that
`shared.outbox_events`' documented schema (database-design.md §34) does
not have — no `attempt_count`, no `next_retry_at`. Adding those columns
now, without the DLQ machinery they exist to feed, would be exactly the
kind of speculative schema addition this project's discipline avoids
(cf. ADR-0013's explicit refusal to build `credit()` "with nothing
calling it"). This task implements the simpler form §28 itself also
describes — "If publishing fails: keep event unpublished, retry" — via
a fixed-interval re-poll (every publish cycle re-attempts every
still-unpublished row). This satisfies the core outbox guarantee (a
committed domain change is never silently lost, even if Kafka is
temporarily unreachable) without the specific timing schedule.

4. Item 3 — Dead Letter Topics, Poison Message Handling, Consumer
   Idempotency: explicitly deferred, not decided here

- DLQ (§31) and poison-message handling (§32) both depend on the
  attempt-tracking Decision 2 defers — nothing yet routes a
  permanently-failing event anywhere but "stays unpublished forever,"
  which is a known, documented gap, not a silent one.
- Consumer idempotency (§29, `shared.processed_events`) is not built —
  no consumer module exists yet (Notification, Analytics, and every
  other documented consumer in event-contracts.md §56's registry are
  all unbuilt). Building the table now would be speculative
  infrastructure with no real caller, the same anti-pattern ADR-0013
  avoided for Wallet's `credit()`.

5. Decision 3 — Which events actually get wired up in this task

Not the full §56 registry (most of it belongs to modules that don't
exist — Pricing, Payment, Promotion, Referral, Verification, Safety,
Support, Advertisement). Wired up: exactly the events whose producing
code already exists and has been explicitly deferring this since its
own task — `ride.requested` (Task 3.1), `ride.accepted` (Task 3.4),
`ride.cancelled` (Tasks 3.3/3.5), `ride.driver_cancelled`* (Task 3.6),
`wallet.debited`/`wallet.credited` (Wallet Foundation/Task 3.5),
`penalty.applied` (Task 3.5), `penalty.strike_recorded` (Task 3.6).

*event-contracts.md's registry documents `ride.cancelled` as a single
event type without distinguishing customer- vs. driver-initiated
cancellation. This task publishes `ride.cancelled` for both, with the
`data.cancelled_by` field ("CUSTOMER" | "DRIVER") carrying that
distinction — an engineering completion of an already-approved event
name, not an invented one; api-contracts.md's own response payloads
already distinguish the two cancellation endpoints this same way.

6. Consequences — documents updated alongside this ADR

- `docs/VISTAAR_IMPLEMENTATION_ROADMAP.md` updated: this task marked
  complete for the scope above once implemented and verified.
- No content changed in `business-rules.md`, `domain-design.md`,
  `event-contracts.md`, `state-machines.md`, or `database-design.md` —
  `shared.outbox_events` is implemented exactly as already documented;
  none of the decisions above required a schema or business-rule
  change (the deferred attempt-tracking columns are exactly that:
  deferred, not added).
