ADR-0065 — Presigned S3 POST Upload (replacing presigned PUT)

Status: Accepted and implemented (2026-09-03) — owner decision
("Approve the real security fix... Replace the existing presigned S3 PUT
upload contract with a presigned S3 POST upload flow")
Date recorded: 2026-09-03
Deciders: Project owner (explicit written decision).
Supersedes: the upload-mechanism half of ADR-0031 (2026-08-25) — that
ADR's provider selection (AWS S3) and general shape (client uploads
directly to S3, this server never sees file bytes) are unchanged; only
the presign method changes, from `generate_presigned_url("put_object")`
to `generate_presigned_post()`.

1. Context

`security-review-pass-2-2026-09-03.md` §3.1 flagged that
`shared/storage.py`'s `_MAX_FILE_SIZE_BYTES = 10MB` was never actually
enforced: a plain presigned PUT URL (what the code issued) has no
mechanism to constrain upload size — S3 only supports a size *range*
condition (`content-length-range`) on a presigned **POST** policy, a
materially different upload shape. That review named this a real,
open gap requiring an owner decision (switch to `generate_presigned_post`
vs. accept the gap), explicitly declining to make the switch silently
since it changes the documented response contract. The owner's
2026-09-03 instruction approves the switch.

2. Decision

1. `shared/storage.py`'s `S3ObjectStorage.create_upload_url()` now calls
   `generate_presigned_post()` instead of `generate_presigned_url
   ("put_object", ...)`. `UploadTarget` gains `upload_fields: dict[str,
   str]` (the multipart form fields the client must submit alongside the
   file) in place of relying on `upload_url` alone.
2. Maximum file size (10 MB, unchanged value) is enforced via a
   `["content-length-range", 1, 10485760]` condition in the signed POST
   policy — S3 itself rejects an oversized (or zero-byte) upload, not
   just a claim this codebase makes without enforcing it.
3. Content-type is pinned as an exact-match condition in the same
   policy (`{"Content-Type": "<type>"}`) — S3 rejects a form POST whose
   declared type doesn't match what was authorized, in addition to the
   existing pre-issue allow-list check (`_ALLOWED_CONTENT_TYPES`,
   unchanged).
4. **Object-key scope** (the owner's explicit additional requirement,
   "validate... authorized object-key scope before issuing the upload
   authorization"): `S3ObjectStorage.__init__` gains a required
   `key_prefix` parameter. Before this pass, both call sites
   (`modules.driver.dependencies.get_object_storage()` and
   `modules.ride.dependencies.get_gps_dispute_object_storage()`)
   constructed an identical `S3ObjectStorage` with no distinguishing
   prefix, and the object key was hardcoded to `driver-uploads/...`
   inside the shared class regardless of which endpoint issued it —
   meaning GPS dispute evidence was silently being filed under the
   driver-document namespace. Now each dependency provider passes its
   own scope (`"driver-uploads"` / `"gps-dispute-evidence"`), and the
   resulting exact key is embedded in the signed POST policy itself
   (verified directly against a real boto3-generated policy: `Bucket`/
   `Key` params are automatically translated into exact-match
   conditions), so S3 — not just this application's bookkeeping —
   rejects an attempt to upload under any other key.
5. Upload authorization remains short-lived (5 minutes, unchanged).
6. Response shape changes: both `POST /api/v1/drivers/me/uploads` and
   `POST /api/v1/rides/{ride_id}/gps-disputes/{dispute_id}/evidence/
   upload-url` now return `upload_fields` alongside `upload_url` (the
   URL alone is no longer sufficient — the client must submit these
   exact fields, with the file itself as the last multipart field, S3's
   own requirement). `uri`/`expires_at` are unchanged.

3. Why this is a clean contract change, not a breaking one

Confirmed by direct search: no caller of either upload-url endpoint
exists anywhere in `apps/mobile` today — the presigned-upload flow was
never wired up client-side. The owner's instruction explicitly notes
this ("No mobile client has yet been built against this endpoint, so
this contract change is approved"). api-contracts.md and
docs/16-mobile's upload contract are updated to document the new shape
directly, not as a versioned/deprecated migration.

4. What this does NOT do

- Does not add file-signature verification, real content-type
  verification (confirming the bytes are actually what `Content-Type`
  claims), or virus/malware scanning — all three require inspecting the
  uploaded bytes, which a presigned-upload flow (PUT or POST) cannot do
  by design; see `shared/storage.py`'s own docstring, unchanged from
  ADR-0031's original scoping.
- Does not change which file types are allowed (still
  `image/jpeg`/`image/png`/`image/webp`/`application/pdf`) or the 10 MB
  limit's actual value — only how the limit is enforced.
- Does not change bucket-level access controls (still fully private, no
  ACL set per-object) — unchanged from ADR-0031.
- Does not embed the authenticated account's id into the object key —
  the key remains a server-generated random UUID under the caller's
  `key_prefix`; authorization is enforced at the metadata-submission
  layer (e.g. `POST .../documents` still requires the authenticated
  driver to own the profile the evidence is attached to), the same
  model ADR-0031 already established and unchanged here.

5. Verification

- `tests/test_shared_storage.py` rewritten: asserts the signed policy's
  actual decoded conditions (not just the surface `upload_fields` dict)
  include the `content-length-range`, `Content-Type`, and exact `key`
  conditions — confirms what S3 will really enforce, not just that a
  field exists.
- New test confirming the two callers' key prefixes never collide
  (`driver-uploads/` vs. `gps-dispute-evidence/`).
- `tests/test_driver_api.py`/`tests/test_gps_dispute_api.py` updated at
  the HTTP layer to assert the new `upload_fields` shape is present in
  real endpoint responses.
- Full backend suite and `ruff`/`mypy` run clean — see the completion
  report this ADR was delivered alongside for exact counts.
- `generate_presigned_post()`, like `generate_presigned_url()`, is a
  pure local HMAC-signing computation (confirmed directly against a
  real boto3 client with dummy credentials) — no network call, no real
  AWS account needed to verify the policy shape for real.
