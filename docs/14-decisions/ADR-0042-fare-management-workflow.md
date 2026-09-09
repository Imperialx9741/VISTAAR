ADR-0042 — Fare Management Workflow (DRAFT → IN_REVIEW → PUBLISHED)

Status: Accepted and implemented (2026-08-26), under the owner's
"continue and complete the whole" authorization to build every
"NEW — SCOPED" item in docs/15-admin-web/admin-web-implementation-plan.md
§4 without a separate per-task confirmation. Recorded before
implementation per this project's own standing "ADR before
implementing a flagged ambiguity" discipline, since this touches an
existing column's meaning on a table read by the live fare-calculation
path (`PricingService.calculate_fare()`), not a purely additive change.

Date recorded: 2026-08-26.

1. Context

`pricing.fare_rules` (database-design.md §15.1) has existed since
ADR-0020 with `active BOOLEAN`, `effective_from`, `effective_until` —
but no admin write path has ever existed for it: the only five rows
that exist were seeded directly by migration 61a5a80a044e, and the only
application code that touches this table is
`FareRuleRepository.get_active_by_category()`, a pure read filtered on
`active = TRUE AND effective_from <= now() AND (effective_until IS
NULL OR effective_until > now())`.

The Admin Web plan (§4.8) asks for a DRAFT → IN_REVIEW → PUBLISHED
authoring workflow — the same "never rewrite historical pricing"
principle Fare Management is stated to require, which this codebase
already honors for `fare_quotes` (a quote freezes its values at
creation) but has never had to honor for `fare_rules` itself, since
nothing has ever edited a rule after its initial seed.

2. Decision 1 — Replace `active` with `status`, not add `status`
   alongside it

```
ALTER TABLE pricing.fare_rules
    ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'DRAFT';
    -- DRAFT | IN_REVIEW | PUBLISHED

UPDATE pricing.fare_rules
    SET status = 'PUBLISHED' WHERE active = TRUE;
    -- rows already active=FALSE stay DRAFT — none exist today
    -- (the seed migration set every row active=TRUE), but the
    -- backfill is written to be correct if that ever changes before
    -- this migration runs.

ALTER TABLE pricing.fare_rules DROP COLUMN active;
```

Rejected alternative: keep `active` as a second, independently-set
column alongside `status`. Two boolean-ish signals for "is this rule
live" is exactly the "don't conflate two real concepts into one table"
problem in reverse — here it would be one concept (liveness) split
across two columns that could disagree. The plan's own proposal already
called for `active` to become "derived... not stored independently" —
this ADR implements that literally: the query computes liveness from
`status='PUBLISHED' AND effective_from <= now() AND (effective_until
IS NULL OR effective_until > now())` directly, and no `active` column
exists to fall out of sync.

Blast radius confirmed narrow before making this change: exactly two
call sites read `FareRule.active` (repositories.py's `_fare_rule_from_
orm()` and `get_active_by_category()`'s own WHERE clause) and one test
helper (`tests/test_pricing_service.py::_rule()`) sets it — no other
module or test touches this field.

3. Decision 2 — Publish closes out the previously-published rule for
   the same category

Creating a new PUBLISHED rule for a category that already has one live
must not leave two simultaneously "active" rows (the query's `ORDER BY
effective_from DESC LIMIT 1` would silently pick one, masking the
overlap instead of preventing it). `PublishFareRule` therefore:

1. Locks (SELECT ... FOR UPDATE) the current PUBLISHED-and-live rule
   for this rule's `vehicle_category`, if one exists.
2. Sets that prior rule's `effective_until` to the new rule's
   `effective_from`.
3. Sets the new rule's `status = 'PUBLISHED'`.

`effective_from` is supplied by the caller at publish time (defaulting
to "now" if omitted) — the plan's own "Publish (sets `effective_from`,
status=PUBLISHED)" phrasing is read as "this is the action that
finally pins down `effective_from`," not "it can only ever be now,"
since a real fare-change rollout (e.g. "effective next Monday
00:00 IST") is a legitimate, unremarkable admin need and nothing in
the plan forecloses it. `effective_from` stays NULL on a DRAFT/
IN_REVIEW row — a rule's live-from moment is not decided until
Publish.

4. Decision 3 — Only the transitions the plan actually names are built

Create (DRAFT) → Submit for Review (DRAFT → IN_REVIEW) → Publish
(IN_REVIEW → PUBLISHED, or DRAFT → PUBLISHED directly — the plan does
not say Submit for Review is mandatory before Publish, only that it
exists as a step, so both a reviewed and an unreviewed draft may be
published; nothing gates Publish on having passed through IN_REVIEW
first). No Edit-while-DRAFT, no Reject/return-to-DRAFT, no Unpublish —
none of these are named in the plan's own §4.8 table, so none are
built. An admin who drafted a rule with a mistake creates a new draft
instead; the old one is simply never published.

5. Decision 4 — List Fare Rules returns every status, not just
   PUBLISHED

The plan's own screen name is "List fare rules (by vehicle category,
with version history)" — version history necessarily includes past
(superseded) and in-progress (DRAFT/IN_REVIEW) rows, not only the
currently-live one. `status` is available as an optional filter for a
caller that wants only one stage.

6. What this does NOT resolve

- Platform fee (a separate, currently-hardcoded dict in
  `matching/router.py`) — the plan itself flags this as NEW — NEEDS
  SCOPING (a real schema addition beyond fare_rules) and stays exactly
  that; this ADR does not touch it.
- "Free waiting" (`free_waiting_minutes`) — the plan notes this as an
  additive, non-blocking future field; not added here since nothing
  requested it be part of this pass.

7. Implementation note (2026-08-26)

Built as designed. Migration `d9a2976f73d9` (revises `92cda537e9c7`)
adds `status`, backfills it from `active`, drops `active`, and relaxes
`effective_from` to nullable — verified `upgrade head` / `downgrade -1`
/ re-`upgrade head` on both the dev and test databases.

One real bug caught by the integration tests, not by inspection: the
migration's first version added the `status` column and dropped
`active` but never relaxed `effective_from`'s NOT NULL constraint,
even though the domain entity/ORM model were already written treating
it as nullable (`effective_from: datetime | None`). Every `POST
/api/v1/admin/fare-rules` call (Create Draft, which never supplies
`effective_from`) failed with a `NotNullViolation` at the database
layer — caught the first time these endpoints' real-Postgres tests
actually ran (not on the first attempt, which only exercised in-memory
fakes and passed cleanly, hiding the gap). Fixed by downgrading,
amending the same migration to add `op.alter_column(...,
nullable=True)`, and re-verifying the full upgrade/downgrade/upgrade
cycle on both databases before re-running the failing tests — a schema
migration and the application code built against it must be verified
together, not just each in isolation.

Full suite passed after the fix (1046 passed, 5 skipped — Kafka-only),
ruff and mypy clean.
