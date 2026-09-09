"""VISTAAR Safety module — Phase 14 (Safety & Support).

Owns `safety.incidents`/`events`, per docs/04-database/database-design.md
§28, implementing domain-design.md §19.3's four commands (TriggerSOS,
AcknowledgeSOS, EscalateSOS, ResolveSafetyIncident).

See docs/14-decisions/ADR-0022-safety-and-support-foundation-scope.md for
the full scope reasoning. This module deliberately does NOT:

- Contact any real emergency service. BR-112: "the exact emergency-
  service integrations are TBD." `escalate_incident()` only transitions
  `safety.incidents.status` and appends a `safety.events` row — it never
  places a call anywhere. Same "internal state transition only, no
  external call" treatment ADR-0018 gave Advertisement's
  `verify_advertisement()`.
- Implement `POST /api/v1/rides/{ride_id}/sos`'s Acknowledge/Escalate/
  Resolve as literal HTTP endpoints. api-contracts.md documents only the
  one SOS-creation endpoint — no shape exists anywhere for the other
  three commands, the same gap ADR-0018 (Advertisement) and ADR-0021
  (Driver Suspend/Reactivate) already hit. Proven directly by unit +
  real-Postgres integration tests instead.
- Reach `IncidentStatus.CLOSED`. Documented in state-machines.md §45's
  state list, but no command anywhere transitions an incident into it —
  same "documented state, no command yet" treatment already given to
  `driver.drivers.operational_status = INELIGIBLE`.

What it does do:

- `trigger_sos()`: composed into `POST /api/v1/rides/{ride_id}/sos`
  (modules/safety/router.py), which also establishes ride participation
  (caller must be that ride's customer or driver) — the one place this
  module imports `modules.ride`, at the router/composition layer only.
- `acknowledge_incident()`/`escalate_incident()`/`resolve_incident()`:
  row-locked (`get_by_id_for_update()`, same mechanism as
  `DriverService.go_online()`), each appending an audit-trail
  `safety.events` row alongside the status transition. `trigger_sos()`
  publishes `safety.sos_triggered` (event-contracts.md §21.1, exact
  documented payload) via the outbox, composed from the one real router
  call site. `resolve_incident()`'s documented `safety.incident_resolved`
  payload (§21.2) is NOT published anywhere yet — there is no router
  composing `resolve_incident()` (Decision 6 above), so there is no live
  call site to compose the outbox write into either; the same "no real
  caller, no invented composition" restraint this session has used
  throughout.

Layering mirrors modules/pricing/ and modules/promotion/:

    domain/         pure business logic — no FastAPI/SQLAlchemy imports
    ports.py        SafetyIncidentRepository, SafetyEventRepository
                    Protocols
    models.py       SQLAlchemy ORM models for the two tables
    repositories.py SQLAlchemy-backed implementations of the ports above
    service.py      application service (use cases): SafetyService
    dependencies.py FastAPI DI wiring
    schemas.py      SosRequest (POST .../sos is the only endpoint here
                    with a request body)
    router.py       POST /api/v1/rides/{ride_id}/sos (api-contracts.md §41)
"""
