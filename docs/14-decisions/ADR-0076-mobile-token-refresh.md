ADR-0076 — Mobile Token Refresh

Status: Accepted and implemented (2026-09-07)
Date recorded: 2026-09-07
Deciders: Closes a gap this app's own code has explicitly documented
since its first login screen was built: `AuthSession.restore()`'s doc
comment and `ApiClient`'s own class doc comment both state "no token-
refresh logic exists... re-login is the only path back in." The backend
side of this was never missing — `POST /api/v1/auth/refresh`
(modules/identity/router.py) has existed and been fully tested this
whole time; nothing in the app ever called it. Same shape of gap as
ADR-0072/0073/0074: a real, already-built, already-tested capability
with no mobile caller — picked up as the next highest-priority item
once Phase 15/16 (this session's own preceding work) turned out to have
nothing further buildable.

1. Context

`AuthApi.verifyOtp()` already parses and returns `refreshToken` from the
login response; `AuthSession` already stores it in memory and persists
it via `TokenStorage`. It was captured and carried around everywhere,
and used nowhere. Two concrete symptoms:

- **Mid-session**: once the access token's `expires_in` (a matter of
  minutes-to-hours, not days) elapses while the app is open, every
  subsequent API call fails with `AUTH_INVALID` (401) forever, even
  though the user is still genuinely logged in and a live refresh token
  sits unused right next to it.
- **Cold start**: `AuthSession.restore()` compares only the *access*
  token's own expiry (`StoredSession.isExpired`) and, if it's passed,
  discards the *entire* session — including a refresh token that is
  very likely still valid (refresh tokens live for
  `identity_settings.refresh_token_expire_days`, materially longer than
  an access token's own lifetime) — forcing a full re-login on every
  app relaunch past that window.

Refresh tokens are single-use and rotated on every call
(`IdentityService.refresh()`: `self._sessions.revoke(session.id)` then
issues a brand new pair) — a real design constraint this ADR's
implementation has to hold correctly, not an incidental detail.

2. Decision

- **`AuthApi.refresh(refreshToken)`** — new method, `POST /api/v1/auth/
  refresh`, `{"refresh_token": "..."}` → the same `AuthTokens` shape
  `verifyOtp()` already returns (a fresh access token AND a fresh,
  rotated refresh token — both must be persisted together, never just
  the access token half).
- **`ApiClient.onAuthInvalid`** — a new, optional, mutable field:
  `Future<String?> Function()?`. Every one of `get()`/`post()`/
  `patch()`/`delete()` now goes through a shared `_withAuthRetry()`
  wrapper: on an `AUTH_INVALID` `ApiException` (and only that code —
  `AUTH_REQUIRED`, "no token sent at all," is never retried, since
  there is nothing to refresh from context), call `onAuthInvalid()`
  once; if it returns a new access token, retry the original request
  exactly once with it; if it returns `null` (refresh itself failed) or
  `onAuthInvalid` isn't set at all (construction-time default, and every
  test's own `ApiClient`), the original `AUTH_INVALID` propagates
  exactly as before this ADR — no behavior change for any caller that
  doesn't opt in.
- **`AuthSession._refreshTokens()`** (private, wired to `ApiClient.
  onAuthInvalid` at construction, since `AuthSession` is already
  created with `context.read<ApiClient>()` available earlier in
  `main.dart`'s provider list) — single-flight: a `Future<String?>?`
  in-flight guard means concurrent callers (several screens' API calls
  all hitting `AUTH_INVALID` around the same moment) share one real
  `/refresh` call and its result, rather than each spending the same
  now-single-use refresh token and all but one failing. A successful
  refresh reuses `signIn()` unchanged (updates in-memory state,
  persists via `TokenStorage`, notifies listeners) — the exact same
  path a fresh login already takes, so there is no second persistence
  code path to keep in sync. A failed refresh calls `signOut()` for
  real (the refresh token itself is invalid/expired/revoked, or the
  account is now suspended) — `HomeRouter`'s existing "signed out ->
  RoleSelectionScreen" reaction handles the rest unchanged.
- **`AuthSession.restore()`** — an access-token-expired stored session
  now attempts one refresh (via the same `_refreshTokens()`) before
  falling back to clearing storage; a stored session's own refresh
  token being *itself* expired/invalid still ends in the same "clear
  and re-login" outcome as before, just one real network round-trip
  later, not assumed from the access token's timestamp alone.

3. What this ADR explicitly does not do

- Does not add proactive/background refresh (refreshing shortly before
  expiry, on a timer) — purely reactive, on an actual `AUTH_INVALID`.
  A background timer is a reasonable future enhancement but adds
  lifecycle complexity (app backgrounded/foregrounded, timer
  cancellation on sign-out) this bounded fix doesn't need to solve the
  stated gap.
- Does not change `POST /api/v1/auth/refresh`, `IdentityService.
  refresh()`, or the rotation/revocation behavior at all — backend-side
  was already correct and fully tested.
- Does not retry more than once — a second `AUTH_INVALID` after a
  successful refresh (which should be structurally impossible
  immediately after a fresh access token, barring near-simultaneous
  revocation) surfaces as a real error rather than looping.

4. Verification

Widget/unit tests (mirroring this app's existing MockClient/fake
conventions): a request that gets `AUTH_INVALID` once, refreshes, and
succeeds on retry; a request whose refresh itself fails surfaces the
original error and signs the session out; two concurrent `AUTH_INVALID`
failures trigger exactly one real `/refresh` call, not two; `restore()`
with an expired access token but a working refresh token restores the
session instead of forcing re-login; `restore()` with no working
refresh token still clears and returns to role selection, as before
this ADR. Full mobile suite run after — see this task's own completion
report for the exact count.
