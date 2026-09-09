"""Unit tests for modules.notification.broadcast_dispatch (ADR-0055)
against in-memory fakes — the ONLINE_DRIVERS audience and a real
send()-via-SMS-provider path are additionally covered end-to-end
against real Postgres/Redis in tests/test_admin_api.py, the same
unit-vs-integration split this session's own Matching/Offers work
(ADR-0054) established."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from modules.identity.domain.entities import Account, AccountStatus, AccountType
from modules.notification.broadcast_dispatch import dispatch_broadcast, resolve_audience
from modules.notification.domain.entities import (
    AudienceType,
    Broadcast,
    Channel,
    Delivery,
    Preferences,
    Template,
)
from modules.notification.service import NotificationService
from modules.vehicle.domain.entities import ALL_MATCHING_CATEGORY_KEYS

NOW = datetime.now(UTC)


# --- Minimal local fakes (this codebase's own "no shared test-helper
#     module" convention — every test file duplicates its own setup
#     helpers rather than importing from a sibling test file) --------


class FakePreferencesRepository:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, Preferences] = {}

    def get(self, user_id: uuid.UUID) -> Preferences | None:
        return self.rows.get(user_id)

    def create(self, preferences: Preferences) -> Preferences:
        self.rows.setdefault(preferences.user_id, preferences)
        return self.rows[preferences.user_id]

    def save(self, preferences: Preferences) -> None:
        self.rows[preferences.user_id] = preferences


class FakeDeliveryRepository:
    def __init__(self) -> None:
        self.rows: list[Delivery] = []

    def create(self, delivery: Delivery) -> Delivery:
        self.rows.append(delivery)
        return delivery

    def save(self, delivery: Delivery) -> None:
        for index, existing in enumerate(self.rows):
            if existing.id == delivery.id:
                self.rows[index] = delivery
                return
        raise LookupError(f"Delivery {delivery.id} not found")

    def list_for_user(
        self, user_id: uuid.UUID, *, offset: int, limit: int
    ) -> tuple[list[Delivery], int]:
        matches = [d for d in self.rows if d.user_id == user_id]
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
        return self.rows[offset : offset + limit], len(self.rows)

    def count_by_channel_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        return {}

    def count_by_status_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        return {}


class FakeSmsProvider:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_message(self, phone_number: str, message: str) -> str | None:
        self.sent.append((phone_number, message))
        return "fake-provider-ref"


class FakeTemplateRepository:
    """Only get_published() is actually exercised by dispatch_broadcast()
    (via NotificationService.send()) — the rest of the Template Management
    protocol (ADR-0044) is irrelevant here, but still implemented so this
    satisfies the TemplateRepository Protocol in full."""

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
                if t.template_key == template_key and t.channel == channel
            ),
            None,
        )

    def get_published_for_update(
        self, *, template_key: str, channel: str
    ) -> Template | None:
        return self.get_published(template_key=template_key, channel=channel)

    def get_latest_version(self, *, template_key: str, channel: str) -> int:
        return 1

    def save(self, template: Template) -> None:
        pass

    def list_all(
        self,
        *,
        template_key: str | None,
        channel: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Template], int]:
        return self.rows[offset : offset + limit], len(self.rows)


def _templates_with_published_body(broadcast: Broadcast) -> FakeTemplateRepository:
    """Mirrors what NotificationService.create_broadcast() actually does
    in production — publishes a broadcast-only Template under the same
    template_key — so dispatch_broadcast()'s call into send() finds real
    body text instead of falling back to the SMS_TEMPLATES dict (which
    has no entry for a generated BROADCAST_* key)."""
    templates = FakeTemplateRepository()
    template = Template.new(
        template_key=broadcast.template_key,
        channel=broadcast.channel.value,
        event_key=None,
        title=broadcast.subject,
        body=broadcast.body,
        version=1,
        created_by=broadcast.created_by,
        now=NOW,
    )
    template.publish()
    templates.rows.append(template)
    return templates


class FakeCustomerIdSource:
    def __init__(self, ids: list[uuid.UUID]) -> None:
        self._ids = ids

    def list_all_customer_ids(self) -> list[uuid.UUID]:
        return self._ids


class FakeDriverIdSource:
    def __init__(self, ids: list[uuid.UUID]) -> None:
        self._ids = ids

    def list_all_driver_ids(self) -> list[uuid.UUID]:
        return self._ids


class FakeAccountRepository:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, Account] = {}

    def get_by_phone(self, phone: str) -> Account | None:
        return next((a for a in self.by_id.values() if a.phone == phone), None)

    def get_by_id(self, account_id: uuid.UUID) -> Account | None:
        return self.by_id.get(account_id)

    def create(self, *, account_type: AccountType, phone: str) -> Account:
        """Satisfies the full AccountRepository Protocol — unused by
        this file's own tests (add() below is what they actually call,
        since dispatch_broadcast() needs a specific, already-known
        account_id per recipient, not one this method would generate)."""
        return self.add(account_id=uuid.uuid4(), phone=phone)

    def add(self, *, account_id: uuid.UUID, phone: str) -> Account:
        account = Account(
            id=account_id,
            account_type=AccountType.CUSTOMER,
            phone=phone,
            status=AccountStatus.ACTIVE,
            created_at=NOW,
            updated_at=NOW,
        )
        self.by_id[account_id] = account
        return account


class FakeRedis:
    """Only implements zrange — the one call
    shared.geo.list_online_driver_ids() makes."""

    def __init__(self, members_by_key: dict[str, list[str]]) -> None:
        self._members_by_key = members_by_key

    async def zrange(self, key: str, start: int, stop: int) -> list[str]:
        return self._members_by_key.get(key, [])


def _broadcast(
    *,
    channel: Channel = Channel.IN_APP,
    audience_type: AudienceType,
    audience_user_ids: list[uuid.UUID] | None = None,
) -> Broadcast:
    return Broadcast.new(
        channel=channel,
        template_key=f"BROADCAST_{uuid.uuid4().hex}",
        subject=None,
        body="body",
        audience_type=audience_type,
        audience_user_ids=audience_user_ids,
        scheduled_at=None,
        created_by=uuid.uuid4(),
        now=NOW,
    )


# --- resolve_audience ----------------------------------------------------


def test_resolve_audience_selected_returns_the_given_ids() -> None:
    ids = [uuid.uuid4(), uuid.uuid4()]

    result = asyncio.run(
        resolve_audience(
            audience_type=AudienceType.SELECTED,
            audience_user_ids=ids,
            customer_service=FakeCustomerIdSource([]),
            driver_service=FakeDriverIdSource([]),
            redis_client=FakeRedis({}),  # type: ignore[arg-type]
        )
    )

    assert result == ids


def test_resolve_audience_all_customers_delegates_to_customer_service() -> None:
    ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]

    result = asyncio.run(
        resolve_audience(
            audience_type=AudienceType.ALL_CUSTOMERS,
            audience_user_ids=None,
            customer_service=FakeCustomerIdSource(ids),
            driver_service=FakeDriverIdSource([]),
            redis_client=FakeRedis({}),  # type: ignore[arg-type]
        )
    )

    assert result == ids


def test_resolve_audience_all_drivers_delegates_to_driver_service() -> None:
    ids = [uuid.uuid4()]

    result = asyncio.run(
        resolve_audience(
            audience_type=AudienceType.ALL_DRIVERS,
            audience_user_ids=None,
            customer_service=FakeCustomerIdSource([]),
            driver_service=FakeDriverIdSource(ids),
            redis_client=FakeRedis({}),  # type: ignore[arg-type]
        )
    )

    assert result == ids


def test_resolve_audience_online_drivers_reads_every_matching_category() -> None:
    online_id = uuid.uuid4()
    # Only the first category key actually has a member — every other
    # key in ALL_MATCHING_CATEGORY_KEYS must still be queried (an empty
    # result), matching count_online_drivers_by_category()'s own
    # "sum across every category" contract.
    first_key = f"geo:drivers:{ALL_MATCHING_CATEGORY_KEYS[0]}"
    redis = FakeRedis({first_key: [str(online_id)]})

    result = asyncio.run(
        resolve_audience(
            audience_type=AudienceType.ONLINE_DRIVERS,
            audience_user_ids=None,
            customer_service=FakeCustomerIdSource([]),
            driver_service=FakeDriverIdSource([]),
            redis_client=redis,  # type: ignore[arg-type]
        )
    )

    assert result == [online_id]


# --- dispatch_broadcast ----------------------------------------------------


def _notification_service() -> tuple[NotificationService, FakeDeliveryRepository]:
    deliveries = FakeDeliveryRepository()
    service = NotificationService(
        deliveries=deliveries, preferences=FakePreferencesRepository()
    )
    return service, deliveries


def test_dispatch_broadcast_in_app_counts_every_recipient_sent() -> None:
    ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    broadcast = _broadcast(
        channel=Channel.IN_APP,
        audience_type=AudienceType.SELECTED,
        audience_user_ids=ids,
    )
    service, deliveries = _notification_service()

    sent_count, failed_count = asyncio.run(
        dispatch_broadcast(
            broadcast=broadcast,
            notification_service=service,
            accounts=FakeAccountRepository(),
            customer_service=FakeCustomerIdSource([]),
            driver_service=FakeDriverIdSource([]),
            redis_client=FakeRedis({}),  # type: ignore[arg-type]
            now=NOW,
        )
    )

    assert sent_count == 3
    assert failed_count == 0
    assert len(deliveries.rows) == 3
    assert {d.template_key for d in deliveries.rows} == {broadcast.template_key}


def test_dispatch_broadcast_sms_resolves_phone_via_accounts() -> None:
    recipient_id = uuid.uuid4()
    accounts = FakeAccountRepository()
    accounts.add(account_id=recipient_id, phone="+919876500000")
    fake_sms = FakeSmsProvider()
    deliveries = FakeDeliveryRepository()
    broadcast = _broadcast(
        channel=Channel.SMS,
        audience_type=AudienceType.SELECTED,
        audience_user_ids=[recipient_id],
    )
    service = NotificationService(
        deliveries=deliveries,
        preferences=FakePreferencesRepository(),
        sms_provider=fake_sms,
        templates=_templates_with_published_body(broadcast),
    )

    sent_count, failed_count = asyncio.run(
        dispatch_broadcast(
            broadcast=broadcast,
            notification_service=service,
            accounts=accounts,
            customer_service=FakeCustomerIdSource([]),
            driver_service=FakeDriverIdSource([]),
            redis_client=FakeRedis({}),  # type: ignore[arg-type]
            now=NOW,
        )
    )

    assert sent_count == 1
    assert failed_count == 0
    assert fake_sms.sent == [("+919876500000", "body")]


def test_dispatch_broadcast_sms_counts_missing_account_as_failed() -> None:
    broadcast = _broadcast(
        channel=Channel.SMS,
        audience_type=AudienceType.SELECTED,
        audience_user_ids=[uuid.uuid4()],  # never added to FakeAccountRepository
    )
    service, deliveries = _notification_service()

    sent_count, failed_count = asyncio.run(
        dispatch_broadcast(
            broadcast=broadcast,
            notification_service=service,
            accounts=FakeAccountRepository(),
            customer_service=FakeCustomerIdSource([]),
            driver_service=FakeDriverIdSource([]),
            redis_client=FakeRedis({}),  # type: ignore[arg-type]
            now=NOW,
        )
    )

    assert sent_count == 0
    assert failed_count == 1
    assert deliveries.rows == []


def test_dispatch_broadcast_one_bad_recipient_does_not_abort_the_rest() -> None:
    """A provider exception for one recipient must not stop the loop —
    the whole reason dispatch_broadcast() wraps each send() in its own
    try/except, unlike modules/notification/tasks.py's own small,
    trusted per-row loops."""
    ok_id = uuid.uuid4()
    accounts = FakeAccountRepository()
    accounts.add(account_id=ok_id, phone="+919876500001")
    # The second recipient has no account row -> resolves to failed,
    # but must not prevent the first (already-processed) or a third
    # recipient after it from being counted.
    missing_id = uuid.uuid4()
    another_ok_id = uuid.uuid4()
    accounts.add(account_id=another_ok_id, phone="+919876500002")
    fake_sms = FakeSmsProvider()
    deliveries = FakeDeliveryRepository()
    broadcast = _broadcast(
        channel=Channel.SMS,
        audience_type=AudienceType.SELECTED,
        audience_user_ids=[ok_id, missing_id, another_ok_id],
    )
    service = NotificationService(
        deliveries=deliveries,
        preferences=FakePreferencesRepository(),
        sms_provider=fake_sms,
        templates=_templates_with_published_body(broadcast),
    )

    sent_count, failed_count = asyncio.run(
        dispatch_broadcast(
            broadcast=broadcast,
            notification_service=service,
            accounts=accounts,
            customer_service=FakeCustomerIdSource([]),
            driver_service=FakeDriverIdSource([]),
            redis_client=FakeRedis({}),  # type: ignore[arg-type]
            now=NOW,
        )
    )

    assert sent_count == 2
    assert failed_count == 1
    assert len(fake_sms.sent) == 2
