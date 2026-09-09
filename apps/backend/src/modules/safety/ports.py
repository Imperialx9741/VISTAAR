"""Abstract interfaces (ports) the application layer depends on."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from modules.safety.domain.entities import SafetyEvent, SafetyIncident


class SafetyIncidentRepository(Protocol):
    def create(self, incident: SafetyIncident) -> SafetyIncident: ...

    def get_by_id(self, incident_id: uuid.UUID) -> SafetyIncident | None: ...

    def get_by_id_for_update(self, incident_id: uuid.UUID) -> SafetyIncident | None:
        """Locks the row (SELECT ... FOR UPDATE) for the remainder of
        the current transaction — used by acknowledge/escalate/resolve
        to serialize concurrent transitions on the same incident, same
        mechanism as modules.driver.service.DriverService.go_online()."""
        ...

    def save(self, incident: SafetyIncident) -> None: ...

    def search(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[SafetyIncident], int]:
        """Admin Web §4.13's Incident Queue. Newest first."""
        ...

    def count_unresolved(self) -> int:
        """Admin Web §3's Dashboard "Open SOS incidents" widget — every
        status except RESOLVED (CLOSED is a documented-but-unreachable
        state, IncidentStatus's own docstring)."""
        ...

    def count_by_status(self) -> dict[str, int]:
        """Admin Web §4.16 Safety/Support report (ADR-0047)."""
        ...

    def average_resolution_minutes_in_range(
        self, *, since: datetime, until: datetime
    ) -> Decimal:
        """AVG(resolved_at - created_at) in minutes, for incidents with
        `resolved_at` in [since, until). 0 if none resolved in range."""
        ...


class SafetyEventRepository(Protocol):
    def create(self, event: SafetyEvent) -> SafetyEvent: ...

    def list_by_incident(self, incident_id: uuid.UUID) -> list[SafetyEvent]: ...
