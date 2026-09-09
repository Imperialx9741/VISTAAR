"""S3-backed object storage — presigned-upload pattern.

ADR-0031 (2026-08-25). Fills a gap this codebase left open since Task
2.3/2.5: api-contracts.md §9 documents `evidence_uri`/`profile_photo_uri`
as the literal placeholder `"uploaded-file-reference"` everywhere it
appears, assuming the client already has a URI from having uploaded a
file *somewhere* — no canonical document ever specified the upload
mechanism itself. `.env.example`'s `STORAGE_ENDPOINT`/`STORAGE_BUCKET`/
`STORAGE_ACCESS_KEY`/`STORAGE_SECRET_KEY` block anticipated exactly this,
Phase 1, never wired into any settings class or code path until now.

The client never sends file bytes through this application server:
`create_upload_url()` returns a short-lived presigned S3 POST target
(a URL plus a set of form fields, not a single URL — see below), the
client uploads directly to S3 as a multipart form POST, then supplies
the returned `object_uri` to whichever already-documented endpoint
expects an `evidence_uri`/`profile_photo_uri` (both unchanged — see
modules/driver/router.py's `POST /api/v1/drivers/me/uploads` and
modules/ride/router.py's GPS dispute evidence upload-url endpoint, the
two callers). This is the standard shape for S3-backed uploads and
avoids proxying potentially large file bytes through this process.

**Presigned POST, not PUT — owner decision, 2026-09-03, approved
explicitly as a real security fix.** An earlier version of this module
issued a plain presigned PUT (`generate_presigned_url("put_object", ...)`)
and this docstring used to carry a "Correction, security review pass 2"
note explaining that a plain PUT cannot enforce a maximum file size at
all — S3 only supports a size *range* condition
(`content-length-range`) on a presigned **POST** policy, a materially
different upload shape (multipart form fields the client POSTs, not a
raw PUT body). `_MAX_FILE_SIZE_BYTES` was defined but never actually
enforced. This is now fixed for real: `S3ObjectStorage.create_upload_url()`
calls `generate_presigned_post()` with a `content-length-range` condition
set to `_MAX_FILE_SIZE_BYTES`, so S3 itself rejects an oversized upload
at the storage layer — not a claim this module makes without enforcing
it. api-contracts.md §9/§56.3 and the mobile-facing upload contract
(docs/16-mobile) are updated to match this response shape change. No
mobile client existed against the old PUT contract (confirmed: no caller
of either upload-url endpoint exists anywhere in `apps/mobile` today),
so this is a clean contract change, not a breaking one for a real client.

Security controls implemented per security.md §17 ("File Upload
Security") to the extent a presigned-upload flow allows:
- A server-generated randomized object key (the client's own filename is
  never used or trusted), scoped under a caller-specific `key_prefix`
  (security.md §17's "authorized object-key scope" — see
  `S3ObjectStorage.__init__`'s own docstring) so driver-document uploads
  and GPS-dispute-evidence uploads can never collide or be confused for
  each other, and the exact key is embedded in the signed POST policy
  itself (not just the URL) — S3 rejects any attempt to upload under a
  different key than the one this module issued.
- A MIME-type/extension allow-list enforced by name before a URL is even
  issued, and also embedded as an exact-match condition in the signed
  POST policy (S3 itself rejects a form POST whose `Content-Type` field
  doesn't match what was authorized, not just this application).
- A maximum file size, enforced via `content-length-range` in the signed
  POST policy (S3 itself rejects an oversized upload).
- A short presigned-URL expiry (5 minutes).

NOT implemented — the presigned-URL/POST pattern cannot enforce these,
since this server never sees the uploaded bytes: file-signature
verification, actual-content-type verification (i.e. confirming the
bytes really are a JPEG, not just that the client claimed
`Content-Type: image/jpeg`), and virus/malware scanning (security.md
§16/§17's other listed controls) all require inspecting the bytes
themselves, which would need either a server-side proxy upload (a
different, larger design this ADR did not choose) or a post-upload
Lambda/webhook-triggered scan (needs a scanning provider, none
configured anywhere in this environment — same "no non-fabricated
substitute" treatment ADR-0022 Decision 4 already gave AskSupportAI's
missing LLM provider).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

_UPLOAD_URL_EXPIRY_SECONDS = 300  # 5 minutes — see this module's docstring.

_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB — a plain engineering
# limit (security.md §17: "Have size limits"), not a documented business
# value; generous enough for a phone-camera photo/scan, small enough to
# bound abuse. Enforced for real via the presigned POST policy's
# `content-length-range` condition — see this module's own docstring.

# security.md §17 ("Validate: Extension"). Deliberately narrow — these
# are the only file types api-contracts.md's own "Allowed evidence"
# equivalent (security.md §15: "Photos, Videos, Documents, Text
# explanation") plausibly needs for a driver KYC document or profile
# photo; no document/spreadsheet/executable type is included.
_ALLOWED_CONTENT_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
}


class UnsupportedContentTypeError(Exception):
    """Raised by create_upload_url() for a content_type outside
    _ALLOWED_CONTENT_TYPES. Not a RideDomainError/etc. subclass — this
    module is shared infrastructure, not owned by any one domain (same
    positioning as shared/idempotency.py, shared/outbox.py)."""

    code = "VALIDATION_FAILED"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(slots=True)
class UploadTarget:
    upload_url: str
    # The multipart form fields the client must include in its POST
    # body (alongside the actual file, which must be the LAST field —
    # S3's own requirement for a multipart POST upload), exactly as
    # boto3's generate_presigned_post() returns them: "key",
    # "Content-Type", "policy", "x-amz-*". Replaces the single PUT URL
    # this field previously carried — see this module's own docstring.
    upload_fields: dict[str, str] = field(default_factory=dict)
    object_uri: str = ""
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class ObjectStorage(Protocol):
    def create_upload_url(self, *, content_type: str) -> UploadTarget:
        """Issues a short-lived presigned upload target for a file of
        the given content_type. Raises UnsupportedContentTypeError if
        content_type is not in the allow-list."""
        ...


class S3ObjectStorage:
    """boto3-backed ObjectStorage. Imports boto3 lazily (inside
    __init__, not at module level) so importing this module never fails
    in an environment without boto3 installed unless this class is
    actually constructed — matching this codebase's general avoidance of
    hard-failing optional infrastructure imports at import time."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        key_prefix: str,
    ) -> None:
        """key_prefix (required, no default): the object-key namespace
        this instance is authorized to issue uploads into — e.g.
        "driver-uploads" for modules.driver.dependencies.
        get_object_storage(), "gps-dispute-evidence" for
        modules.ride.dependencies.get_gps_dispute_object_storage(). Owner
        decision, 2026-09-03: "validate... authorized object-key scope
        before issuing the upload authorization." Two different callers
        previously shared one hardcoded "driver-uploads/" prefix
        regardless of actual purpose (GPS dispute evidence was being
        filed under the driver-document namespace) — now each caller's
        dependency provider passes its own, and the exact resulting key
        is embedded in the signed POST policy itself, so S3 enforces
        the scope, not just this application's own bookkeeping.
        """
        import boto3

        self._bucket = bucket
        self._key_prefix = key_prefix
        # boto3 treats an empty endpoint_url as "use the client's own
        # default AWS endpoint resolution" only when the kwarg is
        # omitted entirely, not when it's an empty string — hence the
        # None-if-blank normalization below.
        self._client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
        )

    def create_upload_url(self, *, content_type: str) -> UploadTarget:
        extension = _ALLOWED_CONTENT_TYPES.get(content_type)
        if extension is None:
            raise UnsupportedContentTypeError(
                f"content_type must be one of {sorted(_ALLOWED_CONTENT_TYPES)}."
            )

        # Randomized key (security.md §17) — never the client's own
        # filename, never guessable — under this instance's authorized
        # key_prefix (this module's own docstring / __init__'s own
        # docstring, "authorized object-key scope").
        key = f"{self._key_prefix}/{uuid.uuid4()}.{extension}"
        now = datetime.now(UTC)
        presigned = self._client.generate_presigned_post(
            Bucket=self._bucket,
            Key=key,
            Fields={
                "Content-Type": content_type,
                # ACL is deliberately omitted, not set to "public-read" —
                # the bucket itself must be private (security.md §17.4:
                # "Use private object storage"), a bucket-policy concern
                # outside this application's own responsibility.
            },
            Conditions=[
                # Exact Content-Type match — a client cannot upload with
                # a different declared type than what was authorized.
                # (boto3 also auto-adds exact "bucket"/"key" conditions
                # from the Bucket/Key params above — verified directly
                # against a real boto3 client's signed policy, not
                # assumed.)
                {"Content-Type": content_type},
                # The actual fix this owner decision approved: S3 itself
                # rejects any upload outside this byte range. Minimum 1,
                # not 0 — a zero-byte "upload" is never a real document.
                ["content-length-range", 1, _MAX_FILE_SIZE_BYTES],
            ],
            ExpiresIn=_UPLOAD_URL_EXPIRY_SECONDS,
        )
        return UploadTarget(
            upload_url=presigned["url"],
            upload_fields=presigned["fields"],
            object_uri=f"s3://{self._bucket}/{key}",
            expires_at=now + timedelta(seconds=_UPLOAD_URL_EXPIRY_SECONDS),
        )
