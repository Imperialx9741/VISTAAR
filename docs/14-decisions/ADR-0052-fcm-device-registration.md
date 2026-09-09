ADR-0052 — Push Notifications: Device Registration + FCM Provider Wiring

Status: Accepted and implemented (2026-08-28) — owner decision ("FCM
device registration API → YES"), resolving the gap ADR-0034 recorded:
"Push (FCM, owner-approved) has no device-token data source anywhere in
this codebase — registering one is itself a new, undocumented endpoint,
so Channel.PUSH raises ChannelNotAvailableError rather than being
faked."

Date recorded: 2026-08-28.
Deciders: Project owner (explicit written decision, 2026-08-28).

1. Context

FCM itself was already owner-approved as the push provider (ADR-0034
Decision 2 records this). What blocked building it was purely the
missing device-token endpoint — a new public API contract, the same
§0.3 gate this codebase stops for everywhere else. The owner's decision
resolves that gate; a real Firebase project/credential is a separate,
still-outstanding dependency (tracked in the owner's own "give me the
credential when this is ready" list) — this ADR builds everything up to
that point, the same "wired, not verified against a live account"
scope ADR-0031 originally gave MSG91/S3.

2. Decision 1 — Device registration is a generic identity-agnostic
   capability, one endpoint, not three

Any account type (customer, driver, admin — ADR-0050's SOS notification
already sends to admins) can register a device. Rather than duplicating
the same logic under /api/v1/customers/me/devices,
/api/v1/drivers/me/devices, /api/v1/admin/me/devices, one endpoint
lives in modules.notification (the domain that already owns delivery)
and is reachable by any authenticated account via get_current_account —
the same "generic capability, gated by account type only where it
actually needs to be" shape ADR-0051 already established for MFA.

```
POST   /api/v1/notifications/me/devices     Register/refresh a token
DELETE /api/v1/notifications/me/devices/{token}   Unregister
```

Register is an upsert keyed on the token itself (globally unique per
app install) — re-registering the same token (e.g. app reopened) just
refreshes `updated_at` and re-associates it with whichever account is
currently authenticated, which correctly handles a device being logged
out of one account and into another without a stale row pointing at
the wrong user.

3. Decision 2 — Schema

```
CREATE TABLE notification.device_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    platform VARCHAR(10) NOT NULL,  -- ANDROID | IOS | WEB
    token TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX ON notification.device_tokens(token);
CREATE INDEX ON notification.device_tokens(user_id);
```

`user_id` is a bare UUID, not a foreign key — the same "no single users
table" reasoning `notification.deliveries.user_id`/
`notification.preferences.user_id` and `penalty.penalties.user_id`
already established (a user may be a customer, driver, or admin; those
identities live in three different tables sharing only
`identity.accounts.id`, not a single referenceable users table).

4. Decision 3 — PushProvider abstraction, mirroring SmsProvider exactly

`modules/notification/ports.py` gains a `PushProvider` Protocol
(`async def send(self, token: str, *, title: str, body: str) ->
str | None`), with two implementations exactly mirroring
`modules/identity/sms.py`'s `DevConsoleSmsProvider`/`Msg91SmsProvider`
split:

- `DevConsolePushProvider` — logs the push instead of sending one,
  always available, no credential. Default (`PUSH_PROVIDER=dev`).
- `FcmPushProvider` — a direct integration against Firebase's
  documented HTTP v1 API and OAuth2 service-account JWT-bearer flow,
  via `httpx`+`pyjwt` (not the official `firebase-admin` Python SDK —
  corrected 2026-09-03; an earlier version of this line claimed
  `firebase-admin` was "added as a dependency," which was never true —
  confirmed directly: it's neither in `pyproject.toml` nor importable
  in this environment. The hand-rolled HTTP v1 client is what
  `modules/notification/push.py` has always actually implemented; this
  was a stale/incorrect claim in this ADR, not a code change), selected
  via `PUSH_PROVIDER=fcm`. Requires `FCM_SERVICE_ACCOUNT_JSON` (a path
  to the Firebase service account credentials file) — not present in
  this environment at the time this ADR was written, so this path was
  wired but unverified against a live Firebase project, the same
  disclosed caveat ADR-0031 gave MSG91's own OTP integration before
  real credentials existed. Verified for real 2026-09-03 — see §9.

5. Decision 4 — NotificationService.send()'s PUSH branch stops
   unconditionally raising

Before this ADR, `channel is Channel.PUSH` always raised
`ChannelNotAvailableError` — there was nothing to send to and no
provider to send with. Now: if the user has no registered device token,
`send()` returns `None` (same soft no-op as a customer with SMS
disabled via preferences — an expected, common case, not an error). If
a token exists, it attempts a real send via whichever `PushProvider` is
configured — `DevConsolePushProvider` by default, so PUSH is now a real,
exercisable channel in dev/test exactly like SMS already is, not merely
faked. `Channel.WHATSAPP` is UNCHANGED — still raises
`ChannelNotAvailableError` unconditionally; the owner's decision batch
did not touch WhatsApp (BSP still unpicked, per the owner's own earlier
instruction).

6. What this does NOT resolve

- A real Firebase project/service account credential — still needed
  before `FcmPushProvider` can actually deliver anything; `PUSH_PROVIDER`
  stays `dev` until the owner supplies one.
- Multi-device fan-out semantics beyond "one row per token" — a user
  with three devices gets three rows and (once FCM is real) three
  pushes per event; no dedup/batching logic beyond what already exists
  per-channel in `Delivery`'s own idempotency key.
- WhatsApp — unaffected, unchanged, still blocked on BSP selection.

7. Addendum, 2026-09-01 — mobile client-side FCM integration

The owner created the Firebase project ("VISTAAR Production", project
ID `vistaar-production-3a79a`) and ran FlutterFire configure against
`apps/mobile`'s existing single Flutter app (one project, one app, both
User and Sarthi roles — no separate per-role registration). This
resolves the mobile half of this ADR's device-registration flow: a new
`PushNotificationManager` (`apps/mobile/lib/core/notifications/
push_notification_manager.dart`) now requests permission, fetches a
real FCM token, and registers/unregisters it through the
`POST`/`DELETE /api/v1/notifications/me/devices` endpoints this ADR
defined, composed on top of the existing, unmodified `NotificationApi`.
See `docs/16-mobile/mobile-app-implementation-plan.md` §6.3 for the
full write-up, including the remaining iOS-only gaps (no
`GoogleService-Info.plist`/`Podfile`, Xcode capability, or APNs key
yet — all four need a real Mac/Xcode/Apple Developer account).

At this point §6's first item still stood: the backend had no
service-account credential for `FcmPushProvider` to actually send
through, so `PUSH_PROVIDER` stayed `dev` everywhere. A mobile device
could register a real token; nothing server-side could deliver to it
yet.

8. Addendum, 2026-09-01 — backend-side FCM credential configured

The owner supplied the Firebase Admin SDK service-account credential
for the same "VISTAAR Production" project, stored outside this repo
(never committed, per this codebase's standing secrets discipline —
same treatment as MSG91/S3/Sentry). `apps/backend/src/modules/
notification/push.py`'s `FcmPushProvider`/`get_push_provider()` needed
no code change — both already existed, built against Firebase's
documented HTTP v1 API and OAuth2 service-account JWT-bearer flow (§5),
and the real credential file was verified to structurally match what
that code expects (`client_email`/`private_key`/`project_id` present,
`project_id` matches `vistaar-production-3a79a`) without ever reading
or printing its contents in full. A new test,
`test_get_push_provider_returns_fcm_provider_when_configured`
(`tests/test_notification_push.py`), fills the one real gap in this
file's existing coverage — the success path (`PUSH_PROVIDER=fcm` plus a
loadable credentials file actually constructing a working
`FcmPushProvider`) had never been exercised, only the dev-default and
misconfigured-fcm cases had.

The **local, git-ignored** `apps/backend`-adjacent root `.env` (created
this session — none existed before) now sets `PUSH_PROVIDER=fcm` and
`FCM_SERVICE_ACCOUNT_JSON` to that credential's path, so a locally-run
backend now sends real pushes via FCM rather than logging them.
**Production/Kubernetes deployment is unaffected** —
`infrastructure/kubernetes/backend-configmap.yaml` still hardcodes
`PUSH_PROVIDER: "dev"`, and `backend-secret.example.yaml`'s own comment
already documents the intended path (mount the credential as a Secret
volume, point `FCM_SERVICE_ACCOUNT_JSON` at the mounted path, flip the
configmap to `"fcm"`) — that mount/flip is real, separate deployment
work this addendum does not do, since a Windows-local file path is
meaningless inside a cluster. No real push has been verified
end-to-end against a live device yet; only construction against the
real credential and the mocked-transport `send()` path (§5) have been
exercised.

9. Addendum, 2026-09-03 — real OAuth2 authentication and a real send()
   call verified against live Google/FCM servers

Closes §8's own remaining gap ("no real push has been verified... only
[mocked] construction... have been exercised") — for the two parts of
the pipeline this environment can actually exercise without a live
mobile device registered:

- **OAuth2 authentication**: `FcmPushProvider._get_access_token()` was
  called for real, using the real credential file (never read into
  this conversation or printed) — Google's real OAuth2 token endpoint
  returned a genuine, valid access token. Definitive proof the service-
  account credential itself is valid and accepted by Google.
- **The `messages:send` call**: sent once, with a syntactically-
  plausible but deliberately non-real registration token (no live
  mobile device is registered anywhere in this environment — the
  mobile-side integration §7 describes exists in the app, but nothing
  has run it against a real device during this backend-only session).
  FCM's real v1 API responded with a structured
  `google.firebase.fcm.v1.FcmError` / `INVALID_ARGUMENT` specifically
  about the registration token — not an authentication error (401/403),
  which confirms the entire authenticated pipeline (JWT signing → OAuth2
  exchange → authenticated HTTPS call → FCM processing the request)
  works end-to-end. The only thing not verified is delivery to an
  actual device, which requires a real mobile client running
  `PushNotificationManager` (§7) and registering a real token — outside
  this session's own scope (backend-only, no device available).
  **Owner decision, 2026-09-03: explicitly not treated as completed —
  recorded as a tracked production-readiness/E2E task for later, not
  just an informal caveat.** See
  `docs/10-testing/testing-strategy.md` §105's own new checklist item.
- No test in `tests/test_notification_push.py` was changed for this —
  per the owner's own instruction, automated tests must not depend on
  live credentials, and none of them do; this was a one-off, manual
  verification script (not committed, deleted after use), not a new
  permanent test.
- `PUSH_PROVIDER=fcm` in the local `.env` is unchanged (was already set
  since §8) — nothing in this addendum touches production/Kubernetes
  configuration, which stays exactly as §8 already described (still
  `"dev"` in `backend-configmap.yaml`, a real, separate deployment task
  once a live cluster exists to mount the credential into).
