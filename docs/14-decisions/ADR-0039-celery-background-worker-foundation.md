ADR-0039 — Celery Background Worker Foundation

Status: Accepted.
Date recorded: 2026-08-26.
Deciders: Project owner (background-worker technology — "Use Celery for
background workers"), this session, 2026-08-26. Everything else decided
under the owner's phase-level-autonomy grant; the two threshold values
in Decision 3 are real mandatory-stop-adjacent engineering-judgment
calls (roadmap §0.3/§0.4), recorded here rather than guessed past.

1. Context

Phase 01's own roadmap entry named "Background worker foundation" as
its one remaining genuinely blocked task since this session began —
Celery was named as a candidate throughout `docs/VISTAAR_IMPLEMENTATION_
ROADMAP.md` and `docs/VISTAAR_AUTONOMOUS_EXECUTION_PLAN.md` but never
approved (§0.4's "no external/technology adoption without an explicit
decision" gate). The owner has now approved it explicitly. This ADR
records the adoption itself and the first real capability it unblocks:
Phase 18's "Scheduled expiry jobs," and two of the events ADR-0038
deliberately deferred (`PromotionExpiring`, `DocumentExpiring`) for
exactly this reason — "no triggering event exists... would need a
scheduled job."

2. Decision 1 — Celery, Redis as broker/backend, no new infrastructure
   dependency

Redis is already provisioned and wired in (`REDIS_URL`, used today for
rate limiting, matching's geo-index, and OTP rate-limit counters) — using
it as Celery's broker and result backend needs no new infrastructure,
only the `celery` Python package. RabbitMQ (Celery's other common
broker) would be a second message-queue technology this project has no
other use for; Redis is the narrower, already-justified choice. Task
results are not consumed anywhere (every task here is fire-and-forget),
so the result backend is configured but largely unused — kept for
Celery's own required configuration shape, not because anything reads
task results back.

3. Decision 2 — A single combined worker+beat process, not yet a
   scaled pool

Unlike `shared/outbox_publisher.py`'s and `modules/notification/
consumer.py`'s in-process asyncio tasks (ADR-0017/ADR-0038), Celery's
own execution model is a genuinely separate OS process — this is
exactly why the roadmap always treated "Background Worker Foundation"
as a bigger, separate decision from those two, not something to fold
into `main.py`'s lifespan. Run as `celery -A shared.celery_app worker
--beat --loglevel=info` — one process handling both scheduling (Beat)
and execution (the worker pool) — rather than two separate Deployments.
Celery Beat must never run more than one instance (duplicate schedules
would double-fire every periodic task), so this combined process is
also deliberately single-replica for now — `infrastructure/kubernetes/
celery-worker-deployment.yaml`'s own `replicas: 1` is not an oversight.
Splitting Beat and the worker pool into separate, independently-scaled
Deployments is a real future option once task volume justifies it — not
built now, since nothing here needs it yet.

4. Decision 3 — First real scheduled tasks: PromotionExpiring and
   DocumentExpiring, and the two engineering-judgment warning windows
   neither document specifies

`modules/notification/tasks.py` adds two Celery Beat periodic tasks,
both reusing `NotificationService.send()` (ADR-0034) exactly the way
`modules/notification/consumer.py` (ADR-0038) already does for
Kafka-triggered events — the only difference is what triggers the
call: a schedule instead of an event.

- `check_expiring_promotions()`: queries `promotion.entitlements` for
  rows with `status = 'ACTIVE'`, `remaining_uses > 0`, and `expires_at`
  strictly between now and the warning window, notifying each
  `customer_id`. Idempotent the same way ADR-0038's consumer is —
  `NotificationService.send()`'s own `(user_id, channel, template_key,
  event_id)` dedup — but with no Kafka event to supply an `event_id`
  from. Not simply the entitlement's own `id` reused directly: that
  would incorrectly suppress a genuinely new warning if the same
  entitlement is ever renewed to a later `expires_at` and then
  approaches expiry a second time. Instead, `event_id` is a `uuid5`
  deterministically derived from `(entitlement_id, expires_at)` —
  stable across repeated daily runs against the *same* expiry value
  (so it still only warns once per expiry), but distinct if
  `expires_at` ever changes. `notification.deliveries.event_id` carries
  no foreign key to any specific event source, so it's free to serve
  this derived-key role here exactly as it serves as a per-Kafka-event
  one in ADR-0038.
- `check_expiring_documents()`: same shape and same derived-event_id
  scheme, over `driver.documents` and `vehicle.documents`
  (`verification_status = 'APPROVED'`, `expires_at` in the same
  window) — driver documents notify `driver_id` directly; vehicle
  documents look up the owning driver via `vehicle.vehicles.driver_id`
  first (mirroring `modules/notification/consumer.py`'s own `ride.
  started` customer lookup, which has the same shape: the row this
  task scans doesn't carry the recipient's ID directly).

Neither document specifies how far in advance to warn. Chosen as
engineering judgment, not a business value (the same class of decision
ADR-0033 Decision 9 already made this session for the destination-
change route-deviation tolerance): a **3-day** warning window for both,
configurable via `PROMOTION_EXPIRY_WARNING_DAYS`/
`DOCUMENT_EXPIRY_WARNING_DAYS` (`core/config.py`, default `"3"`), and a
**daily** Beat schedule (`crontab(hour=2, minute=0)` — a low-traffic
hour, arbitrary but harmless) for both tasks. Either value is a plain
config change if the owner later wants something different — no
schema/API impact.

5. Decision 4 — What stays deferred, not silently expanded into scope

- `WalletLow` (ADR-0038's third deferred-for-"needs a schedule" item):
  on reflection, this one does NOT actually need a scheduled scan — a
  balance crossing a low-balance threshold is naturally an event at the
  moment of a debit, not something that needs periodic polling. Left
  for a future task to wire reactively at `WalletService.debit()`
  (event-driven, matching ADR-0038's own general preference for
  reacting over polling wherever a real trigger point exists) rather
  than folded into this Celery task set just because Celery is now
  available.
- Payment reconciliation: still blocked on Phase 10 (a real gateway),
  not on the worker technology — Celery being approved does not unblock
  this.
- Event retry backoff / dead-letter handling (event-contracts.md §30):
  still needs the `shared.outbox_events` schema's own attempt-tracking
  columns (ADR-0017 §4) — a separate, already-flagged schema decision,
  not something Celery's existence resolves by itself.
- Scaling the worker pool beyond one combined process: not needed yet
  (see Decision 2).

6. Consequences

- New dependency: `celery` (`apps/backend/pyproject.toml`).
- New module: `shared/celery_app.py` (the Celery application object),
  `modules/notification/tasks.py` (the two periodic tasks).
- New Kubernetes artifact: `infrastructure/kubernetes/celery-worker-
  deployment.yaml` (single-replica combined worker+beat) — written and
  reviewed the same way every other Phase 21 artifact was (ADR-0035),
  not applied against a live cluster.
- Phase 01's background-worker gap and two of Phase 18's "Scheduled
  expiry jobs" are now DONE; `docs/VISTAAR_IMPLEMENTATION_ROADMAP.md`
  and `docs/VISTAAR_AUTONOMOUS_EXECUTION_PLAN.md`'s Phase 01/15/18
  write-ups and ADR-0038's own deferred list are corrected accordingly.
