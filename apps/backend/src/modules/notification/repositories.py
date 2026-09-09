"""SQLAlchemy-backed implementations of Notification's ports."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

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
from modules.notification.models import (
    BroadcastORM,
    DeliveryORM,
    DeviceTokenORM,
    PreferencesORM,
    TemplateORM,
)


def _preferences_from_orm(row: PreferencesORM) -> Preferences:
    return Preferences(
        user_id=row.user_id,
        push_enabled=row.push_enabled,
        sms_enabled=row.sms_enabled,
        whatsapp_enabled=row.whatsapp_enabled,
        updated_at=row.updated_at,
    )


class SqlAlchemyPreferencesRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def get(self, user_id: uuid.UUID) -> Preferences | None:
        row = self._db.get(PreferencesORM, user_id)
        return _preferences_from_orm(row) if row else None

    def create(self, preferences: Preferences) -> Preferences:
        row = PreferencesORM(
            user_id=preferences.user_id,
            push_enabled=preferences.push_enabled,
            sms_enabled=preferences.sms_enabled,
            whatsapp_enabled=preferences.whatsapp_enabled,
        )
        self._db.add(row)
        try:
            self._db.flush()
        except IntegrityError:
            # A concurrent first-read for the same user_id already won —
            # same idempotent-on-conflict shape DeliveryRepository.create()
            # below uses for its own unique constraint.
            self._db.rollback()
            existing = self._db.get(PreferencesORM, preferences.user_id)
            assert existing is not None
            return _preferences_from_orm(existing)
        self._db.refresh(row)
        return _preferences_from_orm(row)

    def save(self, preferences: Preferences) -> None:
        row = self._db.get(PreferencesORM, preferences.user_id)
        if row is None:
            raise LookupError(f"Preferences for user {preferences.user_id} not found")
        row.push_enabled = preferences.push_enabled
        row.sms_enabled = preferences.sms_enabled
        row.whatsapp_enabled = preferences.whatsapp_enabled
        self._db.flush()


def _delivery_from_orm(row: DeliveryORM) -> Delivery:
    return Delivery(
        id=row.id,
        user_id=row.user_id,
        channel=Channel(row.channel),
        template_key=row.template_key,
        event_id=row.event_id,
        status=DeliveryStatus(row.status),
        provider_reference=row.provider_reference,
        created_at=row.created_at,
        delivered_at=row.delivered_at,
        template_version_id=row.template_version_id,
        retry_count=row.retry_count,
    )


class SqlAlchemyDeliveryRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, delivery: Delivery) -> Delivery:
        row = DeliveryORM(
            id=delivery.id,
            user_id=delivery.user_id,
            channel=delivery.channel.value,
            template_key=delivery.template_key,
            event_id=delivery.event_id,
            status=delivery.status.value,
            provider_reference=delivery.provider_reference,
            created_at=delivery.created_at,
            delivered_at=delivery.delivered_at,
            template_version_id=delivery.template_version_id,
        )
        self._db.add(row)
        try:
            self._db.flush()
        except IntegrityError:
            # uq_notification_deliveries_dedup (migration b8e4f27a5c93) —
            # a genuine duplicate (user_id, channel, template_key,
            # event_id) already exists; return it instead of erroring,
            # same shape modules.penalty.repositories.
            # SqlAlchemyPenaltyRepository.create() already established.
            self._db.rollback()
            existing = self._db.execute(
                select(DeliveryORM)
                .where(DeliveryORM.user_id == delivery.user_id)
                .where(DeliveryORM.channel == delivery.channel.value)
                .where(DeliveryORM.template_key == delivery.template_key)
                .where(DeliveryORM.event_id == delivery.event_id)
            ).scalar_one()
            return _delivery_from_orm(existing)
        self._db.refresh(row)
        return _delivery_from_orm(row)

    def save(self, delivery: Delivery) -> None:
        row = self._db.get(DeliveryORM, delivery.id)
        if row is None:
            raise LookupError(f"Delivery {delivery.id} not found")
        row.status = delivery.status.value
        row.provider_reference = delivery.provider_reference
        row.delivered_at = delivery.delivered_at
        row.retry_count = delivery.retry_count
        self._db.flush()

    def get_by_id_for_update(self, delivery_id: uuid.UUID) -> Delivery | None:
        row = (
            self._db.execute(
                select(DeliveryORM)
                .where(DeliveryORM.id == delivery_id)
                .with_for_update()
            )
            .scalars()
            .one_or_none()
        )
        return _delivery_from_orm(row) if row else None

    def list_for_user(
        self, user_id: uuid.UUID, *, offset: int, limit: int
    ) -> tuple[list[Delivery], int]:
        total = self._db.execute(
            select(func.count())
            .select_from(DeliveryORM)
            .where(DeliveryORM.user_id == user_id)
        ).scalar_one()
        rows = (
            self._db.execute(
                select(DeliveryORM)
                .where(DeliveryORM.user_id == user_id)
                .order_by(DeliveryORM.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_delivery_from_orm(row) for row in rows], total

    def search(
        self,
        *,
        user_id: uuid.UUID | None,
        channel: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Delivery], int]:
        filters: list[ColumnElement[bool]] = []
        if user_id is not None:
            filters.append(DeliveryORM.user_id == user_id)
        if channel:
            filters.append(DeliveryORM.channel == channel)
        if status:
            filters.append(DeliveryORM.status == status)

        total = self._db.execute(
            select(func.count()).select_from(DeliveryORM).where(*filters)
        ).scalar_one()
        rows = (
            self._db.execute(
                select(DeliveryORM)
                .where(*filters)
                .order_by(DeliveryORM.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_delivery_from_orm(row) for row in rows], total

    def count_by_channel_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        rows = self._db.execute(
            select(DeliveryORM.channel, func.count())
            .where(DeliveryORM.created_at >= since)
            .where(DeliveryORM.created_at < until)
            .group_by(DeliveryORM.channel)
        ).all()
        return {key: value for key, value in rows}  # noqa: C416

    def count_by_status_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        rows = self._db.execute(
            select(DeliveryORM.status, func.count())
            .where(DeliveryORM.created_at >= since)
            .where(DeliveryORM.created_at < until)
            .group_by(DeliveryORM.status)
        ).all()
        return {key: value for key, value in rows}  # noqa: C416


def _template_from_orm(row: TemplateORM) -> Template:
    return Template(
        id=row.id,
        template_key=row.template_key,
        channel=row.channel,
        event_key=row.event_key,
        title=row.title,
        body=row.body,
        version=row.version,
        status=TemplateStatus(row.status),
        created_by=row.created_by,
        created_at=row.created_at,
    )


class SqlAlchemyTemplateRepository:
    """ADR-0044 — Notification Template Management."""

    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, template: Template) -> Template:
        row = TemplateORM(
            id=template.id,
            template_key=template.template_key,
            channel=template.channel,
            event_key=template.event_key,
            title=template.title,
            body=template.body,
            version=template.version,
            status=template.status.value,
            created_by=template.created_by,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _template_from_orm(row)

    def get_by_id(self, template_id: uuid.UUID) -> Template | None:
        row = self._db.get(TemplateORM, template_id)
        return _template_from_orm(row) if row else None

    def get_by_id_for_update(self, template_id: uuid.UUID) -> Template | None:
        row = (
            self._db.execute(
                select(TemplateORM)
                .where(TemplateORM.id == template_id)
                .with_for_update()
            )
            .scalars()
            .one_or_none()
        )
        return _template_from_orm(row) if row else None

    def _published_query(
        self, *, template_key: str, channel: str
    ) -> Select[tuple[TemplateORM]]:
        return (
            select(TemplateORM)
            .where(TemplateORM.template_key == template_key)
            .where(TemplateORM.channel == channel)
            .where(TemplateORM.status == TemplateStatus.PUBLISHED.value)
        )

    def get_published(self, *, template_key: str, channel: str) -> Template | None:
        row = (
            self._db.execute(
                self._published_query(template_key=template_key, channel=channel)
            )
            .scalars()
            .one_or_none()
        )
        return _template_from_orm(row) if row else None

    def get_published_for_update(
        self, *, template_key: str, channel: str
    ) -> Template | None:
        row = (
            self._db.execute(
                self._published_query(
                    template_key=template_key, channel=channel
                ).with_for_update()
            )
            .scalars()
            .one_or_none()
        )
        return _template_from_orm(row) if row else None

    def get_latest_version(self, *, template_key: str, channel: str) -> int:
        version = self._db.execute(
            select(func.max(TemplateORM.version))
            .where(TemplateORM.template_key == template_key)
            .where(TemplateORM.channel == channel)
        ).scalar_one_or_none()
        return version or 0

    def save(self, template: Template) -> None:
        row = self._db.get(TemplateORM, template.id)
        if row is None:
            raise LookupError(f"Template {template.id} not found")
        row.status = template.status.value
        self._db.flush()

    def list_all(
        self,
        *,
        template_key: str | None,
        channel: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Template], int]:
        filters: list[ColumnElement[bool]] = []
        if template_key:
            filters.append(TemplateORM.template_key == template_key)
        if channel:
            filters.append(TemplateORM.channel == channel)
        if status:
            filters.append(TemplateORM.status == status)

        total = self._db.execute(
            select(func.count()).select_from(TemplateORM).where(*filters)
        ).scalar_one()
        rows = (
            self._db.execute(
                select(TemplateORM)
                .where(*filters)
                .order_by(TemplateORM.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_template_from_orm(row) for row in rows], total


def _device_token_from_orm(row: DeviceTokenORM) -> DeviceToken:
    return DeviceToken(
        id=row.id,
        user_id=row.user_id,
        platform=Platform(row.platform),
        token=row.token,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyDeviceTokenRepository:
    """ADR-0052 — Push Notifications device registration."""

    def __init__(self, db: DbSession) -> None:
        self._db = db

    def upsert(self, device_token: DeviceToken) -> DeviceToken:
        existing = self._db.execute(
            select(DeviceTokenORM).where(DeviceTokenORM.token == device_token.token)
        ).scalar_one_or_none()
        if existing is None:
            row = DeviceTokenORM(
                id=device_token.id,
                user_id=device_token.user_id,
                platform=device_token.platform.value,
                token=device_token.token,
            )
            self._db.add(row)
        else:
            row = existing
            row.user_id = device_token.user_id
            row.platform = device_token.platform.value
        self._db.flush()
        self._db.refresh(row)
        return _device_token_from_orm(row)

    def list_for_user(self, user_id: uuid.UUID) -> list[DeviceToken]:
        rows = (
            self._db.execute(
                select(DeviceTokenORM).where(DeviceTokenORM.user_id == user_id)
            )
            .scalars()
            .all()
        )
        return [_device_token_from_orm(row) for row in rows]

    def delete(self, *, user_id: uuid.UUID, token: str) -> None:
        row = self._db.execute(
            select(DeviceTokenORM).where(
                DeviceTokenORM.user_id == user_id, DeviceTokenORM.token == token
            )
        ).scalar_one_or_none()
        if row is not None:
            self._db.delete(row)
            self._db.flush()


def _broadcast_from_orm(row: BroadcastORM) -> Broadcast:
    return Broadcast(
        id=row.id,
        channel=Channel(row.channel),
        template_key=row.template_key,
        subject=row.subject,
        body=row.body,
        audience_type=AudienceType(row.audience_type),
        audience_user_ids=[uuid.UUID(raw) for raw in row.audience_user_ids]
        if row.audience_user_ids
        else None,
        status=BroadcastStatus(row.status),
        scheduled_at=row.scheduled_at,
        sent_count=row.sent_count,
        failed_count=row.failed_count,
        created_by=row.created_by,
        created_at=row.created_at,
        sent_at=row.sent_at,
    )


class SqlAlchemyBroadcastRepository:
    """ADR-0055 — Compose/Send Broadcast + Audience Selection."""

    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, broadcast: Broadcast) -> Broadcast:
        row = BroadcastORM(
            id=broadcast.id,
            channel=broadcast.channel.value,
            template_key=broadcast.template_key,
            subject=broadcast.subject,
            body=broadcast.body,
            audience_type=broadcast.audience_type.value,
            audience_user_ids=[str(uid) for uid in broadcast.audience_user_ids]
            if broadcast.audience_user_ids
            else None,
            status=broadcast.status.value,
            scheduled_at=broadcast.scheduled_at,
            sent_count=broadcast.sent_count,
            failed_count=broadcast.failed_count,
            created_by=broadcast.created_by,
            created_at=broadcast.created_at,
            sent_at=broadcast.sent_at,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _broadcast_from_orm(row)

    def get_by_id(self, broadcast_id: uuid.UUID) -> Broadcast | None:
        row = self._db.get(BroadcastORM, broadcast_id)
        return _broadcast_from_orm(row) if row else None

    def save(self, broadcast: Broadcast) -> None:
        row = self._db.get(BroadcastORM, broadcast.id)
        if row is None:
            raise LookupError(f"Broadcast {broadcast.id} not found")
        row.status = broadcast.status.value
        row.sent_count = broadcast.sent_count
        row.failed_count = broadcast.failed_count
        row.sent_at = broadcast.sent_at
        self._db.flush()

    def search(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[Broadcast], int]:
        filters: list[ColumnElement[bool]] = []
        if status:
            filters.append(BroadcastORM.status == status)

        total = self._db.execute(
            select(func.count()).select_from(BroadcastORM).where(*filters)
        ).scalar_one()
        rows = (
            self._db.execute(
                select(BroadcastORM)
                .where(*filters)
                .order_by(BroadcastORM.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_broadcast_from_orm(row) for row in rows], total

    def list_due(self, *, now: datetime) -> list[Broadcast]:
        rows = (
            self._db.execute(
                select(BroadcastORM)
                .where(BroadcastORM.status == BroadcastStatus.SCHEDULED.value)
                .where(BroadcastORM.scheduled_at.is_not(None))
                .where(BroadcastORM.scheduled_at <= now)
                .order_by(BroadcastORM.scheduled_at.asc())
            )
            .scalars()
            .all()
        )
        return [_broadcast_from_orm(row) for row in rows]
