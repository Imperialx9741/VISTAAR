VISTAAR — Security Review, Pass 2

Date: 2026-09-03
Reviewer: Claude Code (code-level review, not a substitute for an external
audit or penetration test — see security-review-2026-09-02.md §7, which
applies equally here)
Scope: exactly the "not yet covered — pass 2" list
security-review-2026-09-02.md §6 named — object-level authorization/IDOR,
mass assignment protection, input validation, monetary/currency
validation, file upload security, promotion/referral race-condition
protection, CI/CD security scanning, container security. Rate limiting
(that same document's finding 4.1, HIGH) was already fixed separately —
see ADR-0061.

1. Summary

| # | Area | Result |
| :-- | :-- | :-- |
| 1 | Object-level authorization / IDOR (security.md §8, §52) | **Confirmed clean** — no action needed |
| 2 | Mass assignment protection (§53) | **Confirmed clean** — no action needed |
| 3 | Input validation — amounts/currency (§54–56) | **Confirmed clean** — no action needed |
| 4 | Promotion/referral race conditions (§37–38) | **Confirmed clean** — no action needed |
| 5 | File upload size limit (§17) | **Fixed** — was silently unenforced despite a docstring claiming otherwise. Docstring corrected in this pass; the real enforcement mechanism (presigned POST) was owner-approved and implemented 2026-09-03 — see ADR-0065. |
| 6 | Dependency pinning (§73–74) | **Fixed** — no lockfile existed anywhere in the repo |
| 7 | CI/CD security scanning (§75) | **Fixed** — secret scanning, container scanning, and Admin Web dependency scanning added |
| 8 | Container permissions (§74) | **Fixed** — Kubernetes-level `securityContext` added |

2. Confirmed clean (no action needed)

2.1 Object-level authorization / IDOR (security.md §8, §52)

Spot-checked every endpoint in `src/modules/*/router.py` that accepts a
resource id in its path and is not admin-only-by-router-dependency:
`GET/POST .../rides/{ride_id}` (and its cancel/driver-cancel/arrived/
otp-refresh/start/complete/pickup-change/destination-change variants),
`GET .../rides/{ride_id}/gps-disputes/{dispute_id}` (+ its evidence
upload-url endpoint), `GET .../vehicles/{vehicle_id}` (+ activate/
deactivate/update), `GET .../support/cases/{case_id}`,
`POST .../rides/{ride_id}/sos`, `DELETE .../me/devices/{token}`. Every
one either passes the authenticated account's id into the service layer
as an explicit ownership-scoping parameter (`customer_id=account.id`,
`driver_id=account.id`) that the service/repository layer filters on, or
does an explicit `account.id not in (ride.customer_id, ride.driver_id)`
check before touching the resource — consistently returning "not found"
rather than "forbidden" for an unowned resource (the same IDOR-safe
convention throughout, so a client can't distinguish "doesn't exist"
from "exists but isn't yours"). No gap found in this pass. Not
exhaustive line-by-line — pass 1's own caveat about this being a
targeted, not fully exhaustive, review still applies.

2.2 Mass assignment protection (security.md §53)

Every PATCH/POST body that gets converted via `.model_dump()` and
passed into a service update (`UpdateCustomerProfileBody`,
`UpdateDriverProfileBody`, `UpdateVehicleBody`) declares only a narrow,
explicit allow-list of fields at the Pydantic level — no request schema
anywhere in `src/modules/*/schemas.py` defines a `wallet_balance`,
`role`, `status`, `verification_status`, or `operational_status`-style
field a client could smuggle in. Confirmed no schema sets
`model_config = ConfigDict(extra="allow")` anywhere — Pydantic v2's
default (`extra="ignore"`) is in effect everywhere, so even an
unexpected JSON key a client sends is silently dropped during
validation, never reaching `.model_dump()`. `UpdateVehicleBody`'s own
docstring already names exactly which fields were deliberately excluded
and why. No gap found.

2.3 Input validation — monetary amounts and currency (security.md
§54–56)

No request schema anywhere types a money-bearing field (`amount`,
`fare`, `balance`, `fee`) as `float` — every one uses `Decimal`,
matching `WalletService`'s own Decimal-throughout arithmetic and
`wallet.wallets.balance`'s `NUMERIC(12,2)` column type. `float(...)`
conversions exist only at the JSON-response-serialization boundary
(JSON has no native decimal type), never in storage or computation. No
request schema anywhere defines a `currency` field at all — every
response hardcodes `"currency": "INR"` server-side, so there is no code
path through which a client could select a different currency. Both
satisfy security.md §55/§56 by construction, not by a runtime check
that could be bypassed. No gap found.

2.4 Promotion/referral race conditions (security.md §37–38)

`PromotionService.redeem_campaign_code()` locks the campaign row first
(`get_by_code_for_update`) before checking status/window/eligibility/
minimum-fare/usage-limits — including the per-customer usage-limit
check, which is therefore also race-safe (two concurrent redemption
attempts by the same customer serialize on the same campaign row lock,
not just two different customers). `ReferralService.attach_referral()`
enforces self-referral rejection (BR-025) before creating a `Referral`
row, backed by `uq_referrals_referred_id` (a referred party can only
ever be referred once, enforced by the repository raising
`AlreadyReferredError` on the real unique-constraint violation) —
reward issuance is keyed by an idempotency key
(`get_by_idempotency_key`) so a retried composition can't double-issue
a reward. No gap found.

3. Fixed this pass

3.1 [MEDIUM] File upload size limit was silently unenforced
(security.md §17) — **RESOLVED 2026-09-03, see
[ADR-0065](../14-decisions/ADR-0065-presigned-post-upload-security-fix.md)**

`shared/storage.py` defined `_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024`
with a docstring claiming it was "enforced via S3's own presigned
POST/PUT content-length condition where the backing SDK supports it" —
that claim was false. `S3ObjectStorage.create_upload_url()` calls
`generate_presigned_url("put_object", ...)`, a plain presigned PUT;
Amazon S3 only supports a size *range* condition
(`content-length-range`) on presigned **POST** policies, a materially
different upload shape (multipart form fields the client POSTs, not a
raw PUT body) — `generate_presigned_url` for PUT has no equivalent.
`_MAX_FILE_SIZE_BYTES` was never referenced anywhere else in the
codebase (confirmed by a repo-wide grep) — dead code masquerading as an
enforced control.

**Resolved 2026-09-03** — the owner approved the fix this section had
flagged as needing an explicit decision: switch to
`generate_presigned_post`. See ADR-0065 for the full account. Summary:
`S3ObjectStorage.create_upload_url()` now issues a presigned POST with a
real `content-length-range` condition (S3 itself rejects an oversized
upload), plus a caller-specific `key_prefix` closing a second, related
gap this review's original pass didn't name explicitly (GPS dispute
evidence and driver documents previously shared one hardcoded object-key
namespace). `tests/test_shared_storage.py` now asserts against the
signed policy's actual decoded conditions, not just that a field exists.

3.2 [MEDIUM] No dependency lockfile existed anywhere in the backend
(security.md §73/§74)

Every dependency in `pyproject.toml` was declared with an unbounded
`>=` floor and no upper bound; no `uv.lock`/`requirements.txt` was
committed anywhere. Every build — the production Docker image and every
CI run — re-resolved "whatever is newest and compatible" at build time:
not reproducible build-to-build, and a newly-published compromised
package version would be pulled into the shipped image automatically,
with no review step at all.

Fixed: generated and committed `apps/backend/uv.lock` (`uv lock`, 66
resolved packages), and changed `Dockerfile`'s builder stage from
`uv pip install -r pyproject.toml` (uv's "pip interface," which ignores
uv.lock even when one exists) to `uv sync --frozen --no-dev
--no-install-project` (uv's lockfile-aware "project interface") —
`--frozen` makes the build fail loudly if `uv.lock` and `pyproject.toml`
ever drift out of sync, rather than silently re-resolving.

Verified for real, not just reviewed by reading: built the image
(`docker build`), ran it against local Postgres/Redis with Kafka
deliberately unreachable — it started, degraded gracefully on the
Kafka connection exactly as deployment-runbook.md §6 already documented
for the pre-lockfile image, `GET /health` returned
`200 {"status":"OK"}`, the container ran as the non-root `vistaar` user,
and every key runtime dependency (fastapi, sqlalchemy, redis, boto3,
celery) imported cleanly inside the running container. Also re-ran
`pip-audit` against the locked versions specifically (via
`uv export --frozen`) — `No known vulnerabilities found`.

One real bug was caught and fixed before this was considered done: the
first attempt created the venv at `uv sync`'s own default location
(`.venv`) and `mv`-ed it to `/opt/venv` to match the existing multi-
stage layout — this silently breaks every entry-point script in the
venv (`bin/uvicorn` etc.), since they embed an absolute shebang path
back to their *original* location; moving the directory doesn't update
it. Confirmed by direct reproduction (`exec /opt/venv/bin/uvicorn: no
such file or directory` at container start) and fixed by pointing uv at
`/opt/venv` directly via `UV_PROJECT_ENVIRONMENT` instead of creating-
then-moving.

**Scope note**: only the production Docker image now installs from the
lockfile. `.github/workflows/ci.yml`'s own "Install Dependencies" step
(`uv pip install --system -e . --group dev`) still re-resolves fresh on
every CI run, unchanged — deliberately not touched this pass, since
verifying a CI workflow change actually works requires running it on
GitHub Actions, which this environment cannot do, and getting it wrong
would silently break every future CI run. The production image (what
actually ships) was the higher-value, verifiable target; CI's own
reproducibility is a smaller, real, still-open gap.

3.3 [MEDIUM] CI/CD had no secret scanning, no container scanning, and
Admin Web had no dependency scanning (security.md §75)

Backend Python dependencies were already scanned (`pip-audit`, existing
before this pass); nothing else in security.md §75's list existed.
Added to `.github/workflows/ci.yml`:

- **Secret scanning** — a new `secret-scanning` job running Gitleaks
  (`gitleaks/gitleaks-action@v2`) against the full checked-out history
  (`fetch-depth: 0`), not just the working tree.
- **Container image scanning** — a new `container-scan` job that builds
  the real production image (`apps/backend/Dockerfile`, the same one
  §3.2 above verified runs correctly) and scans it with Trivy
  (`aquasecurity/trivy-action@0.28.0`), failing on CRITICAL/HIGH
  findings. **Actually run, not just written** — pulled and ran the
  real `aquasec/trivy` image against the real built
  `vistaar-backend` image via Docker directly (this environment has no
  GitHub Actions runner, but does have Docker). First result: 18
  CRITICAL/HIGH findings, all in `python:3.12-slim`'s own OS packages
  (gzip, perl-base, libsqlite3-0, etc.), zero in the application's own
  Python dependencies — and all 18 had no fixed version published yet
  (Trivy's own "Fixed Version" column empty for every one). Configuring
  the job to fail on those would have meant permanently red CI from day
  one, over nothing actionable. Added `ignore-unfixed: true` and
  re-ran the identical real scan against the identical image: zero
  findings — confirmed this doesn't just hide the problem, it correctly
  excludes only the unfixable-today findings while still catching
  anything genuinely fixable (including a future vulnerability in the
  app's own dependencies, the moment a fix exists).
- **Admin Web dependency scanning** — `npm audit --audit-level=high`
  added to the existing `admin-web-checks` job (parity with the
  backend's pre-existing `pip-audit` step).

**Honesty note, matching deployment-runbook.md's own "verified vs.
reviewed by reading" split**: the full workflow YAML was validated as
structurally correct (`yaml.safe_load`, parses cleanly, 5 jobs) but
**not run as an actual GitHub Actions workflow** — this environment has
no runner for that. Two of the three new checks were still verified for
real by running the equivalent tool directly, outside GitHub Actions:
`npm audit --audit-level=high` was run for real in `apps/admin-web`
(`found 0 vulnerabilities`), and the Trivy container scan was run for
real via Docker, as described above. Only the Gitleaks secret-scanning
job is genuinely unverified — no local Gitleaks binary was available to
test against, and its exact licensing terms for this repo's plan/
visibility were not checked either; if that job fails on a licensing
error rather than an actual secret finding, that's the first thing to
check (flagged directly in the workflow file's own comment). Flutter/
Dart has no equivalent dependency-vulnerability-scanning action this
review found to be as mature/established as `pip-audit`/`npm audit` —
left as a known, named gap rather than added as a step that might not
meaningfully do anything.

3.4 [LOW] No Kubernetes-level container permission restrictions
(security.md §74)

`backend-deployment.yaml`/`celery-worker-deployment.yaml` had no
`securityContext` at all — the non-root user was enforced only by the
image's own Dockerfile `USER` directive, with nothing independently
verifying that at the Kubernetes level. A future image regression that
accidentally reverted to running as root would have gone uncaught.

Fixed: added pod-level `securityContext: {runAsNonRoot: true}` and
container-level `securityContext: {allowPrivilegeEscalation: false,
capabilities: {drop: [ALL]}}` to both Deployments. Structurally
validated (`yaml.safe_load`); **not** run against a real cluster — this
environment has no reachable Kubernetes cluster, matching deployment-
runbook.md §6's own already-documented limitation.

Deliberately did **not** set `readOnlyRootFilesystem: true`, despite
confirming the application code itself has no runtime disk-write path
(a repo-wide grep found exactly one `open()` call anywhere in
`apps/backend/src`, and it's a read of a credentials file, not a
write) — third-party libraries (boto3, httpx, sentry-sdk, uvicorn
itself) may still write to `/tmp` for reasons this review did not
exhaustively trace, and there is no reachable cluster to actually
confirm the pod starts cleanly with it enabled. Flagged in the
manifest's own comment as a real, low-risk-to-verify next step once a
real cluster exists, not silently assumed safe.

4. What this pass does not do

- Does not change the P2P ride-fare model, customer penalty collection,
  or touch iOS/Apple work.
- ~~Does not decide the presigned-PUT-vs-POST question~~ — resolved
  2026-09-03, see §3.1 and ADR-0065.
- Does not change CI's own dependency-install reproducibility (§3.2's
  scope note) — the production image is fixed, CI's own environment
  is not, deliberately, pending an actual GitHub Actions run to verify
  any change to it.
- Does not add a Flutter/Dart dependency-vulnerability scan — no
  established, mature tool for this was found; not faked.
- Does not run any of the new CI jobs for real — verified structurally
  only (§3.3/§3.4's own honesty notes).
