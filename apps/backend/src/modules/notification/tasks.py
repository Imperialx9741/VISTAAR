"""Celery periodic tasks for Notification (ADR-0039).

Two of the events ADR-0038 deliberately deferred — `PromotionActivated`
was wired via the Kafka consumer, but `PromotionExpiring`/
`DocumentExpiring` needed a scheduled scan, which had no background-
worker technology to run on until now. Same NotificationService.send()
dispatch as modules/notification/consumer.py (ADR-0038) — only the
trigger differs (a schedule instead of a Kafka event).

Each Celery task wraps a pure, directly-testable async function (no
Celery/DB-session decorator involved) — the same "loop wraps a testable
unit" separation OutboxPublisher.publish_pending()/NotificationConsumer.
handle_event() already established.

retry_failed_notifications (ADR-0075, 2026-09-04) is the fourth task
here, for a different reason than the first three: not a missing
trigger for a real event, but the one bounded retry a FAILED SMS/PUSH
send never otherwise gets (NotificationService.send()'s own
mark_failed() is terminal by design).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from core.config import settings
from core.database import SessionLocal
from core.redis import get_redis_client
from modules.customer.repositories import SqlAlchemyCustomerRepository
from modules.customer.service import CustomerService
from modules.driver.repositories import SqlAlchemyDriverRepository
from modules.driver.service import DriverService
from modules.identity.repositories import SqlAlchemyAccountRepository
from modules.identity.sms import get_sms_provider
from modules.notification.broadcast_dispatch import dispatch_broadcast
from modules.notification.domain.entities import Channel
from modules.notification.push import get_push_provider
from modules.notification.repositories import (
    SqlAlchemyBroadcastRepository,
    SqlAlchemyDeliveryRepository,
    SqlAlchemyDeviceTokenRepository,
    SqlAlchemyPreferencesRepository,
    SqlAlchemyTemplateRepository,
)
from modules.notification.service import NotificationService
from shared.celery_app import celery_app

logger = logging.getLogger("vistaar.notification.tasks")

TEMPLATE_PROMOTION_EXPIRING = "PROMOTION_EXPIRING"
TEMPLATE_DOCUMENT_EXPIRING = "DOCUMENT_EXPIRING"


def _expiry_event_id(entity_id: uuid.UUID, expires_at: datetime) -> uuid.UUID:
    """Deterministic per (entity, expires_at) pair — stable across
    repeated daily runs against the same expiry value (so this still
    only warns once), but distinct if expires_at ever changes (e.g. the
    entity is renewed and later approaches expiry again). Not simply
    entity_id reused directly — see ADR-0039 Decision 3."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"{entity_id}:{expires_at.isoformat()}")


async def check_expiring_promotions(*, db: DbSession, now: datetime) -> int:
    """Returns the number of notifications actually sent (not
    preference-gated/deduped away) — purely for logging, not asserted
    on by anything."""
    threshold = now + timedelta(days=settings.PROMOTION_EXPIRY_WARNING_DAYS)
    rows = db.execute(
        text(
            "SELECT id, customer_id, expires_at FROM promotion.entitlements "
            "WHERE status = 'ACTIVE' AND remaining_uses > 0 "
            "AND expires_at > :now AND expires_at <= :threshold"
        ),
        {"now": now, "threshold": threshold},
    ).fetchall()

    notification_service = NotificationService(
        deliveries=SqlAlchemyDeliveryRepository(db),
        preferences=SqlAlchemyPreferencesRepository(db),
        sms_provider=get_sms_provider(),
        templates=SqlAlchemyTemplateRepository(db),
    )
    sent = 0
    for row in rows:
        delivery = await notification_service.send(
            user_id=row.customer_id,
            channel=Channel.IN_APP,
            template_key=TEMPLATE_PROMOTION_EXPIRING,
            recipient=None,
            event_id=_expiry_event_id(row.id, row.expires_at),
            now=now,
        )
        if delivery is not None and delivery.status.value == "SENT":
            sent += 1
    db.commit()
    return sent


async def check_expiring_documents(*, db: DbSession, now: datetime) -> int:
    threshold = now + timedelta(days=settings.DOCUMENT_EXPIRY_WARNING_DAYS)
    notification_service = NotificationService(
        deliveries=SqlAlchemyDeliveryRepository(db),
        preferences=SqlAlchemyPreferencesRepository(db),
        sms_provider=get_sms_provider(),
        templates=SqlAlchemyTemplateRepository(db),
    )
    sent = 0

    driver_rows = db.execute(
        text(
            "SELECT id, driver_id, expires_at FROM driver.documents "
            "WHERE verification_status = 'APPROVED' "
            "AND expires_at > :now AND expires_at <= :threshold"
        ),
        {"now": now, "threshold": threshold},
    ).fetchall()
    for row in driver_rows:
        delivery = await notification_service.send(
            user_id=row.driver_id,
            channel=Channel.IN_APP,
            template_key=TEMPLATE_DOCUMENT_EXPIRING,
            recipient=None,
            event_id=_expiry_event_id(row.id, row.expires_at),
            now=now,
        )
        if delivery is not None and delivery.status.value == "SENT":
            sent += 1

    # vehicle.documents doesn't carry driver_id directly — looked up via
    # the owning vehicle, same shape as modules/notification/consumer.
    # py's ride.started handler looking up a ride's customer_id.
    vehicle_rows = db.execute(
        text(
            "SELECT vd.id, vd.expires_at, v.driver_id "
            "FROM vehicle.documents vd "
            "JOIN vehicle.vehicles v ON v.id = vd.vehicle_id "
            "WHERE vd.verification_status = 'APPROVED' "
            "AND vd.expires_at > :now AND vd.expires_at <= :threshold"
        ),
        {"now": now, "threshold": threshold},
    ).fetchall()
    for row in vehicle_rows:
        delivery = await notification_service.send(
            user_id=row.driver_id,
            channel=Channel.IN_APP,
            template_key=TEMPLATE_DOCUMENT_EXPIRING,
            recipient=None,
            event_id=_expiry_event_id(row.id, row.expires_at),
            now=now,
        )
        if delivery is not None and delivery.status.value == "SENT":
            sent += 1

    db.commit()
    return sent


async def send_scheduled_broadcasts(*, db: DbSession, now: datetime) -> int:
    """ADR-0055 — the scheduled half of Compose/Send Broadcast. An
    immediate (scheduled_at IS NULL) broadcast is dispatched
    synchronously by modules/admin/router.py's own POST handler and
    never reaches here; this only ever picks up a future-dated
    broadcast whose scheduled_at has now arrived. Returns the number of
    broadcasts dispatched (not the number of recipients — see
    modules.notification.broadcast_dispatch.dispatch_broadcast() for
    per-recipient sent/failed counts, persisted onto each broadcast
    row)."""
    notification_service = NotificationService(
        deliveries=SqlAlchemyDeliveryRepository(db),
        preferences=SqlAlchemyPreferencesRepository(db),
        sms_provider=get_sms_provider(),
        templates=SqlAlchemyTemplateRepository(db),
        broadcasts=SqlAlchemyBroadcastRepository(db),
    )
    due = notification_service.list_due_broadcasts(now=now)
    if not due:
        return 0

    customer_service = CustomerService(customers=SqlAlchemyCustomerRepository(db))
    driver_service = DriverService(drivers=SqlAlchemyDriverRepository(db))
    accounts = SqlAlchemyAccountRepository(db)
    redis_client = get_redis_client()
    try:
        for broadcast in due:
            sent_count, failed_count = await dispatch_broadcast(
                broadcast=broadcast,
                notification_service=notification_service,
                accounts=accounts,
                customer_service=customer_service,
                driver_service=driver_service,
                redis_client=redis_client,
                now=now,
            )
            notification_service.mark_broadcast_sent(
                broadcast.id,
                sent_count=sent_count,
                failed_count=failed_count,
                now=now,
            )
            db.commit()
    finally:
        await redis_client.aclose()
    return len(due)


async def retry_failed_notifications(*, db: DbSession, now: datetime) -> int:
    """One bounded retry attempt for every FAILED SMS/PUSH delivery that
    has never been retried (ADR-0075, closing the gap Phase 15's own
    audit flagged and left unfixed). Raw SQL scan, same style
    check_expiring_promotions/check_expiring_documents above already
    use — `retry_count = 0` is the exclusivity condition (not a time
    window): NotificationService.retry_delivery() always stamps it to 1
    after one genuine attempt regardless of outcome, so this query
    naturally never revisits a row twice, no matter how often this task
    runs. IN_APP/WHATSAPP are never FAILED in the first place (see that
    ADR), so this only ever selects SMS/PUSH. Returns the number of
    deliveries actually retried (attempted, not necessarily
    successful) — purely for logging."""
    rows = db.execute(
        text(
            "SELECT id, channel, user_id FROM notification.deliveries "
            "WHERE status = 'FAILED' AND retry_count = 0 "
            "AND channel IN ('SMS', 'PUSH')"
        )
    ).fetchall()
    if not rows:
        return 0

    notification_service = NotificationService(
        deliveries=SqlAlchemyDeliveryRepository(db),
        preferences=SqlAlchemyPreferencesRepository(db),
        sms_provider=get_sms_provider(),
        templates=SqlAlchemyTemplateRepository(db),
        device_tokens=SqlAlchemyDeviceTokenRepository(db),
        push_provider=get_push_provider(),
    )
    retried = 0
    for row in rows:
        recipient: str | None = None
        if row.channel == "SMS":
            # A retry uses the *current* phone number, not a stale copy
            # from original send time — see this module's own docstring
            # for why none was ever persisted onto the delivery row.
            account_row = db.execute(
                text("SELECT phone FROM identity.accounts WHERE id = :id"),
                {"id": row.user_id},
            ).fetchone()
            if account_row is None:
                # Account deleted since the original send — nothing to
                # retry to; leave retry_count at 0 rather than guessing,
                # consistent with this task's own "best-effort, not
                # authoritative" scope (Part 3/README's established
                # philosophy for every other best-effort composition in
                # this codebase).
                continue
            recipient = account_row.phone
        await notification_service.retry_delivery(row.id, recipient=recipient, now=now)
        retried += 1
    db.commit()
    return retried


def _run_with_fresh_session(coro_factory: Any) -> int:
    """Celery tasks run synchronously in a worker process — bridges to
    the async NotificationService the same way every other Celery task
    entrypoint in this module does, with its own fresh DB session
    (mirrors OutboxPublisher.publish_pending()'s and modules.
    notification.consumer.handle_event()'s own per-call SessionLocal()
    pattern)."""
    db = SessionLocal()
    try:
        return asyncio.run(coro_factory(db=db, now=datetime.now(UTC)))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@celery_app.task(name="notification.check_expiring_promotions")
def check_expiring_promotions_task() -> int:
    count = _run_with_fresh_session(check_expiring_promotions)
    logger.info("check_expiring_promotions_task sent %s notifications.", count)
    return count


@celery_app.task(name="notification.check_expiring_documents")
def check_expiring_documents_task() -> int:
    count = _run_with_fresh_session(check_expiring_documents)
    logger.info("check_expiring_documents_task sent %s notifications.", count)
    return count


@celery_app.task(name="notification.send_scheduled_broadcasts")
def send_scheduled_broadcasts_task() -> int:
    count = _run_with_fresh_session(send_scheduled_broadcasts)
    logger.info("send_scheduled_broadcasts_task dispatched %s broadcasts.", count)
    return count


@celery_app.task(name="notification.retry_failed_notifications")
def retry_failed_notifications_task() -> int:
    count = _run_with_fresh_session(retry_failed_notifications)
    logger.info("retry_failed_notifications_task retried %s deliveries.", count)
    return count
