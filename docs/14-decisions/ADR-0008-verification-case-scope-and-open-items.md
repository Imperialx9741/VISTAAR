ADR-0008 — Verification Case Scope and Open Items

Status: Decisions 1–4, 6, 8, and 9 Accepted (approved business/architecture
decisions). Items 5 and 7 — Decision required — NOT decided by this
record.
Date recorded: 2026-08-21
Deciders: Approved via the "VISTAAR — Phase 2 / Task 2.6 — Verification &
Compliance — Decision Resolution" task, resolving several of the open
questions Task 2.6's initial research plan surfaced. Does not implement
any code, schema, or provider integration — see §6.

1. Context

Task 2.5 (Driver & Vehicle Document Management) left every document at
`verification_status = PENDING` by design — no code anywhere transitions
it. Researching Task 2.6 found that the documentation set already defines
a complete, dedicated Verification Domain
([technical-architecture.md §4](../03-architecture/technical-architecture.md),
domain #13 of 18; [database-design.md §3](../04-database/database-design.md),
`verification` schema; [domain-design.md §18](../04-domain-design/domain-design.md);
[state-machines.md §43](../07-state-machines/state-machines.md)) — a
`verification.cases`/`verification.evidence`/`verification.results` model,
separate from the document tables themselves. Several integration
questions were not resolved by that documentation alone and required an
explicit decision:

- Does submitting a document create a verification case automatically?
- Does this task expose an admin/manual-review HTTP surface?
- Do vehicle documents participate, given they have no HTTP endpoint
  ([ADR-0007](ADR-0007-document-type-and-endpoint-scope.md))?
- Are PUC/Fitness in scope, given the task brief's own text mentions them
  but no VISTAAR source document does?
- How does a verification case's outcome relate to the document's own
  `verification_status`?

2. Decisions

**1. Document submission → verification case (Accepted).** Submitting a
driver or vehicle document creates a `verification.cases` row (and a
corresponding `verification.evidence` row) in the documented `PENDING`
state — matching the `SubmitEvidence` command
(domain-design.md §18.3) and BR-098's "Registered → Documents submitted →
Verified → Approved" sequence. Creating the case is record-keeping only:
it is not a verification outcome, and no `APPROVED`/`REJECTED` decision is
made merely because the case exists.

**2. No admin/manual-review HTTP surface in Task 2.6 (Accepted).** The
Verification domain's service/data model may represent manual review
conceptually (the documented `MANUAL_REVIEW` state and
`RequestManualReview`/`CompleteManualReview` commands), but no admin
endpoint or admin UI is built until a dedicated Admin-verification task
exists. This follows the same precedent already established for
`ApproveDriver`/`RejectDriver` (Task 2.3) and `ApproveVehicle`/
`RejectVehicle` (Task 2.4) — both explicitly deferred as Admin-domain
work.

**3. Vehicle documents participate, service-layer only (Accepted).** Both
driver and vehicle documents get verification cases through the same
provider-neutral architecture. This does not add a vehicle-document HTTP
endpoint — ADR-0007 and the current `api-contracts.md` still govern what
is exposed over HTTP; only the internal service/repository layer gains
verification-case support for vehicle documents.

**4. PUC/Fitness remain excluded (Accepted).** Neither is an authoritative
VISTAAR document type today — confirmed by repository-wide search: zero
mentions in `PRD.md` or `business-rules.md`. The only place either term
appears anywhere in this repository is as an explicit non-example in
[ADR-0007](ADR-0007-document-type-and-endpoint-scope.md) and in the Task
2.6 task brief's own illustrative text — neither is a VISTAAR source of
truth. Recorded explicitly:

- PUC is not currently an authoritative VISTAAR document type.
- Fitness is not currently an authoritative VISTAAR document type.
- If the product owner wants either added, `PRD.md`/`business-rules.md`
  must be explicitly updated first.
- After that documentation decision, affected database/API/event/test
  documents must be reconciled before any implementation — no schema,
  enum, verification logic, or route for either is created until then.

**5. No automatic status write-back (mechanism now implemented — Phase 2
/ Task 2.6B; automatic triggering remains unresolved).**
`verification.cases.status` (`PENDING`/`PROCESSING`/`APPROVED`/`REJECTED`/
`MANUAL_REVIEW`/`EXPIRED`, state-machines.md §43) and
`driver.documents.verification_status`/`vehicle.documents.verification_status`
(`PENDING`/`APPROVED`/`REJECTED`/`EXPIRED`, state-machines.md §44) were
two separate, explicitly-not-reconciled status systems when this ADR was
first recorded. Task 2.6B added the write-back mechanism —
`DriverDocumentService`/`VehicleDocumentService.apply_verification_outcome()`
— called explicitly by whoever completes a manual review
(`VerificationService.complete_manual_review()`), never automatically.
This ADR still does not invent a rule for *when* that call happens: no
HTTP endpoint triggers either method (none is documented anywhere), so
in practice nothing but tests currently exercises this path. A document
still stays at its own `verification_status` unless something explicitly
calls `apply_verification_outcome()` — the mechanism exists; an
automatic/HTTP-triggered workflow does not.

**6. AI/OCR stays optional and non-authoritative (Accepted — reaffirms
existing architecture, not a new decision).** Per
technical-architecture.md §39–40 and domain-design.md §18: AI may inspect,
extract fields from, classify, or flag a document for quality/tampering
issues, and may recommend `APPROVE`/`REJECT`/`REVIEW`, but must never
independently establish a government document's legal validity, and must
not bypass required human review for ambiguous or high-risk evidence. No
AI/OCR provider is integrated by this ADR.

**7. Verification provider remains unresolved (Decision required — NOT
decided).** `business-rules.md §43` ("Items Still TBD") explicitly lists
"Verification provider" and "Final KYC document list" as not finalized.
This ADR does not select VAHAN, SARATHI, DigiLocker, any third-party
verification vendor, any OCR vendor, or any AI vendor. No credentials are
requested or stored.

**8. External-integrations register created (Accepted).** See §5 below.

**9. Evidence-conditional case creation (Accepted — addendum, recorded
during the Task 2.6 implementation-planning follow-up).** A document
record may always be created without `evidence_uri` —
[Task 2.5](ADR-0007-document-type-and-endpoint-scope.md)'s schema already
makes it nullable on both `driver.documents` and `vehicle.documents`, and
this ADR does not change that. Whether decision 1's verification case is
actually created depends solely on whether `evidence_uri` is present at
submission time:

- **Present** → create `verification.cases` + `verification.evidence` in
  `PENDING`.
- **Absent** → create only the document record; no case, no evidence row;
  the caller-visible verification-case identifier is `null`.

No placeholder/synthetic `evidence_uri` is ever generated to force a case
into existence — `verification.evidence.evidence_uri` staying `NOT NULL`
(database-design.md §27.2) is respected exactly as documented, not worked
around. `driver.documents.evidence_uri`/`vehicle.documents.evidence_uri`
are not made mandatory by this ADR. This rule applies identically to
driver and vehicle documents at the service layer — the same
`VerificationService.submit_evidence()` is called (or not called) by the
same evidence-presence test for both subject types, so driver and vehicle
documents never diverge in behavior, only in whether an HTTP caller
(driver) or a direct service-layer caller (vehicle — no HTTP endpoint yet,
decision 3 / ADR-0007) triggers it.

3. What this ADR does NOT do

- Does not create the `verification` PostgreSQL schema, any migration, or
  the `modules/verification/` module — that remains a separate,
  not-yet-approved implementation step (see §6).
- Does not change `api-contracts.md`'s documented response shape — the
  future addition of a `case_id` field to
  `POST /api/v1/drivers/me/documents`'s response is recorded as planned
  in the Task 2.6 implementation plan, not made here.
- Does not integrate any external provider or request any API key.
- Does not modify `driver.drivers`/`vehicle.vehicles` eligibility fields
  or any runtime business logic.

4. Source documents reviewed

`business-rules.md` §43 (Items Still TBD), `PRD.md` §9/§11 (Driver
Registration and Verification; Driver Document Expiry),
`technical-architecture.md` §4–5 (Logical Domains; Verification Domain
§5.13), §39–40 (Verification Architecture; AI Verification Safety),
`domain-design.md` §18 (Verification Domain), `database-design.md` §3
(PostgreSQL Schemas), §27 (Verification Tables), `state-machines.md` §43
(Verification State Machine), §44 (Driver Document State),
`event-contracts.md` §18 (Verification Events), `security.md` §16
(Evidence Security), §52 (Object-Level Authorization), §65 (Logging
Security), §89 (Open Security Configuration), `implementation-readiness.md`
§15 (Verification Module).

5. External-integrations register

Recorded in
[docs/03-architecture/external-integrations-register.md](../03-architecture/external-integrations-register.md)
(new file, created alongside this ADR). Every verification-related
provider row is marked "Not selected — pending explicit provider decision
(business-rules.md §43)"; no row contains a real credential or vendor
commitment.

6. Consequences

- A future Task 2.6 implementation can proceed against decisions 1–4 and
  6 without re-litigating them, building: `modules/verification/`
  (domain/ports/models/repositories/service/dependencies only — no HTTP
  route beyond the one additive `case_id` field on the existing driver
  document response), a `VerificationProvider` protocol with a single
  `ManualReviewVerificationProvider` implementation (mirroring
  `modules.identity.sms.DevConsoleSmsProvider`'s "explicit stub, no real
  integration" precedent), and the three documented tables with no added
  columns.
- Item 5's mechanism is now built (Task 2.6B); what remains open is only
  *when* it fires automatically — no HTTP endpoint or scheduled trigger
  calls `complete_manual_review()`/`apply_verification_outcome()` today.
  Item 7 remains fully open. Closing item 7 requires a product/business
  decision on which verification provider(s)
  VISTAAR will use, recorded in `business-rules.md` (replacing the current
  §43 TBD entry) before any credential is requested or any integration is
  built.
- Any future task touching verification-case-to-document-status behavior,
  PUC/Fitness, or provider selection should link back to this ADR rather
  than re-deciding ad hoc.
