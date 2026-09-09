ADR-0034 — Notification Domain Foundation (In-App + SMS)

Status: Accepted.
Date recorded: 2026-08-25.
Deciders: Project owner (channel set, provider approvals), via
AskUserQuestion earlier in this session — VISTAAR session, 2026-08-25.
Everything else decided under the owner's phase-level-autonomy grant;
the items below were real mandatory-stop conditions (roadmap §0.3), not
guessed past.

1. Context

The owner approved four notification channels — in-app, WhatsApp, push,
SMS — with push explicitly approved against Firebase Cloud Messaging
(FCM), and WhatsApp explicitly NOT to be built or given a chosen
provider yet ("First identify exactly what BSP setup/credentials are
required and prepare the integration plan. Do not implement or choose a
provider without my approval."). Before implementing, this task found
domain-design.md §20 and technical-architecture.md §46 already document
the Notification domain's responsibility, schema, and the list of
events it should eventually consume — down to `notification.
preferences`/`notification.deliveries` table shapes (database-design.md
§32). Three real gaps surfaced during that research, none of them
values-are-TBD gaps this ADR can resolve silently:

2. Decision 1 — No HTTP endpoint exists anywhere for Notification; none
   is invented here

api-contracts.md documents zero Notification endpoints — no `GET my
notifications`, no preferences read/write route, nothing. This is the
same §0.3 "new public API contract" stop condition ADR-0018
(Advertisement) and ADR-0021 (Driver Suspension/Reactivation) already
hit and declined to cross. The domain/service/repository layer below is
built fully and tested at the service layer, ready for whichever future
task gets a real endpoint documented to compose it into — same
treatment those two ADRs already established.

3. Decision 2 — Push (FCM) is scoped out of this task specifically: no
   device-token data source exists anywhere in this codebase

Sending a push notification needs a target device token. Nothing in
this codebase collects, stores, or exposes one: `identity.sessions.
device_metadata` is free-form text captured for session/logout tracking
(§5.3), not a structured FCM/APNs registration token, and no documented
endpoint anywhere accepts one from a client. Building the FCM *send*
call now would be code with no real token to ever call it with — the
same "flag the specific gap, don't invent past it" treatment ADR-0031
gave Admoto and Mapbox. This is genuinely a separate, larger task (a
device-token-registration endpoint is itself a new public API contract,
Decision 1's same stop condition) — not attempted here despite FCM
being an approved provider; the approval covers *which* push provider to
use once a real token source exists, not a mandate to build against a
non-existent one now.

4. Decision 3 — WhatsApp: requirements analysis only, per explicit
   instruction; no BSP chosen, no code written

The owner's own instruction already scopes this precisely: identify
what a BSP integration would need, do not implement or choose. See the
companion note delivered alongside this ADR (not a document change —
the owner asked for an analysis, not a docs update) for the concrete
findings: a WhatsApp Business API integration needs (a) a Business
Solution Provider account (Gupshup/Interakt/Twilio/etc. — the owner has
a WhatsApp Business account already but no BSP selected), (b) Meta's
own template pre-approval process for any outbound message content
(WhatsApp, like Indian SMS DLT, requires pre-registered message
templates — free-text outbound messages are rejected outside a 24-hour
customer-initiated session window), (c) a webhook endpoint for delivery
receipts/inbound replies, and (d) a phone-number-verification/
onboarding step with the chosen BSP. `notification.preferences.
whatsapp_enabled` (already documented) is left in the schema, unused by
any real send path, the same "documented column, no live caller yet"
treatment `pricing.fare_rules.per_minute` already gets.

5. Decision 4 — SMS reuses MSG91, generalized from OTP-only; template
   *content* is placeholder, explicitly flagged, not ratified copy

modules.identity.sms's `Msg91SmsProvider` only ever sent OTP codes via
MSG91's OTP-specific endpoint (`/api/v5/otp`). General notifications
need MSG91's separate transactional/promotional SMS API, which — like
WhatsApp and India's SMS regulation generally (DLT, the mandatory
telecom-registered-template system) — expects pre-registered template
content in production, not arbitrary free text; no DLT registration
exists in this environment, so this integration carries the exact same
"wired, not verified against a live account" flag ADR-0031 already gave
MSG91's OTP path. Message *wording* itself is nowhere documented (only
that the domain "owns... templates" — domain-design.md §20.2, no actual
copy). A small in-repo `template_key -> message` lookup is written as
explicitly-flagged placeholder content (illustrative, not approved
customer-facing copy) — the same treatment given engineering-judgment
values elsewhere (e.g. ADR-0033's route-deviation tolerance), since
getting exact wording right has no schema/API impact and is trivially
revised later, and building nothing at all serves no one.

6. Decision 5 — Delivery is synchronous, composed at the router; not a
   Kafka consumer

technical-architecture.md §46 describes the Notification service as
consuming a list of domain events (RideAccepted, DriverArrived, etc.)
over Kafka. No Kafka consumer exists anywhere in this codebase yet —
Phase 18's own status explicitly flags "Kafka consumers... remain
undone (need a real consumer module, not more engineering time)."
Building the first one is a separate, materially larger undertaking
(consumer groups, offset tracking, retry/DLT semantics) than this task
was asked to do. `NotificationService.send()` is instead composed
directly at the router, synchronously, immediately after the triggering
write commits — the same pattern every other cross-module composition
in this codebase already uses (PricingService, MatchingService, etc.),
and the same "no consumer, still published" acceptance this session has
already applied to every other documented-but-unconsumed event. Only a
small, explicitly-flagged subset of technical-architecture.md §46's full
event list is wired in this task (ride.accepted, ride.arrived) as a
proof that the mechanism is real, not a mechanical sweep of the whole
list — the remaining trigger points are a repeatable, bounded follow-up
task, not invented here.

7. Decision 6 — Schema: exactly as documented, IN_APP added to the
   Channel enum without a preferences column

`notification.preferences`/`notification.deliveries` (database-design.md
§32.1/§32.2) are created unmodified. `notification.preferences` only
documents push_enabled/sms_enabled/whatsapp_enabled — no in_app_enabled
column, and none is added: in-app delivery is an internal record with no
external send to opt out of (the same reasoning `ride.gps_verifications`
never needed a "can I skip this" preference). The `Channel` enum
(IN_APP/SMS/PUSH/WHATSAPP) still includes PUSH/WHATSAPP even though
neither has a real provider yet — matching this codebase's own "0 for
now, not deleted" precedent for documented-but-currently-inert fields —
calling `send()` with either raises a clear, typed error rather than
silently doing nothing or crashing unhelpfully.

8. Consequences — documents updated alongside this ADR

- database-design.md §32 gains an implementation-status note (no shape
  changed).
- domain-design.md §20 gains an implementation-status note.
- technical-architecture.md §46 gains an implementation-status note
  scoping exactly which events are wired vs. documented-only.
- docs/VISTAAR_AUTONOMOUS_EXECUTION_PLAN.md's Phase 15 entry corrected.
- No api-contracts.md change — no endpoint exists to annotate (Decision
  1).
