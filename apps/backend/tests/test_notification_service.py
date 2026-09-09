"""Unit tests for NotificationService against in-memory fake
repositories and a fake SMS provider (ADR-0034).

Async send() calls are driven via asyncio.run() from ordinary sync test
functions — no pytest-asyncio plugin is configured in this codebase
(see tests/test_identity_sms.py's identical pattern)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from modules.notification.domain.entities import (
    AudienceType,
    Broadcast,
    BroadcastStatus,
    Channel,
    Delivery,
    DeliveryStatus,
    DeviceToken,
    Platform,
    Preferences,
    Template,
    TemplateStatus,
)
from modules.notification.domain.errors import (
    BroadcastNotFoundError,
    ChannelNotAvailableError,
    InvalidBroadcastInputError,
    InvalidTemplateStateTransitionError,
    TemplateNotFoundError,
    UnknownTemplateError,
)
from modules.notification.domain.templates import render_sms
from modules.notification.service import NotificationService

USER_ID = uuid.uuid4()
NOW = datetime.now(UTC)


class FakePreferencesRepository:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, Preferences] = {}

    def get(self, user_id: uuid.UUID) -> Preferences | None:
        return self.rows.get(user_id)

    def create(self, preferences: Preferences) -> Preferences:
        if preferences.user_id in self.rows:
            return self.rows[preferences.user_id]
        self.rows[preferences.user_id] = preferences
        return preferences

    def save(self, preferences: Preferences) -> None:
        if preferences.user_id not in self.rows:
            raise LookupError(f"Preferences for {preferences.user_id} not found")
        self.rows[preferences.user_id] = preferences


class FakeDeliveryRepository:
    def __init__(self) -> None:
        self.rows: list[Delivery] = []

    def create(self, delivery: Delivery) -> Delivery:
        existing = next(
            (
                d
                for d in self.rows
                if d.user_id == delivery.user_id
                and d.channel == delivery.channel
                and d.template_key == delivery.template_key
                and d.event_id == delivery.event_id
            ),
            None,
        )
        if existing is not None:
            # uq_notification_deliveries_dedup equivalent — idempotent.
            return existing
        self.rows.append(delivery)
        return delivery

    def save(self, delivery: Delivery) -> None:
        for index, existing in enumerate(self.rows):
            if existing.id == delivery.id:
                self.rows[index] = delivery
                return
        raise LookupError(f"Delivery {delivery.id} not found")

    def get_by_id_for_update(self, delivery_id: uuid.UUID) -> Delivery | None:
        return next((d for d in self.rows if d.id == delivery_id), None)

    def list_for_user(
        self, user_id: uuid.UUID, *, offset: int, limit: int
    ) -> tuple[list[Delivery], int]:
        matches = sorted(
            (d for d in self.rows if d.user_id == user_id),
            key=lambda d: d.created_at,
            reverse=True,
        )
        return matches[offset : offset + limit], len(matches)

    def search(
        self,
        *,
        user_id: uuid.UUID | None,
        channel: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Delivery], int]:
        matches = sorted(
            (
                d
                for d in self.rows
                if (user_id is None or d.user_id == user_id)
                and (channel is None or d.channel.value == channel)
                and (status is None or d.status.value == status)
            ),
            key=lambda d: d.created_at,
            reverse=True,
        )
        return matches[offset : offset + limit], len(matches)

    def count_by_channel_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for d in self.rows:
            if since <= d.created_at < until:
                key = d.channel.value
                counts[key] = counts.get(key, 0) + 1
        return counts

    def count_by_status_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for d in self.rows:
            if since <= d.created_at < until:
                key = d.status.value
                counts[key] = counts.get(key, 0) + 1
        return counts


class FakeTemplateRepository:
    def __init__(self) -> None:
        self.rows: list[Template] = []

    def create(self, template: Template) -> Template:
        self.rows.append(template)
        return template

    def get_by_id(self, template_id: uuid.UUID) -> Template | None:
        return next((t for t in self.rows if t.id == template_id), None)

    def get_by_id_for_update(self, template_id: uuid.UUID) -> Template | None:
        return self.get_by_id(template_id)

    def get_published(self, *, template_key: str, channel: str) -> Template | None:
        return next(
            (
                t
                for t in self.rows
                if t.template_key == template_key
                and t.channel == channel
                and t.status is TemplateStatus.PUBLISHED
            ),
            None,
        )

    def get_published_for_update(
        self, *, template_key: str, channel: str
    ) -> Template | None:
        return self.get_published(template_key=template_key, channel=channel)

    def get_latest_version(self, *, template_key: str, channel: str) -> int:
        versions = [
            t.version
            for t in self.rows
            if t.template_key == template_key and t.channel == channel
        ]
        return max(versions, default=0)

    def save(self, template: Template) -> None:
        for index, existing in enumerate(self.rows):
            if existing.id == template.id:
                self.rows[index] = template
                return
        raise LookupError(f"Template {template.id} not found")

    def list_all(
        self,
        *,
        template_key: str | None,
        channel: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Template], int]:
        matches = [
            t
            for t in self.rows
            if (template_key is None or t.template_key == template_key)
            and (channel is None or t.channel == channel)
            and (status is None or t.status.value == status)
        ]
        matches.sort(key=lambda t: t.created_at, reverse=True)
        return matches[offset : offset + limit], len(matches)


class FakeSmsProvider:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[tuple[str, str]] = []

    async def send_message(self, phone_number: str, message: str) -> str | None:
        if self.fail:
            raise RuntimeError("simulated SMS provider failure")
        self.sent.append((phone_number, message))
        return "fake-provider-ref-123"


class FakeDeviceTokenRepository:
    def __init__(self) -> None:
        self.rows: list[DeviceToken] = []

    def upsert(self, device_token: DeviceToken) -> DeviceToken:
        for index, existing in enumerate(self.rows):
            if existing.token == device_token.token:
                self.rows[index] = device_token
                return device_token
        self.rows.append(device_token)
        return device_token

    def list_for_user(self, user_id: uuid.UUID) -> list[DeviceToken]:
        return [d for d in self.rows if d.user_id == user_id]

    def delete(self, *, user_id: uuid.UUID, token: str) -> None:
        self.rows = [
            d for d in self.rows if not (d.user_id == user_id and d.token == token)
        ]


class FakePushProvider:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, token: str, *, title: str, body: str) -> str | None:
        if self.fail:
            raise RuntimeError("simulated push provider failure")
        self.sent.append((token, title, body))
        return "fake-push-message-name"


# --- render_sms ---------------------------------------------------------


def test_render_sms_returns_known_template() -> None:
    assert "accepted" in render_sms("RIDE_ACCEPTED").lower()


def test_render_sms_raises_for_unknown_template() -> None:
    with pytest.raises(UnknownTemplateError):
        render_sms("SOME_UNKNOWN_KEY")


# --- get_or_create_preferences ------------------------------------------


def test_get_or_create_preferences_creates_a_default_row() -> None:
    fake_preferences = FakePreferencesRepository()
    service = NotificationService(
        deliveries=FakeDeliveryRepository(), preferences=fake_preferences
    )

    preferences = service.get_or_create_preferences(user_id=USER_ID, now=NOW)

    assert preferences.user_id == USER_ID
    assert preferences.push_enabled is True
    assert preferences.sms_enabled is True
    assert preferences.whatsapp_enabled is True
    assert fake_preferences.rows[USER_ID] == preferences


def test_get_or_create_preferences_returns_the_existing_row() -> None:
    fake_preferences = FakePreferencesRepository()
    service = NotificationService(
        deliveries=FakeDeliveryRepository(), preferences=fake_preferences
    )
    first = service.get_or_create_preferences(user_id=USER_ID, now=NOW)

    second = service.get_or_create_preferences(user_id=USER_ID, now=NOW)

    assert second == first
    assert len(fake_preferences.rows) == 1


# --- send() — IN_APP -----------------------------------------------------


def test_send_in_app_is_immediately_marked_sent() -> None:
    fake_deliveries = FakeDeliveryRepository()
    service = NotificationService(
        deliveries=fake_deliveries, preferences=FakePreferencesRepository()
    )

    delivery = asyncio.run(
        service.send(
            user_id=USER_ID,
            channel=Channel.IN_APP,
            template_key="RIDE_ACCEPTED",
            recipient=None,
            event_id=None,
            now=NOW,
        )
    )

    assert delivery is not None
    assert delivery.status is DeliveryStatus.SENT
    assert delivery.provider_reference is None
    assert delivery.delivered_at == NOW
    assert fake_deliveries.rows == [delivery]


def test_send_in_app_is_never_gated_by_preferences() -> None:
    """No in_app_enabled column exists (ADR-0034 Decision 6) — IN_APP
    always sends regardless of what's in notification.preferences."""
    fake_preferences = FakePreferencesRepository()
    fake_preferences.rows[USER_ID] = Preferences(
        user_id=USER_ID,
        push_enabled=False,
        sms_enabled=False,
        whatsapp_enabled=False,
        updated_at=NOW,
    )
    service = NotificationService(
        deliveries=FakeDeliveryRepository(), preferences=fake_preferences
    )

    delivery = asyncio.run(
        service.send(
            user_id=USER_ID,
            channel=Channel.IN_APP,
            template_key="RIDE_ARRIVED",
            recipient=None,
            event_id=None,
            now=NOW,
        )
    )

    assert delivery is not None
    assert delivery.status is DeliveryStatus.SENT


def test_send_in_app_is_idempotent_per_dedup_key() -> None:
    fake_deliveries = FakeDeliveryRepository()
    service = NotificationService(
        deliveries=fake_deliveries, preferences=FakePreferencesRepository()
    )
    event_id = uuid.uuid4()

    async def _send_twice() -> tuple[Delivery | None, Delivery | None]:
        first = await service.send(
            user_id=USER_ID,
            channel=Channel.IN_APP,
            template_key="RIDE_ACCEPTED",
            recipient=None,
            event_id=event_id,
            now=NOW,
        )
        second = await service.send(
            user_id=USER_ID,
            channel=Channel.IN_APP,
            template_key="RIDE_ACCEPTED",
            recipient=None,
            event_id=event_id,
            now=NOW,
        )
        return first, second

    first, second = asyncio.run(_send_twice())

    assert first is not None and second is not None
    assert first.id == second.id
    assert len(fake_deliveries.rows) == 1


# --- send() — SMS ----------------------------------------------------------


def test_send_sms_dispatches_via_the_provider() -> None:
    fake_sms = FakeSmsProvider()
    service = NotificationService(
        deliveries=FakeDeliveryRepository(),
        preferences=FakePreferencesRepository(),
        sms_provider=fake_sms,
    )

    delivery = asyncio.run(
        service.send(
            user_id=USER_ID,
            channel=Channel.SMS,
            template_key="RIDE_ACCEPTED",
            recipient="+919876543210",
            event_id=None,
            now=NOW,
        )
    )

    assert delivery is not None
    assert delivery.status is DeliveryStatus.SENT
    assert delivery.provider_reference == "fake-provider-ref-123"
    assert fake_sms.sent == [("+919876543210", render_sms("RIDE_ACCEPTED"))]
    assert delivery.template_version_id is None  # no TemplateRepository wired


def test_send_sms_falls_back_when_no_template_is_published() -> None:
    """ADR-0044: a TemplateRepository IS wired, but no PUBLISHED row
    exists yet for this (template_key, channel) — same last-resort
    fallback to SMS_TEMPLATES as when no repository is wired at all."""
    fake_sms = FakeSmsProvider()
    service = NotificationService(
        deliveries=FakeDeliveryRepository(),
        preferences=FakePreferencesRepository(),
        sms_provider=fake_sms,
        templates=FakeTemplateRepository(),
    )

    delivery = asyncio.run(
        service.send(
            user_id=USER_ID,
            channel=Channel.SMS,
            template_key="RIDE_ACCEPTED",
            recipient="+919876543210",
            event_id=None,
            now=NOW,
        )
    )

    assert delivery is not None
    assert fake_sms.sent == [("+919876543210", render_sms("RIDE_ACCEPTED"))]
    assert delivery.template_version_id is None


def test_send_sms_uses_the_published_template_body_and_stamps_the_version() -> None:
    """ADR-0044 Decision 2: a PUBLISHED row for (template_key, channel)
    wins over the hardcoded SMS_TEMPLATES fallback, and its id is
    stamped on the created Delivery row."""
    fake_templates = FakeTemplateRepository()
    published = Template.new(
        template_key="RIDE_ACCEPTED",
        channel="SMS",
        event_key=None,
        title=None,
        body="Custom admin-edited wording for ride acceptance.",
        version=1,
        created_by=uuid.uuid4(),
        now=NOW,
    )
    published.publish()
    fake_templates.rows.append(published)
    fake_sms = FakeSmsProvider()
    service = NotificationService(
        deliveries=FakeDeliveryRepository(),
        preferences=FakePreferencesRepository(),
        sms_provider=fake_sms,
        templates=fake_templates,
    )

    delivery = asyncio.run(
        service.send(
            user_id=USER_ID,
            channel=Channel.SMS,
            template_key="RIDE_ACCEPTED",
            recipient="+919876543210",
            event_id=None,
            now=NOW,
        )
    )

    assert delivery is not None
    assert fake_sms.sent == [
        ("+919876543210", "Custom admin-edited wording for ride acceptance.")
    ]
    assert delivery.template_version_id == published.id


def test_send_sms_skipped_when_preference_disabled() -> None:
    fake_preferences = FakePreferencesRepository()
    fake_preferences.rows[USER_ID] = Preferences(
        user_id=USER_ID,
        push_enabled=True,
        sms_enabled=False,
        whatsapp_enabled=True,
        updated_at=NOW,
    )
    fake_sms = FakeSmsProvider()
    fake_deliveries = FakeDeliveryRepository()
    service = NotificationService(
        deliveries=fake_deliveries,
        preferences=fake_preferences,
        sms_provider=fake_sms,
    )

    delivery = asyncio.run(
        service.send(
            user_id=USER_ID,
            channel=Channel.SMS,
            template_key="RIDE_ACCEPTED",
            recipient="+919876543210",
            event_id=None,
            now=NOW,
        )
    )

    assert delivery is None
    assert fake_sms.sent == []
    assert fake_deliveries.rows == []


def test_send_sms_marks_failed_when_the_provider_raises() -> None:
    fake_sms = FakeSmsProvider(fail=True)
    fake_deliveries = FakeDeliveryRepository()
    service = NotificationService(
        deliveries=fake_deliveries,
        preferences=FakePreferencesRepository(),
        sms_provider=fake_sms,
    )

    delivery = asyncio.run(
        service.send(
            user_id=USER_ID,
            channel=Channel.SMS,
            template_key="RIDE_ACCEPTED",
            recipient="+919876543210",
            event_id=None,
            now=NOW,
        )
    )

    assert delivery is not None
    assert delivery.status is DeliveryStatus.FAILED
    assert delivery.provider_reference is None
    # The FAILED row is still persisted, not raised past the caller —
    # a notification failure must not roll back the caller's own
    # transaction (domain-design.md §20.4).
    assert fake_deliveries.rows == [delivery]


def test_send_sms_is_idempotent_per_dedup_key() -> None:
    fake_sms = FakeSmsProvider()
    fake_deliveries = FakeDeliveryRepository()
    service = NotificationService(
        deliveries=fake_deliveries,
        preferences=FakePreferencesRepository(),
        sms_provider=fake_sms,
    )
    event_id = uuid.uuid4()

    async def _send_twice() -> None:
        await service.send(
            user_id=USER_ID,
            channel=Channel.SMS,
            template_key="RIDE_ACCEPTED",
            recipient="+919876543210",
            event_id=event_id,
            now=NOW,
        )
        await service.send(
            user_id=USER_ID,
            channel=Channel.SMS,
            template_key="RIDE_ACCEPTED",
            recipient="+919876543210",
            event_id=event_id,
            now=NOW,
        )

    asyncio.run(_send_twice())

    assert len(fake_sms.sent) == 1  # not sent twice
    assert len(fake_deliveries.rows) == 1


# --- send() — PUSH (ADR-0052) -----------------------------------------------


def _push_service(
    *,
    device_tokens: FakeDeviceTokenRepository | None = None,
    push_provider: FakePushProvider | None = None,
    templates: FakeTemplateRepository | None = None,
    preferences: FakePreferencesRepository | None = None,
) -> tuple[NotificationService, FakeDeliveryRepository]:
    deliveries = FakeDeliveryRepository()
    service = NotificationService(
        deliveries=deliveries,
        preferences=preferences or FakePreferencesRepository(),
        device_tokens=device_tokens or FakeDeviceTokenRepository(),
        push_provider=push_provider or FakePushProvider(),
        templates=templates,
    )
    return service, deliveries


def _published_push_template(*, title: str = "Title", body: str = "Body") -> Template:
    return Template(
        id=uuid.uuid4(),
        template_key="SOME_EVENT",
        channel="PUSH",
        event_key=None,
        title=title,
        body=body,
        version=1,
        status=TemplateStatus.PUBLISHED,
        created_by=uuid.uuid4(),
        created_at=NOW,
    )


def test_send_push_returns_none_when_no_device_registered() -> None:
    service, deliveries = _push_service()

    result = asyncio.run(
        service.send(
            user_id=USER_ID,
            channel=Channel.PUSH,
            template_key="SOME_EVENT",
            recipient=None,
            event_id=None,
            now=NOW,
        )
    )

    assert result is None
    assert deliveries.rows == []


def test_send_push_returns_none_when_disabled_via_preferences() -> None:
    preferences = FakePreferencesRepository()
    preferences.rows[USER_ID] = Preferences(
        user_id=USER_ID,
        push_enabled=False,
        sms_enabled=True,
        whatsapp_enabled=True,
        updated_at=NOW,
    )
    device_tokens = FakeDeviceTokenRepository()
    device_tokens.rows.append(
        DeviceToken.new(
            user_id=USER_ID, platform=Platform.ANDROID, token="tok-1", now=NOW
        )
    )
    service, deliveries = _push_service(
        device_tokens=device_tokens, preferences=preferences
    )

    result = asyncio.run(
        service.send(
            user_id=USER_ID,
            channel=Channel.PUSH,
            template_key="SOME_EVENT",
            recipient=None,
            event_id=None,
            now=NOW,
        )
    )

    assert result is None
    assert deliveries.rows == []


def test_send_push_raises_when_no_published_template() -> None:
    device_tokens = FakeDeviceTokenRepository()
    device_tokens.rows.append(
        DeviceToken.new(
            user_id=USER_ID, platform=Platform.ANDROID, token="tok-1", now=NOW
        )
    )
    service, _ = _push_service(
        device_tokens=device_tokens, templates=FakeTemplateRepository()
    )

    with pytest.raises(TemplateNotFoundError):
        asyncio.run(
            service.send(
                user_id=USER_ID,
                channel=Channel.PUSH,
                template_key="SOME_EVENT",
                recipient=None,
                event_id=None,
                now=NOW,
            )
        )


def test_send_push_delivers_via_provider_with_published_template() -> None:
    device_tokens = FakeDeviceTokenRepository()
    device_tokens.rows.append(
        DeviceToken.new(
            user_id=USER_ID, platform=Platform.ANDROID, token="tok-1", now=NOW
        )
    )
    templates = FakeTemplateRepository()
    templates.rows.append(_published_push_template(title="Hi", body="There"))
    push_provider = FakePushProvider()
    service, deliveries = _push_service(
        device_tokens=device_tokens, templates=templates, push_provider=push_provider
    )

    result = asyncio.run(
        service.send(
            user_id=USER_ID,
            channel=Channel.PUSH,
            template_key="SOME_EVENT",
            recipient=None,
            event_id=None,
            now=NOW,
        )
    )

    assert result is not None
    assert result.status is DeliveryStatus.SENT
    assert push_provider.sent == [("tok-1", "Hi", "There")]


def test_send_push_fans_out_to_every_registered_device() -> None:
    device_tokens = FakeDeviceTokenRepository()
    device_tokens.rows.append(
        DeviceToken.new(
            user_id=USER_ID, platform=Platform.ANDROID, token="tok-1", now=NOW
        )
    )
    device_tokens.rows.append(
        DeviceToken.new(user_id=USER_ID, platform=Platform.IOS, token="tok-2", now=NOW)
    )
    templates = FakeTemplateRepository()
    templates.rows.append(_published_push_template())
    push_provider = FakePushProvider()
    service, _ = _push_service(
        device_tokens=device_tokens, templates=templates, push_provider=push_provider
    )

    asyncio.run(
        service.send(
            user_id=USER_ID,
            channel=Channel.PUSH,
            template_key="SOME_EVENT",
            recipient=None,
            event_id=None,
            now=NOW,
        )
    )

    assert {sent[0] for sent in push_provider.sent} == {"tok-1", "tok-2"}


def test_send_push_marks_failed_when_provider_raises() -> None:
    device_tokens = FakeDeviceTokenRepository()
    device_tokens.rows.append(
        DeviceToken.new(
            user_id=USER_ID, platform=Platform.ANDROID, token="tok-1", now=NOW
        )
    )
    templates = FakeTemplateRepository()
    templates.rows.append(_published_push_template())
    service, _ = _push_service(
        device_tokens=device_tokens,
        templates=templates,
        push_provider=FakePushProvider(fail=True),
    )

    result = asyncio.run(
        service.send(
            user_id=USER_ID,
            channel=Channel.PUSH,
            template_key="SOME_EVENT",
            recipient=None,
            event_id=None,
            now=NOW,
        )
    )

    assert result is not None
    assert result.status is DeliveryStatus.FAILED


def test_register_device_upserts_via_repository() -> None:
    device_tokens = FakeDeviceTokenRepository()
    service = NotificationService(
        deliveries=FakeDeliveryRepository(),
        preferences=FakePreferencesRepository(),
        device_tokens=device_tokens,
    )

    result = service.register_device(
        user_id=USER_ID, platform=Platform.ANDROID, token="tok-1", now=NOW
    )

    assert result.token == "tok-1"
    assert device_tokens.list_for_user(USER_ID) == [result]


def test_unregister_device_deletes_via_repository() -> None:
    device_tokens = FakeDeviceTokenRepository()
    device_tokens.rows.append(
        DeviceToken.new(
            user_id=USER_ID, platform=Platform.ANDROID, token="tok-1", now=NOW
        )
    )
    service = NotificationService(
        deliveries=FakeDeliveryRepository(),
        preferences=FakePreferencesRepository(),
        device_tokens=device_tokens,
    )

    service.unregister_device(user_id=USER_ID, token="tok-1")

    assert device_tokens.list_for_user(USER_ID) == []


def test_send_whatsapp_raises_channel_not_available() -> None:
    service = NotificationService(
        deliveries=FakeDeliveryRepository(), preferences=FakePreferencesRepository()
    )

    with pytest.raises(ChannelNotAvailableError):
        asyncio.run(
            service.send(
                user_id=USER_ID,
                channel=Channel.WHATSAPP,
                template_key="RIDE_ACCEPTED",
                recipient=None,
                event_id=None,
                now=NOW,
            )
        )


# --- Notification Template Management (ADR-0044) ----------------------


def _template_service(fake_templates: FakeTemplateRepository) -> NotificationService:
    return NotificationService(
        deliveries=FakeDeliveryRepository(),
        preferences=FakePreferencesRepository(),
        templates=fake_templates,
    )


def test_create_template_starts_at_version_1_then_increments() -> None:
    service = _template_service(FakeTemplateRepository())
    admin_id = uuid.uuid4()

    v1 = service.create_template(
        template_key="RIDE_ACCEPTED",
        channel="SMS",
        event_key="ride.accepted",
        title=None,
        body="v1 wording",
        created_by=admin_id,
        now=NOW,
    )
    v2 = service.create_template(
        template_key="RIDE_ACCEPTED",
        channel="SMS",
        event_key="ride.accepted",
        title=None,
        body="v2 wording",
        created_by=admin_id,
        now=NOW,
    )

    assert v1.version == 1
    assert v1.status is TemplateStatus.DRAFT
    assert v2.version == 2
    # A different channel for the same template_key starts its own
    # independent version chain at 1.
    push_v1 = service.create_template(
        template_key="RIDE_ACCEPTED",
        channel="PUSH",
        event_key="ride.accepted",
        title="You're on your way",
        body="push wording",
        created_by=admin_id,
        now=NOW,
    )
    assert push_v1.version == 1


def test_publish_template_archives_the_previous_published_version() -> None:
    fake_templates = FakeTemplateRepository()
    service = _template_service(fake_templates)
    admin_id = uuid.uuid4()

    v1 = service.create_template(
        template_key="RIDE_ARRIVED",
        channel="SMS",
        event_key="ride.arrived",
        title=None,
        body="v1 wording",
        created_by=admin_id,
        now=NOW,
    )
    service.publish_template(v1.id)
    v2 = service.create_template(
        template_key="RIDE_ARRIVED",
        channel="SMS",
        event_key="ride.arrived",
        title=None,
        body="v2 wording",
        created_by=admin_id,
        now=NOW,
    )

    published_v2 = service.publish_template(v2.id)

    assert published_v2.status is TemplateStatus.PUBLISHED
    archived_v1 = service.get_template(v1.id)
    assert archived_v1.status is TemplateStatus.ARCHIVED
    live = fake_templates.get_published(template_key="RIDE_ARRIVED", channel="SMS")
    assert live is not None
    assert live.id == v2.id


def test_publish_template_rejects_a_non_draft_version() -> None:
    fake_templates = FakeTemplateRepository()
    service = _template_service(fake_templates)
    admin_id = uuid.uuid4()
    v1 = service.create_template(
        template_key="RIDE_ARRIVED",
        channel="SMS",
        event_key="ride.arrived",
        title=None,
        body="v1 wording",
        created_by=admin_id,
        now=NOW,
    )
    service.publish_template(v1.id)

    with pytest.raises(InvalidTemplateStateTransitionError):
        service.publish_template(v1.id)


def test_get_template_raises_not_found_for_an_unknown_id() -> None:
    service = _template_service(FakeTemplateRepository())

    with pytest.raises(TemplateNotFoundError):
        service.get_template(uuid.uuid4())


def test_list_templates_filters_by_template_key_channel_and_status() -> None:
    fake_templates = FakeTemplateRepository()
    service = _template_service(fake_templates)
    admin_id = uuid.uuid4()
    service.create_template(
        template_key="RIDE_ACCEPTED",
        channel="SMS",
        event_key=None,
        title=None,
        body="body",
        created_by=admin_id,
        now=NOW,
    )
    other = service.create_template(
        template_key="RIDE_ARRIVED",
        channel="SMS",
        event_key=None,
        title=None,
        body="body",
        created_by=admin_id,
        now=NOW,
    )
    service.publish_template(other.id)

    items, total = service.list_templates(
        template_key="RIDE_ARRIVED",
        channel=None,
        status="PUBLISHED",
        offset=0,
        limit=20,
    )

    assert total == 1
    assert items[0].id == other.id


# --- Compose/Send Broadcast + Audience Selection (ADR-0055) --------------


class FakeBroadcastRepository:
    def __init__(self) -> None:
        self.rows: list[Broadcast] = []

    def create(self, broadcast: Broadcast) -> Broadcast:
        self.rows.append(broadcast)
        return broadcast

    def get_by_id(self, broadcast_id: uuid.UUID) -> Broadcast | None:
        return next((b for b in self.rows if b.id == broadcast_id), None)

    def save(self, broadcast: Broadcast) -> None:
        for index, existing in enumerate(self.rows):
            if existing.id == broadcast.id:
                self.rows[index] = broadcast
                return
        raise LookupError(f"Broadcast {broadcast.id} not found")

    def search(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[Broadcast], int]:
        matches = sorted(
            (b for b in self.rows if status is None or b.status.value == status),
            key=lambda b: b.created_at,
            reverse=True,
        )
        return matches[offset : offset + limit], len(matches)

    def list_due(self, *, now: datetime) -> list[Broadcast]:
        return [
            b
            for b in self.rows
            if b.status is BroadcastStatus.SCHEDULED
            and b.scheduled_at is not None
            and b.scheduled_at <= now
        ]


def _broadcast_service() -> tuple[
    NotificationService, FakeBroadcastRepository, FakeTemplateRepository
]:
    broadcasts = FakeBroadcastRepository()
    templates = FakeTemplateRepository()
    service = NotificationService(
        deliveries=FakeDeliveryRepository(),
        preferences=FakePreferencesRepository(),
        templates=templates,
        broadcasts=broadcasts,
    )
    return service, broadcasts, templates


def test_create_broadcast_publishes_a_broadcast_only_template() -> None:
    service, fake_broadcasts, fake_templates = _broadcast_service()
    admin_id = uuid.uuid4()

    broadcast = service.create_broadcast(
        channel=Channel.IN_APP,
        subject="Maintenance notice",
        body="VISTAAR will be briefly unavailable tonight for maintenance.",
        audience_type=AudienceType.ALL_CUSTOMERS,
        audience_user_ids=None,
        scheduled_at=None,
        created_by=admin_id,
        now=NOW,
    )

    assert fake_broadcasts.rows == [broadcast]
    published = next(
        t for t in fake_templates.rows if t.template_key == broadcast.template_key
    )
    assert published.status is TemplateStatus.PUBLISHED
    assert published.event_key is None
    assert published.body == broadcast.body
    # Still SCHEDULED — create_broadcast() never dispatches itself
    # (that composition lives at the router layer); an immediate
    # broadcast is flipped to SENT by mark_broadcast_sent() afterward.
    assert broadcast.status is BroadcastStatus.SCHEDULED
    assert broadcast.scheduled_at is None


def test_create_broadcast_rejects_whatsapp() -> None:
    service, _, _ = _broadcast_service()

    with pytest.raises(InvalidBroadcastInputError):
        service.create_broadcast(
            channel=Channel.WHATSAPP,
            subject=None,
            body="body",
            audience_type=AudienceType.ALL_DRIVERS,
            audience_user_ids=None,
            scheduled_at=None,
            created_by=uuid.uuid4(),
            now=NOW,
        )


def test_create_broadcast_rejects_blank_body() -> None:
    service, _, _ = _broadcast_service()

    with pytest.raises(InvalidBroadcastInputError):
        service.create_broadcast(
            channel=Channel.IN_APP,
            subject=None,
            body="   ",
            audience_type=AudienceType.ALL_DRIVERS,
            audience_user_ids=None,
            scheduled_at=None,
            created_by=uuid.uuid4(),
            now=NOW,
        )


def test_create_broadcast_selected_requires_audience_user_ids() -> None:
    service, _, _ = _broadcast_service()

    with pytest.raises(InvalidBroadcastInputError):
        service.create_broadcast(
            channel=Channel.IN_APP,
            subject=None,
            body="body",
            audience_type=AudienceType.SELECTED,
            audience_user_ids=None,
            scheduled_at=None,
            created_by=uuid.uuid4(),
            now=NOW,
        )


def test_create_broadcast_non_selected_rejects_audience_user_ids() -> None:
    service, _, _ = _broadcast_service()

    with pytest.raises(InvalidBroadcastInputError):
        service.create_broadcast(
            channel=Channel.IN_APP,
            subject=None,
            body="body",
            audience_type=AudienceType.ALL_DRIVERS,
            audience_user_ids=[uuid.uuid4()],
            scheduled_at=None,
            created_by=uuid.uuid4(),
            now=NOW,
        )


def test_create_broadcast_does_not_persist_an_invalid_broadcast_template() -> None:
    """A validation failure (Broadcast.new() is pure, no I/O) must never
    leave behind an orphan PUBLISHED template with no Broadcast row
    referencing it."""
    service, fake_broadcasts, fake_templates = _broadcast_service()

    with pytest.raises(InvalidBroadcastInputError):
        service.create_broadcast(
            channel=Channel.WHATSAPP,
            subject=None,
            body="body",
            audience_type=AudienceType.ALL_DRIVERS,
            audience_user_ids=None,
            scheduled_at=None,
            created_by=uuid.uuid4(),
            now=NOW,
        )

    assert fake_broadcasts.rows == []
    assert fake_templates.rows == []


def test_create_broadcast_past_scheduled_at_is_treated_as_now() -> None:
    service, _, _ = _broadcast_service()

    broadcast = service.create_broadcast(
        channel=Channel.IN_APP,
        subject=None,
        body="body",
        audience_type=AudienceType.ALL_DRIVERS,
        audience_user_ids=None,
        scheduled_at=NOW - timedelta(minutes=5),
        created_by=uuid.uuid4(),
        now=NOW,
    )

    assert broadcast.scheduled_at is None


def test_get_broadcast_raises_not_found() -> None:
    service, _, _ = _broadcast_service()

    with pytest.raises(BroadcastNotFoundError):
        service.get_broadcast(uuid.uuid4())


def test_search_broadcasts_filters_by_status() -> None:
    service, fake_broadcasts, _ = _broadcast_service()
    admin_id = uuid.uuid4()

    scheduled = service.create_broadcast(
        channel=Channel.IN_APP,
        subject=None,
        body="body",
        audience_type=AudienceType.ALL_DRIVERS,
        audience_user_ids=None,
        scheduled_at=NOW + timedelta(days=1),
        created_by=admin_id,
        now=NOW,
    )
    immediate = service.create_broadcast(
        channel=Channel.IN_APP,
        subject=None,
        body="body",
        audience_type=AudienceType.ALL_CUSTOMERS,
        audience_user_ids=None,
        scheduled_at=None,
        created_by=admin_id,
        now=NOW,
    )
    service.mark_broadcast_sent(immediate.id, sent_count=3, failed_count=1, now=NOW)

    scheduled_items, scheduled_total = service.search_broadcasts(
        status="SCHEDULED", offset=0, limit=20
    )
    sent_items, sent_total = service.search_broadcasts(
        status="SENT", offset=0, limit=20
    )

    assert scheduled_total == 1
    assert scheduled_items[0].id == scheduled.id
    assert sent_total == 1
    assert sent_items[0].id == immediate.id
    assert sent_items[0].sent_count == 3
    assert sent_items[0].failed_count == 1
    assert fake_broadcasts.rows  # sanity: both rows actually persisted


def test_mark_broadcast_sent_updates_status_and_counts() -> None:
    service, _, _ = _broadcast_service()
    broadcast = service.create_broadcast(
        channel=Channel.IN_APP,
        subject=None,
        body="body",
        audience_type=AudienceType.ALL_DRIVERS,
        audience_user_ids=None,
        scheduled_at=None,
        created_by=uuid.uuid4(),
        now=NOW,
    )

    updated = service.mark_broadcast_sent(
        broadcast.id, sent_count=10, failed_count=2, now=NOW
    )

    assert updated.status is BroadcastStatus.SENT
    assert updated.sent_count == 10
    assert updated.failed_count == 2
    assert updated.sent_at == NOW


# --- retry_delivery (ADR-0075) -------------------------------------------


def _failed_delivery(*, channel: Channel, template_key: str = "SOME_EVENT") -> Delivery:
    return Delivery(
        id=uuid.uuid4(),
        user_id=USER_ID,
        channel=channel,
        template_key=template_key,
        event_id=None,
        status=DeliveryStatus.FAILED,
        provider_reference=None,
        created_at=NOW,
        delivered_at=None,
    )


def test_retry_delivery_returns_none_for_an_unknown_id() -> None:
    service = NotificationService(
        deliveries=FakeDeliveryRepository(), preferences=FakePreferencesRepository()
    )

    result = asyncio.run(service.retry_delivery(uuid.uuid4(), recipient=None, now=NOW))

    assert result is None


def test_retry_delivery_is_a_noop_for_a_non_failed_delivery() -> None:
    fake_deliveries = FakeDeliveryRepository()
    pending = Delivery.new(
        user_id=USER_ID, channel=Channel.SMS, template_key="X", event_id=None, now=NOW
    )
    fake_deliveries.rows.append(pending)
    service = NotificationService(
        deliveries=fake_deliveries, preferences=FakePreferencesRepository()
    )

    result = asyncio.run(
        service.retry_delivery(pending.id, recipient="+919876543210", now=NOW)
    )

    assert result is not None
    assert result.status is DeliveryStatus.PENDING
    assert result.retry_count == 0


def test_retry_delivery_is_a_noop_once_already_retried() -> None:
    fake_deliveries = FakeDeliveryRepository()
    failed = _failed_delivery(channel=Channel.SMS)
    failed.retry_count = 1
    fake_deliveries.rows.append(failed)
    fake_sms = FakeSmsProvider()
    service = NotificationService(
        deliveries=fake_deliveries,
        preferences=FakePreferencesRepository(),
        sms_provider=fake_sms,
    )

    result = asyncio.run(
        service.retry_delivery(failed.id, recipient="+919876543210", now=NOW)
    )

    assert result is not None
    assert result.status is DeliveryStatus.FAILED
    # Never re-attempted — the provider was never called a second time.
    assert fake_sms.sent == []


def test_retry_sms_delivery_succeeding_marks_sent_and_stamps_retry_count() -> None:
    fake_deliveries = FakeDeliveryRepository()
    failed = _failed_delivery(channel=Channel.SMS, template_key="RIDE_ACCEPTED")
    fake_deliveries.rows.append(failed)
    fake_sms = FakeSmsProvider()
    service = NotificationService(
        deliveries=fake_deliveries,
        preferences=FakePreferencesRepository(),
        sms_provider=fake_sms,
    )

    result = asyncio.run(
        service.retry_delivery(failed.id, recipient="+919876543210", now=NOW)
    )

    assert result is not None
    assert result.status is DeliveryStatus.SENT
    assert result.retry_count == 1
    assert result.provider_reference == "fake-provider-ref-123"
    assert fake_sms.sent == [("+919876543210", render_sms("RIDE_ACCEPTED"))]
    # Persisted, not just returned.
    assert fake_deliveries.rows[0].status is DeliveryStatus.SENT


def test_retry_sms_delivery_failing_again_stays_failed_and_stamps_retry_count() -> None:
    fake_deliveries = FakeDeliveryRepository()
    failed = _failed_delivery(channel=Channel.SMS, template_key="RIDE_ACCEPTED")
    fake_deliveries.rows.append(failed)
    service = NotificationService(
        deliveries=fake_deliveries,
        preferences=FakePreferencesRepository(),
        sms_provider=FakeSmsProvider(fail=True),
    )

    result = asyncio.run(
        service.retry_delivery(failed.id, recipient="+919876543210", now=NOW)
    )

    assert result is not None
    assert result.status is DeliveryStatus.FAILED
    assert result.retry_count == 1


def test_retry_push_delivery_succeeding_marks_sent() -> None:
    fake_deliveries = FakeDeliveryRepository()
    failed = _failed_delivery(channel=Channel.PUSH)
    fake_deliveries.rows.append(failed)
    device_tokens = FakeDeviceTokenRepository()
    device_tokens.rows.append(
        DeviceToken.new(
            user_id=USER_ID, platform=Platform.ANDROID, token="tok-1", now=NOW
        )
    )
    templates = FakeTemplateRepository()
    templates.rows.append(_published_push_template())
    push_provider = FakePushProvider()
    service = NotificationService(
        deliveries=fake_deliveries,
        preferences=FakePreferencesRepository(),
        device_tokens=device_tokens,
        push_provider=push_provider,
        templates=templates,
    )

    result = asyncio.run(service.retry_delivery(failed.id, recipient=None, now=NOW))

    assert result is not None
    assert result.status is DeliveryStatus.SENT
    assert result.retry_count == 1
    assert push_provider.sent == [("tok-1", "Title", "Body")]


def test_retry_push_with_no_template_stamps_retried_without_sending() -> None:
    fake_deliveries = FakeDeliveryRepository()
    failed = _failed_delivery(channel=Channel.PUSH)
    fake_deliveries.rows.append(failed)
    device_tokens = FakeDeviceTokenRepository()
    device_tokens.rows.append(
        DeviceToken.new(
            user_id=USER_ID, platform=Platform.ANDROID, token="tok-1", now=NOW
        )
    )
    push_provider = FakePushProvider()
    service = NotificationService(
        deliveries=fake_deliveries,
        preferences=FakePreferencesRepository(),
        device_tokens=device_tokens,
        push_provider=push_provider,
        templates=FakeTemplateRepository(),
    )

    result = asyncio.run(service.retry_delivery(failed.id, recipient=None, now=NOW))

    assert result is not None
    assert result.status is DeliveryStatus.FAILED
    assert result.retry_count == 1
    assert push_provider.sent == []
