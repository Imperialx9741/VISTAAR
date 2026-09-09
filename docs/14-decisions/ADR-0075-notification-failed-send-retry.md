ADR-0075 — Notification FAILED-Send Retry

Status: Accepted and implemented (2026-09-04)
Date recorded: 2026-09-04
Deciders: Closes the one gap Phase 15's own audit (earlier the same
day) found and explicitly left unfixed: "a FAILED SMS/PUSH send has no
retry mechanism at all — `mark_failed()` is terminal, there is no
backoff/re-attempt for a transient provider failure." That audit's own
suggested shape — "a bounded fix (e.g. a Celery Beat task retrying
recent FAILED rows once)" — is what this ADR implements, unmodified.

1. Context

`NotificationService.send()` (ADR-0034) creates a `notification.
deliveries` row, dispatches once via the channel's provider, and calls
`mark_failed()` on any exception — terminal, by design, so a single
transient SMS/FCM outage never blocks the caller (ride/router.py,
consumer.py, etc.) that triggered it. Nothing ever revisits a FAILED
row afterward. IN_APP never fails (`send()` marks it SENT
unconditionally, no provider call) — this ADR only ever concerns SMS
and PUSH.

`notification.deliveries` does not persist enough to blindly replay
`send()` a second time: `send()`'s own dedup constraint
(`uq_notification_deliveries_dedup` on `user_id, channel, template_key,
event_id`) means calling it again with the same arguments just returns
the existing FAILED row without re-attempting anything (`send()`'s own
"a dedup hit returned an already-resolved delivery — nothing left to
dispatch" short-circuit). A real retry needs a different entrypoint.

2. Decision

**One new column, one new repository/service method, one new Celery
Beat task — bounded to exactly one retry attempt per delivery, no
open-ended backoff loop.**

- **`notification.deliveries.retry_count SMALLINT NOT NULL DEFAULT 0`**
  (migration, new). The only new state needed: 0 means "never
  retried", 1 means "retried once" — permanently excluded from the
  task's own query after that, whichever way the retry landed. No
  business meaning beyond that boundary; this ADR does not build
  exponential backoff or a configurable retry limit (BR-nothing names
  one, and the audit's own suggested scope was "once").
- **`DeliveryRepository.get_by_id_for_update()`** (new — the Protocol
  had no single-row lookup at all before this, only `list_for_user`/
  `search`) — same `.with_for_update()` pattern
  `TemplateRepository.get_by_id_for_update()` already established in
  this same module.
- **`NotificationService.retry_delivery(delivery_id, *, recipient,
  now)`** — locks the row, no-ops (returns the row unchanged) unless
  `status == FAILED and retry_count == 0`, re-renders the PUBLISHED
  template exactly as `send()` does, re-attempts the SMS/PUSH provider
  call via the same try/except-and-mark shape `send()` uses, then
  always increments `retry_count` to 1 regardless of outcome (a
  successful retry marks SENT + retry_count=1; a failed retry stays
  FAILED + retry_count=1, permanently). `recipient` is supplied by the
  caller, same as `send()` itself already requires for SMS — this
  method still never imports `modules.identity` (domain-design.md's
  module-boundary rule, unchanged).
- **`modules/notification/tasks.py::retry_failed_notifications()`** +
  `retry_failed_notifications_task` (Celery Beat, every 5 minutes —
  same cadence `send-scheduled-broadcasts`/
  `promote-due-scheduled-rides` already use in
  `shared/celery_app.py`, for the same "correct first, not fastest
  possible" reasoning ADR-0054 already established). Scans
  `notification.deliveries` directly (raw SQL, the same style
  `check_expiring_promotions`/`check_expiring_documents` already use in
  this file) for `status = 'FAILED' AND retry_count = 0 AND channel IN
  ('SMS','PUSH')`; for SMS, looks up the current phone number via
  `identity.accounts` (a user's phone can legitimately differ from
  whatever it was at original send time — a retry should use the
  current one, not a stale copy this design deliberately never
  persisted).

3. What this ADR explicitly does not do

- Does not add exponential backoff, a configurable max-retry count, or
  a dead-letter concept for notifications — Phase 18's outbox
  DLQ (ADR-0071) is a different pipeline (event delivery, not
  notification delivery) and is not reused or extended here; a single
  bounded retry is the audit's own stated scope.
- Does not change `send()`'s own behavior, dedup constraint, or
  signature at all.
- Does not retry IN_APP (never fails) or WHATSAPP (no provider exists
  — `send()` raises `ChannelNotAvailableError` before ever creating a
  row, so no WHATSAPP row is ever FAILED in the first place).
- Does not add an admin-facing "retry now" button — out of scope for
  this pass; `search_deliveries()` (already built) already lets an
  admin see a FAILED row's `retry_count`, which is enough to observe
  this working.

4. Verification

Service-level unit tests (fakes, mirroring this module's existing
`test_notification_service.py` conventions): a FAILED SMS delivery
retried once and succeeding marks SENT with retry_count=1; retried once
and failing again stays FAILED with retry_count=1; a delivery already
at retry_count=1 is left untouched by a second call (no double-retry);
a PENDING or SENT delivery is left untouched (nothing to retry). A real
migration upgrade/downgrade round-trip test. Full backend suite run
after — see this task's own completion report for the exact count.
