ADR-0007 — Document Type Vocabulary and Document API Endpoint Scope

Status: Decision required for the vocabulary/versioning items — NOT
decided by this record. The endpoint-scope item is settled for this task
by following the existing documented contract exactly (no new decision
needed there — see §4).
Date recorded: 2026-08-21
Deciders: Recorded from repository evidence during Phase 2 / Task 2.5
(Driver & Vehicle Document Management Foundation), before implementation
began, per that task's "if a genuine ambiguity exists, flag it rather
than silently choosing" governance rule. Does not invent any business
rule, database column, or API endpoint.

1. Problem

Task 2.5 needs to accept and store `document_type` for both
`driver.documents` and `vehicle.documents`
([database-design.md §7.2/§8.2](../04-database/database-design.md)), and
needs to decide which HTTP surface to expose for document
submission/retrieval. Two things a full "document management" task would
normally need are not settled anywhere in the canonical documents.

2. Item A — No canonical `document_type` enum

Unlike `vehicle.category` (explicitly enumerated as BIKE/AUTO/CAB in
database-design.md §8.1 and business-rules.md), no source document lists
valid `document_type` values:

- `business-rules.md` BR-097 only describes document *categories* in
  prose ("Government identification, Driving licence" under Personal;
  "RC, Insurance, Vehicle registration number, Vehicle photo" under
  Vehicle) — never as exact string tokens.
- `api-contracts.md` §9's "Submit Driver Document" example uses
  `"document_type": "DRIVING_LICENSE"` as a single illustrative value,
  not as one entry in a documented enum.
- `database-design.md` §7.2/§8.2 defines the column as `VARCHAR(40)`
  with no `CHECK` constraint and no accompanying enum list.

**Decision recorded by this ADR**: Task 2.5 does not invent a
`document_type` enum (e.g. `GOVERNMENT_ID`/`RC`/`INSURANCE`/`PUC`/
`FITNESS`). `document_type` is accepted as a normalized (trimmed,
uppercased for consistent querying — a technical normalization, not a
business rule), non-blank string of at most 40 characters, matching the
documented column exactly. No government/OCR/compliance semantics are
inferred from the string; it is stored and returned as opaque data. The
canonical document-type vocabulary remains an **explicit future
product/API decision** — closing it requires a business-rules.md addition
listing the approved values and, if a `CHECK`/enum constraint is wanted,
a corresponding database-design.md and migration change.

3. Item B — Document API endpoint scope and replacement semantics

`api-contracts.md` §9 documents exactly one document-related endpoint:
`POST /api/v1/drivers/me/documents`. Confirmed by inspection:

- No GET (list or single) endpoint for driver documents is documented
  anywhere.
- No vehicle-document HTTP endpoint (POST, GET, or otherwise) is
  documented anywhere, despite `vehicle.documents` being fully specified
  in database-design.md §8.2 and "vehicle documents" being listed under
  the Vehicle Domain's ownership in domain-design.md §8.2.
- No source document describes what happens when a driver/vehicle
  resubmits a document of the same `document_type` (no `is_current`/
  `superseded_by` column, no `UNIQUE` constraint on
  `(driver_id, document_type)` in the documented schema, no prose
  anywhere).

This is the same shape of gap Task 2.4 encountered for
`GET/PATCH /api/v1/drivers/me/vehicles/{id}` — that gap was correctly
left unimplemented until a dedicated follow-up task explicitly authorized
adding them
([ADR-0006](ADR-0006-vehicle-lifecycle-single-active-vehicle.md) §5).

**Decision recorded by this ADR**: Task 2.5 follows the same precedent.
`POST /api/v1/drivers/me/documents` is implemented exactly as documented.
Driver document GET/list, and any vehicle-document HTTP endpoint, are
**not** added — the domain/service/repository layer for both is still
built (list/get/create), so the capability exists and is tested at the
service layer, but no HTTP route is attached to it. Document
replacement/versioning is **not** invented either: each submission
creates a new, independent row; no submission supersedes or deactivates a
prior one. Both remain **explicit future API-contract decisions** —
closing them requires an api-contracts.md addition (new documented
routes, and a stated replacement policy) analogous to how ADR-0006 §5
closed the equivalent vehicle-endpoint gap.

4. What this ADR does NOT change

- No `business-rules.md`, `database-design.md`, or `api-contracts.md`
  change is made by this ADR itself (api-contracts.md gains only a
  request/response example for the already-documented POST endpoint, and
  a cross-reference note to this ADR — not new endpoints).
- No code in this task infers document-type semantics, exposes an
  undocumented endpoint, or implements replacement/versioning logic.

5. Consequences

- A future task closing item A needs: an approved `document_type`
  vocabulary in business-rules.md, and (if desired) a `CHECK` constraint
  or enum in database-design.md/migrations.
- A future task closing item B needs: an explicit product/API decision on
  driver document retrieval and vehicle document endpoints, documented in
  api-contracts.md first (mirroring how ADR-0006 preceded the vehicle
  GET/PATCH addition), plus a stated document-replacement policy.
- Until then, any code relying on document retrieval beyond the service
  layer, or on a specific `document_type` vocabulary, does not exist in
  this codebase — future tasks should link back to this ADR rather than
  re-deciding either question ad hoc.
