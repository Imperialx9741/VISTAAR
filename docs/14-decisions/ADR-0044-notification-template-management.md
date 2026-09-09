ADR-0044 — Notification Template Management

Status: Accepted and implemented (2026-08-26) — owner decision #2 of the
2026-08-26 "approved product decisions" batch, recorded design-only per
the owner's "DO NOT IMPLEMENT RUNTIME CODE YET" instruction on that
batch, then implemented the same day under the owner's subsequent
broader authorization to build everything not blocked on an external
credential.

Date recorded: 2026-08-26.
Deciders: Project owner (explicit written decision, 2026-08-26).

1. Context

`modules/notification/domain/templates.py`'s `SMS_TEMPLATES` dict is
today's entire template store: two hardcoded strings
(`RIDE_ACCEPTED`, `RIDE_ARRIVED`), SMS-only, no admin visibility, no
version history — explicitly documented there as "flat, static
placeholder copy... a future task's job, not this one's" (ADR-0034
Decision 4). `NotificationService.send()` takes a `template_key` and
renders it via `render_sms()`; no other channel has any template
content at all. The Admin Web plan's own §4.12 flagged turning this
into a real DB-editable system as "NEEDS SCOPING (a real schema
addition)" — this ADR is that scoping.

2. Decision 1 — `notification.templates`: append-only version chain
   per (template_key, channel), not effective-dated windows

Unlike Fare Management/Platform Fees/Referral Rewards, the owner's own
requirement list for this feature says "draft/publish" (two states),
not "draft/review/publish" — and asks for "version history," not
"effective dating." Templates don't need a *scheduled future rollout*
the way a fare or fee change does; they need "what did version 3 say,
and when did it become the live one."

```
CREATE TABLE notification.templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_key VARCHAR(50) NOT NULL,   -- logical identity, e.g. 'RIDE_ACCEPTED'
                                          -- (today's SMS_TEMPLATES keys, extended
                                          -- to every channel)
    channel VARCHAR(20) NOT NULL,        -- IN_APP | SMS | PUSH | WHATSAPP
    event_key VARCHAR(50),               -- which domain event this template is
                                          -- for (nullable — a template may exist
                                          -- for manual/admin-broadcast use only,
                                          -- not tied to an automatic trigger)
    title VARCHAR(200),                  -- nullable (SMS has no title; PUSH/IN_APP may)
    body TEXT NOT NULL,
    version INT NOT NULL,                -- 1, 2, 3... per (template_key, channel)
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',  -- DRAFT | PUBLISHED
    created_by UUID NOT NULL REFERENCES admin.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_notification_templates_one_published
ON notification.templates (template_key, channel)
WHERE status = 'PUBLISHED';
```

Editing an existing template creates a *new row* (`version = previous
+ 1`, `status = 'DRAFT'`) rather than mutating one in place — the
version chain itself IS the version history the owner asked for; no
separate history table is needed. Publishing a new version
automatically un-publishes (not deletes) the prior PUBLISHED row for
that `(template_key, channel)` — same partial-unique-index technique,
enforced application-side (set the old row's status back to a
non-PUBLISHED terminal state, e.g. `ARCHIVED`, in the same transaction
that publishes the new one; the partial unique index is the safety net
against a race, not the primary mechanism).

3. Decision 2 — `notification.deliveries` gains one additive column:
   which template *version* was actually used

"Published template used for future notifications; historical sent
notifications remain unchanged" only holds if a `Delivery` row can
prove, after the fact, exactly what was rendered — today `deliveries`
stores only `template_key` (a stable logical name), and if that
name's content is later edited, nothing on the delivery row would
distinguish "sent under the old wording" from "sent under the new
wording." Additive, nullable column:

```
ALTER TABLE notification.deliveries
    ADD COLUMN template_version_id UUID REFERENCES notification.templates(id);
```

NULL for every row created before this ships (a real gap in
after-the-fact auditability for that historical data — accepted, not
backfillable, since the exact wording sent for those rows was never
captured anywhere to begin with). `NotificationService.send()` looks
up the currently-PUBLISHED template for `(template_key, channel)`,
renders its `body` (still no variable-substitution/templating engine —
none is requested here and none is invented), and stamps
`template_version_id` on the created `Delivery` row. This is the same
"copy at the moment of the event, never read live again" principle
ADR-0041 §6.1 and ADR-0043 §3 both already apply to their own domains.

Resolved during implementation (2026-08-26), amending this Decision:
the old static `SMS_TEMPLATES` Python dict (ADR-0034 Decision 4) is
NOT deleted. It remains in `modules/notification/domain/templates.py`
as a last-resort fallback — used only when no PUBLISHED
`notification.templates` row exists yet for a given `(template_key,
channel)` — for the same two reasons ADR-0043 §4 already gave its own
old hardcoded constants: (1) production race-safety, so `send()` never
hard-fails just because nobody has published a template for a key yet;
(2) this codebase's aggressive integration-test cleanup
(`tests/_integration_db.py`'s `truncate_integration_tables()`, used by
several notification/driver/vehicle-document/verification test files)
wipes `notification.templates` mid-session, and the seeding migration
only runs once per test session — without a fallback, any test file
that runs after a cleanup would silently lose SMS rendering for
`RIDE_ACCEPTED`/`RIDE_ARRIVED`. The migration still seeds one PUBLISHED
version-1 row per template so nothing changes for the common case; the
fallback exists only for the gap between "no PUBLISHED row" and
"someone commits to reseeding it."

4. Decision 3 — No provider secrets anywhere in this feature

The owner's explicit constraint: "Do not expose provider secrets in
the Admin UI." Nothing in `notification.templates` needs to — this
table only ever stores message *content* (title/body/channel/event
association), never credentials. MSG91/Firebase/WhatsApp-BSP
credentials already live exclusively in environment configuration
(`core/config.py`) and are never read by, returned from, or editable
through any admin endpoint this ADR proposes. Documented here
explicitly so the implementing task treats it as a hard boundary, not
an oversight to catch in review.

5. Decision 4 — Admin endpoints

```
POST /api/v1/admin/notifications/templates                    Create Draft (version 1, or next version of an existing template_key+channel)
GET  /api/v1/admin/notifications/templates?template_key=&channel=&status=   List (version history)
GET  /api/v1/admin/notifications/templates/{id}                 Get one version
POST /api/v1/admin/notifications/templates/{id}/publish         DRAFT -> PUBLISHED (archives the prior PUBLISHED version, if any)
```

Permission key `NOTIFICATIONS` (already exists, ADR-0040). Every
mutation audited. No Edit-in-place — "edit" is always "create a new
DRAFT version," matching Fare Management's own "no edit-while-DRAFT
mutation of a terminal concept" discipline in spirit, and directly
serving "historical sent notifications remain unchanged" by
construction (there is nothing to mutate that a past delivery could
have pointed to).

6. What this does NOT resolve

- No variable substitution / localization — `render_sms()`'s
  replacement is still a flat string lookup, now DB-backed instead of
  a Python dict; templating is a separate, unrequested feature.
- Compose/Send Broadcast, Audience Selection, and device-token
  registration remain exactly as NEEDS SCOPING as api-contracts.md
  §46.10 already documented — this ADR makes template *content*
  editable, it does not add a way to send an ad hoc admin-composed
  message (there is still no column anywhere for that, and the owner's
  decision batch did not revisit it).
