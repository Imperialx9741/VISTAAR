VISTAAR — Security Review, Pass 1

Date: 2026-09-02
Reviewer: Claude Code (code-level review, not a substitute for an external
audit or penetration test — see §7 below)
Scope: `apps/backend/src`, checked against every control `docs/08-security/
security.md` defines. This is a targeted first pass over the highest-risk
categories (authentication, secrets, financial concurrency, rate limiting,
logging/monitoring) — not yet an exhaustive line-by-line audit of all 90
sections. §6 lists what a fuller pass 2 still needs to cover.

1. Summary

| # | Finding | Severity | Status |
| :-- | :-- | :-- | :-- |
| 1 | `JWT_SECRET` placeholder could silently reach production | HIGH | **Fixed** |
| 2 | Sentry could capture `Authorization`/`Cookie` headers | MEDIUM | **Fixed** |
| 3 | Rate limiting covers only OTP request/verify | HIGH | **Fixed** (2026-09-02, see §4 addendum) |
| 4 | OTP sent as an MSG91 URL query parameter | LOW / INFORMATIONAL | Open — likely unavoidable |
| 5 | Admin login brute-force protection | — | Confirmed clean, no action needed |
| 6 | Wallet concurrency control | — | Confirmed clean, no action needed |
| 7 | Hardcoded secrets, CORS wildcard, security headers | — | Confirmed clean, no action needed |
| 8 | Payment gateway / cash-confirmation controls (§27–32) | — | N/A — see addendum below |

2. Findings — fixed this pass

2.1 [HIGH] `JWT_SECRET` placeholder could silently reach production — FIXED

`core/config.py` defaults `JWT_SECRET` to a fixed placeholder string
(`"placeholder_jwt_secret_key_minimum_32_characters_long"`), committed in
this public source file. `Settings.validate()` only rejected an *empty*
value — a deployment that started without explicitly overriding the
environment variable would boot successfully signing every access and
refresh token with that publicly-known value. Since this backend's
authentication is JWT-based (`Authorization: Bearer <token>`), anyone who
has read this repository could forge a valid token for any account,
including `ADMIN` — a full authentication bypass, not a theoretical one.
Nothing gated this by `APP_ENV`, so `APP_ENV=production` alone would not
have caught it either.

Fix: `validate()` now rejects the placeholder value outright whenever
`APP_ENV != "development"` (`core/config.py`). Local development keeps the
existing convenience of never having to set `JWT_SECRET` by hand; every
other environment (`testing`, `staging`, `production`) now fails to start
unless a real secret is supplied. 3 new tests in `tests/test_config.py`
(`test_placeholder_jwt_secret_rejected_outside_development`,
`test_placeholder_jwt_secret_still_allowed_in_development`,
`test_real_jwt_secret_allowed_in_production`); `test_custom_environment_
overrides` updated to supply a real secret now that it exercises
`APP_ENV=production`.

**Action still required from the operator**: generate a real, randomly
generated `JWT_SECRET` (e.g. `openssl rand -hex 32`) and set it via the
real secret manager before any staging/production deployment — this fix
only prevents the silent placeholder failure mode, it does not supply the
real value.

2.2 [MEDIUM] Sentry could capture `Authorization`/`Cookie` headers — FIXED

`main.py`'s `sentry_sdk.init()` call did not set `send_default_pii` or a
`before_send` hook. sentry-sdk 2.68.1 (the installed version) defaults
`send_default_pii` to `False` and has a built-in `EventScrubber` that
redacts common sensitive key names by default — so this was not a
confirmed active leak — but the intent was never stated explicitly in this
codebase, which is exactly the kind of implicit-safe-default security.md
§2 ("secure by default") asks not to rely on silently.

Fix: `send_default_pii=False` is now explicit, plus a new `before_send`
hook (`_scrub_sensitive_sentry_data`) that redacts `Authorization`/
`Cookie` header values on every outgoing event as defense-in-depth, in
case a future change ever flips `send_default_pii` without re-checking
this file. 4 new tests in `tests/test_main.py`
(`TestScrubSensitiveSentryData`).

This is currently dormant either way — `SENTRY_DSN` is empty by default
(sentry-sdk's own documented "disabled" state) and no real Sentry account
exists in this environment; the fix takes effect the moment a real DSN is
configured.

3. Findings — confirmed clean (no action needed)

- **Admin login brute-force protection (security.md §21)**: administrative
  accounts authenticate through the same phone+OTP flow as customers/
  drivers (`modules/identity/router.py`) — there is no separate
  password-based admin login path. The existing OTP rate limiter
  (`modules/identity/rate_limit.py`, Redis-backed, phone + IP dimensions,
  resend cooldown) therefore already covers admin login; this is not a
  separate gap.
- **Wallet concurrency (security.md §24)**: `modules/wallet/repositories.py`
  uses `SELECT ... FOR UPDATE` (`with_for_update()`) before every mutation
  — real row-level locking, not an assumed-safe read-then-write.
  `shared/idempotency.py` is wired through wallet's own service/domain
  layer, matching security.md §22's idempotency requirement.
- **Hardcoded secrets**: a repository-wide grep for inline
  `key`/`secret`/`password`/`token` string literals found no real-looking
  values — only the already-known `fake_*`/`placeholder_*` scaffold
  defaults `.env.example` documents.
- **CORS**: `CORS_ALLOWED_ORIGINS` defaults to a specific origin
  (`http://localhost:3000`), never a wildcard; `allow_credentials=False`
  is deliberate (bearer-token auth, not cookies — see `main.py`'s own
  comment).
- **Security headers (security.md §64)**: `SecurityHeadersMiddleware`
  (ADR-0036) applies CSP/`X-Content-Type-Options`/`Referrer-Policy`/HSTS/
  frame restrictions to every response except the interactive-docs paths,
  by design (documented in the ADR).
- **SQL injection**: every query surveyed in `wallet`/`ride`/`identity`
  repositories uses SQLAlchemy's ORM/`select()` construct — no raw string
  concatenation into SQL was found in the modules checked this pass.

4. Open finding requiring a decision

4.1 [HIGH] Rate limiting covers only OTP request/verify

security.md §20 requires rate limiting on: OTP requests, OTP verification,
login attempts, ride creation, ride cancellation, ride offers, fare
changes, payment creation, wallet recharge, cash confirmation, promotion
usage, referral attachment, support messages, evidence uploads, and admin
APIs.

Verified against the actual code: only `modules/identity/rate_limit.py`
(OTP request/verify, phone + IP dimensions) exists. None of the other
~13 categories have any rate limiting — not in application code
(no equivalent module elsewhere), and not at the infrastructure edge
(`infrastructure/kubernetes/backend-ingress.yaml` has no
`nginx.ingress.kubernetes.io/limit-rps` or equivalent annotation, and no
API gateway/WAF layer is configured anywhere in `infrastructure/`).

This is real, exploitable exposure today: nothing stops a scripted client
from hammering `POST /api/v1/rides`, admin endpoints, evidence uploads, or
any other authenticated endpoint at unlimited request volume once a
session exists — the rate limiter this codebase already has does not
generalize to them automatically.

Why this is flagged as "needs a decision" rather than fixed outright: two
materially different architectures satisfy §20, and this codebase has not
chosen between them yet —

- **Application-level**, extending the existing Redis-backed
  `OtpRateLimiter` pattern (or a new generic per-endpoint/per-user
  limiter) into a shared dependency every router composes — more
  precise (can rate-limit by `customer_id`/`driver_id`, not just IP), more
  code to write and test per endpoint category.
- **Edge-level**, via the Kubernetes ingress or a fronting API gateway
  (rate-limit annotations, or a dedicated component) — one shared
  mechanism, less precise (typically IP/route-based only, no easy access
  to the authenticated user identity), and depends on the real ingress
  controller/gateway choice for the eventual cloud deployment (§4 of the
  earlier production-readiness conversation) — not yet decided.

**Recommendation**: application-level, reusing the existing Redis
infrastructure, for the endpoints where the true business identity
(`customer_id`/`driver_id`) matters (ride creation/cancellation, payment,
promotion/referral, wallet recharge) — edge-level as a second, coarser
layer once the real ingress is chosen, for defense-in-depth against
unauthenticated/pre-session abuse. This is a real, non-trivial
implementation task (a shared dependency + wiring into ~13 endpoint
categories + tests), not a one-line fix like §2's two findings — flagging
it here rather than silently building it, since it touches request
handling on financially-sensitive endpoints project convention treats as
needing the same "plan first" discipline as a new API contract.

4.1 Addendum, 2026-09-02 (same day) — FIXED

Implemented exactly the recommendation above: application-level, Redis-
backed, per authenticated account. See ADR-0061 for the full design and
`shared/rate_limit.py` for the generic mechanism (a fixed-window
counter, generalizing `modules/identity/rate_limit.py`'s own
already-proven algorithm). Every category from security.md §20 that has
a real corresponding endpoint is now covered — ride creation,
cancellation, offer accept/reject, pickup/destination change, wallet
recharge (create + confirm), promotion redemption, referral attach,
support case creation, evidence-upload URL requests, and a blanket
per-admin-account limit across every `/api/v1/admin/*` route. "Payment
creation" and "cash confirmation" remain N/A — neither endpoint exists
under the approved P2P ride-fare model (§8 above). "Login attempts" is
already covered by the existing OTP verify rate limiter (admin
authenticates through the same OTP flow — confirmed in §3 above).

Edge-level rate limiting (the second, coarser layer this section's
original recommendation also named, for unauthenticated/pre-session
abuse) remains **not** implemented — still blocked on the real ingress
controller/gateway choice (deployment-runbook.md §5.6), unchanged by
this pass.

Tests: 6 new unit tests (`tests/test_rate_limit.py`, the generic
mechanism against real Redis) + 7 new real-HTTP integration tests
(`tests/test_rate_limiting_api.py`, a representative endpoint per
account type and per composition style — not every single rate-limited
endpoint individually, since the wiring pattern is mechanically
identical everywhere it was applied; see that file's own docstring).
Full backend suite: 1360 passed, 5 skipped, 0 failed (was 1353),
ruff/mypy clean.

5. Findings — informational, no action taken

5.1 [LOW] OTP sent as a URL query parameter to MSG91

`modules/identity/sms.py`'s `Msg91SmsProvider.send_otp()` sends the OTP
value as an HTTP query parameter (`params={"otp": otp, ...}`) to MSG91's
own documented v5 OTP API. This backend's own code never logs it (verified
— only `response.text`/exception messages are logged on failure, never the
outgoing request). The residual risk is outside this codebase's control:
any intermediate infrastructure between this backend and MSG91 (a
corporate egress proxy, an API gateway with full-URL access logging) could
capture the OTP in plaintext logs, since it's part of the request URL, not
the body. This is dictated by MSG91's own documented API shape (already
flagged as unverified against a live account, ADR-0031 Decision 1) — not
something fixable from this side without violating their interface.
Worth a note in the real deployment's egress-logging configuration once
one exists, not a code change here.

6. Not yet covered — pass 2

**Update, 2026-09-03: pass 2 is done — see
`security-review-pass-2-2026-09-03.md`.** The list below is preserved
as pass 1 originally wrote it, for the record; every item on it was
addressed in that follow-up document (IDOR/mass-assignment/input-
validation/promotion-referral confirmed clean, file-upload size limit
and dependency pinning/CI scanning/container permissions fixed).
Dependency vulnerability scanning (§73) and container security (§74)
below refer to backend-only gaps that existed at the time this was
written — pass 2 also covers Admin Web's own dependency scanning,
which this original list didn't separately call out.

This pass focused on authentication, secrets, financial concurrency,
CORS/headers, and monitoring configuration. Not yet systematically
audited against the real code:

- Object-level authorization / IDOR spot checks across every router
  (§8, §52) — the pattern was confirmed correct in the endpoints read
  incidentally during this pass, but not exhaustively checked route by
  route.
- Mass assignment protection (§53) — Pydantic request-schema field
  allow-listing, across every router.
- Input validation (§54–56) — monetary amount representation
  (integer/Decimal vs. float) across every module that touches money.
- File upload security (§16–17) — evidence upload MIME/size/content
  validation.
- Promotion/referral replay and race-condition protection (§37–38) —
  code-level check, not just the domain tests already in the suite.
- Dependency vulnerability scanning (§73) and CI/CD security scanning
  (§75) — `.github/workflows/ci.yml` has not yet been checked for
  secret-scanning/dependency-scanning/SAST steps.
- Container security (§74) — the backend `Dockerfile`.
- GPS anomaly detection (§13) and fraud prevention (§67–70) — these are
  largely unbuilt by design (business thresholds are explicitly TBD per
  PRD.md/business-rules.md), not a code defect to find.

7. What this review is not

This is a code-level review by an AI coding assistant working from the
same repository the application ships from — it is not a substitute for:
an external penetration test, a review by a human security engineer
against a running deployment, a dependency/CVE scan against the exact
pinned versions in `pubspec.lock`/`requirements`/`package-lock.json`, or
a compliance audit (PCI-DSS scope will apply once a real payment gateway
is integrated). `security.md` itself stays `Status: Draft` — this review
does not change that; it is one input toward eventually closing it out,
not a replacement for it.

8. Addendum, 2026-09-02 (same day) — Payment Gateway Security (§27–32)
   correction

Row 8's original "N/A — no payment module exists yet" was accurate but
incomplete: this is not merely unbuilt, pending work — VISTAAR's
approved payment model (ADR-0025, ADR-0026) means no *ride-fare*
gateway will ever exist at all (the customer pays the driver directly,
peer-to-peer; VISTAAR is never in that path). `security.md` §27-32
described the pre-ADR-0025 model in detail and had never been
reconciled — ADR-0025 §5 explicitly flagged this as a known,
unaddressed contradiction. Both sections there, and the `payment.*`
event family in `event-contracts.md` §14 (same ADR-0025 §5 flag), were
annotated superseded/corrected in this pass (2026-09-02) — see
`docs/02-business/known-functional-gaps-2026-09-02.md` for what
payment-related work is actually still real and open: an
outstanding-penalty display (ADR-0026, buildable now, no gateway
needed) and two separate still-undecided gateway integrations (driver
wallet recharge; customer penalty collection).
