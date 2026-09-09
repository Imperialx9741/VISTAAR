"""Safety domain entities and validation.

Field shapes match docs/04-database/database-design.md §28.1
(safety.incidents) and §28.2 (safety.events) exactly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from modules.safety.domain.errors import (
    InvalidCoordinateError,
    InvalidIncidentTypeError,
)

_MAX_INCIDENT_TYPE_LENGTH = 50  # matches database-design.md §28.1's VARCHAR(50)
_MIN_LATITUDE = -90.0
_MAX_LATITUDE = 90.0
_MIN_LONGITUDE = -180.0
_MAX_LONGITUDE = 180.0


class IncidentStatus(StrEnum):
    """Exactly state-machines.md §45's documented 5-state lifecycle.
    CLOSED has no command reaching it anywhere in this codebase — see
    ADR-0022 Decision 3, same "documented state, no command yet"
    treatment already given to driver.drivers.operational_status =
    INELIGIBLE."""

    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class SafetyEventType(StrEnum):
    """safety.events.event_type — the four transitions this module's
    commands actually produce (ADR-0022 Decision 3). No canonical list
    is documented beyond event-contracts.md §21's two payload-specified
    event *names* (safety.sos_triggered, safety.incident_resolved) —
    these four values are an engineering choice for this table's own
    audit-trail granularity, not a business rule."""

    SOS_TRIGGERED = "SOS_TRIGGERED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"


def validate_incident_type(incident_type: str) -> str:
    """No canonical incident_type enum is documented anywhere — see
    ADR-0022. Only shape is validated, normalized to uppercase, same
    treatment modules.vehicle.domain.entities.validate_document_type
    established for the identical "no documented enum" situation."""
    stripped = incident_type.strip().upper()
    if not stripped:
        raise InvalidIncidentTypeError("incident_type cannot be blank.")
    if len(stripped) > _MAX_INCIDENT_TYPE_LENGTH:
        raise InvalidIncidentTypeError(
            f"incident_type cannot exceed {_MAX_INCIDENT_TYPE_LENGTH} characters."
        )
    return stripped


@dataclass(slots=True)
class Coordinates:
    """latitude/longitude only — same shape and range validation as
    modules.ride.domain.entities.Coordinates, duplicated rather than
    imported (this module does not depend on modules.ride; the router
    layer is the only place the two are ever composed)."""

    latitude: float
    longitude: float


def validate_coordinates(latitude: float, longitude: float) -> Coordinates:
    if not (_MIN_LATITUDE <= latitude <= _MAX_LATITUDE):
        raise InvalidCoordinateError(
            f"latitude must be between {_MIN_LATITUDE} and {_MAX_LATITUDE}."
        )
    if not (_MIN_LONGITUDE <= longitude <= _MAX_LONGITUDE):
        raise InvalidCoordinateError(
            f"longitude must be between {_MIN_LONGITUDE} and {_MAX_LONGITUDE}."
        )
    return Coordinates(latitude=latitude, longitude=longitude)


@dataclass(slots=True)
class SafetyIncident:
    id: uuid.UUID
    ride_id: uuid.UUID | None
    reporter_id: uuid.UUID
    incident_type: str
    status: IncidentStatus
    location: Coordinates | None
    created_at: datetime
    resolved_at: datetime | None

    @staticmethod
    def new(
        *,
        ride_id: uuid.UUID | None,
        reporter_id: uuid.UUID,
        incident_type: str,
        latitude: float,
        longitude: float,
        now: datetime,
    ) -> SafetyIncident:
        return SafetyIncident(
            id=uuid.uuid4(),
            ride_id=ride_id,
            reporter_id=reporter_id,
            incident_type=validate_incident_type(incident_type),
            status=IncidentStatus.OPEN,
            location=validate_coordinates(latitude, longitude),
            created_at=now,
            resolved_at=None,
        )


@dataclass(slots=True)
class SafetyEvent:
    id: uuid.UUID
    incident_id: uuid.UUID
    event_type: SafetyEventType
    actor_id: uuid.UUID | None
    metadata: dict[str, object] | None
    created_at: datetime

    @staticmethod
    def new(
        *,
        incident_id: uuid.UUID,
        event_type: SafetyEventType,
        actor_id: uuid.UUID | None,
        metadata: dict[str, object] | None = None,
        now: datetime,
    ) -> SafetyEvent:
        return SafetyEvent(
            id=uuid.uuid4(),
            incident_id=incident_id,
            event_type=event_type,
            actor_id=actor_id,
            metadata=metadata,
            created_at=now,
        )
