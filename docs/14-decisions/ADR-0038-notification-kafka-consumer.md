ADR-0038 — Notification Kafka Consumer (First Real Consumer in This Codebase)

Status: Accepted.
Date recorded: 2026-08-26.
Deciders: Continuing autonomously under the owner's phase-level-autonomy
grant. No owner-level decision gate applies to the mechanism itself;
Decision 3 below records the one genuine engineering-judgment call this
task made on event/recipient scope, rather than guessing past silently.

1. Context

ADR-0034 built Notification's foundation with two events composed
synchronously at the router layer (`ride.accepted`, `ride.arrived`),
explicitly named as "a proof of concept... rather than a real Kafka
consumer, none of which exists anywhere in this codebase." This task
builds that consumer — the first one in this codebase (Phase 15/18's
own long-standing "no real Kafka consumer" gap, reconfirmed as recently
as ADR-0036/ADR-0037's own write-ups).

2. Decision 1 — In-process asyncio task, not a separate worker process

Mirrors ADR-0017 Decision 1's own precedent for the outbox *publisher*
exactly: an `AIOKafkaConsumer` started/stopped from `main.py`'s
`lifespan()`, running as its own `asyncio.create_task()` loop alongside
the existing publisher task — not a Celery/separate-process worker. The
Background Worker Foundation technology decision (Phase 01/18) remains
unapproved; this consumer is small enough not to need it, the same
reasoning ADR-0017 already established for the publisher side of the
exact same pipeline.

3. Decision 2 — Topics, group ID, and offset/retry handling

Subscribes to `vistaar.ride` and `vistaar.penalty` — exactly the topics
`shared/outbox_publisher.py`'s own `topic_for_event_type()` produces for
the event types wired below (event-contracts.md §6: one topic per
event-type domain). Consumer group `vistaar-notification-consumer`
(distinguishes this consumer's committed offsets from the outbox
publisher's own producer, and any future second consumer). Manual offset
commit — `enable_auto_commit=False`, committed only after a message's
handler returns successfully — not the outbox publisher's own
row-by-row DB commit (there is no per-message DB row to mark), but the
same underlying philosophy: a message that fails to handle is left
uncommitted and reprocessed on the next poll rather than silently
dropped. This is safe under Kafka's at-least-once delivery precisely
because `NotificationService.send()` (ADR-0034) is already idempotent on
`(user_id, channel, template_key, event_id)` — a redelivered message
calls `send()` again, hits the existing Delivery row, and does not
re-send.

4. Decision 3 — Which documented events are wired now, and which are
   deliberately deferred

domain-design.md §20.3 lists 14 example events Notification "consumes";
event-contracts.md's own per-event "Consumers:" lists (§10.4, §10.8,
§10.9, §17.1) name Notification explicitly and specifically for four of
them — checked directly against the source of truth rather than just
domain-design.md's looser example list, and cross-checked against what
this codebase actually publishes to Kafka (`grep event_type=` across
every router) before deciding:

Wired (a real outbox event exists, Notification is explicitly named as
a consumer in event-contracts.md, and the recipient is unambiguous;
IN_APP channel only — matching ADR-0034's existing SMS-cost/DLT-
registration caution):
- RideStarted → `ride.started` (event-contracts.md §10.4) → the ride's
  customer. The event payload only carries `driver_id`, not
  `customer_id` — the consumer looks up `ride.rides.customer_id` by the
  payload's `ride_id` rather than guessing or skipping the event over a
  missing field a one-row read easily supplies.
- RideCompleted → `ride.completed` (§10.8) → the ride's customer
  (payload already includes `customer_id`).
- RideCancelled → `ride.cancelled` (§10.9) → whichever party did NOT
  cancel — the payload carries `cancelled_by` ("CUSTOMER" or "DRIVER")
  but neither ID directly, so the consumer looks up both `customer_id`
  and `driver_id` from `ride.rides` and notifies the other one. Skipped
  (not an error) when that ride never had a driver assigned yet (a
  customer can cancel while still SEARCHING) — there is no one on the
  other side to tell.
- PenaltyApplied → `penalty.applied` (§17.1) → the penalized user
  (`data.user_id`, already in the payload).

Deliberately deferred, not silently skipped:
- SOSTriggered (`safety.sos_triggered` exists and is published) — who
  should actually receive this notification is a genuine, undocumented
  judgment call (the reporter themselves, as an "we received your SOS"
  acknowledgment? the other ride party? this is a safety-sensitive flow
  ADR-0022 already scoped narrowly — "never contacts any real emergency
  service" — and guessing wrong here has higher stakes than the other
  events). Left for a future task with its own explicit reasoning.
  RESOLVED (ADR-0050, 2026-08-28): the recipient is VISTAAR's own
  internal safety/call-center team (every Super Admin plus every
  employee admin holding SAFETY MANAGE access), not the reporter or the
  other ride party — now wired into `NotificationConsumer`.
- PromotionActivated — the closest real event, `promotion.reserved`,
  means "held pending use," not "activated/applied." Wiring it under
  the documented name would silently redefine what the event means;
  skipped rather than stretched.
- FareChanged — the closest real events, `ride.pickup_changed`/
  `ride.destination_changed`, already return the new fare directly in
  that same HTTP request's response to the customer who just asked for
  the change (api-contracts.md §26 etc.) — an additional async
  notification for information the same actor's own request already
  gave them is redundant, not obviously wrong, but also not a clear win;
  left for a future task to decide deliberately rather than added here
  as an assumed default.
- PaymentRequired / PaymentConfirmed — N/A (ADR-0025: VISTAAR never
  collects the ride fare in any form; no such event will ever exist
  under the current payment model).
- WalletLow / PromotionExpiring / DocumentExpiring — no triggering
  event exists anywhere in this codebase; each would need a scheduled/
  periodic check (a threshold crossing, an approaching expiry date),
  which is Background Worker Foundation territory (Phase 01, still
  unapproved) — not something this event-driven consumer can produce on
  its own.

  Resolved (ADR-0039, 2026-08-26): the owner approved Celery, closing
  the Background Worker Foundation gap. `PromotionExpiring`/
  `DocumentExpiring` are now real Celery Beat periodic tasks
  (`modules/notification/tasks.py`) — not this Kafka consumer, since
  neither ever had a triggering event to consume in the first place;
  ADR-0039 covers the design. `WalletLow` stays deferred, but for a
  different reason on reflection: a balance crossing a low threshold is
  naturally an event at the moment of a debit, not something that
  benefits from periodic scanning — better wired reactively at
  `WalletService.debit()` in a future task than folded into the
  scheduled-task set just because Celery is now available.
- SupportEscalated — no corresponding real event exists. `support.
  case_created` exists but means case creation, not escalation;
  `safety` module's own `SafetyEventType.ESCALATED` is a *different*,
  internal `safety.events` audit-log row (SOS escalation), never
  published to Kafka at all — not the same thing as a support case
  being escalated.

5. Decision 4 — Additive, not a replacement for the existing synchronous
   dispatch

`ride.accepted`/`ride.arrived`'s existing router-composed synchronous
`NotificationService.send()` calls (ADR-0034, in
`modules/matching/router.py` and `modules/ride/router.py`) are left
completely untouched — this consumer does NOT also subscribe to those
two events. Migrating them onto the consumer is a separate, valid future
decision (it would change delivery from "within the same HTTP request"
to "after the outbox publisher's next poll interval," a real behavior
and latency change, not just a refactor) — not required to prove this
consumer mechanism works, and not undertaken here to avoid rewriting
`test_matching_api.py`/`test_ride_lifecycle_api.py`'s existing synchronous
assertions for no functional gain this task set out to deliver.

6. What this implements

- `modules/notification/consumer.py`: `NotificationConsumer` class
  (`start()`/`stop()`/`consume_forever()`, mirroring `OutboxPublisher`'s
  own shape) plus a pure, directly-testable `handle_event(envelope: dict,
  *, notification_service, db) -> None` function that the loop calls per
  message — the same "loop wraps a testable unit" separation
  `run_outbox_publisher_loop()`/`publish_pending()` already established.
- `main.py`'s `lifespan()` starts/stops this alongside the existing
  outbox publisher task, with the same "retry Kafka connection forever,
  never block API startup" tolerance `_start_and_run_outbox_publisher()`
  already has.
- New `template_key` string constants (`RIDE_STARTED`, `RIDE_COMPLETED`,
  `RIDE_CANCELLED`, `PENALTY_APPLIED`) — no new `SMS_TEMPLATES` entries
  needed, since all four are IN_APP-only and `NotificationService.send()`
  only renders an SMS template when `channel is Channel.SMS` (unchanged
  from ADR-0034).

7. Consequences

- This is the first real Kafka consumer in the codebase — Phase 15's
  and Phase 18's own long-standing "no consumer exists" gap is now
  partially closed (four events consumed, all four explicitly named as
  Notification's own responsibility in event-contracts.md; the rest is
  exactly Decision 3's deferred list, not a hidden remainder).
- No live Kafka broker exists in this dev environment to run an
  end-to-end smoke test against (confirmed: only `postgres`/`redis`
  containers run locally) — verified instead via a direct unit/
  integration test of `handle_event()` against real Postgres `ride`
  rows (to prove the `ride.started`/`ride.cancelled` customer/driver
  lookup paths, including the "no driver yet" skip case) and fakes for
  the repository/SMS-provider seams, mirroring `test_notification_
  service.py`'s own established testing convention for this domain.
