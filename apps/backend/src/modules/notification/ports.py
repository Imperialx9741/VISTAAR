"""Abstract interfaces (ports) the application layer depends on."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol

from modules.notification.domain.entities import (
    Broadcast,
    Delivery,
    DeviceToken,
    Preferences,
    Template,
)


class PreferencesRepository(Protocol):
    def get(self, user_id: uuid.UUID) -> Preferences | None:
        """Unlocked read — None if no row exists yet (the caller
        auto-provisions a default via get_or_create(), matching
        CustomerService.get_profile()'s own precedent)."""
        ...

    def create(self, preferences: Preferences) -> Preferences:
        """Inserts `preferences`. Racing concurrent first-reads for the
        same user_id are handled the same way GpsDisputeRepository's
        siblings handle their own races — see NotificationService.
        get_or_create_preferences()'s own docstring."""
        ...

    def save(self, preferences: Preferences) -> None:
        """Persists `preferences`'s current enabled flags back onto the
        existing row."""
        ...


class DeliveryRepository(Protocol):
    def create(self, delivery: Delivery) -> Delivery:
        """Inserts `delivery`. Safe under concurrent double-submission
        of the same (user_id, channel, template_key, event_id): migration
        b8e4f27a5c93's uq_notification_deliveries_dedup means a genuine
        duplicate insert raises IntegrityError — the implementation
        catches this and returns the already-existing row instead, the
        same idempotent-on-conflict shape modules.penalty.repositories.
        SqlAlchemyPenaltyRepository.create() already established."""
        ...

    def save(self, delivery: Delivery) -> None:
        """Persists `delivery`'s current status/provider_reference/
        delivered_at/retry_count back onto the existing row."""
        ...

    def get_by_id_for_update(self, delivery_id: uuid.UUID) -> Delivery | None:
        """Row-locked (ADR-0075) — same `.with_for_update()` pattern
        `TemplateRepository.get_by_id_for_update()` below already
        established in this module, for `retry_delivery()`'s own
        transaction."""
        ...

    def list_for_user(
        self, user_id: uuid.UUID, *, offset: int, limit: int
    ) -> tuple[list[Delivery], int]:
        """Newest-first. No endpoint reads this yet (ADR-0034 Decision
        1) — ready for whichever future task documents one."""
        ...

    def search(
        self,
        *,
        user_id: uuid.UUID | None,
        channel: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Delivery], int]:
        """Admin Web §4.12's "Notification history / delivery status" —
        unlike list_for_user(), not scoped to one user_id (that filter
        stays optional here). Newest first."""
        ...

    def count_by_channel_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        """Admin Web §4.16 Notifications report (ADR-0047) —
        `created_at` in [since, until)."""
        ...

    def count_by_status_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]: ...


class TemplateRepository(Protocol):
    """ADR-0044 — Notification Template Management."""

    def create(self, template: Template) -> Template:
        """Inserts `template`. Callers compute `version` beforehand via
        get_latest_version()."""
        ...

    def get_by_id(self, template_id: uuid.UUID) -> Template | None: ...

    def get_by_id_for_update(self, template_id: uuid.UUID) -> Template | None:
        """Row-locked, for the Publish transaction."""
        ...

    def get_published(self, *, template_key: str, channel: str) -> Template | None:
        """The live version NotificationService.send() renders — None
        if no PUBLISHED row exists for this (template_key, channel),
        in which case the caller falls back to its own last-resort
        constant (ADR-0044, same "no fallback is too fragile" lesson
        ADR-0043 already learned)."""
        ...

    def get_published_for_update(
        self, *, template_key: str, channel: str
    ) -> Template | None:
        """Row-locked, so Publish can archive the prior live version
        in the same transaction without a race."""
        ...

    def get_latest_version(self, *, template_key: str, channel: str) -> int:
        """0 if no version exists yet for this (template_key, channel)
        — the next Create call uses this + 1."""
        ...

    def save(self, template: Template) -> None:
        """Persists `template`'s current `status` back onto the
        existing row — the only mutable field post-creation."""
        ...

    def list_all(
        self,
        *,
        template_key: str | None,
        channel: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Template], int]:
        """Version history — every status, not just PUBLISHED, newest
        version first."""
        ...


class SmsMessageProvider(Protocol):
    """A generalization of modules.identity.sms's existing OTP-only
    SmsProvider protocol — ADR-0034 Decision 4. Returns an optional
    provider-assigned reference (e.g. a message ID) on success."""

    async def send_message(self, phone_number: str, message: str) -> str | None: ...


class DeviceTokenRepository(Protocol):
    """ADR-0052 — Push Notifications device registration."""

    def upsert(self, device_token: DeviceToken) -> DeviceToken:
        """Insert-or-update keyed on `token` itself (globally unique per
        app install, not per user) — re-registering the same token
        refreshes updated_at and re-associates it with whichever
        account is currently authenticated."""
        ...

    def list_for_user(self, user_id: uuid.UUID) -> list[DeviceToken]:
        """Every registered device for this user — a real push send
        fans out to all of them."""
        ...

    def delete(self, *, user_id: uuid.UUID, token: str) -> None:
        """No-op (not an error) if no such row exists for this user —
        matching this codebase's own established idempotent-delete
        convention (e.g. shared/geo.py's remove_driver_location())."""
        ...


class PushProvider(Protocol):
    """ADR-0052 — mirrors modules.identity.ports.SmsProvider's own
    provider-neutral shape exactly. Returns an optional provider-
    assigned reference (e.g. FCM's message name) on success."""

    async def send(self, token: str, *, title: str, body: str) -> str | None: ...


class BroadcastRepository(Protocol):
    """ADR-0055 — Compose/Send Broadcast + Audience Selection."""

    def create(self, broadcast: Broadcast) -> Broadcast:
        """Inserts `broadcast`."""
        ...

    def get_by_id(self, broadcast_id: uuid.UUID) -> Broadcast | None: ...

    def save(self, broadcast: Broadcast) -> None:
        """Persists `broadcast`'s current status/sent_count/failed_count/
        sent_at back onto the existing row — the only mutable fields
        post-creation."""
        ...

    def search(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[Broadcast], int]:
        """Admin Web §4.12's broadcast history — newest first."""
        ...

    def list_due(self, *, now: datetime) -> list[Broadcast]:
        """Every SCHEDULED broadcast whose scheduled_at has arrived —
        polled periodically by modules.notification.tasks' Celery Beat
        task (ADR-0039's own foundation), not pushed to. An immediate
        (scheduled_at=None) broadcast is dispatched synchronously by
        NotificationService.create_broadcast() itself and never appears
        here — this only ever surfaces broadcasts that were still
        SCHEDULED as of some prior request."""
        ...
