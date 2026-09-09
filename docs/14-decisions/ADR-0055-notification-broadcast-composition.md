ADR-0055 — Notification Compose/Send Broadcast + Audience Selection
(Tier C)

Status: Accepted and implemented (2026-08-29) — owner decision, choosing
Tier C of the three scoping options presented in this ADR's own
preceding scoping report (2026-08-29). Resolves Admin Web §4.12's last
three open rows (Compose/send broadcast, Schedule a broadcast, Audience
selection), the only item left anywhere in the Admin Web implementation
plan's original scope without a resolved decision.

Date recorded: 2026-08-29.
Deciders: Project owner (explicit written decision, 2026-08-29, "Tier C
(Recommended)").

1. Context

See §1 of this ADR's own preceding scoping report (preserved below,
unchanged) for the full inspection this decision was based on.

`NotificationService.send()` (`modules/notification/service.py`) takes
exactly one `user_id`, one `channel`, and one `template_key` — it
dispatches to a single recipient using either a PUBLISHED
`notification.templates` row (ADR-0044) or, failing that, the old
hardcoded `SMS_TEMPLATES` fallback. Nothing accepted an admin-typed
message body at send time, and nothing looped it over more than one
recipient, before this ADR.

`notification.templates` (ADR-0044) already had a nullable `event_key`
column, and that migration's own comment said it existed "for manual/
admin-broadcast use only, not tied to an automatic trigger" — Templates
was deliberately built to also hold broadcast *content*, but ADR-0044
itself was explicit that Templates "makes message content editable, it
doesn't add ad hoc composition." This ADR is that missing trigger.

`shared/geo.py`'s GEO sets store `driver_id` as the member of each
`geo:drivers:{category}` set — so an "online drivers" audience is
resolvable to real driver ids via a new `list_online_driver_ids()`, not
just a count.

`modules/notification/tasks.py` (ADR-0039) already established the
fan-out-and-call-`send()`-per-row pattern this feature reuses.

2. Decision 1 — Composition reuses Templates, doesn't duplicate it

Rather than inventing a second content-storage mechanism, a broadcast's
free-text `subject`/`body` is published as a one-off Template at
creation time — `template_key = f"BROADCAST_{uuid4().hex}"`,
`event_key=None` (exactly the "manual/admin-broadcast use only" case
ADR-0044's own schema comment anticipated), created and immediately
published in the same request. Every recipient's actual send then goes
through `NotificationService.send()` unchanged, using that
template_key — so a broadcast's `Delivery` rows are indistinguishable
in kind from any other admin-triggered notification, and get the same
`template_version_id` provenance stamp for free. The admin never sees
this template — it exists only as `send()`'s existing content-resolution
mechanism, reused rather than duplicated.

```
CREATE TABLE notification.broadcasts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel VARCHAR(20) NOT NULL,          -- IN_APP | SMS | PUSH
    template_key VARCHAR(50) NOT NULL,     -- the auto-published Template's key
    subject VARCHAR(200),
    body TEXT NOT NULL,
    audience_type VARCHAR(30) NOT NULL,    -- ALL_CUSTOMERS | ALL_DRIVERS |
                                            -- ONLINE_DRIVERS | SELECTED
    audience_user_ids JSONB,               -- only for SELECTED
    status VARCHAR(20) NOT NULL DEFAULT 'SCHEDULED',  -- SCHEDULED | SENT
    scheduled_at TIMESTAMPTZ,              -- NULL = send now
    sent_count INT NOT NULL DEFAULT 0,
    failed_count INT NOT NULL DEFAULT 0,
    created_by UUID NOT NULL REFERENCES admin.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ
);
```

No FAILED status at the broadcast level — an individual recipient's
send failing (bad phone, no device token, provider error) is tracked
per-recipient in `failed_count`, not treated as the whole broadcast
failing. `status` starts SCHEDULED even for an immediate broadcast (a
NULL/past `scheduled_at`) — the same request that inserts the row
dispatches and flips it to SENT before returning, so a row a later
request still finds SCHEDULED only ever means a genuinely future-dated
one still awaiting its `scheduled_at`.

3. Decision 2 — Endpoints

```
POST /api/v1/admin/notifications/broadcasts
{"channel", "subject"?, "body", "audience_type",
 "audience_user_ids"? (required iff SELECTED), "scheduled_at"?}

GET /api/v1/admin/notifications/broadcasts?status=&page=&page_size=
GET /api/v1/admin/notifications/broadcasts/{broadcast_id}
```

`POST` requires `MANAGE` on `AdminModule.NOTIFICATIONS` — the same bar
Template create/publish already sets, not `VIEW`, since this sends real
messages to real users. `GET` (both) require `VIEW`. Every send is
audited (`admin.audit_logs`) with the audience type, resolved recipient
*counts* (sent/failed, not the full id list — keeps the audit row
bounded even for an "all customers"-sized audience), channel, and
status.

When `scheduled_at` is omitted or already in the past, the endpoint
resolves the audience and dispatches synchronously, in-request, before
returning — the response already reflects `status=SENT` and real
`sent_count`/`failed_count`. This runs inline rather than through a
queued job for the immediate case; a very large synchronous audience
(e.g. "all customers" at real production scale) is a known, explicitly
accepted tradeoff of this build, not a silently ignored one — see §6.

4. Decision 3 — Audience resolution (always fresh, always server-side)

| Audience type | Resolution |
| :--- | :--- |
| ALL_CUSTOMERS | Every `customer.customers` row (`CustomerService.list_all_customer_ids()`, new) |
| ALL_DRIVERS | Every `driver.drivers` row (`DriverService.list_all_driver_ids()`, new) |
| ONLINE_DRIVERS | `geo:drivers:{category}` GEO set members, every category (`geo.list_online_driver_ids()`, new) |
| SELECTED | The explicit id list the admin typed/pasted, one per line or comma-separated (same textarea precedent Offers/Coupons' own `eligible_customer_ids` already established) |

Resolution happens in a new shared module,
`modules/notification/broadcast_dispatch.py` (`resolve_audience()` +
`dispatch_broadcast()`), used identically by both the immediate-send
path (the POST handler above) and the scheduled path (Decision 5) — so
a scheduled broadcast's audience is resolved fresh at its actual send
time, never snapshotted at compose time. Membership of
ALL_CUSTOMERS/ALL_DRIVERS/ONLINE_DRIVERS can genuinely change between
when a scheduled broadcast is created and when it fires; only
SELECTED's id list is fixed at compose time, by definition.

5. Decision 4 — SMS phone resolution

For an SMS broadcast, each recipient's `customer_id`/`driver_id` IS
`identity.accounts.id` (the same shared-primary-key relationship
Customer Detail's own composition already relies on) — `dispatch_
broadcast()` resolves the phone via `AccountRepository.get_by_id()`
per recipient before calling `send()`. A missing account is counted as
failed, not treated as aborting the whole broadcast.

6. Decision 5 — Scheduling

A future `scheduled_at` leaves the broadcast row `SCHEDULED`. A new
Celery Beat task (`modules/notification/tasks.py`'s `send_scheduled_
broadcasts`/`send_scheduled_broadcasts_task`, registered in `shared/
celery_app.py` at `crontab(minute="*/5")` — a 5-minute poll, not the
once-daily cadence the two pre-existing expiry-check tasks use, since a
scheduled broadcast names a specific time an admin actually chose)
polls `BroadcastRepository.list_due()` (`status='SCHEDULED' AND
scheduled_at <= now`) and dispatches each exactly the same way the
immediate path does, via the same `dispatch_broadcast()`.

7. What this does NOT resolve

- A real Firebase/FCM credential — external dependency, ADR-0052 §5,
  unaffected.
- WhatsApp BSP selection — owner-reserved separately; WHATSAPP is
  rejected outright at the API layer for a broadcast (`VALIDATION_
  FAILED`), same as `NotificationService.send()` already does.
- Large-audience async/queued dispatch for the immediate-send path —
  an "all customers"-sized broadcast currently dispatches synchronously
  in one HTTP request. This is a known, accepted scope limitation of
  this build (not silently punted): the scheduled path already proves
  out background dispatch via Celery, so moving the immediate path onto
  the same mechanism is a small, well-understood follow-up if request
  latency at real production scale ever becomes a problem — not
  invented speculatively here.
- Any change to `NotificationService.send()`'s single-recipient
  signature — the fan-out lives one layer above it, in `broadcast_
  dispatch.py`, exactly as originally scoped.

8. Tests

Backend: unit tests for `Broadcast.new()`'s domain validation and
`NotificationService.create_broadcast()`/`search_broadcasts()`/`mark_
broadcast_sent()` against a fake repository (`test_notification_
service.py`); unit tests for `resolve_audience()`/`dispatch_broadcast()`
against fakes, including a one-bad-recipient-does-not-abort-the-rest
case (`test_broadcast_dispatch.py`); real-Postgres/real-Redis
integration tests for all three endpoints, including permission
enforcement (VIEW cannot POST) and a real ONLINE_DRIVERS audience
(`test_admin_api.py`); real-Postgres integration tests for the
scheduled-dispatch Celery task, using this codebase's own truncated-
table fixture for exact ALL_CUSTOMERS/ALL_DRIVERS count assertions
(`test_notification_tasks.py`). Frontend: a compose form (audience-type-
conditional recipient textarea, schedule field) and a broadcast list +
detail screen, each with loading/empty/error/permission-denied
coverage.

9. Consequences — documents updated alongside this ADR

- `docs/04-database/database-design.md` §32.5: `notification.
  broadcasts`, documented.
- `docs/05-api/api-contracts.md` §46.21: the three new endpoint shapes,
  implemented.
- `docs/15-admin-web/admin-web-implementation-plan.md` §4.12 and §10:
  Compose/Send Broadcast, Schedule a broadcast, and Audience selection
  move from NEW — NEEDS SCOPING to IMPLEMENTED — the last open item
  anywhere in this plan's original scope.
- `docs/VISTAAR_IMPLEMENTATION_ROADMAP.md`: dated narrative entry for
  this build.

---

Appendix — the preceding scoping report (2026-08-29, unchanged, kept
for the record of what was inspected before this decision)

Three tiers were presented:

- Tier A — Trigger an existing published Template at an audience, no
  free text. Weakest fit to "compose" — an admin still has to create/
  publish a Template first, in a separate screen.
- Tier B — Tier A + true one-off free-text composition (its own
  `subject`/`body`, no Template/version history required).
- Tier C — Tier B + scheduling (`scheduled_at` + a periodic dispatch
  task). Chosen: closes out all three open plan rows (Compose,
  Schedule, Audience) in one pass, reusing every mechanism already
  inspected (Templates, Celery, the Redis GEO index) with no new
  abstraction invented.

Audience resolution mechanics, security/RBAC posture, and the required
test list presented in the original scoping report match Decisions 3-8
above exactly — nothing changed between the proposal and what was
built.
