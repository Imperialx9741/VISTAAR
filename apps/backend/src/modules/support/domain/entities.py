"""Support domain entities and validation.

Field shapes match docs/04-database/database-design.md §30.1
(support.cases, plus the additive ride_id column — ADR-0022 Decision 1)
and §30.2 (support.messages) exactly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from modules.support.domain.errors import InvalidCategoryError, InvalidMessageError

_MAX_CATEGORY_LENGTH = 50  # matches database-design.md §30.1's VARCHAR(50)
_MAX_MESSAGE_LENGTH = 4000  # defensive application-level bound only —
# support.messages.message is TEXT, no documented limit.

_DEFAULT_PRIORITY = "NORMAL"  # database-design.md §30.1's documented default


class CaseStatus(StrEnum):
    """Exactly state-machines.md §46's documented 6-state lifecycle.
    IN_PROGRESS/WAITING_FOR_USER/CLOSED have no command reaching them
    anywhere in this codebase — see ADR-0022 Decision 2, same
    "documented state, no command yet" treatment already given to
    modules.safety.domain.entities.IncidentStatus.CLOSED."""

    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class SenderType(StrEnum):
    """support.messages.sender_type. AI is included for schema
    completeness (event-contracts.md/domain-design.md both name an AI
    actor) even though nothing in this codebase ever creates a message
    with it — AskSupportAI is BLOCKED (ADR-0022 Decision 4)."""

    CUSTOMER = "CUSTOMER"
    DRIVER = "DRIVER"
    ADMIN = "ADMIN"
    AI = "AI"


def validate_category(category: str | None) -> str | None:
    """No canonical category enum is documented anywhere — see
    ADR-0022. Only shape is validated, normalized to uppercase, same
    treatment modules.vehicle.domain.entities.validate_document_type
    established for the identical "no documented enum" situation."""
    if category is None:
        return None
    stripped = category.strip().upper()
    if not stripped:
        return None
    if len(stripped) > _MAX_CATEGORY_LENGTH:
        raise InvalidCategoryError(
            f"category cannot exceed {_MAX_CATEGORY_LENGTH} characters."
        )
    return stripped


def validate_message(message: str) -> str:
    stripped = message.strip()
    if not stripped:
        raise InvalidMessageError("message cannot be blank.")
    if len(stripped) > _MAX_MESSAGE_LENGTH:
        raise InvalidMessageError(
            f"message cannot exceed {_MAX_MESSAGE_LENGTH} characters."
        )
    return stripped


@dataclass(slots=True)
class SupportCase:
    id: uuid.UUID
    user_id: uuid.UUID
    ride_id: uuid.UUID | None
    category: str | None
    priority: str
    status: CaseStatus
    assigned_admin_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def new(
        *,
        user_id: uuid.UUID,
        ride_id: uuid.UUID | None,
        category: str | None,
        now: datetime,
    ) -> SupportCase:
        return SupportCase(
            id=uuid.uuid4(),
            user_id=user_id,
            ride_id=ride_id,
            category=validate_category(category),
            priority=_DEFAULT_PRIORITY,
            status=CaseStatus.OPEN,
            assigned_admin_id=None,
            created_at=now,
            updated_at=now,
        )


@dataclass(slots=True)
class SupportMessage:
    id: uuid.UUID
    case_id: uuid.UUID
    sender_type: SenderType
    sender_id: uuid.UUID | None
    message: str
    created_at: datetime

    @staticmethod
    def new(
        *,
        case_id: uuid.UUID,
        sender_type: SenderType,
        sender_id: uuid.UUID | None,
        message: str,
        now: datetime,
    ) -> SupportMessage:
        return SupportMessage(
            id=uuid.uuid4(),
            case_id=case_id,
            sender_type=sender_type,
            sender_id=sender_id,
            message=validate_message(message),
            created_at=now,
        )
