ADR-0010 — Ride Creation (Task 3.1) Scope and Open Items

Status: Decisions 1–5 Accepted (temporary/interim decisions, explicitly
marked as such where the underlying dependency — Pricing, Promotion,
Payment, Matching — does not exist in code yet). Decision 7 Accepted
(schema-authority reconciliation, no business content changed). Item 6
(NO_DRIVER state conflict) — Decision required, NOT decided by this
record, explicitly deferred.
Date recorded: 2026-08-22
Deciders: Approved via the "VISTAAR — Ride Booking / Task 3.1 — Create
Ride Request" planning and decision-resolution exchange, resolving the
ambiguities Task 3.1's initial research plan surfaced before any code
was written, per implementation-readiness.md §74's "if implementation
encounters a genuine unresolved business question: STOP, identify the
exact ambiguity, ask a focused question, record the decision, update
the relevant document, then continue" rule. This record itself
implements no code — see §8.

1. Context

Task 3.1 (Ride Booking — Create Ride Request) is the first task to
touch the Ride Domain. Researching it against api-contracts.md §12,
event-contracts.md §10.1, database-design.md §9, state-machines.md §3–4,
domain-design.md §9, and technical-architecture.md §11–12 surfaced
several genuine gaps between what those documents describe and what
currently exists in the repository:

- api-contracts.md §12's documented server flow for `POST /api/v1/rides`
  is `Validate customer → Validate coordinates → Calculate fare → Apply
  eligible promotion → Create ride → Start matching`, and its response
  schema requires a populated `fare` object. The Pricing module (fare
  formula) is Phase 5 and explicitly TBD (database-design.md §15.1:
  "Exact fare values remain TBD"); the Promotion module is Phase 6; and
  Matching is a separate ride-lifecycle task, deliberately excluded from
  Task 3.1's scope by the task itself. None of the three exist in code.
- The request body's `payment_method` field (e.g. `"ONLINE"`) has no
  corresponding column anywhere in `ride.rides` (database-design.md
  §9.1) or any other documented table, and no enum is defined for it.
- `ride.state_history` (database-design.md §9.2) is stated
  unconditionally ("every authoritative ride-state transition must
  create a history record") but nothing in the repository writes to it
  yet, since no ride-state-changing code has existed before this task.
- `ride.rides` requires `GEOMETRY(Point, 4326)` columns (PostGIS), but
  the dev database has no `postgis` extension installed, and
  `infrastructure/docker/docker-compose.dev.yml` uses plain
  `postgres:16-alpine`, which doesn't bundle PostGIS.
- `POST /api/v1/rides` documents an `Idempotency-Key` header, and
  `shared.idempotency_keys` (database-design.md §35) has a full schema,
  but no module has implemented idempotency-key handling yet.
- No business rule, error code, or state-machine text anywhere
  restricts how many `SEARCHING` rides one customer may have
  simultaneously.
- `domain-design.md` §9.3 and `technical-architecture.md` §12 both list
  a `NO_DRIVER` ride state; `state-machines.md` §3.1 (the authoritative
  state-machine document) does not.
- `technical-architecture.md` §11's `rides` table (flat name,
  `fare_quote_id`/`final_fare` columns) conflicts with
  `database-design.md` §9.1's `ride.rides` (schema-qualified, matching
  every table migrated so far).

2. Decision 1 — Fare: temporary `null`

`POST /api/v1/rides` returns `"fare": null` in Task 3.1's implementation,
in place of the documented `{base, discount, total, currency}` object.
This is an explicitly temporary state, not a schema or contract change:
the target response shape in api-contracts.md §12 is unchanged and
annotated (not rewritten) with this interim behavior. `ride.rides.
active_fare_quote_id` stays `NULL` — no fare formula is invented, and no
`pricing.*` row is created. This will be resolved when the Pricing
module (Phase 5) exists and a follow-up task wires fare calculation into
ride creation.

3. Decision 2 — `payment_method`: accepted, validated, not persisted
   **[Superseded 2026-09-03 — field removed entirely from the API,
   owner decision: no user-facing payment-method selection anywhere in
   the app. See ADR-0025's cross-reference and
   modules/ride/domain/entities.py's own docstring.]**

`payment_method` is accepted in the request body and validated as a
non-empty string (format/presence only — no enum is invented, since none
is documented). It is not written to any table and does not influence
ride creation in any way. Persistence and behavior for this field belong
to the Payment domain, not yet built (Phase 5) — a future task must
decide where it is stored and how it's used, informed by whatever the
Payment domain's actual schema turns out to require.

4. Decision 3 — `ride.state_history`: implemented now

Task 3.1 writes one `ride.state_history` row (`from_status = NULL`,
`to_status = 'SEARCHING'`) in the same database transaction as the
`ride.rides` insert. Unlike fare/promotion/matching, this has no
undelivered dependency — the table is self-contained to the Ride domain,
and database-design.md §9.2's requirement is unconditional, not
phase-gated. `shared.outbox_events`/Kafka publication of `ride.requested`
(event-contracts.md §10.1) remains out of scope for Task 3.1 — no
consumer (Matching, Notification) exists yet to receive it, and building
unused publish infrastructure ahead of a real consumer is deferred to
whichever task first needs one.

5. Decision 4 — PostGIS: added as required infrastructure

PostGIS is added as required infrastructure for Task 3.1, not treated as
a business decision (implementation-readiness.md §75: technical details
that don't affect VISTAAR policy are an engineering choice):

- `infrastructure/docker/docker-compose.dev.yml`'s `postgres` service
  image changes from `postgres:16-alpine` to a PostGIS-enabled image
  (`postgis/postgis:16-3.4`).
- The new ride-domain migration runs `CREATE EXTENSION IF NOT EXISTS
  postgis` before creating `ride.rides`.
- Both the development database and the dedicated test database
  (`vistaar_test_db`, introduced by the Task 2.7B test-isolation
  correction) must be verified to run this migration successfully before
  Task 3.1 is considered complete — the test database is provisioned
  against the same Postgres server/image as the dev database via
  `tests/_integration_db.py`, so the image change covers both once
  confirmed.

6. Decision 5 — Idempotency: `shared.idempotency_keys`, no invented
   duplicate-ride policy

`POST /api/v1/rides` implements the documented `Idempotency-Key`
mechanism against `shared.idempotency_keys` (database-design.md §35): a
repeated request with the same key and the same request body returns the
original response rather than creating a second ride; a repeated key
with a different body is rejected (`IDEMPOTENCY_KEY_REUSE`, already
mapped in `shared/api_envelope.py`). This is the documented mechanism
for retry-safety on this endpoint specifically, and does not extend to —
and must not be read as — a business rule limiting how many distinct
`SEARCHING` rides a customer may have at once. No such rule is
documented anywhere (business-rules.md, PRD.md, and api-contracts.md
§49's error-code list all lack one), and none is invented here. A
customer submitting two genuinely different ride requests gets two
rides; a customer retrying the same request gets the same ride back.

7. Decision 7 — `database-design.md` is the authoritative ride schema

`ride.rides` is implemented exactly as `database-design.md` §9.1
specifies (schema-qualified table name, `original_pickup`/
`current_pickup`/`original_destination`/`current_destination`,
`active_fare_quote_id`, the documented timestamp columns).
`technical-architecture.md` §11–12's earlier flat-table draft (`rides`,
`fare_quote_id`, `final_fare`) is superseded for schema purposes — it
predates the schema-qualified naming convention every other table
(`driver.drivers`, `vehicle.vehicles`, `identity.accounts`, etc.) has
already used since before this task, and `technical-architecture.md` is
not part of the documented conflict-resolution hierarchy
(implementation-readiness.md §2) the way `database-design.md` is. No
business content changes as a result — this is the same kind of filing/
authority reconciliation ADR-0003 already performed elsewhere in this
documentation set, not a new design decision.

Item 6 — NO_DRIVER conflict: explicitly not resolved here

`domain-design.md` §9.3 and `technical-architecture.md` §12 list a
`NO_DRIVER` ride state (with `RETRY`/`FARE_INCREASE` transitions back to
`SEARCHING`, matching business-rules.md BR-031's "no driver accepts"
customer options); `state-machines.md` §3.1 — the authoritative
state-machine document — does not list it at all. Task 3.1 only creates
rides into `SEARCHING`; it never reaches a "no driver accepts" outcome,
so this conflict does not block it. It is recorded here, unresolved, for
whichever future ride-lifecycle/matching task first needs to implement
that outcome — that task must not silently pick a side.

8. Addendum — `vehicle_category` has no column either (found during
   implementation)

While implementing Decision 3–5, re-verifying the exact column list of
`database-design.md` §9.1's `ride.rides` `CREATE TABLE` (not just its
prose description) found that, like `payment_method` (Decision 2),
`vehicle_category` also has no corresponding column anywhere in
`ride.rides` — the table has `id`, `customer_id`, `driver_id`,
`vehicle_id`, `status`, the four geometry columns,
`active_fare_quote_id`, and the documented timestamps, and nothing else.
`event-contracts.md` §10.1's `ride.requested` payload does carry
`vehicle_category`, which is a plausible reason the column doesn't
need to exist on `ride.rides` itself (Matching would read it from the
event, not the ride row) — but Task 3.1 doesn't publish that event
(Decision 3), so there is currently no destination for this value at
all beyond the request itself.

Resolved the same way as Decision 2: `vehicle_category` is required in
the request and validated against the existing `VehicleCategory` enum
(reused from `modules.vehicle.domain.entities`, no new enum), but is not
stored on `ride.rides` and is not added as a new column — adding one
would be inventing schema `database-design.md` doesn't document. The
`Ride` domain entity mirrors `ride.rides`'s actual column list exactly
(matching this codebase's established modeling convention, e.g.
`modules.vehicle.domain.entities.Vehicle`) and therefore has no
`vehicle_category` field. A future task (most likely whichever task
first publishes `ride.requested` and/or builds Matching) must decide
whether `vehicle_category` needs a `ride.rides` column added via a new
migration, or whether flowing it through the event only is sufficient —
not decided here.

9. Consequences — documents updated alongside this ADR

- `api-contracts.md` §12: response example changed to `"fare": null`,
  with a note explaining the temporary state and pointing here;
  `payment_method` annotated as accepted-but-unpersisted.
- `technical-architecture.md` §11: annotated (not rewritten) to mark its
  `rides` table as superseded by `database-design.md` §9.1 for schema
  purposes, pointing here.
- No content changed in `database-design.md`, `domain-design.md`,
  `event-contracts.md`, `state-machines.md`, or `business-rules.md` —
  none of the decisions above require it. `event-contracts.md` §10.1's
  `ride.requested` payload (which includes `fare_quote_id`) remains the
  documented target shape for whenever that event is actually published
  (Decision 3); it is not published by Task 3.1.
- This ADR does not resolve Item 6, and does not implement Pricing,
  Promotion, Matching, or Payment. Those remain separate, later roadmap
  tasks.
