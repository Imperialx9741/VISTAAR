ADR-0032 — GPS Dispute Manual Review Implementation

Status: Decided and implemented (2026-08-25)
Deciders: Project owner (approved BR-124/BR-125 as drafted, via
AskUserQuestion) + this record (the implementation shape: schema,
endpoints, event names — none of which BR-124/BR-125 themselves specify,
same "engineering plumbing, not a business decision" treatment every
other ride-lifecycle endpoint shape in this codebase already got, e.g.
ADR-0028's GpsVerificationBody, ADR-0030's ConfirmEarlyDropBody).

1. Context

business-rules.md BR-124/BR-125 (approved 2026-08-25) formalize the GPS
manual-review/dispute workflow: when GPS verification for Driver Arrival
or Destination Completion reaches its terminal `GPS_VERIFICATION_FAILED`
outcome (ADR-0028), a 24-hour manual review opens instead of leaving the
ride permanently stuck. This record designs and implements exactly that
— no more, no less. It does not touch Early Drop (BR-124 explicitly
excludes it — no GPS verification step exists there to fail, ADR-0030).

2. Decision

Decision 1 — Owned by the Ride domain, not a new domain/schema. Same
reasoning ADR-0028 already established for `ride.gps_verifications`/
`ride.ride_otps`: this is a direct continuation of the Ride domain's own
GPS-verification concept ("what happens after the 3rd failure"), not a
standalone `dispute.*` domain — consistent with ADR-0028's own resolution
of ADR-0002 ("Support/Admin capability, not a new domain"). Two new
tables under the `ride` schema: `ride.gps_disputes` and
`ride.gps_dispute_evidence`.

`ride.gps_disputes`: id, ride_id (FK), gps_verification_id (FK to the
exact terminal-FAIL `ride.gps_verifications` row that opened it — BR-124:
"the original failed GPS verification record is not erased or altered"),
verification_type (ARRIVAL/COMPLETION, denormalized for query
convenience, matching gps_verifications' own precedent), opened_at,
evidence_deadline (opened_at + 24h), status (OPEN/RESOLVED/EXPIRED),
decision (APPROVE/REJECT, null until RESOLVED), decided_by,
decided_reason, decided_at.

`ride.gps_dispute_evidence`: id, dispute_id (FK), submitted_by (customer
or driver account id — polymorphic, same untyped-UUID precedent as
penalty.penalties.user_id/support.cases.user_id), evidence_type
(PHOTO/VIDEO/DOCUMENT/TEXT, per BR-125), uri (nullable — set for
PHOTO/VIDEO/DOCUMENT), text_explanation (nullable — set for TEXT),
submitted_at.

Decision 2 — Auto-opened, not client-initiated. mark_arrived()/
complete_ride() (ADR-0028) already compute the terminal-failure case
before raising `GpsVerificationFailedError`; this record extends both to
also create the `ride.gps_disputes` row (referencing the just-created
terminal `ride.gps_verifications` row) in the SAME transaction —
audit-trail-first, same pattern the FAIL-recording write itself already
uses. `GpsVerificationFailedError` gains an optional `dispute_id`
attribute so the HTTP error response's `details` (shared/api_envelope.py
already supports this) can tell the caller which dispute to act on —
without it, the client would have no way to discover the dispute exists.

Decision 3 — Evidence upload reuses ADR-0031's S3 flow, broadened.
ADR-0031's `POST /api/v1/drivers/me/uploads` was explicitly scoped to
driver-only uploads; BR-125 needs both customer AND driver to submit
evidence. Rather than widen that driver-namespaced endpoint's meaning, a
new, dispute-scoped upload-URL endpoint is added
(`POST /api/v1/rides/{ride_id}/gps-disputes/{dispute_id}/evidence/
upload-url`, customer-or-driver, ownership-checked against the ride) —
same underlying `shared.storage.ObjectStorage`, no new storage code.

Decision 4 — Five new endpoints (api-contracts.md had zero "dispute"
endpoints before this — ADR-0002's own finding):

- `POST /api/v1/rides/{ride_id}/gps-disputes/{dispute_id}/evidence/upload-url`
  — customer-or-driver, own ride. Returns a presigned S3 upload target
  (POST since ADR-0065, 2026-09-03 — was PUT originally).
- `POST /api/v1/rides/{ride_id}/gps-disputes/{dispute_id}/evidence` —
  customer-or-driver, own ride. Records one evidence item
  (`evidence_type` + `uri` or `text`). Rejected once the dispute is no
  longer OPEN (already RESOLVED, or the 24h window has lazily expired it
  — see Decision 5).
- `GET /api/v1/rides/{ride_id}/gps-disputes/{dispute_id}` —
  customer/driver (own ride) or admin. Dispute + its evidence list.
- `GET /api/v1/admin/gps-disputes` — admin, paginated Search (status
  filter), matching Search Penalties' own established shape (ADR-0023).
- `POST /api/v1/admin/gps-disputes/{dispute_id}/resolve` — admin.
  `{action: "APPROVE"|"REJECT", reason}`. APPROVE performs the exact ride
  transition mark_arrived()/complete_ride() would have on a real PASS
  (extracted into a shared private helper so the logic is written once);
  REJECT only records the decision.

Decision 5 — Lazy expiry, no background worker. Same "no background
worker, evaluate on next read/write" precedent as
MatchingService.expire_stale_offers() (ADR-0011 Decision 2): any
read/write that touches an OPEN dispute past its evidence_deadline first
transitions it to EXPIRED (a real write, not a computed-on-the-fly
status) before proceeding — evidence submission after that point is
rejected (`RideDomainError`, code `INVALID_STATE_TRANSITION`), matching
BR-124's "window elapses → original GPS result stands."

Decision 6 — Events. `ride.gps_dispute_opened`/`ride.gps_dispute_resolved`
added to event-contracts.md §10 — no prior event family existed for this
(the same "no dispute.* event family" gap ADR-0002 found). Producer
"Ride Service", consumers Notification/Analytics (no other consumer
exists in this codebase, same restraint used throughout).

3. What this implements

- Migration: `ride.gps_disputes`, `ride.gps_dispute_evidence`.
- `RideService.submit_gps_dispute_evidence()`, `.get_gps_dispute()`,
  `.search_gps_disputes()`, `.resolve_gps_dispute()`; `mark_arrived()`/
  `complete_ride()` extended per Decision 2.
- `modules/ride/router.py`: the four ride-scoped endpoints (Decision 4);
  `modules/admin/router.py`: Search + Resolve.
- `GpsVerificationFailedError.dispute_id` (optional attribute).

4. Consequences

- Closes the last unimplemented piece of the GPS-verification-dispute
  question ADR-0002 raised — not the elaborate evidence-window/APPROVE-
  REJECT mechanics wholesale (those needed BR-124/BR-125's own
  ratification first, which this ADR's prerequisite supplied), but
  exactly what those two rules now establish.
- Payment gateway (SBI Bank — still needs clarification), background-
  worker technology, and cloud/deployment provider remain the three
  fully open items — untouched by this record.
