"""Notification domain entities.

Field shapes match docs/04-database/database-design.md §32.1
(notification.preferences) and §32.2 (notification.deliveries) exactly
(ADR-0034).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from modules.notification.domain.errors import (
    InvalidBroadcastInputError,
    InvalidTemplateInputError,
    InvalidTemplateStateTransitionError,
)


class Channel(StrEnum):
    """§32.1's three documented preference columns (push/sms/whatsapp)
    plus IN_APP, which has no preference column — ADR-0034 Decision 6.
    PUSH/WHATSAPP have no real provider yet (ADR-0034 Decisions 2/3);
    they exist here because the schema already documents them, the same
    "0 for now, not deleted" treatment this codebase gives every other
    documented-but-currently-inert field."""

    IN_APP = "IN_APP"
    SMS = "SMS"
    PUSH = "PUSH"
    WHATSAPP = "WHATSAPP"


class DeliveryStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class Platform(StrEnum):
    """ADR-0052 — the three real client platforms an FCM token can come
    from. No source document enumerates these; matches Firebase's own
    documented client SDKs (Android/iOS/Web) rather than inventing a
    different set."""

    ANDROID = "ANDROID"
    IOS = "IOS"
    WEB = "WEB"


@dataclass(slots=True)
class DeviceToken:
    """ADR-0052 — one row per registered push token. `user_id` is a bare
    UUID, not a foreign key — the same "no single users table" reasoning
    Delivery.user_id/Preferences.user_id below already rely on (a user
    may be a customer, driver, or admin; those identities live in three
    separate tables sharing only identity.accounts.id)."""

    id: uuid.UUID
    user_id: uuid.UUID
    platform: Platform
    token: str
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def new(
        *, user_id: uuid.UUID, platform: Platform, token: str, now: datetime
    ) -> DeviceToken:
        return DeviceToken(
            id=uuid.uuid4(),
            user_id=user_id,
            platform=platform,
            token=token,
            created_at=now,
            updated_at=now,
        )


@dataclass(slots=True)
class Preferences:
    user_id: uuid.UUID
    push_enabled: bool
    sms_enabled: bool
    whatsapp_enabled: bool
    updated_at: datetime

    @staticmethod
    def default(*, user_id: uuid.UUID, now: datetime) -> Preferences:
        """database-design.md §32.1's documented defaults — all three
        channels enabled until a user explicitly opts out."""
        return Preferences(
            user_id=user_id,
            push_enabled=True,
            sms_enabled=True,
            whatsapp_enabled=True,
            updated_at=now,
        )


@dataclass(slots=True)
class Delivery:
    id: uuid.UUID
    user_id: uuid.UUID
    channel: Channel
    template_key: str
    event_id: uuid.UUID | None
    status: DeliveryStatus
    provider_reference: str | None
    created_at: datetime
    delivered_at: datetime | None
    # Which notification.templates row (a specific version) was
    # actually rendered for this delivery (ADR-0044 Decision 2) — None
    # for every delivery sent before this shipped, and also whenever no
    # PUBLISHED template row existed at send time and the old hardcoded
    # SMS_TEMPLATES fallback was used instead. Stamped once, at
    # creation; never changes afterward — proves what was sent even if
    # the template is edited later.
    template_version_id: uuid.UUID | None = None
    # ADR-0075 — 0 (default) means never retried; retry_delivery() below
    # sets this to 1 after its one bounded attempt, whichever way it
    # landed, so the retry task's own query never revisits this row
    # again. Never decremented; no meaning above 1 exists yet.
    retry_count: int = 0

    @staticmethod
    def new(
        *,
        user_id: uuid.UUID,
        channel: Channel,
        template_key: str,
        event_id: uuid.UUID | None,
        now: datetime,
        template_version_id: uuid.UUID | None = None,
    ) -> Delivery:
        return Delivery(
            id=uuid.uuid4(),
            user_id=user_id,
            channel=channel,
            template_key=template_key,
            event_id=event_id,
            status=DeliveryStatus.PENDING,
            provider_reference=None,
            template_version_id=template_version_id,
            created_at=now,
            delivered_at=None,
        )

    def mark_sent(self, *, provider_reference: str | None, now: datetime) -> None:
        self.status = DeliveryStatus.SENT
        self.provider_reference = provider_reference
        self.delivered_at = now

    def mark_failed(self, *, provider_reference: str | None) -> None:
        self.status = DeliveryStatus.FAILED
        self.provider_reference = provider_reference


class TemplateStatus(StrEnum):
    """DRAFT -> PUBLISHED, plus ARCHIVED for a version publishing has
    superseded (ADR-0044 Decision 1). Simpler than FareRuleStatus/
    RewardConfigStatus's DRAFT/IN_REVIEW/PUBLISHED — the owner's own
    requirement list asked for "draft/publish", not a review step."""

    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


@dataclass(slots=True)
class Template:
    """One version in the append-only chain for a (template_key,
    channel) pair (ADR-0044 Decision 1). Editing an existing template
    creates a new row (`version = previous + 1`, `status = DRAFT`)
    rather than mutating one in place — the version chain itself IS the
    version history, no separate history table."""

    id: uuid.UUID
    template_key: str
    channel: str
    event_key: str | None
    title: str | None
    body: str
    version: int
    status: TemplateStatus
    created_by: uuid.UUID
    created_at: datetime

    @staticmethod
    def new(
        *,
        template_key: str,
        channel: str,
        event_key: str | None,
        title: str | None,
        body: str,
        version: int,
        created_by: uuid.UUID,
        now: datetime,
    ) -> Template:
        if not body.strip():
            raise InvalidTemplateInputError("body must not be blank.")
        return Template(
            id=uuid.uuid4(),
            template_key=template_key,
            channel=channel,
            event_key=event_key,
            title=title,
            body=body,
            version=version,
            status=TemplateStatus.DRAFT,
            created_by=created_by,
            created_at=now,
        )

    def publish(self) -> None:
        if self.status is not TemplateStatus.DRAFT:
            raise InvalidTemplateStateTransitionError(
                f"Cannot publish a template version in status {self.status}."
            )
        self.status = TemplateStatus.PUBLISHED

    def archive(self) -> None:
        """Called on the prior PUBLISHED version for the same
        (template_key, channel) in the same transaction that publishes
        a new one (ADR-0044 Decision 1) — "un-publish", not delete."""
        self.status = TemplateStatus.ARCHIVED


class AudienceType(StrEnum):
    """ADR-0055 Decision 3 — who a broadcast resolves to at send time.
    Resolution always happens server-side, fresh, at the moment of
    actual dispatch (never a client-supplied id list except SELECTED,
    and never a snapshot taken at compose time) — membership of
    ALL_CUSTOMERS/ALL_DRIVERS/ONLINE_DRIVERS can change between when a
    scheduled broadcast is created and when it actually sends."""

    ALL_CUSTOMERS = "ALL_CUSTOMERS"
    ALL_DRIVERS = "ALL_DRIVERS"
    ONLINE_DRIVERS = "ONLINE_DRIVERS"
    SELECTED = "SELECTED"


class BroadcastStatus(StrEnum):
    """No FAILED state at the broadcast level — an individual
    recipient's send failing (bad phone, no device token, provider
    error) is tracked per-recipient in failed_count, not treated as the
    whole broadcast failing; SENT means "dispatch ran," not "every
    recipient necessarily received it," the same distinction
    Delivery.status already draws one level down."""

    SCHEDULED = "SCHEDULED"
    SENT = "SENT"


@dataclass(slots=True)
class Broadcast:
    """ADR-0055 (Tier C) — Compose/Send Broadcast + Audience Selection.

    Composition reuses `notification.templates` exactly as ADR-0044's
    own schema comment anticipated ("a template may exist for manual/
    admin-broadcast use only, not tied to an automatic trigger"): a
    broadcast's free-text subject/body is published as a one-off
    `Template` (`event_key=None`, a `template_key` unique to this
    broadcast) at creation time, and every recipient's actual
    `NotificationService.send()` call dispatches that template — so a
    broadcast's `Delivery` rows are indistinguishable in kind from any
    other admin-triggered notification, and get the same
    `template_version_id` provenance stamp for free.
    """

    id: uuid.UUID
    channel: Channel
    template_key: str
    subject: str | None
    body: str
    audience_type: AudienceType
    audience_user_ids: list[uuid.UUID] | None
    status: BroadcastStatus
    scheduled_at: datetime | None
    sent_count: int
    failed_count: int
    created_by: uuid.UUID
    created_at: datetime
    sent_at: datetime | None

    @staticmethod
    def new(
        *,
        channel: Channel,
        template_key: str,
        subject: str | None,
        body: str,
        audience_type: AudienceType,
        audience_user_ids: list[uuid.UUID] | None,
        scheduled_at: datetime | None,
        created_by: uuid.UUID,
        now: datetime,
    ) -> Broadcast:
        if channel is Channel.WHATSAPP:
            raise InvalidBroadcastInputError(
                "WHATSAPP has no provider configured yet (ADR-0034 "
                "Decision 3 — BSP not yet picked); choose IN_APP, SMS, "
                "or PUSH."
            )
        if not body.strip():
            raise InvalidBroadcastInputError("body must not be blank.")
        if audience_type is AudienceType.SELECTED:
            if not audience_user_ids:
                raise InvalidBroadcastInputError(
                    "audience_user_ids is required and must be non-empty "
                    "when audience_type is SELECTED."
                )
        elif audience_user_ids:
            raise InvalidBroadcastInputError(
                "audience_user_ids is only accepted when audience_type is SELECTED."
            )
        if scheduled_at is not None and scheduled_at <= now:
            # Same-as-now or past is treated as "send now", not an
            # error — matches Publish Fare Rule's own "omitted means
            # effective now" precedent rather than rejecting a
            # borderline timestamp.
            scheduled_at = None
        # Always starts SCHEDULED, even when scheduled_at is None (=
        # "due immediately") — the caller (NotificationService.
        # create_broadcast()) dispatches and calls mark_sent() right
        # after insert for the immediate case, so this constructor
        # never has to guess whether dispatch will actually succeed
        # before it has even been attempted.
        return Broadcast(
            id=uuid.uuid4(),
            channel=channel,
            template_key=template_key,
            subject=subject,
            body=body,
            audience_type=audience_type,
            audience_user_ids=audience_user_ids,
            status=BroadcastStatus.SCHEDULED,
            scheduled_at=scheduled_at,
            sent_count=0,
            failed_count=0,
            created_by=created_by,
            created_at=now,
            sent_at=None,
        )

    def mark_sent(self, *, sent_count: int, failed_count: int, now: datetime) -> None:
        self.status = BroadcastStatus.SENT
        self.sent_count = sent_count
        self.failed_count = failed_count
        self.sent_at = now
