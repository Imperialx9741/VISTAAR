"""Application service (use cases) for Safety.

Implements domain-design.md §19.3's four commands. See
modules/safety/__init__.py for the full scope (ADR-0022) — notably,
EscalateSOS never contacts any real emergency service (BR-112's exact
integrations are TBD); it only transitions safety.incidents.status.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from modules.safety.domain.entities import (
    IncidentStatus,
    SafetyEvent,
    SafetyEventType,
    SafetyIncident,
)
from modules.safety.domain.errors import (
    IncidentNotAcknowledgeableError,
    IncidentNotEscalatableError,
    IncidentNotFoundError,
    IncidentNotResolvableError,
)
from modules.safety.ports import SafetyEventRepository, SafetyIncidentRepository


class SafetyService:
    def __init__(
        self, *, incidents: SafetyIncidentRepository, events: SafetyEventRepository
    ) -> None:
        self._incidents = incidents
        self._events = events

    def trigger_sos(
        self,
        *,
        ride_id: uuid.UUID | None,
        reporter_id: uuid.UUID,
        incident_type: str,
        latitude: float,
        longitude: float,
        now: datetime,
    ) -> SafetyIncident:
        """TriggerSOS (domain-design.md §19.3). SOS creation is
        immediate (state-machines.md §45) — no precondition beyond
        input validation."""
        incident = SafetyIncident.new(
            ride_id=ride_id,
            reporter_id=reporter_id,
            incident_type=incident_type,
            latitude=latitude,
            longitude=longitude,
            now=now,
        )
        created = self._incidents.create(incident)
        self._events.create(
            SafetyEvent.new(
                incident_id=created.id,
                event_type=SafetyEventType.SOS_TRIGGERED,
                actor_id=reporter_id,
                now=now,
            )
        )
        return created

    def acknowledge_incident(
        self, *, incident_id: uuid.UUID, actor_id: uuid.UUID | None, now: datetime
    ) -> SafetyIncident:
        """AcknowledgeSOS: OPEN -> ACKNOWLEDGED. Concurrency: row-locked,
        same mechanism as DriverService.go_online()."""
        incident = self._get_for_update(incident_id)
        if incident.status is not IncidentStatus.OPEN:
            raise IncidentNotAcknowledgeableError(
                "This incident is not in an acknowledgeable state."
            )
        incident.status = IncidentStatus.ACKNOWLEDGED
        self._incidents.save(incident)
        self._events.create(
            SafetyEvent.new(
                incident_id=incident.id,
                event_type=SafetyEventType.ACKNOWLEDGED,
                actor_id=actor_id,
                now=now,
            )
        )
        return incident

    def escalate_incident(
        self, *, incident_id: uuid.UUID, actor_id: uuid.UUID | None, now: datetime
    ) -> SafetyIncident:
        """EscalateSOS: ACKNOWLEDGED -> IN_PROGRESS (ADR-0022
        Decision 3). Never contacts a real emergency service — see this
        module's docstring."""
        incident = self._get_for_update(incident_id)
        if incident.status is not IncidentStatus.ACKNOWLEDGED:
            raise IncidentNotEscalatableError(
                "This incident is not in an escalatable state."
            )
        incident.status = IncidentStatus.IN_PROGRESS
        self._incidents.save(incident)
        self._events.create(
            SafetyEvent.new(
                incident_id=incident.id,
                event_type=SafetyEventType.ESCALATED,
                actor_id=actor_id,
                now=now,
            )
        )
        return incident

    def resolve_incident(
        self, *, incident_id: uuid.UUID, actor_id: uuid.UUID | None, now: datetime
    ) -> SafetyIncident:
        """ResolveSafetyIncident: IN_PROGRESS -> RESOLVED."""
        incident = self._get_for_update(incident_id)
        if incident.status is not IncidentStatus.IN_PROGRESS:
            raise IncidentNotResolvableError(
                "This incident is not in a resolvable state."
            )
        incident.status = IncidentStatus.RESOLVED
        incident.resolved_at = now
        self._incidents.save(incident)
        self._events.create(
            SafetyEvent.new(
                incident_id=incident.id,
                event_type=SafetyEventType.RESOLVED,
                actor_id=actor_id,
                now=now,
            )
        )
        return incident

    def get_incident(self, *, incident_id: uuid.UUID) -> SafetyIncident:
        incident = self._incidents.get_by_id(incident_id)
        if incident is None:
            raise IncidentNotFoundError("Incident not found.")
        return incident

    def search_incidents(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[SafetyIncident], int]:
        return self._incidents.search(status=status, offset=offset, limit=limit)

    def count_unresolved_incidents(self) -> int:
        return self._incidents.count_unresolved()

    # --- Reports (Admin Web §4.16, ADR-0047) -------------------------

    def count_incidents_by_status(self) -> dict[str, int]:
        return self._incidents.count_by_status()

    def average_incident_resolution_minutes_in_range(
        self, *, since: datetime, until: datetime
    ) -> Decimal:
        return self._incidents.average_resolution_minutes_in_range(
            since=since, until=until
        )

    def _get_for_update(self, incident_id: uuid.UUID) -> SafetyIncident:
        incident = self._incidents.get_by_id_for_update(incident_id)
        if incident is None:
            raise IncidentNotFoundError("Incident not found.")
        return incident
