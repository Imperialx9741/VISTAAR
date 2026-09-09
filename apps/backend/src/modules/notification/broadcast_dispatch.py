"""Shared broadcast dispatch logic (ADR-0055).

Resolves a Broadcast's audience to concrete recipient ids and fans out
NotificationService.send() to each one. Used by both the immediate-send
path (modules/admin/router.py's POST .../notifications/broadcasts, for
a broadcast with no scheduled_at) and the scheduled-broadcast Celery
Beat task (modules/notification/tasks.py), so the two paths can never
drift apart — a scheduled broadcast dispatches exactly the same way an
immediate one does, just later.

Audience resolution always happens here, at actual dispatch time, never
at Broadcast.new()/create time — membership of ALL_CUSTOMERS/
ALL_DRIVERS/ONLINE_DRIVERS can change between when a scheduled
broadcast is composed and when it actually sends; only SELECTED's
explicit id list is fixed at compose time (ADR-0055 Decision 3).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Protocol

from redis.asyncio import Redis

from modules.identity.ports import AccountRepository
from modules.notification.domain.entities import AudienceType, Broadcast, Channel
from modules.notification.service import NotificationService
from modules.vehicle.domain.entities import ALL_MATCHING_CATEGORY_KEYS
from shared import geo

logger = logging.getLogger("vistaar.notification.broadcast")


class CustomerIdSource(Protocol):
    """The one CustomerService method this module needs — a narrower,
    structurally-typed dependency than importing the whole service, so
    a unit test can satisfy it with a two-line fake instead of a full
    CustomerRepository implementation. modules.customer.service.
    CustomerService already satisfies this Protocol as-is."""

    def list_all_customer_ids(self) -> list[uuid.UUID]: ...


class DriverIdSource(Protocol):
    """Same reasoning as CustomerIdSource, for DriverService."""

    def list_all_driver_ids(self) -> list[uuid.UUID]: ...


async def resolve_audience(
    *,
    audience_type: AudienceType,
    audience_user_ids: list[uuid.UUID] | None,
    customer_service: CustomerIdSource,
    driver_service: DriverIdSource,
    redis_client: Redis,
) -> list[uuid.UUID]:
    if audience_type is AudienceType.SELECTED:
        return list(audience_user_ids or [])
    if audience_type is AudienceType.ALL_CUSTOMERS:
        return customer_service.list_all_customer_ids()
    if audience_type is AudienceType.ALL_DRIVERS:
        return driver_service.list_all_driver_ids()
    # AudienceType.ONLINE_DRIVERS — the only remaining case.
    return await geo.list_online_driver_ids(
        redis_client, category_keys=ALL_MATCHING_CATEGORY_KEYS
    )


async def dispatch_broadcast(
    *,
    broadcast: Broadcast,
    notification_service: NotificationService,
    accounts: AccountRepository,
    customer_service: CustomerIdSource,
    driver_service: DriverIdSource,
    redis_client: Redis,
    now: datetime,
) -> tuple[int, int]:
    """Resolves `broadcast`'s audience fresh and calls
    NotificationService.send() once per recipient, using the
    broadcast-only template_key its own creation already published —
    so each Delivery row this produces is indistinguishable in kind
    from any other admin-triggered send. Catches every per-recipient
    exception (a bad/missing account, a provider error) so one bad row
    never aborts the rest of a potentially large audience — a stronger
    guarantee than modules/notification/tasks.py's own per-row loops
    need, since those iterate a small, trusted, already-filtered SQL
    result set, not an entire customer/driver base. Returns
    (sent_count, failed_count); a recipient who is opted out or has no
    registered device is counted as neither (matching Delivery
    returning None for that case)."""
    channel = broadcast.channel
    recipient_ids = await resolve_audience(
        audience_type=broadcast.audience_type,
        audience_user_ids=broadcast.audience_user_ids,
        customer_service=customer_service,
        driver_service=driver_service,
        redis_client=redis_client,
    )
    sent_count = 0
    failed_count = 0
    for user_id in recipient_ids:
        recipient_phone: str | None = None
        if channel is Channel.SMS:
            # customer_id/driver_id IS identity.accounts.id (the same
            # shared-primary-key relationship Customer Detail's own
            # phone lookup already relies on) — phone itself lives only
            # in identity.accounts, a separate module boundary this
            # module does not otherwise cross.
            account = accounts.get_by_id(user_id)
            if account is None:
                failed_count += 1
                continue
            recipient_phone = account.phone
        try:
            delivery = await notification_service.send(
                user_id=user_id,
                channel=channel,
                template_key=broadcast.template_key,
                recipient=recipient_phone,
                event_id=None,
                now=now,
            )
        except Exception:
            logger.exception(
                "Broadcast dispatch failed (broadcast_id=%s user_id=%s)",
                broadcast.id,
                user_id,
            )
            failed_count += 1
            continue
        if delivery is None:
            continue
        if delivery.status.value == "SENT":
            sent_count += 1
        elif delivery.status.value == "FAILED":
            failed_count += 1
    return sent_count, failed_count
