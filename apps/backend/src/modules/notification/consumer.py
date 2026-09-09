"""Notification Kafka Consumer — ADR-0038.

The first real Kafka consumer in this codebase (Phase 15/18's own
long-standing "no consumer exists" gap). Subscribes to the topics
`shared/outbox_publisher.py` produces for the event types below and
dispatches each to `NotificationService.send()` (ADR-0034) — additive
only: `ride.accepted`/`ride.arrived`'s existing synchronous router-level
dispatch is untouched (ADR-0038 Decision 4).

Runs as an in-process asyncio task from main.py's lifespan, mirroring
`shared/outbox_publisher.py`'s own OutboxPublisher shape exactly (ADR-
0038 Decision 1) — not a separate worker process.

Consumer Idempotency (event-contracts.md §29, ADR-0071, 2026-09-04):
`handle_event()` checks/records `shared.processed_events` around every
handler dispatch, closing the roadmap's "Event idempotency: NOT
implemented on the consumer side" gap (ADR-0017 §4 deferred it for
lack of a real consumer; this module is now that consumer). This sits
alongside, not in place of, each handler's own narrower dedup where one
already exists.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from aiokafka import AIOKafkaConsumer
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from core.config import settings
from core.database import SessionLocal
from modules.identity.sms import get_sms_provider
from modules.notification.domain.entities import Channel
from modules.notification.repositories import (
    SqlAlchemyDeliveryRepository,
    SqlAlchemyPreferencesRepository,
    SqlAlchemyTemplateRepository,
)
from modules.notification.service import NotificationService

logger = logging.getLogger("vistaar.notification.consumer")

_GROUP_ID = "vistaar-notification-consumer"
_TOPICS = ("vistaar.ride", "vistaar.penalty", "vistaar.safety")

# ADR-0038 Decision 3 — template_key constants for the events wired here.
# No SMS_TEMPLATES (domain/templates.py) entry needed for the first
# four: all four are IN_APP-only, and NotificationService.send() only
# renders an SMS template when channel is Channel.SMS (unchanged from
# ADR-0034) — render_sms() raises UnknownTemplateError for any key
# without an entry there. SOS_TRIGGERED (ADR-0050) IS sent over SMS too
# (see _handle_sos_triggered() below), so it DOES have a real
# SMS_TEMPLATES entry — the first Kafka-consumer-triggered event that
# actually needs one.
TEMPLATE_RIDE_STARTED = "RIDE_STARTED"
TEMPLATE_RIDE_COMPLETED = "RIDE_COMPLETED"
TEMPLATE_RIDE_CANCELLED = "RIDE_CANCELLED"
TEMPLATE_PENALTY_APPLIED = "PENALTY_APPLIED"
TEMPLATE_SOS_TRIGGERED = "SOS_TRIGGERED"


def _get_ride_row(db: DbSession, ride_id: str) -> Any | None:
    return db.execute(
        text("SELECT customer_id, driver_id FROM ride.rides WHERE id = :id"),
        {"id": ride_id},
    ).fetchone()


def _get_safety_team_admins(db: DbSession) -> list[Any]:
    """ADR-0050 — every active admin who counts as VISTAAR's internal
    safety/call-center team: every Super Admin (implicit full access,
    ADR-0040) plus every employee admin holding MANAGE on SAFETY.
    Raw SQL against admin.users/admin.permissions/identity.accounts
    directly, not a modules.admin service/repository import — same
    shortcut this file's own _get_ride_row() already uses for
    modules.ride, not a new cross-module composition pattern."""
    return list(
        db.execute(
            text(
                "SELECT DISTINCT a.id AS admin_id, ia.phone AS phone "
                "FROM admin.users a "
                "JOIN identity.accounts ia ON ia.id = a.id "
                "WHERE a.status = 'ACTIVE' AND ("
                "  a.role = 'SUPER_ADMIN'"
                "  OR EXISTS ("
                "    SELECT 1 FROM admin.permissions p "
                "    WHERE p.admin_id = a.id AND p.module = 'SAFETY' "
                "      AND p.access_level = 'MANAGE'"
                "  )"
                ")"
            )
        ).fetchall()
    )


async def _handle_ride_started(
    data: dict[str, Any], *, notification_service: NotificationService, db: DbSession
) -> None:
    """event-contracts.md §10.4. Payload only carries driver_id — the
    customer is looked up by ride_id rather than the event being
    skipped over a field it doesn't happen to carry."""
    row = _get_ride_row(db, data["ride_id"])
    if row is None:
        logger.warning(
            "ride.started for unknown ride_id=%s — nothing to notify.",
            data["ride_id"],
        )
        return
    await notification_service.send(
        user_id=row.customer_id,
        channel=Channel.IN_APP,
        template_key=TEMPLATE_RIDE_STARTED,
        recipient=None,
        event_id=uuid.UUID(data["_event_id"]),
        now=datetime.now(UTC),
    )


async def _handle_ride_completed(
    data: dict[str, Any], *, notification_service: NotificationService, db: DbSession
) -> None:
    """event-contracts.md §10.8. customer_id is already in the payload."""
    await notification_service.send(
        user_id=uuid.UUID(data["customer_id"]),
        channel=Channel.IN_APP,
        template_key=TEMPLATE_RIDE_COMPLETED,
        recipient=None,
        event_id=uuid.UUID(data["_event_id"]),
        now=datetime.now(UTC),
    )


async def _handle_ride_cancelled(
    data: dict[str, Any], *, notification_service: NotificationService, db: DbSession
) -> None:
    """event-contracts.md §10.9. Notifies whichever party did NOT
    cancel — the payload carries `cancelled_by` (a role, "CUSTOMER" or
    "DRIVER") but neither ID directly, so both are looked up by
    ride_id. Skipped (not an error) when the ride never had a driver
    assigned yet (a customer may cancel while still SEARCHING)."""
    row = _get_ride_row(db, data["ride_id"])
    if row is None:
        logger.warning(
            "ride.cancelled for unknown ride_id=%s — nothing to notify.",
            data["ride_id"],
        )
        return

    recipient_id = (
        row.driver_id if data["cancelled_by"] == "CUSTOMER" else row.customer_id
    )
    if recipient_id is None:
        return

    await notification_service.send(
        user_id=recipient_id,
        channel=Channel.IN_APP,
        template_key=TEMPLATE_RIDE_CANCELLED,
        recipient=None,
        event_id=uuid.UUID(data["_event_id"]),
        now=datetime.now(UTC),
    )


async def _handle_penalty_applied(
    data: dict[str, Any], *, notification_service: NotificationService, db: DbSession
) -> None:
    """event-contracts.md §17.1. user_id is already in the payload."""
    await notification_service.send(
        user_id=uuid.UUID(data["user_id"]),
        channel=Channel.IN_APP,
        template_key=TEMPLATE_PENALTY_APPLIED,
        recipient=None,
        event_id=uuid.UUID(data["_event_id"]),
        now=datetime.now(UTC),
    )


async def _handle_sos_triggered(
    data: dict[str, Any], *, notification_service: NotificationService, db: DbSession
) -> None:
    """event-contracts.md §21.1 (ADR-0050). Unlike every other handler
    here, the recipient isn't derived from the event's own payload — it's
    VISTAAR's internal safety/call-center team, looked up fresh on every
    incident (an admin's permissions can change between two SOS events).
    Sent over both IN_APP and SMS (not IN_APP-only like the other four
    handlers) — an SOS is time-sensitive enough that an in-app badge
    alone isn't enough. A missing phone number (shouldn't happen — every
    admin.users row shares its id with a real identity.accounts row) or
    an individual admin's SMS failure never blocks notifying the rest:
    NotificationService.send() already handles a single send failure
    internally (marks that one Delivery FAILED, doesn't raise) — see its
    own docstring."""
    admins = _get_safety_team_admins(db)
    if not admins:
        logger.warning(
            "safety.sos_triggered for incident_id=%s but no active "
            "Super Admin or SAFETY-MANAGE admin exists to notify.",
            data["incident_id"],
        )
        return

    event_id = uuid.UUID(data["_event_id"])
    now = datetime.now(UTC)
    for admin in admins:
        await notification_service.send(
            user_id=admin.admin_id,
            channel=Channel.IN_APP,
            template_key=TEMPLATE_SOS_TRIGGERED,
            recipient=None,
            event_id=event_id,
            now=now,
        )
        await notification_service.send(
            user_id=admin.admin_id,
            channel=Channel.SMS,
            template_key=TEMPLATE_SOS_TRIGGERED,
            recipient=admin.phone,
            event_id=event_id,
            now=now,
        )


_HANDLERS = {
    "ride.started": _handle_ride_started,
    "ride.completed": _handle_ride_completed,
    "ride.cancelled": _handle_ride_cancelled,
    "penalty.applied": _handle_penalty_applied,
    "safety.sos_triggered": _handle_sos_triggered,
}


#: event-contracts.md §29's `consumer_name` — this file's own identity
#: in shared.processed_events. A single fixed constant is correct today
#: since NotificationConsumer is the only real Kafka consumer in this
#: codebase; a second consumer would pick its own name.
_CONSUMER_NAME = "notification-consumer"


def _already_processed(db: DbSession, *, event_id: str) -> bool:
    """event-contracts.md §29's dedup check. Consulted for every
    registered event_type before its handler runs — a general guard on
    top of (not a replacement for) whatever narrower dedup a specific
    handler's own side effect already has (e.g. NotificationService.
    send()'s (user_id, channel, template_key, event_id) constraint,
    ADR-0034) — future handlers get this protection even if they never
    add one of their own."""
    row = db.execute(
        text(
            "SELECT 1 FROM shared.processed_events "
            "WHERE consumer_name = :consumer_name AND event_id = :event_id"
        ),
        {"consumer_name": _CONSUMER_NAME, "event_id": event_id},
    ).fetchone()
    return row is not None


def _mark_processed(db: DbSession, *, event_id: str) -> None:
    """`ON CONFLICT DO NOTHING`, not a plain INSERT: the row is written
    in the same transaction/commit as the handler's own side effect
    below, so a genuinely concurrent redelivery racing this exact
    (consumer_name, event_id) pair — vanishingly unlikely for a single
    partition's single consumer, but not impossible under a rebalance —
    never raises a duplicate-key error into the caller."""
    db.execute(
        text(
            "INSERT INTO shared.processed_events (consumer_name, event_id) "
            "VALUES (:consumer_name, :event_id) "
            "ON CONFLICT (consumer_name, event_id) DO NOTHING"
        ),
        {"consumer_name": _CONSUMER_NAME, "event_id": event_id},
    )


async def handle_event(envelope: dict[str, Any], *, db: DbSession) -> None:
    """Dispatches one decoded event-contracts.md §3 envelope to its
    handler, if any is registered (ADR-0038 Decision 3's wired list —
    every other event_type on the subscribed topics is silently
    ignored, not an error: this consumer does not yet cover every
    event those topics carry).

    Consumer Idempotency (event-contracts.md §29, ADR-0071, 2026-09-04):
    BEGIN -> check event_id already processed -> already? return/ACK :
    apply effect -> record event_id -> COMMIT/ACK, exactly as documented
    — `shared.processed_events` is checked before the handler runs and
    recorded in the same commit as its side effect, so a message
    redelivered after a consumer restart (this consumer's own retry
    mechanism — NotificationConsumer.consume_forever() only commits a
    Kafka offset after a successful handle_event(), ADR-0038 Decision 2)
    can never re-apply an already-applied effect.

    Builds its own NotificationService per call (own DB session, own
    SMS provider) — mirrors OutboxPublisher.publish_pending()'s own
    per-call SessionLocal() pattern rather than holding a long-lived
    service instance across the whole consumer loop."""
    event_type = envelope.get("event_type")
    handler = _HANDLERS.get(event_type)  # type: ignore[arg-type]
    if handler is None:
        return

    event_id = envelope["event_id"]
    if _already_processed(db, event_id=event_id):
        logger.info(
            "Event %s (type=%s) already processed by %s — skipping (redelivery).",
            event_id,
            event_type,
            _CONSUMER_NAME,
        )
        return

    data = dict(envelope.get("data") or {})
    data["_event_id"] = event_id

    notification_service = NotificationService(
        deliveries=SqlAlchemyDeliveryRepository(db),
        preferences=SqlAlchemyPreferencesRepository(db),
        sms_provider=get_sms_provider(),
        templates=SqlAlchemyTemplateRepository(db),
    )
    await handler(data, notification_service=notification_service, db=db)
    _mark_processed(db, event_id=event_id)
    db.commit()


class NotificationConsumer:
    """Wraps one AIOKafkaConsumer instance, started/stopped once for the
    life of the consumer loop — mirrors OutboxPublisher's own
    one-producer-for-the-whole-loop lifecycle exactly."""

    def __init__(self) -> None:
        self._consumer: AIOKafkaConsumer | None = None

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            *_TOPICS,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=_GROUP_ID,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        await self._consumer.start()

    async def stop(self) -> None:
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None

    async def consume_forever(self) -> None:
        """Runs until cancelled. Each message's offset is committed only
        after its handler returns successfully (ADR-0038 Decision 2) — a
        message that fails to handle is left uncommitted; Kafka
        redelivers it starting from the last *committed* offset the next
        time this consumer group starts consuming that partition (a
        process restart or rebalance, not literally "the next message in
        this same run" — the local iterator has already moved past it).
        Safe under that at-least-once redelivery two ways: the general
        `shared.processed_events` check (ADR-0071, see handle_event()'s
        own docstring) plus, for these specific handlers,
        NotificationService.send()'s (ADR-0034) own (user_id, channel,
        template_key, event_id) dedup.

        Unlike shared/outbox_publisher.py's OutboxPublisher (ADR-0071),
        this consumer does not itself apply configurable backoff, a
        maximum-attempts limit, or a dead-letter path to a message that
        keeps failing to handle — redelivery-on-restart is the only
        retry mechanism today. Scoped out of ADR-0071 deliberately (see
        that ADR §5) rather than left as an unflagged gap."""
        if self._consumer is None:
            raise RuntimeError("NotificationConsumer.start() must be called first.")

        async for message in self._consumer:
            db = SessionLocal()
            try:
                envelope = json.loads(message.value.decode("utf-8"))
                await handle_event(envelope, db=db)
            except Exception:
                db.rollback()
                logger.exception(
                    "Failed to handle notification event at %s partition=%s "
                    "offset=%s — will be redelivered (offset not committed).",
                    message.topic,
                    message.partition,
                    message.offset,
                )
                continue
            finally:
                db.close()

            await self._consumer.commit()
