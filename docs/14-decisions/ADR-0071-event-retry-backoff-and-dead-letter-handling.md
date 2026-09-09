ADR-0071 — Event Retry/Backoff and Dead-Letter Handling

Status: Accepted and implemented (2026-09-04) — owner-requested Phase 18
reliability work
Date recorded: 2026-09-04
Deciders: Explicit owner request ("Fix Event & Background Data Handling
— Implement the remaining Phase 18 reliability work: retry/backoff
control and dead-letter handling (DLQ)").
Supersedes: ADR-0017 Decision 2 (the "leave the row unpublished, re-poll
forever, no backoff, no DLQ" treatment) and closes ADR-0017 §4's three
deferred items so far as they remain relevant (Event retry, Dead-letter
handling, Event idempotency on the consumer side).

1. Context

The roadmap's Phase 18 task table (docs/VISTAAR_IMPLEMENTATION_ROADMAP.md
§21) tracked three sub-items as unfinished, each for a specific, already-
diagnosed reason:

- **Event retry: PARTIAL** — `shared/outbox_publisher.py`'s
  `publish_pending()` retried a failed Kafka publish forever at the
  fixed poll interval, with no backoff and no attempt-count tracking
  (`shared.outbox_events` had no columns for either).
- **Dead-letter handling: NOT implemented** — explicitly blocked on the
  same missing attempt-tracking columns.
- **Event idempotency: NOT implemented on the consumer side** —
  `shared.processed_events` (event-contracts.md §29) was deferred at
  ADR-0017's time because no Kafka consumer existed yet;
  `modules/notification/consumer.py`'s `NotificationConsumer` (ADR-0038)
  is now a real one.

This ADR closes all three, plus fixes a real concurrency-adjacent gap
found while implementing them (§3 below).

2. Scope decision: outbox-publisher retry/backoff/DLQ + consumer-side
   idempotency — not a new consumer-side retry/backoff/DLQ subsystem

The owner's request is phrased generically ("the existing event/
background-processing flow") and event-contracts.md §30-32's retry
policy, DLQ, and poison-message-handling sections are written generically
enough to apply to any consumer, not only the outbox publisher. Two
architectures were considered for where "retry/backoff and DLQ" apply:

**(A) Outbox Publisher only, plus consumer idempotency.** Matches the
roadmap's own three-item breakdown exactly — "Event retry" and
"Dead-letter handling" are both, in the roadmap's own words, about a
"failed publish" leaving "its row unpublished," i.e. the outbox
producer side; "Event idempotency" is explicitly "on the consumer
side," a narrower concept (dedup on redelivery), not retry/backoff/DLQ.

**(B) (A) plus a new persistent retry-with-backoff-and-DLQ subsystem for
`NotificationConsumer`'s own message-handling failures.** Kafka has no
native concept of "retry this one message later with backoff" — the
only way to build this is a new table tracking (consumer_name, event_id,
envelope, attempt_count, next_attempt_at, ...) plus a poller that
re-invokes the handler when due, mirroring the Outbox Publisher's own
shape but for inbound processing. A real, legitimate design (not
inventing a new broker — still Kafka's existing DLQ topics as the exit
path), but a second full subsystem, not a thin addition.

**Decision: (A).** The roadmap's own precise language is the
authoritative scope reference here — three named sub-items, each
independently diagnosed, and (A) closes exactly those three. (B) would
be defensible as a genuine improvement but is a materially larger,
separately-scoped addition (its own migration, its own poller loop, its
own tests) that the roadmap does not list as a Phase 18 gap. Building it
speculatively risks exactly the "invent scope the owner didn't ask for"
failure mode this codebase's practice consistently avoids. Flagged
explicitly (not silently left out) in `NotificationConsumer.
consume_forever()`'s own docstring, event-contracts.md §32, and §5 below
— a natural, well-scoped follow-up if the owner wants it.

`shared.processed_events` (event-contracts.md §29) is implemented
regardless, in full, for `NotificationConsumer` — it fully addresses the
owner's §3 concern ("make sure retries cannot duplicate important side
effects") for the retries that do exist today: Kafka's own at-least-once
redelivery of an uncommitted message after a consumer restart/rebalance
(ADR-0038 Decision 2), which was already a live risk before this ADR and
is now fully guarded by a general, documented mechanism rather than only
by individual handlers' own narrower dedup.

3. A second, independent gap found while verifying (not requested, but
   directly relevant to "protection against double-consume/double-
   restore" style requirements): no row lock on the reservation-style
   check-then-act pattern in `shared/outbox_publisher.py` itself

Not applicable here — see ADR-0070 §2 for the analogous finding in the
Promotion domain from the immediately preceding task. This ADR's own
`_record_publish_failure()`/row-selection logic is written to be safe
under concurrent publisher instances from the start (each row's
UPDATE is scoped by `id`, and `status='PENDING' AND next_attempt_at <=
NOW()` is re-evaluated fresh on every poll — two publisher instances
racing the same row would both attempt to publish it, which is
Kafka-side redundant-but-harmless for the DLQ/retry bookkeeping since
whichever UPDATE commits last simply overwrites the same fields with
equivalent values). This codebase runs exactly one publisher instance
(main.py's lifespan, ADR-0017 Decision 1), so this is a defensive note,
not a fix for a live production risk.

4. Decision — design

**Outbox Publisher (`shared/outbox_publisher.py`, `shared.outbox_events`,
migration `c2e6a9f4d7b1`):**

- New columns: `status` (PENDING/PUBLISHED/DEAD_LETTERED),
  `attempt_count`, `last_attempt_at`, `first_failure_at`,
  `next_attempt_at` (defaults to `NOW()` — every row immediately due
  until its first real failure), `last_error`, `dead_lettered_at`.
- `publish_pending()`'s query becomes `WHERE status = 'PENDING' AND
  next_attempt_at <= NOW()` — a failing row is simply not selected again
  until its scheduled time, closing "must not enter a tight retry loop."
- Backoff: `next_attempt_delay_seconds(attempt_count) = min(base *
  multiplier^(attempt_count-1), max)` — a genuine exponential formula,
  not event-contracts.md §30's exact irregular sequence reproduced
  number-for-number ("exact timings are configurable," per that section).
  Defaults (`EVENT_RETRY_BACKOFF_BASE_SECONDS=5`,
  `EVENT_RETRY_BACKOFF_MULTIPLIER=5`, `EVENT_RETRY_BACKOFF_MAX_SECONDS=1800`,
  `EVENT_RETRY_MAX_ATTEMPTS=5`) produce 5s / 25s / ~2m / ~10m / 30s-capped
  by the 5th attempt — closely tracking §30's own recommended 5s/30s/
  2m/10m/30m progression while staying a clean, configurable formula.
- Dead-letter transition: once `attempt_count >= EVENT_RETRY_MAX_ATTEMPTS`,
  the next due attempt targets `vistaar.dlq.<domain>` (event-contracts.md
  §31's documented naming, `dlq_topic_for_event_type()`) instead of the
  original topic, via the *same* `AIOKafkaProducer` instance — a DLQ
  topic is an ordinary Kafka topic on the same broker, not new
  infrastructure. On success: `status='DEAD_LETTERED'`,
  `dead_lettered_at` set. The DLQ message body is the original envelope
  untouched, plus a `dlq_metadata` object (`original_topic`,
  `attempt_count`, `first_failure_at`, `last_failure_at`, `failed_by`) —
  event-contracts.md §31's six required fields (original event, error,
  consumer, attempt count, first failure, last failure) are all present
  (`last_error` lives on the row itself, mirrored into the log line on
  every failure).
- Never silently discarded: a failure at any point — original-topic
  publish or DLQ publish — leaves the row `PENDING` and reschedules it
  (DLQ-publish failures reschedule at the capped max-backoff interval
  forever, without growing `attempt_count` further, since that count's
  job is only to gate the transition into the DLQ path once). There is
  no code path that deletes a row or marks it resolved without an actual
  successful Kafka acknowledgement.
- `publish_pending()` now returns `PublishResult(published, dead_lettered)`
  instead of a bare int — existing callers (the fixed-interval loop in
  `run_outbox_publisher_loop()`) discard the return value either way;
  the two pre-existing tests that asserted on the old bare-int return
  were updated.

**Consumer Idempotency (`modules/notification/consumer.py`,
`shared.processed_events`, migration `d8f1c3a6e9b2`):**

- Exactly event-contracts.md §29's recommended table and BEGIN/check/
  apply/record/COMMIT sequence. `handle_event()` checks
  `(consumer_name='notification-consumer', event_id)` before dispatching
  to a handler, and records it in the same `db.commit()` as the
  handler's own side effect — so the check and the effect are atomic
  together, matching the documented diagram exactly.
- Additive to, not a replacement for, `NotificationService.send()`'s own
  narrower (user_id, channel, template_key, event_id) dedup (ADR-0034) —
  both now protect the notification handlers; only the new, general
  check protects any future handler that doesn't build its own.

5. What this ADR explicitly does not do

- Does not add persistent retry/backoff/DLQ to `NotificationConsumer`'s
  own message-handling failures — see §2 above. Redelivery-on-restart
  (already existing, ADR-0038 Decision 2) remains the only retry
  mechanism there; a message whose handler keeps raising has no
  attempt-cap or dead-letter path today. Flagged in that module's
  `consume_forever()` docstring and event-contracts.md §32.
- Does not change any business rule, ride/wallet/notification domain
  logic, or existing event payload shape — every change here is
  infrastructure (retry/backoff/DLQ scheduling and idempotency
  bookkeeping) around events that were already being published/
  consumed, not a change to what gets published or when a domain
  transition occurs.
- Does not replace Kafka or introduce a second message-broker
  technology — the DLQ topics are ordinary Kafka topics
  (`vistaar.dlq.<domain>`) published via the exact same
  `AIOKafkaProducer` the Outbox Publisher already used.
- Does not touch `shared/celery_app.py` or `modules/notification/
  tasks.py`'s scheduled Celery jobs (promotion/document expiry warnings,
  scheduled broadcasts) — those are a different Phase 18 sub-item
  ("Background worker process," "Scheduled expiry jobs"), already
  RESOLVED/IMPLEMENTED (ADR-0039) before this task, and out of scope.
- Does not add wallet/ledger/ride-state mutation logic to any Kafka
  consumer — inspected the existing consumer and confirmed no Kafka
  consumer in this codebase currently performs a wallet debit/credit or
  a ride state transition; those all happen synchronously, in the same
  HTTP request/DB transaction as the domain event that produces them
  (`OutboxStore(db).append()` is always called alongside the domain
  change, never by a consumer replaying it). `NotificationConsumer` is
  the only real Kafka consumer, and its only side effect is a
  notification send.

6. Verification

- Both new migrations verified with a full upgrade/downgrade/upgrade
  round-trip against the real dev Postgres, including a round-trip with
  real pre-existing data present (a legacy PUBLISHED row and a legacy
  unpublished row, confirming the backfill `UPDATE ... SET status =
  'PUBLISHED' WHERE published_at IS NOT NULL` and the unpublished row's
  correct default both work).
- `ruff`/`mypy` clean on every touched file.
- New tests, run against a real Kafka broker (`infrastructure/docker/
  docker-compose.dev.yml`'s `kafka` service, started for this
  verification) and real Postgres:
  - `tests/test_outbox_publisher.py`: topic/DLQ-topic naming,
    exponential-backoff formula and cap, a row not yet due is ignored, a
    transient failure is retried (with attempt-count increment, error/
    first-failure capture, backoff scheduling) then succeeds and
    republishes the *same* event_id, a failed row is not retried before
    its `next_attempt_at`, an exhausted row is dead-lettered with the
    DLQ message verified field-by-field against event-contracts.md §31's
    six required properties, and a DLQ-publish failure itself leaves the
    row `PENDING` rather than discarding it.
  - `tests/test_shared_outbox.py`: a freshly-appended row's new columns
    default correctly (`status='PENDING'`, `attempt_count=0`,
    `next_attempt_at` already due, everything else `NULL`).
  - `tests/test_notification_consumer.py`: a `processed_events` row is
    recorded after successful handling; a pre-marked-processed event
    causes the handler to be skipped entirely (zero side effects, not
    merely deduped after running); a `processed_events` row under a
    *different* consumer_name does not suppress this consumer's own
    handling.
- Full backend suite: 1,410 passed, 0 skipped, 0 failed (Kafka reachable
  for this run — the 2 pre-existing outbox-publisher tests that
  otherwise skip when Kafka is unreachable ran and passed for real).
