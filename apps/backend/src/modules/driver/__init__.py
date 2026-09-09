"""VISTAAR Driver module — Driver Profile Foundation (Phase 2 / Task 2.3)
+ Driver Document Management Foundation (Phase 2 / Task 2.5) + Driver
Online/Offline (Phase 2 / Task 2.7B).

Owns the driver's business profile, document records, and availability
(operational_status), per docs/04-domain-design/domain-design.md §7
(Driver Domain) and docs/04-database/database-design.md §7.1
(driver.drivers) / §7.2 (driver.documents). Get Profile, Update Profile,
Submit Document, Go Online, and Go Offline are implemented — see the
list of explicit exclusions below, all deferred to later tasks.

Go Online (api-contracts.md §10) needs eligibility data
(driver.drivers.verification_status, plus vehicle verification/
operational status and document validity) that spans both this module
and modules/vehicle/. Consistent with this module never importing
modules.vehicle (see below), DriverService.go_online() takes that
vehicle-side data as plain pre-computed values; modules/driver/router.py
is what actually fetches the driver's ACTIVE vehicle and its documents
via modules.vehicle's own services and composes the two — the same
API-layer-only composition pattern modules/vehicle/router.py already
uses for driver+vehicle in the other direction (Activate/Deactivate
Vehicle reading driver.drivers.operational_status).

Explicitly out of scope for this module (do not extend it to cover these
without a new task):

- Vehicle management (vehicle.vehicles — Task 2.4, modules/vehicle/).
- Document verification/approval — document.verification_status exists
  in the schema and is always created as PENDING; nothing in this module
  ever transitions it (see Task 2.5's final report). No OCR/AI, no
  government verification APIs (VAHAN/SARATHI/DL/RC/Insurance/PUC/
  Fitness), no object-storage integration (evidence_uri is opaque
  metadata only — never dereferenced/fetched, see ADR-0007), no expiry
  scheduling.
- Driver document GET/list via HTTP — not documented anywhere
  (api-contracts.md only documents POST). DriverDocumentService still
  implements list/get for internal completeness; only submit_document()
  has a router. See ADR-0007.
- A canonical document_type enum — none exists in the documentation set;
  document_type is validated as shape only (non-blank, ≤40 chars,
  normalized to uppercase), not against a value list. See ADR-0007.
- Document replacement/versioning — each submission creates a new,
  independent row; no supersede/replace semantics exist. See ADR-0007.
- SuspendDriver/ReactivateDriver (domain-design.md §7.4) — implemented at
  the service layer as of Phase 03 (ADR-0021):
  `DriverService.suspend_driver()`/`reactivate_driver()`, concurrency-safe
  (row-locked, same mechanism as go_online()/go_offline()). NOT wired to
  any HTTP endpoint — api-contracts.md documents no
  `POST /api/v1/admin/drivers/{id}/suspend`(or `/reactivate`) shape
  anywhere, unlike Approve/Reject Driver, which had one already; inventing
  one would be the same "new public API contract" §0.3 gate ADR-0018 hit
  for Advertisement. Proven directly by unit + real-Postgres integration
  tests instead. Automatic, threshold-based suspension (BR-069/117/119's
  progressive cancellation-abuse enforcement) remains explicitly out of
  scope — exact strike thresholds and suspension duration are still TBD
  (business-rules.md §43), unchanged by ADR-0021; only the manual,
  admin-triggered command is built. Nothing transitions operational_status
  to INELIGIBLE (document-expiry-triggered ineligibility, BR-104) — no
  expiry-monitoring job exists.
- Admin approval/rejection of a driver (ApproveDriver/RejectDriver,
  domain-design.md §7.4 — an Admin-domain workflow; implemented in
  modules/driver/service.py as of Task 2.7A, invoked from
  modules/admin/router.py).
- Driver strikes, ride/matching, wallet, payments, notifications.

verification_status is server-controlled and READ-ONLY through this
module's own API (GET/PATCH /me) — it only ever changes via
ApproveDriver/RejectDriver (Task 2.7A, modules/admin/router.py).
operational_status is likewise never accepted from PATCH /me, but as of
Task 2.7B it does transition through this module's own Go Online/Go
Offline endpoints (OFFLINE <-> ONLINE only — see service.py). strikes
remains untouched by anything in this module.

Layering mirrors modules/customer/ and modules/identity/ exactly:

    domain/         pure business logic — no FastAPI/SQLAlchemy imports
    ports.py        DriverRepository, DriverDocumentRepository Protocols
    models.py       SQLAlchemy ORM models (infrastructure)
    repositories.py SQLAlchemy-backed implementations of the ports
    service.py      application services (use cases)
    schemas.py      Pydantic request DTOs
    dependencies.py FastAPI DI wiring (reuses modules.identity's
                    require_driver as-is — no new auth code here)
    router.py       FastAPI routes under /api/v1/drivers
"""
