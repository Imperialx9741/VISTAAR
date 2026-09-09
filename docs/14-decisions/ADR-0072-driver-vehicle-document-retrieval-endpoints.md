ADR-0072 — Driver Document Retrieval and Vehicle Document HTTP Endpoints

Status: Accepted and implemented (2026-09-04)
Date recorded: 2026-09-04
Deciders: Closes ADR-0007 §5 item B's explicitly-flagged future gap,
following the exact precedent ADR-0006 §5 already set for the
equivalent Vehicle GET/PATCH gap ("a dedicated follow-up task
explicitly authorized adding them"). Undertaken as part of completing
Phase 3's mobile Sarthi onboarding flow (owner-requested autonomous
engineering pass, 2026-09-04) — the mobile app cannot let a Sarthi see
or submit their own document/vehicle-document status without these.

1. Context

ADR-0007 recorded, before Task 2.5 implementation began, that two
capabilities were fully built at the service/repository layer
(`DriverDocumentService.list_documents()`/`get_document()`,
`VehicleDocumentService.submit_document()`/`list_documents()`/
`get_document()`) but deliberately had **no HTTP route** — the same
gap Task 2.4 originally left for Vehicle GET/single and PATCH, closed
three tasks later by ADR-0006 once a follow-up task needed them for
real. That is this task.

api-contracts.md §9 (line 466-468) explicitly states this in the
present tense: "Driver document retrieval (GET/list) and any vehicle-
document endpoint are not documented here and are not implemented —
see ADR-0007." This ADR is the api-contracts.md-preceding decision
ADR-0007 §5 itself said closing this gap would need.

2. What ADR-0007 explicitly reserved as *separate*, still-open
   decisions — NOT decided or touched by this ADR

- **Item A, a canonical `document_type` vocabulary.** Still not
  decided. `document_type` remains exactly what it always was: an
  opaque, normalized (trimmed, uppercased), ≤40-character string with
  no enum, no CHECK constraint, no inferred semantics. Nothing below
  invents one.
- **Document replacement/versioning semantics.** Still not decided.
  Each submission remains a new, independent row; no submission
  supersedes, deactivates, or is linked to a prior one. The new list
  endpoints below simply return every row that exists, newest first —
  they do not introduce an `is_current` concept.

Building the retrieval/submission HTTP surface does not require either
of these — a client can list/submit opaque-string-typed, independently-
versioned rows exactly as the service layer already does, and does so
below.

3. Decision — three new endpoints, exactly mirroring already-documented
   shapes

- **`GET /api/v1/drivers/me/documents`** — the caller's own driver
  documents, newest first. Response: `{"data": {"documents": [...]}}`,
  each item the exact same shape §9's POST already returns
  (`_document_data()`, unchanged) — `verification_case_id` is `null`
  here (a list read has no single verification-submission event to
  report against; unchanged concept from POST's own response).
- **`POST /api/v1/drivers/me/vehicles/{vehicle_id}/documents`** —
  submits a vehicle document, mirroring §9's driver-document POST
  field-for-field (`document_type`, `document_number`, `evidence_uri`,
  `expires_at`) and response shape
  (`document_id`/`document_type`/`document_number`/`evidence_uri`/
  `verification_status`/`expires_at`/`created_at`/`updated_at`/
  `verification_case_id`) — the vehicle-document equivalent of the
  exact mechanism §9 already documents, including the same
  `verification_service.submit_evidence(...)` composition when
  `evidence_uri` is supplied (`VERIFICATION_TYPE.VEHICLE_DOCUMENT` —
  already a real enum member, confirmed against
  `modules/verification/domain/entities.py`, not invented here).
  Ownership-checked: 404 (`RESOURCE_NOT_FOUND`) if `vehicle_id` doesn't
  belong to the caller, the same IDOR-safe pattern `GET .../vehicles/
  {vehicle_id}` already uses.
- **`GET /api/v1/drivers/me/vehicles/{vehicle_id}/documents`** — that
  vehicle's documents, newest first, same ownership check.

4. Verification

Real HTTP + real Postgres tests (mirroring `tests/test_driver_api.py`/
`tests/test_vehicle_api.py`'s own existing conventions): submit-then-
list round trip for both driver and vehicle documents, ownership
rejection (another driver's vehicle_id returns 404), evidence_uri
present/absent both produce the correct `verification_case_id`
behavior, unauthenticated/wrong-account-type rejection. Full backend
suite run after — see this task's own completion report for the exact
count.

5. What this ADR explicitly does not do

- Does not decide `document_type`'s vocabulary or add a CHECK
  constraint/enum (ADR-0007 item A, still open).
- Does not add document replacement/versioning/supersede logic
  (ADR-0007 item B's other still-open half).
- Does not change `POST /api/v1/drivers/me/documents`'s existing
  behavior or response shape at all.
- Does not add a single-document GET (`.../documents/{document_id}`)
  for either driver or vehicle documents — not needed by any real
  caller yet (the mobile onboarding screen this ADR was written to
  unblock only ever needs the list), same "no invented composition
  with no real caller" restraint this codebase applies throughout.
