"""VISTAAR Notification module — Notification Domain Foundation.

See docs/14-decisions/ADR-0034-notification-domain-foundation.md for the
full reasoning. Owns `notification.preferences` and
`notification.deliveries`, per docs/04-database/database-design.md §32.

Implements no HTTP endpoint of its own — api-contracts.md documents zero
Notification routes anywhere (no `GET my notifications`, no preferences
read/write route), the same §0.3 "new public API contract" stop
condition ADR-0018 (Advertisement) and ADR-0021 (Driver Suspension/
Reactivation) already hit and declined to cross. `NotificationService.
send()` is composed directly at other modules' routers (see below), the
same one-directional composition shape every other cross-module call in
this codebase uses.

This module deliberately does NOT implement:

- PUSH (Firebase Cloud Messaging, owner-approved as the provider) — no
  device-token data source exists anywhere in this codebase (`identity.
  sessions.device_metadata` is free-form session/logout text, not a
  structured FCM/APNs registration token; no documented endpoint accepts
  one). Building the FCM send call now would be code with nothing real
  to call it with — registering a device token is itself a new public
  API contract, the same stop condition above. `Channel.PUSH` exists in
  the enum (documented in `notification.preferences.push_enabled`); no
  provider implements it — `NotificationService.send()` raises
  `ChannelNotAvailableError` if asked to use it.
- WHATSAPP — the owner explicitly asked for a requirements analysis, not
  an implementation or a provider choice. `Channel.WHATSAPP` exists in
  the enum for the same "documented column, no live caller" reason PUSH
  does; calling `send()` with it raises the same error.
- A real Kafka consumer — technical-architecture.md §46 describes
  Notification as consuming domain events over Kafka; no Kafka consumer
  exists anywhere in this codebase yet (Phase 18's own status: "Kafka
  consumers... remain undone"). `send()` is instead composed
  synchronously at a small, explicitly-flagged subset of existing router
  endpoints (ride.accepted, ride.arrived) as a proof the mechanism is
  real — wiring the rest of §46's documented event list is a repeatable,
  bounded follow-up, not attempted here.
- Message template *rendering* (variable substitution, localization) —
  `templates.py`'s lookup is flat, static placeholder copy per
  `template_key`, explicitly flagged as illustrative, not approved
  customer-facing wording (no document specifies actual message text
  anywhere).
- India SMS DLT template registration / MSG91's transactional-SMS
  endpoint verification — the same "wired, not verified against a live
  account" caveat ADR-0031 already gave MSG91's OTP integration.

What it does do:

- `NotificationService.send()`: creates a PENDING `notification.
  deliveries` row, dispatches via the channel's provider (IN_APP: an
  immediate DB-only write, no external call, always allowed — no
  `in_app_enabled` preference column exists to gate it; SMS: reuses
  `modules.identity.sms`'s MSG91 integration, generalized from OTP-only),
  and persists the final SENT/FAILED status. Respects `notification.
  preferences` for SMS (skips — returns `None`, no row created — if the
  user has disabled it; IN_APP is never gated). Idempotent per
  `uq_notification_deliveries_dedup` (migration b8e4f27a5c93) — a
  retried/racing call for the same (user_id, channel, template_key,
  event_id) returns the existing row rather than creating a second one,
  the same idempotent-on-conflict shape `modules.penalty.repositories`
  already established for `penalty.penalties`.
- `NotificationService.get_preferences()`/`update_preferences()`: pure
  DB read/write against `notification.preferences`, auto-provisioning a
  default (all channels enabled) row on first read — matching
  `CustomerService.get_profile()`'s own "auto-provision on first access"
  precedent. No endpoint exists to expose these yet (see above); the
  service methods are ready for whichever future task documents one.

Layering mirrors modules/penalty/ and modules/wallet/:

    domain/         pure business logic — no FastAPI/SQLAlchemy imports
    ports.py        PreferencesRepository, DeliveryRepository Protocols
    models.py       SQLAlchemy ORM models for notification.preferences/deliveries
    repositories.py SQLAlchemy-backed implementations of the ports above
    service.py      application service (use cases): NotificationService
    dependencies.py FastAPI DI wiring

No schemas.py, no router.py — this module has no request/response DTOs
and no HTTP surface of its own; see "Implements no HTTP endpoint" above.
"""
