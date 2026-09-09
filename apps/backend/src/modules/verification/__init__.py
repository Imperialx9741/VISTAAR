"""VISTAAR Verification module — Verification & Compliance Foundation
(Phase 2 / Task 2.6).

Owns evidence verification, per
docs/03-architecture/technical-architecture.md §4 (domain #13 of 18) /
§5.13 (Verification Domain), docs/04-domain-design/domain-design.md §18,
and docs/04-database/database-design.md §3 (`verification` schema) / §27
(Verification Tables). This is a genuinely separate domain from Driver/
Vehicle — unlike `driver.documents`/`vehicle.documents` (Task 2.5, owned
by the Driver/Vehicle domains themselves), verification *cases* are their
own documented domain with their own schema, so this module is not folded
into modules/driver or modules/vehicle.

See docs/14-decisions/ADR-0008-verification-case-scope-and-open-items.md
for the design decisions this module implements. Summary:

- `SubmitEvidence` (domain-design.md §18.3) is implemented as
  `VerificationService.submit_evidence()` — creates a `PENDING`
  `verification.cases` row + a `verification.evidence` row. Wired into
  `POST /api/v1/drivers/me/documents` (modules/driver/router.py), and
  only when `evidence_uri` is present at submission (ADR-0008 item 9;
  `verification.evidence.evidence_uri` is `NOT NULL`, while
  `driver.documents.evidence_uri`/`vehicle.documents.evidence_uri` are
  nullable — no placeholder evidence is ever invented to force a case
  into existence).
- `RunAIVerification` is implemented as
  `VerificationService.run_verification()`, calling a
  `VerificationProvider` (providers.py) — but is not invoked
  automatically by anything in this task. It exists, is fully tested, and
  is ready for whenever a trigger (admin action, scheduled job, etc.) is
  approved.
- `ApproveEvidence`/`RejectEvidence`/`RequestManualReview`/
  `CompleteManualReview` are NOT implemented — those require an admin
  actor; explicitly deferred to a future Admin-verification task
  (ADR-0008 item 2), same precedent as `ApproveDriver`/`ApproveVehicle`.
- The only `VerificationProvider` implementation is
  `ManualReviewVerificationProvider` (providers.py), which always returns
  `MANUAL_REVIEW` — no AI/OCR or authoritative external provider is
  integrated (ADR-0008 items 6–7; business-rules.md §43 lists
  "Verification provider" as explicitly unresolved). No API key is
  requested or stored.
- Vehicle documents participate in this same model at the service layer
  only (ADR-0008 item 3) — `VerificationService` is subject-agnostic and
  works identically for `subject_type="VEHICLE_DOCUMENT"`, proven by
  tests, but nothing in `modules/vehicle/` calls it automatically: doing
  so would require `modules/vehicle` to import `modules/verification`
  with no router to compose at (vehicle documents still have no HTTP
  endpoint — ADR-0007). A future vehicle-document endpoint can wire the
  same composition `modules/driver/router.py` already demonstrates.
- No automatic write-back exists between `verification.cases.status` and
  `driver.documents.verification_status`/`vehicle.documents.verification_status`
  (ADR-0008 item 5 — explicitly unresolved, two separate status systems).
- PUC/Fitness are not supported document types anywhere in this module or
  any other (ADR-0008 item 4 — not authoritative VISTAAR document types).

Explicitly out of scope for this module (do not extend without a new
task): any HTTP route (admin or otherwise), Kafka publishing of
`verification.*` events (event-contracts.md §18 defines the payloads;
publishing them is unused here, same precedent as Task 2.4's unpublished
`vehicle.*` events), Redis state, notifications, any external
verification/AI/OCR provider integration, PUC/Fitness document types,
`driver.drivers`/`vehicle.vehicles` eligibility changes.

Layering mirrors every other module:

    domain/         pure business logic — no FastAPI/SQLAlchemy imports
    ports.py        VerificationCaseRepository Protocol
    models.py       SQLAlchemy ORM models (infrastructure)
    repositories.py SQLAlchemy-backed implementation of the port
    providers.py    VerificationProvider Protocol + the one stub adapter
    service.py      application service (use cases)
    dependencies.py FastAPI DI wiring — consumed by other modules' routers
"""
