ADR-0050 — SOS Escalation: VISTAAR Internal Safety/Call-Center Team

Status: Accepted and implemented (2026-08-28) — owner decision, resolving
BR-112's "the exact emergency-service integrations are: TBD" and the
`safety.sos_triggered` recipient gap ADR-0038 deferred with "SOSTriggered's
recipient is a genuine, safety-sensitive judgment call left unmade."

Date recorded: 2026-08-28.
Deciders: Project owner (explicit written decision, 2026-08-28).

1. Context

BR-112 lists SOS incident capture fields (ride ID, reporter, GPS, vehicle,
status, timestamp) but leaves "the exact emergency-service integrations"
TBD. `event-contracts.md` §21.1 already documents `safety.sos_triggered`
with Notification explicitly listed as a consumer, and the outbox
publisher already emits it (`modules/safety/router.py`'s `trigger_sos`
endpoint) — the event has existed since ADR-0022; only a consumer was
missing. When ADR-0038 built the first real Kafka consumer
(`NotificationConsumer`), it deliberately left `safety.sos_triggered`
unwired, giving the exact reason this ADR now resolves: no source
document said who should receive it.

2. Decision

The recipient is VISTAAR's own internal safety/call-center staff — not a
real police/emergency-service API integration. Concretely: every active
`admin.users` row that is either `SUPER_ADMIN` (implicit full access,
ADR-0040) or holds `MANAGE` access on the `SAFETY` module
(`admin.permissions`), notified over both real channels this codebase
already has (IN_APP + SMS, ADR-0034) — SMS specifically because an SOS is
time-sensitive and an in-app badge alone could go unseen. No new
provider, no new channel, no new event: `safety.sos_triggered` already
exists and already names Notification as a consumer; this ADR only
supplies the missing recipient rule and wires
`NotificationConsumer` to it, the same shape ADR-0038 already used for
`ride.started`/`ride.completed`/`ride.cancelled`/`penalty.applied`.

Finding the recipient set reuses this consumer file's own established
shortcut (`_get_ride_row()`'s raw SQL against another module's table,
not a service/repository import) rather than importing modules.admin —
consistent with the one precedent already in this exact file, not a new
cross-module composition pattern.

3. What this does NOT resolve

- Any real police/emergency-service API integration — BR-112's "exact
  emergency-service integrations" stays internal-only by this decision;
  a future external integration is a separate decision if ever made.
- A dedicated "call-center staff" account type or role distinct from
  the existing Super Admin / employee-admin-with-SAFETY-access model —
  reusing the existing admin permission model is the whole point of this
  decision, not a gap.
- Any change to `EscalateSOS`'s existing ACKNOWLEDGED -> IN_PROGRESS
  admin-only transition (ADR-0022 Decision 3) — this ADR only adds a
  notification at TRIGGER time, not a new state or workflow step.
