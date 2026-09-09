"""Application service (use cases) for Notification (ADR-0034)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from modules.notification.domain.entities import (
    AudienceType,
    Broadcast,
    Channel,
    Delivery,
    DeliveryStatus,
    DeviceToken,
    Platform,
    Preferences,
    Template,
)
from modules.notification.domain.errors import (
    BroadcastNotFoundError,
    ChannelNotAvailableError,
    TemplateNotFoundError,
)
from modules.notification.domain.templates import render_sms
from modules.notification.ports import (
    BroadcastRepository,
    DeliveryRepository,
    DeviceTokenRepository,
    PreferencesRepository,
    PushProvider,
    SmsMessageProvider,
    TemplateRepository,
)

logger = logging.getLogger("vistaar.notification")


class NotificationService:
    def __init__(
        self,
        *,
        deliveries: DeliveryRepository,
        preferences: PreferencesRepository,
        sms_provider: SmsMessageProvider | None = None,
        templates: TemplateRepository | None = None,
        device_tokens: DeviceTokenRepository | None = None,
        push_provider: PushProvider | None = None,
        broadcasts: BroadcastRepository | None = None,
    ) -> None:
        self._deliveries = deliveries
        self._preferences = preferences
        # Optional (default None) so callers that only ever need IN_APP
        # delivery (no live caller yet — this task's own trigger points
        # all use IN_APP, see modules/ride/router.py) don't need to wire
        # an SMS provider they'll never use.
        self._sms_provider = sms_provider
        # Optional (default None) for the same reason, and for existing
        # unit tests that construct NotificationService directly without
        # it — the real get_notification_service() DI wiring always
        # provides one. `send()` below falls back to the old hardcoded
        # SMS_TEMPLATES dict whenever this is None OR no PUBLISHED row
        # exists yet (ADR-0044, same fallback discipline ADR-0043 uses).
        self._templates = templates
        # ADR-0052 — same optional-dependency reasoning as sms_provider
        # above: callers that never touch PUSH (register_device()/
        # unregister_device(), or send() for any other channel) don't
        # need either wired.
        self._device_tokens = device_tokens
        self._push_provider = push_provider
        # ADR-0055 — same optional-dependency reasoning as templates/
        # device_tokens above: only broadcast-related methods touch this.
        self._broadcasts = broadcasts

    def get_or_create_preferences(
        self, *, user_id: uuid.UUID, now: datetime
    ) -> Preferences:
        """Auto-provisions a default (all channels enabled) row on first
        read, matching CustomerService.get_profile()'s own "auto-
        provision on first access" precedent — no endpoint exposes this
        yet (ADR-0034 Decision 1), but callers of send() below still
        need somewhere to read a real preference from."""
        existing = self._preferences.get(user_id)
        if existing is not None:
            return existing
        return self._preferences.create(Preferences.default(user_id=user_id, now=now))

    # --- Push device registration (ADR-0052) --------------------------

    def register_device(
        self, *, user_id: uuid.UUID, platform: Platform, token: str, now: datetime
    ) -> DeviceToken:
        assert self._device_tokens is not None, "register_device() needs device_tokens"
        return self._device_tokens.upsert(
            DeviceToken.new(user_id=user_id, platform=platform, token=token, now=now)
        )

    def unregister_device(self, *, user_id: uuid.UUID, token: str) -> None:
        assert self._device_tokens is not None, (
            "unregister_device() needs device_tokens"
        )
        self._device_tokens.delete(user_id=user_id, token=token)

    async def send(
        self,
        *,
        user_id: uuid.UUID,
        channel: Channel,
        template_key: str,
        recipient: str | None,
        event_id: uuid.UUID | None,
        now: datetime,
    ) -> Delivery | None:
        """Creates a PENDING notification.deliveries row, dispatches via
        the channel's provider, and persists the final status. Returns
        None (no row created) if the user has disabled this channel via
        their preferences — IN_APP has no preference column and is
        never gated (ADR-0034 Decision 6). `recipient` is the phone
        number for SMS (ignored for IN_APP); required whenever it would
        actually be used.

        Idempotent: a retried/racing call for the same (user_id, channel,
        template_key, event_id) returns the already-existing row rather
        than sending twice (DeliveryRepository.create()'s own dedup
        constraint)."""
        if channel is Channel.SMS:
            preferences = self.get_or_create_preferences(user_id=user_id, now=now)
            if not preferences.sms_enabled:
                return None
        elif channel is Channel.PUSH:
            # ADR-0052 — real now, gated the same two ways SMS already
            # is: the user's own preference, then "is there actually
            # anywhere to send this" (no device token registered is the
            # PUSH equivalent of SMS's "no phone number" — always true
            # for every account, so SMS never needed this second gate;
            # PUSH does, since registration is opt-in and most accounts
            # won't have registered a device yet).
            preferences = self.get_or_create_preferences(user_id=user_id, now=now)
            if not preferences.push_enabled:
                return None
            assert self._device_tokens is not None, "PUSH send requires device_tokens"
            device_tokens = self._device_tokens.list_for_user(user_id)
            if not device_tokens:
                return None
        elif channel is Channel.WHATSAPP:
            raise ChannelNotAvailableError(
                f"{channel.value} has no provider configured yet "
                "(ADR-0034 Decision 3 — BSP not yet picked)."
            )
        # IN_APP: no preference to check (ADR-0034 Decision 6).

        # ADR-0044 Decision 2: look up the currently-PUBLISHED template
        # (if any) and stamp its id on the created Delivery row now, so
        # a later edit to the template can never change what this row
        # proves was sent. None whenever no TemplateRepository is wired
        # or no PUBLISHED row exists yet for this (template_key,
        # channel) — send() still proceeds, via the SMS_TEMPLATES
        # fallback below.
        published_template = (
            self._templates.get_published(
                template_key=template_key, channel=channel.value
            )
            if self._templates is not None
            else None
        )

        delivery = self._deliveries.create(
            Delivery.new(
                user_id=user_id,
                channel=channel,
                template_key=template_key,
                event_id=event_id,
                now=now,
                template_version_id=published_template.id
                if published_template
                else None,
            )
        )
        if delivery.status.value != "PENDING":
            # A dedup hit returned an already-resolved delivery — nothing
            # left to dispatch.
            return delivery

        if channel is Channel.IN_APP:
            delivery.mark_sent(provider_reference=None, now=now)
            self._deliveries.save(delivery)
            return delivery

        if channel is Channel.PUSH:
            # ADR-0052. Unlike SMS's SMS_TEMPLATES last-resort fallback,
            # there is no equivalent static fallback for PUSH — no
            # existing caller depends on stable placeholder push copy
            # the way RIDE_ACCEPTED/RIDE_ARRIVED depend on SMS_TEMPLATES
            # today, so inventing one here would be speculative content
            # for events that don't even send over PUSH yet. A real
            # PUBLISHED (template_key, PUSH) template is required.
            if published_template is None:
                raise TemplateNotFoundError(
                    f"No PUBLISHED PUSH template exists for "
                    f"template_key={template_key!r}."
                )
            assert self._push_provider is not None, "PUSH send requires push_provider"
            title = published_template.title or template_key
            sent_reference: str | None = None
            any_sent = False
            # Reuses the same list the gating section above already
            # fetched (device_tokens) — channel is Channel.PUSH here
            # only when that branch ran and didn't already return None,
            # so it's always a non-empty list by this point.
            for device in device_tokens:
                try:
                    sent_reference = await self._push_provider.send(
                        device.token, title=title, body=published_template.body
                    )
                    any_sent = True
                except Exception as exc:  # noqa: BLE001 - best-effort, see class docstring
                    logger.error(
                        "Notification PUSH send failed (user_id=%s "
                        "template_key=%s device=%s): %s",
                        user_id,
                        template_key,
                        device.id,
                        exc,
                    )
            if any_sent:
                delivery.mark_sent(provider_reference=sent_reference, now=now)
            else:
                delivery.mark_failed(provider_reference=None)
            self._deliveries.save(delivery)
            return delivery

        # SMS from here on.
        assert self._sms_provider is not None, "SMS send requires sms_provider"
        assert recipient is not None, "SMS send requires a recipient phone number"
        message = (
            published_template.body if published_template else render_sms(template_key)
        )
        try:
            provider_reference = await self._sms_provider.send_message(
                recipient, message
            )
        except Exception as exc:  # noqa: BLE001 - best-effort delivery, see class docstring
            logger.error(
                "Notification SMS send failed (user_id=%s template_key=%s): %s",
                user_id,
                template_key,
                exc,
            )
            delivery.mark_failed(provider_reference=None)
            self._deliveries.save(delivery)
            return delivery

        delivery.mark_sent(provider_reference=provider_reference, now=now)
        self._deliveries.save(delivery)
        return delivery

    async def retry_delivery(
        self, delivery_id: uuid.UUID, *, recipient: str | None, now: datetime
    ) -> Delivery | None:
        """One bounded retry attempt for a FAILED SMS/PUSH delivery
        (ADR-0075) — the gap Phase 15's own audit found: `send()`'s
        terminal `mark_failed()` never gets revisited on its own.
        `recipient` is the caller's job to supply (SMS phone number;
        ignored for PUSH), same division of responsibility `send()`
        itself already has — this method still never imports
        `modules.identity`.

        No-ops (returns the row as-is) for anything already retried
        once (`retry_count != 0`), not FAILED, or IN_APP/WHATSAPP (never
        FAILED in the first place) — `retry_count` is always stamped to
        1 after a genuine attempt, whichever way it lands, so a second
        call for the same delivery_id is always a no-op from then on.
        Returns None only if `delivery_id` doesn't exist at all."""
        delivery = self._deliveries.get_by_id_for_update(delivery_id)
        if delivery is None:
            return None
        if delivery.status is not DeliveryStatus.FAILED or delivery.retry_count != 0:
            return delivery

        published_template = (
            self._templates.get_published(
                template_key=delivery.template_key, channel=delivery.channel.value
            )
            if self._templates is not None
            else None
        )

        if delivery.channel is Channel.PUSH:
            assert self._device_tokens is not None, "PUSH retry requires device_tokens"
            assert self._push_provider is not None, "PUSH retry requires push_provider"
            if published_template is None:
                # Same "no invented fallback copy" restraint send()
                # applies — nothing sensible to retry without one.
                delivery.retry_count = 1
                self._deliveries.save(delivery)
                return delivery
            device_tokens = self._device_tokens.list_for_user(delivery.user_id)
            title = published_template.title or delivery.template_key
            any_sent = False
            sent_reference: str | None = None
            for device in device_tokens:
                try:
                    sent_reference = await self._push_provider.send(
                        device.token, title=title, body=published_template.body
                    )
                    any_sent = True
                except Exception as exc:  # noqa: BLE001 - best-effort, see class docstring
                    logger.error(
                        "Notification PUSH retry failed (delivery_id=%s "
                        "device=%s): %s",
                        delivery_id,
                        device.id,
                        exc,
                    )
            if any_sent:
                delivery.mark_sent(provider_reference=sent_reference, now=now)
            else:
                delivery.mark_failed(provider_reference=None)
            delivery.retry_count = 1
            self._deliveries.save(delivery)
            return delivery

        # SMS from here on — the only other channel send() can FAIL.
        assert self._sms_provider is not None, "SMS retry requires sms_provider"
        assert recipient is not None, "SMS retry requires a recipient phone number"
        message = (
            published_template.body
            if published_template
            else render_sms(delivery.template_key)
        )
        try:
            provider_reference = await self._sms_provider.send_message(
                recipient, message
            )
        except Exception as exc:  # noqa: BLE001 - best-effort, see class docstring
            logger.error(
                "Notification SMS retry failed (delivery_id=%s): %s",
                delivery_id,
                exc,
            )
            delivery.mark_failed(provider_reference=None)
            delivery.retry_count = 1
            self._deliveries.save(delivery)
            return delivery

        delivery.mark_sent(provider_reference=provider_reference, now=now)
        delivery.retry_count = 1
        self._deliveries.save(delivery)
        return delivery

    # --- Admin (Admin Web §4.12) ------------------------------------

    def search_deliveries(
        self,
        *,
        user_id: uuid.UUID | None,
        channel: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Delivery], int]:
        return self._deliveries.search(
            user_id=user_id,
            channel=channel,
            status=status,
            offset=offset,
            limit=limit,
        )

    # --- Reports (Admin Web §4.16, ADR-0047) -------------------------

    def count_deliveries_by_channel_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        return self._deliveries.count_by_channel_in_range(since=since, until=until)

    def count_deliveries_by_status_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        return self._deliveries.count_by_status_in_range(since=since, until=until)

    # --- Notification Template Management (Admin Web §4.12, ADR-0044) --

    def create_template(
        self,
        *,
        template_key: str,
        channel: str,
        event_key: str | None,
        title: str | None,
        body: str,
        created_by: uuid.UUID,
        now: datetime,
    ) -> Template:
        """Version 1 if no version exists yet for (template_key,
        channel); otherwise the next version — always starts DRAFT.
        There is deliberately no separate "Edit" operation: an edit IS
        a new Create (ADR-0044 Decision 4)."""
        assert self._templates is not None
        next_version = (
            self._templates.get_latest_version(
                template_key=template_key, channel=channel
            )
            + 1
        )
        template = Template.new(
            template_key=template_key,
            channel=channel,
            event_key=event_key,
            title=title,
            body=body,
            version=next_version,
            created_by=created_by,
            now=now,
        )
        return self._templates.create(template)

    def get_template(self, template_id: uuid.UUID) -> Template:
        assert self._templates is not None
        template = self._templates.get_by_id(template_id)
        if template is None:
            raise TemplateNotFoundError("Template not found.")
        return template

    def list_templates(
        self,
        *,
        template_key: str | None,
        channel: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Template], int]:
        assert self._templates is not None
        return self._templates.list_all(
            template_key=template_key,
            channel=channel,
            status=status,
            offset=offset,
            limit=limit,
        )

    def publish_template(self, template_id: uuid.UUID) -> Template:
        """DRAFT -> PUBLISHED; archives (not deletes) the prior
        PUBLISHED version for the same (template_key, channel), if any
        — the identical "close out the previous one" mechanism
        ADR-0042/ADR-0043 already established, adapted to this
        feature's simpler two-state (no effective-dating) lifecycle."""
        assert self._templates is not None
        template = self._templates.get_by_id_for_update(template_id)
        if template is None:
            raise TemplateNotFoundError("Template not found.")

        previous = self._templates.get_published_for_update(
            template_key=template.template_key, channel=template.channel
        )
        if previous is not None and previous.id != template.id:
            previous.archive()
            self._templates.save(previous)

        template.publish()
        self._templates.save(template)
        return template

    # --- Compose/Send Broadcast + Audience Selection (Admin Web §4.12,
    #     ADR-0055) -----------------------------------------------------

    def create_broadcast(
        self,
        *,
        channel: Channel,
        subject: str | None,
        body: str,
        audience_type: AudienceType,
        audience_user_ids: list[uuid.UUID] | None,
        scheduled_at: datetime | None,
        created_by: uuid.UUID,
        now: datetime,
    ) -> Broadcast:
        """Validates first (Broadcast.new() below is pure, no I/O), then
        publishes a broadcast-only Template — `event_key=None`, exactly
        the "manual/admin-broadcast use only" case ADR-0044's own schema
        comment anticipated — and inserts the Broadcast row referencing
        it. Deliberately does NOT dispatch anything: composing send()
        across the customer/driver/geo module boundaries this service
        does not import stays at the router layer (modules/admin/
        router.py's own established composition pattern, e.g. CSV Bulk
        Customer Targeting's phone-resolution composition). Callers
        dispatch immediately via modules.notification.broadcast_dispatch.
        dispatch_broadcast() when scheduled_at resolves to None (send
        now), then call mark_broadcast_sent(); a still-future
        scheduled_at is left SCHEDULED for tasks.py's Celery Beat task
        to pick up later."""
        assert self._broadcasts is not None, "create_broadcast needs broadcasts"
        template_key = f"BROADCAST_{uuid.uuid4().hex}"
        broadcast = Broadcast.new(
            channel=channel,
            template_key=template_key,
            subject=subject,
            body=body,
            audience_type=audience_type,
            audience_user_ids=audience_user_ids,
            scheduled_at=scheduled_at,
            created_by=created_by,
            now=now,
        )
        template = self.create_template(
            template_key=template_key,
            channel=channel.value,
            event_key=None,
            title=subject,
            body=body,
            created_by=created_by,
            now=now,
        )
        self.publish_template(template.id)
        return self._broadcasts.create(broadcast)

    def get_broadcast(self, broadcast_id: uuid.UUID) -> Broadcast:
        assert self._broadcasts is not None
        broadcast = self._broadcasts.get_by_id(broadcast_id)
        if broadcast is None:
            raise BroadcastNotFoundError("Broadcast not found.")
        return broadcast

    def search_broadcasts(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[Broadcast], int]:
        assert self._broadcasts is not None
        return self._broadcasts.search(status=status, offset=offset, limit=limit)

    def list_due_broadcasts(self, *, now: datetime) -> list[Broadcast]:
        """Every SCHEDULED broadcast whose scheduled_at has arrived —
        tasks.py's Celery Beat task polls this."""
        assert self._broadcasts is not None
        return self._broadcasts.list_due(now=now)

    def mark_broadcast_sent(
        self,
        broadcast_id: uuid.UUID,
        *,
        sent_count: int,
        failed_count: int,
        now: datetime,
    ) -> Broadcast:
        assert self._broadcasts is not None
        broadcast = self.get_broadcast(broadcast_id)
        broadcast.mark_sent(sent_count=sent_count, failed_count=failed_count, now=now)
        self._broadcasts.save(broadcast)
        return broadcast
