"""FastAPI dependency wiring for Notification."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session as DbSession

from core.database import get_db
from modules.identity.dependencies import get_sms_provider_dependency
from modules.identity.ports import SmsProvider
from modules.notification.push import get_push_provider
from modules.notification.repositories import (
    SqlAlchemyBroadcastRepository,
    SqlAlchemyDeliveryRepository,
    SqlAlchemyDeviceTokenRepository,
    SqlAlchemyPreferencesRepository,
    SqlAlchemyTemplateRepository,
)
from modules.notification.service import NotificationService


def get_notification_service(
    db: Annotated[DbSession, Depends(get_db)],
    sms_provider: Annotated[SmsProvider, Depends(get_sms_provider_dependency)],
) -> NotificationService:
    """Reuses modules.identity's own SMS provider dependency (ADR-0034
    Decision 4) rather than constructing a second one — `SmsProvider`
    (identity's own protocol) now includes send_message() alongside
    send_otp(), so it satisfies modules.notification.ports.
    SmsMessageProvider directly."""
    return NotificationService(
        deliveries=SqlAlchemyDeliveryRepository(db),
        preferences=SqlAlchemyPreferencesRepository(db),
        sms_provider=sms_provider,
        templates=SqlAlchemyTemplateRepository(db),
        device_tokens=SqlAlchemyDeviceTokenRepository(db),
        push_provider=get_push_provider(),
        broadcasts=SqlAlchemyBroadcastRepository(db),
    )
