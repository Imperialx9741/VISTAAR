ADR-0022 — Safety & Support: Minimal Foundation Scope

Status: Accepted
Date recorded: 2026-08-24
Deciders: Approved under the owner's phase-level autonomy grant ("continue"
after Driver Suspension & Reactivation, VISTAAR session, 2026-08-24) — the
roadmap's own mandatory stop conditions (§0.3/§0.4) were checked and
correctly bite for one real piece of this phase (AI Support, Decision 4).

1. Context

Phase 14 (Safety & Support, 11 roadmap tasks) covers two domains:
Safety (domain-design.md §19: `safety.incidents`/`safety.events`,
database-design.md §28) and Support/AI (domain-design.md §21:
`support.cases`/`support.messages`, database-design.md §29-30). Unlike
several earlier phases this session, both have real documented schema,
state machines (state-machines.md §45-46), and — for a genuine subset —
real documented HTTP endpoints: `POST /api/v1/rides/{ride_id}/sos` (§41),
`POST /api/v1/support/cases` and `GET /api/v1/support/cases/{case_id}`
(§44). One endpoint is also documented but out of reach for a real
reason: `POST /api/v1/support/ai/message` (§45, AI Support) needs a real
LLM to produce its `message`/`confidence`/`escalation_required` response
— no provider is named, no credential exists (§0.4).

2. Decision 1 — Build the full domain/service/repository layer for both
   Safety and Support; one additive schema column

`safety.incidents`/`safety.events` and `support.cases`/`support.messages`
built exactly as database-design.md §28-30 documents, with one addition:
`support.cases.ride_id UUID REFERENCES ride.rides(id)` (nullable) — the
documented `POST /api/v1/support/cases` request body includes `ride_id`
(§44), but database-design.md's `support.cases` schema has no column to
store it. Same "additive, non-breaking, clearly justified" extension
already used repeatedly this session (`cab_tier`, `minimum_fare`) — the
request field has an obvious, real use (an agent needs to know which
ride a support case concerns) unlike ADR-0010 Decision 2's
`payment_method` (accepted-but-discarded, because nothing consumes it).
The request body's `message` field becomes the case's first
`support.messages` row, `sender_type`/`sender_id` derived from the
caller's authenticated account — not a separate call the client must
make.

3. Decision 2 — Commands beyond domain-design.md's literal list, where
   the roadmap's 11 tasks and the real schema both require them

domain-design.md §19.3 lists 4 Safety commands (`TriggerSOS`,
`AcknowledgeSOS`, `EscalateSOS`, `ResolveSafetyIncident`) and §21.3 lists
4 Support commands (`AskSupportAI`, `CreateSupportCase`,
`EscalateToHuman`, `ResolveSupportCase`) — narrower than the roadmap's 11
distinct tasks (SOS creation/location/ride context, Safety
workflow/escalation, Support case/assignment/conversation, AI/Human
escalation, Resolve support case) and narrower than what
`support.cases.assigned_admin_id` and `support.messages` clearly need a
real command to populate. Two additions, both non-speculative (the
schema/task list already requires them, not invented business rules):

- `PostSupportMessage` — appends a `support.messages` row. Covers the
  roadmap's "Support conversation" task; not itself a state transition
  (does not change `support.cases.status`).
- `AssignSupportCase` — sets `assigned_admin_id`, OPEN -> ASSIGNED.
  Covers both "Support assignment" and "Human escalation": this
  codebase has no AI actor to escalate *from* (`AskSupportAI` is
  BLOCKED — Decision 4), so the only real "human escalation" path is an
  admin claiming/being assigned the case. Would emit `support.escalated`
  (event-contracts.md §23, payload `{case_id, reason}`, e.g.
  `reason="MANUAL_ASSIGNMENT"` — that event's example reason
  (`"AI_LOW_CONFIDENCE"`) is AI-specific, but the payload shape itself
  is generic enough to cover a non-AI reason too) once a real caller
  exists — see Decision 6: no HTTP endpoint composes this command yet,
  so no outbox row is written for it either, the same "no real caller,
  no invented composition" restraint used throughout this session.

4. Decision 3 — Safety Incident lifecycle mapping (state-machines.md §45)

`OPEN -> ACKNOWLEDGED -> IN_PROGRESS -> RESOLVED -> CLOSED` is documented
as a state list, not paired 1:1 with domain-design.md's 4 commands.
Mapped as: `TriggerSOS` creates OPEN; `AcknowledgeSOS` OPEN ->
ACKNOWLEDGED; `EscalateSOS` ACKNOWLEDGED -> IN_PROGRESS (the closest
sensible reading of "escalating" an incident that's been acknowledged —
moving it into active handling); `ResolveSafetyIncident` IN_PROGRESS ->
RESOLVED. CLOSED has no documented command anywhere and is left
unreached — same "documented state, no command reaches it yet" treatment
already given to `driver.drivers.operational_status = INELIGIBLE`.

5. Decision 4 — AI Support is BLOCKED; not built, not stubbed

`POST /api/v1/support/ai/message` requires a real LLM (technical-
architecture.md names "Groq/OpenAI-compatible LLM" as the intended stack
choice, the same "approved-choice-but-uncredentialed" shape Maps/Mapbox
had for Pricing — ADR-0020 Decision 5) to produce genuine
`message`/`confidence` content — no credential exists in this
environment (checked: `.env.example`, `core/config.py`). Unlike
distance (which has a legitimate non-AI interim substitute, haversine),
there is no non-fabricated substitute for an LLM's natural-language
response — stubbing one would mean returning text that *looks*
AI-generated but isn't, which is actively misleading, not merely
incomplete. `AskSupportAI` and the roadmap's "AI escalation" task
(the AI's own `escalation_required` decision) are both BLOCKED
transitively — neither is built, guessed at, or faked.

6. Decision 5 — No emergency-service integration; `EscalateSOS` never
   places a real call

BR-112: "exact emergency-service integrations are TBD." `EscalateSOS`
only ever transitions `safety.incidents.status` and appends a
`safety.events` row — it never contacts any external service. Same
"internal state transition only, no external call" treatment ADR-0018
gave Advertisement's `verify_advertisement()` (a manual admin decision,
not an Admoto API call).

7. Decision 6 — HTTP surface: exactly the 3 buildable documented
   endpoints; no invented ones for the rest

`POST /api/v1/rides/{ride_id}/sos` (ride-participant-only — the caller
must be that ride's `customer_id` or `driver_id`, IDOR-safe "not found"
otherwise), `POST /api/v1/support/cases`, `GET /api/v1/support/cases/
{case_id}` are implemented. `AcknowledgeSOS`/`EscalateSOS`/
`ResolveSafetyIncident` and `AssignSupportCase`/`PostSupportMessage`/
`ResolveSupportCase` have **no** documented HTTP shape anywhere — same
gap ADR-0018 (Advertisement) and ADR-0021 (Driver Suspend/Reactivate)
already hit. Proven directly by unit + real-Postgres integration tests
instead of inventing an endpoint. Lost and Found (`POST /api/v1/rides/
{ride_id}/lost-item`, `GET /api/v1/lost-items/{case_id}`, BR-113-115,
database-design.md §29.1) is a real, documented, buildable feature but
is not one of Phase 14's 11 listed roadmap tasks — left for whichever
task actually owns it, not silently absorbed into this one.

8. Consequences — documents updated alongside this ADR

- `docs/VISTAAR_IMPLEMENTATION_ROADMAP.md` updated: this task marked
  complete for the scope above.
- No content changed in `business-rules.md`, `domain-design.md`,
  `event-contracts.md`, `state-machines.md`, or `database-design.md`
  beyond the one additive column recorded in Decision 1 — the domain
  built matches what they already specify with nothing contradicted.
