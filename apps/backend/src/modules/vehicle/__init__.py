"""VISTAAR Vehicle module — Vehicle Management (Phase 2 / Task 2.4).

Owns vehicle records for drivers, per
docs/04-domain-design/domain-design.md §8 (Vehicle Domain) and
docs/04-database/database-design.md §8.1 (vehicle.vehicles).

Implements exactly the four endpoints
docs/05-api/api-contracts.md §11 documents — no more, no less:

    POST   /api/v1/drivers/me/vehicles              Add Vehicle
    GET    /api/v1/drivers/me/vehicles               List Vehicles
    POST   /api/v1/drivers/me/vehicles/{id}/activate    Activate Vehicle
    POST   /api/v1/drivers/me/vehicles/{id}/deactivate  Deactivate Vehicle

Notably, api-contracts.md §11 does NOT document a "get single vehicle"
endpoint or an "update vehicle fields" (PATCH) endpoint, even though this
task's brief mentions "update permitted vehicle information" as a
conceptual goal. Per that same brief's instruction to follow the
documented contract exactly rather than the illustrative route list, no
PATCH/GET-single endpoint is implemented here — flagged explicitly in
this task's final report rather than silently added or silently skipped.

vehicle.documents (database-design.md §8.2) was added in Phase 2 / Task
2.5 at the domain/service/repository layer only — no HTTP endpoint is
documented anywhere for it (see
docs/14-decisions/ADR-0007-document-type-and-endpoint-scope.md), so none
is exposed. VehicleDocumentService trusts its caller to have already
established vehicle ownership (e.g. via VehicleService.get_vehicle())
before use — see service.py.

Explicitly out of scope for this task (do not extend this module to
cover these without a new task):

- Any vehicle-document HTTP endpoint (POST/GET) — not documented
  anywhere; see ADR-0007.
- Document verification/approval, a canonical document_type enum, and
  document replacement/versioning — see ADR-0007. No OCR/AI, no
  government verification APIs, no object-storage integration
  (evidence_uri is opaque metadata only), no expiry scheduling.
- ApproveVehicle/RejectVehicle (domain-design.md §8.3 — an Admin-domain
  workflow, not this task's).
- Kafka publishing of vehicle.approved/vehicle.activated/
  vehicle.deactivated, even though — unlike Identity/Customer/Driver's
  events — event-contracts.md §20 already defines payloads for these.
  Publishing them is still out of scope per this task's explicit "Do not
  create vehicle Kafka topics/producers/consumers" instruction; the
  existing contract is simply a more ready foundation for whenever that
  work happens.
- Ride/matching eligibility computation (a vehicle being APPROVED+ACTIVE
  is a precondition for matching per domain-design.md §8.4, but actually
  using that for matching belongs to the Matching domain, not here).

Driver-offline enforcement (BR-102 / api-contracts.md §11's "Vehicle
switching is not allowed while ONLINE or ON_RIDE") reads
driver.drivers.operational_status — the field Task 2.3 already created —
rather than inventing a second, duplicate availability mechanism. See
router.py for how this is composed across the driver and vehicle modules
without either module importing the other's service/domain code (same
API-layer-composition pattern already used for Identity+Customer and
Identity+Driver).

Layering mirrors modules/driver/ and modules/customer/:

    domain/         pure business logic — no FastAPI/SQLAlchemy imports
    ports.py        VehicleRepository, VehicleDocumentRepository Protocols
    models.py       SQLAlchemy ORM models (infrastructure)
    repositories.py SQLAlchemy-backed implementations of the ports
    service.py      application services (use cases)
    schemas.py      Pydantic request DTO
    dependencies.py FastAPI DI wiring (reuses modules.identity's
                    require_driver as-is — no new auth code here)
    router.py       FastAPI routes under /api/v1/drivers/me/vehicles
"""
