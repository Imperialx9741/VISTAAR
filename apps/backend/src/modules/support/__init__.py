"""VISTAAR Support module — Phase 14 (Safety & Support).

Owns `support.cases`/`messages`, per docs/04-database/database-design.md
§30 (plus one additive column — see below), implementing domain-design.md
§21.3's CreateSupportCase/ResolveSupportCase plus two additions ADR-0022
records.

See docs/14-decisions/ADR-0022-safety-and-support-foundation-scope.md for
the full scope reasoning. Also, since Phase 13 (ADR-0029, 2026-08-25):
`create_case()` is how both documented dispute concepts (BR-121's
ride-fare disputes, domain-design.md §17.3's DisputePenalty) are filed —
`category: "RIDE_FARE_DISPUTE"` / `"PENALTY_DISPUTE"`, plain conventions
on this already-generic column, no new column/table/endpoint added here.
A penalty dispute is decided via modules.penalty's own already-existing
`resolve_penalty()` (`action: "WAIVE"`), not by this module.

This module deliberately does NOT:

- Implement `AskSupportAI` / `POST /api/v1/support/ai/message`. Needs a
  real LLM (technical-architecture.md names "Groq/OpenAI-compatible
  LLM" as the intended stack) to produce a genuine `message`/
  `confidence` response — no provider is configured anywhere in this
  environment (§0.4). Unlike Pricing's distance calculation (which has a
  legitimate non-AI interim substitute, haversine — ADR-0020 Decision 5),
  there is no non-fabricated substitute for an LLM's natural-language
  output; stubbing one would mean returning text that *looks*
  AI-generated but isn't. The roadmap's "AI escalation" task is
  transitively blocked the same way — nothing computes an
  `escalation_required` decision without a real AI call to decide it.
- Implement Assign/Resolve/PostMessage as literal HTTP endpoints.
  api-contracts.md documents only Create/Get Support Case — no shape
  exists anywhere for the other three commands, the same gap ADR-0018
  (Advertisement) and ADR-0021 (Driver Suspend/Reactivate) already hit.
  Proven directly by unit + real-Postgres integration tests instead.
- Reach `CaseStatus.IN_PROGRESS`/`WAITING_FOR_USER`/`CLOSED`. All three
  are documented in state-machines.md §46's state list, but no command
  anywhere transitions a case into them — same "documented state, no
  command yet" treatment already given to
  `modules.safety.domain.entities.IncidentStatus.CLOSED`.

What it does do:

- `create_case()`: composed into `POST /api/v1/support/cases`
  (modules/support/router.py). The documented request's `message` field
  becomes the case's first `support.messages` row automatically — the
  client does not make a separate call for it.
- `post_message()`: appends further `support.messages` rows ("Support
  conversation") without changing case status.
- `assign_case()`: OPEN -> ASSIGNED, sets `assigned_admin_id`. Covers
  both the roadmap's "Support assignment" and "Human escalation" tasks —
  this codebase has no AI actor to escalate *from* (AskSupportAI is
  BLOCKED above), so an admin claiming the case *is* the human
  escalation. `support.escalated`'s documented payload (event-
  contracts.md §23, `{case_id, reason}`) is NOT published anywhere yet —
  there is no router composing `assign_case()` (Decision 6 above), so
  there is no live call site to compose the outbox write into either;
  the same "no real caller, no invented composition" restraint this
  session has used throughout.
- `resolve_case()`: valid from any status except already
  RESOLVED/CLOSED.
- `get_case_with_messages()`: composed into `GET /api/v1/support/cases/
  {case_id}` — an admin may view any case; a customer/driver only their
  own.

`support.cases.ride_id` (additive beyond database-design.md §30.1 — see
ADR-0022 Decision 1) exists because api-contracts.md §44's documented
request body includes `ride_id` with nowhere in the original schema to
store it.

Layering mirrors modules/safety/:

    domain/         pure business logic — no FastAPI/SQLAlchemy imports
    ports.py        SupportCaseRepository, SupportMessageRepository
                    Protocols
    models.py       SQLAlchemy ORM models for the two tables
    repositories.py SQLAlchemy-backed implementations of the ports above
    service.py      application service (use cases): SupportService
    dependencies.py FastAPI DI wiring
    schemas.py      CreateSupportCaseBody
    router.py       POST /api/v1/support/cases,
                    GET /api/v1/support/cases/{case_id}
                    (api-contracts.md §44)
"""
