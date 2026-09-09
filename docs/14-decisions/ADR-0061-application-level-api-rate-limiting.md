ADR-0061 — Application-Level API Rate Limiting

Status: Accepted — owner directive ("Continue all Android, backend,
Admin Web, integrations, security, testing, and production-readiness
work that can proceed independently," 2026-09-02), acting on
security-review-2026-09-02.md finding 4.1 (HIGH, previously open).
Implemented the same day.
Date recorded: 2026-09-02
Deciders: security-review-2026-09-02.md's own recommendation, adopted
without further owner input needed — security.md §89 already lists
"Exact API rate limits" as engineering configuration, not a business
decision requiring a separate approval step, and the review itself
already framed application-level vs. edge-level as the one real
architectural choice, recommending application-level.

1. Decision

Every category security.md §20 lists that has a real, existing
endpoint is now rate-limited, application-level, per authenticated
account (`customer_id`/`driver_id`/admin account id) — not per IP, and
not at the infrastructure edge:

- Ride creation, ride cancellation (customer + driver cancel), ride
  offer accept/reject, pickup change, destination change.
- Wallet recharge (both create-order and confirm).
- Promotion redemption, referral attach.
- Support case creation.
- Evidence-upload URL requests (driver documents and GPS-dispute
  evidence share the same presigned-URL endpoint — see §3).
- Every `/api/v1/admin/*` endpoint, via one blanket per-admin-account
  limit rather than a per-endpoint one (see §4).

OTP request/verify keep their own pre-existing, already-tested
`RedisOtpRateLimiter` unchanged — this ADR extends the same fixed-
window-counter algorithm to every category that had none, it does not
replace what already worked. "Login attempts" (security.md §20) needed
no new code: every account type, including ADMIN, authenticates through
that same OTP flow (confirmed in security-review-2026-09-02.md §3), so
it was already covered.

2. Why application-level, not edge-level

security-review-2026-09-02.md §4.1 named both as real options and
recommended application-level specifically because it can key on the
true business identity (`customer_id`/`driver_id`), not just IP/route —
materially more precise for exactly the abuse pattern that matters here
(one authenticated account hammering an endpoint), and it needs no
dependency on which real ingress controller/API gateway the eventual
DigitalOcean deployment ends up using (still undecided —
deployment-runbook.md §5.6).

Edge-level rate limiting (IP/route-based, at the ingress or a fronting
gateway) remains valuable as a *second*, coarser layer specifically for
unauthenticated/pre-session abuse (e.g. hammering `POST /api/v1/auth/
otp/request` from many IPs, which the existing IP-dimension OTP limiter
already partly covers) — this ADR does not build that layer; it is
still blocked on the ingress/gateway decision, unchanged by this pass.

3. Design

`shared/rate_limit.py` — a generic Redis-backed fixed-window counter
(`RateLimiter.check_and_increment(key, limit, window_seconds)`,
`INCR` + `EXPIRE`), directly generalizing
`modules/identity/rate_limit.py`'s `RedisOtpRateLimiter` algorithm
rather than inventing a new one. `rate_limit_key(category, identity)`
builds `"ratelimit:{category}:{identity}"` — distinct categories never
share a counter for the same identity (a driver's wallet-recharge limit
is independent of their ride-offer-response limit).

Two composition styles, matching where each category naturally sits:

- **Explicit, per-handler** (every category except admin): each router
  handler calls `RateLimiter(redis_client).check_and_increment(...)`
  in its own `try/except RateLimitedError` block, near the top, before
  any state-changing work — the same "reject cheaply before real work"
  ordering `IdempotencyStore`/ADR-0058's low-balance gate already use in
  this codebase. On `RateLimitedError`, returns `429` with the standard
  envelope (`error.code = "RATE_LIMITED"`, api-contracts.md §49's
  existing code — reused, not a new one minted per category).
- **Blanket, router-level** (admin only): a single FastAPI dependency,
  `enforce_admin_api_rate_limit`
  (`modules/admin/dependencies.py`), composed once via `APIRouter(...,
  dependencies=[Depends(enforce_admin_api_rate_limit)])` in
  `modules/admin/router.py` — applies to every one of that router's
  several dozen endpoints with zero per-handler changes. Chosen over
  per-endpoint limits for admin specifically: "an admin operator is
  doing something abnormal across the whole API" is the real signal
  worth catching there, not a reason to hand-tune dozens of individual
  limits for routes that are mostly read/search endpoints anyway. This
  path raises a raw `HTTPException(status_code=429, detail="RATE_LIMITED")`
  instead of building the envelope itself — matching
  `require_account_type`'s own established convention for auth-layer
  dependency failures (401/403) in `modules/identity/dependencies.py`,
  since this dependency sits at that same layer, not inside a router
  handler body.

`shared/rate_limit.py` takes no dependency on `core.config` or
`shared.api_envelope` — limits/windows are passed in by each caller
(from `core/config.py`'s `RATE_LIMIT_*` settings), the same
configuration-as-parameters split `shared/pagination.py`'s own
docstring already documents and requires of `shared/` modules.

4. Evidence uploads — one endpoint, two document types

`POST /api/v1/drivers/me/uploads` (presigned-URL request) is the single
entry point both driver-document and vehicle-document evidence uploads
go through (confirmed directly — no separate vehicle-side upload
endpoint exists); the GPS-dispute evidence upload-url endpoint
(`POST /api/v1/rides/{ride_id}/gps-disputes/{dispute_id}/evidence/
upload-url`) is rate-limited the same way, independently. Both use the
`"evidence_upload"` category. The presigned-URL request is the actual
abuse surface (unlimited S3 presigned URLs), not the later document-
metadata submission — that's what's gated, not `POST /me/documents`.

5. What "Payment creation" and "Cash confirmation" map to

Neither has a real endpoint under the approved P2P ride-fare model
(ADR-0025/ADR-0026) — VISTAAR never collects the ride fare, so there is
no payment-creation or cash-confirmation flow to rate-limit. Genuinely
N/A, not an oversight (security-review-2026-09-02.md §8 already
established this same point for the broader "Payment Gateway Security"
sections). Wallet recharge — the one real payment-adjacent flow that
does exist — is covered.

6. Exact limits are configuration, not a business rule

Every `RATE_LIMIT_*` value (`core/config.py`, `.env.example`) is a
reasonable engineering-judgment default, explicitly the kind of
"implementation/configuration choice rather than an unresolved business
rule" security.md §89 already names for "Exact API rate limits" —
identical treatment to `modules/identity/config.py`'s own pre-existing
OTP rate-limit defaults. Not tuned against real production traffic
(none exists yet); revisit once real usage data is available. All
validated positive at startup (`Settings.validate()`), same pattern
every other numeric engineering setting in `core/config.py` already
follows.

7. Testing

6 new unit tests (`tests/test_rate_limit.py`) against real local Redis
(not a fake/mock client) — the fixed-window algorithm itself: requests
within the limit succeed, the request that exceeds it raises, a
rejected request stays rejected without resetting its own window
(cannot be evaded by retrying), and distinct categories/identities have
independent counters.

7 new real-HTTP/real-Postgres/real-Redis integration tests
(`tests/test_rate_limiting_api.py`) — a representative endpoint per
account type (customer, driver, admin) and per composition style
(explicit per-handler, and the structurally different admin blanket
dependency), each proving the real HTTP 429/`RATE_LIMITED` behavior and
that the limit is per-identity, not global (a second customer/driver/
admin has their own independent bucket). Deliberately not one dedicated
negative test per individual rate-limited endpoint — the wiring pattern
is mechanically identical everywhere else it was applied (ride
cancellation, both fare-change endpoints, promotion redemption,
referral attach), and those endpoints' own existing test files already
exercise the modified code path (just without a RATE_LIMITED-specific
assertion) via the full suite passing.

Full backend suite: 1360 passed, 5 skipped, 0 failed (was 1353 before
this ADR's tests, 1347 before item 3/Wallet Recharge's own tests
earlier the same day), ruff/mypy clean. No existing test's behavior
changed — every affected endpoint gained one new required
`redis_client` parameter (FastAPI-injected, invisible to any HTTP
caller) and one new early check that only ever fires when a real limit
is actually exceeded, which no pre-existing test does at the (generous)
default thresholds.

8. What this ADR does not do

- Does not implement edge-level/infrastructure rate limiting — still
  blocked on the real ingress/gateway choice (§2).
- Does not add a per-endpoint limit for every admin route — the
  blanket admin limiter is a deliberate, documented design choice (§3),
  not a shortcut standing in for per-endpoint limits not yet written.
- Does not change any business rule, the P2P ride-fare model, customer
  penalty collection, or touch iOS/Apple work in any way.
- Does not tune limits against real traffic — no real production usage
  data exists yet to tune against.
