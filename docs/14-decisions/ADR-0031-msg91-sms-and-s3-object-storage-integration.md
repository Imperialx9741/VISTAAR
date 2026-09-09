ADR-0031 — MSG91 SMS Provider & AWS S3 Object Storage Integration

Status: Decided and implemented (2026-08-25). The S3 upload *mechanism*
half (presigned PUT) is superseded 2026-09-03 by
[ADR-0065](ADR-0065-presigned-post-upload-security-fix.md) (presigned
POST, closing a real unenforced-file-size gap) — the provider choice
(AWS S3) and overall shape (client uploads directly to S3, this server
never sees file bytes) are unchanged.
Deciders: Project owner (provider selection, via AskUserQuestion) + this
record (integration shape, an engineering/plumbing decision — no business
rule is invented by either integration below).

1. Context

Two of the project owner's four open provider decisions were answered:
MSG91 for SMS/notifications, AWS S3 for object storage (driver document
evidence / profile photos). Both integrations plug into seams this
codebase already, deliberately, left open:

- modules/identity/sms.py: "`get_sms_provider()` is the single place a
  real provider will be wired in later, behind the same `SmsProvider`
  protocol — no call site elsewhere in this module will need to change."
  `SMS_PROVIDER=dev` (console-log adapter) was the only implemented
  value; any other value raised `NotImplementedError` naming
  MSG91/Twilio/Exotel/etc. by name as future candidates.
- `evidence_uri`/`profile_photo_uri` (api-contracts.md §9): documented
  everywhere as the literal placeholder string `"uploaded-file-reference"`
  — the client is assumed to already have a URI from having uploaded a
  file *somewhere*, but no canonical document (api-contracts.md,
  database-design.md, technical-architecture.md) ever specifies the
  upload mechanism itself. `.env.example` already had a generic, never-
  wired-up `STORAGE_ENDPOINT`/`STORAGE_BUCKET`/`STORAGE_ACCESS_KEY`/
  `STORAGE_SECRET_KEY` block anticipating exactly this.

2. Decision

Decision 1 — MSG91, real HTTP call, same `SmsProvider` protocol.
`Msg91SmsProvider` implements `send_otp()` via MSG91's documented v5 OTP
API (`POST https://control.msg91.com/api/v5/otp`, `authkey` header,
`template_id`/`mobile`/`otp` params — VISTAAR supplies its own
already-generated OTP value rather than letting MSG91 generate one, since
this codebase already owns OTP generation/hashing end-to-end,
modules.identity.domain.otp). Selected via `SMS_PROVIDER=msg91` (was
already the documented mechanism — no new selection concept). New env
vars: `MSG91_AUTH_KEY`, `MSG91_TEMPLATE_ID`.

CAVEAT, stated plainly rather than presented as verified: this is built
from general knowledge of MSG91's public v5 OTP API, not a live
integration test against a real MSG91 account/credentials (none exist in
this environment). The overall shape (authkey header, template-based
OTP send, custom OTP value support) is standard for this class of
provider, but exact field names/response shape should be confirmed
against MSG91's current API reference and a real account before
production use — flagged in the code itself, not silently assumed
correct.

Decision 2 — S3, presigned-upload-URL pattern, driver-scoped only.
A new endpoint, `POST /api/v1/drivers/me/uploads`, returns a short-lived
presigned S3 PUT URL plus the resulting object's URI (`s3://bucket/key`,
recorded as the eventual `evidence_uri`/`profile_photo_uri` value) — the
client uploads the file bytes directly to S3, then supplies that same
URI to the ALREADY-DOCUMENTED `POST /api/v1/drivers/me/documents` or
`PATCH /api/v1/drivers/me` calls, both of which are completely unchanged.
This is the standard shape for S3-backed uploads (avoids proxying
potentially large file bytes through the application server) and adds
exactly one new endpoint rather than redesigning either existing,
documented request contract.

Scope deliberately narrowed to driver-facing uploads only: vehicle
documents have no HTTP endpoint at all (ADR-0007: "No HTTP route exists
for vehicle documents... ADR-0007 for the full reasoning") —
`VehicleDocumentService.submit_document()` is called directly at the
service layer, proven by tests, with no router. Building an upload-URL
endpoint for vehicle documents would require first deciding to expose
vehicle document submission over HTTP at all, a materially different,
larger decision ADR-0007 explicitly scoped out — not assumed here.

Security controls implemented, per security.md §16-17's documented
requirements for evidence/file uploads (reused for this general-purpose
driver-upload endpoint, the closest documented analog): server-generated
randomized object key (never the client-supplied filename), MIME/
extension allow-list, a hard size limit, a short presigned-URL expiry
(5 minutes — long enough for a mobile upload, short enough to limit a
leaked URL's blast radius), and a private bucket (no public-read ACL,
matching `.env.example`'s already-provisioned but never-implemented
`STORAGE_*` block). NOT implemented, flagged rather than fabricated: virus/
malware scanning (security.md §16) — no scanning provider is configured
anywhere in this environment, the same "no non-fabricated substitute"
reasoning ADR-0022 Decision 4 already applied to AskSupportAI's missing
LLM provider. Access logging beyond what S3/CloudTrail itself provides
is also not built — no logging/observability provider is configured
either.

3. What this implements

- `modules/identity/sms.py`: `Msg91SmsProvider`, selected via
  `SMS_PROVIDER=msg91`; `DevConsoleSmsProvider` remains the default and
  is unchanged.
- `shared/storage.py`: `ObjectStorage` Protocol + `S3ObjectStorage`
  (boto3-backed) implementation — `create_upload_url(content_type,
  extension) -> (upload_url, object_uri)`.
- `POST /api/v1/drivers/me/uploads` (new, modules/driver/router.py):
  driver-only, returns `{upload_url, uri, expires_at}`. Neither
  `POST /api/v1/drivers/me/documents` nor `PATCH /api/v1/drivers/me`
  changes shape — both already accepted an opaque `evidence_uri`/
  `profile_photo_uri` string.
- New dependency: `boto3`. New env vars (`.env.example`): `SMS_PROVIDER`
  documented (was already read, never shown as an example),
  `MSG91_AUTH_KEY`, `MSG91_TEMPLATE_ID`; `STORAGE_*` block's existing
  four vars are now actually read (previously provisioned, unused).

4. Consequences

- `SMS_PROVIDER=dev` (console log) stays the default — nothing about
  existing test behavior changes; `Msg91SmsProvider` is exercised via
  fake-HTTP-client unit tests, never a real network call, matching this
  codebase's own external-call testing discipline elsewhere (e.g.
  RedisNearbyDriverIndex against a real Redis, not MSG91 against a real
  MSG91 — the boundary here is httpx.AsyncClient, which IS fully
  fake-able unlike Redis).
- The payment gateway question (SBI Bank, ambiguous — see the project
  owner's own flagged follow-up) and the GPS-verification-dispute
  business rule (BR-124/BR-125, drafted, awaiting approval) are both
  UNCHANGED by this record — neither is addressed here.
