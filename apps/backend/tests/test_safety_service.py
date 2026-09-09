"""Unit tests for SafetyService against in-memory fake repositories."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from modules.safety.domain.entities import IncidentStatus, SafetyEvent, SafetyIncident
from modules.safety.domain.errors import (
    IncidentNotAcknowledgeableError,
    IncidentNotEscalatableError,
    IncidentNotFoundError,
    IncidentNotResolvableError,
    InvalidCoordinateError,
    InvalidIncidentTypeError,
)
from modules.safety.service import SafetyService

RIDE_ID = uuid.uuid4()
REPORTER_ID = uuid.uuid4()
NOW = datetime.now(UTC)


class FakeSafetyIncidentRepository:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, SafetyIncident] = {}

    def create(self, incident: SafetyIncident) -> SafetyIncident:
        self.by_id[incident.id] = incident
        return incident

    def get_by_id(self, incident_id: uuid.UUID) -> SafetyIncident | None:
        return self.by_id.get(incident_id)

    def get_by_id_for_update(self, incident_id: uuid.UUID) -> SafetyIncident | None:
        return self.by_id.get(incident_id)

    def save(self, incident: SafetyIncident) -> None:
        self.by_id[incident.id] = incident

    def search(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[SafetyIncident], int]:
        matches = sorted(
            (
                i
                for i in self.by_id.values()
                if status is None or i.status.value == status
            ),
            key=lambda i: i.created_at,
            reverse=True,
        )
        return matches[offset : offset + limit], len(matches)

    def count_unresolved(self) -> int:
        return sum(1 for i in self.by_id.values() if i.status.value != "RESOLVED")

    def count_by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for i in self.by_id.values():
            counts[i.status.value] = counts.get(i.status.value, 0) + 1
        return counts

    def average_resolution_minutes_in_range(
        self, *, since: datetime, until: datetime
    ) -> Decimal:
        durations = [
            (i.resolved_at - i.created_at).total_seconds() / 60
            for i in self.by_id.values()
            if i.resolved_at is not None and since <= i.resolved_at < until
        ]
        if not durations:
            return Decimal("0")
        return Decimal(str(sum(durations) / len(durations)))


class FakeSafetyEventRepository:
    def __init__(self) -> None:
        self.created: list[SafetyEvent] = []

    def create(self, event: SafetyEvent) -> SafetyEvent:
        self.created.append(event)
        return event

    def list_by_incident(self, incident_id: uuid.UUID) -> list[SafetyEvent]:
        return [e for e in self.created if e.incident_id == incident_id]


@pytest.fixture
def incidents() -> FakeSafetyIncidentRepository:
    return FakeSafetyIncidentRepository()


@pytest.fixture
def events() -> FakeSafetyEventRepository:
    return FakeSafetyEventRepository()


@pytest.fixture
def service(
    incidents: FakeSafetyIncidentRepository, events: FakeSafetyEventRepository
) -> SafetyService:
    return SafetyService(incidents=incidents, events=events)


def _trigger(service: SafetyService, **overrides: object) -> SafetyIncident:
    defaults: dict[str, object] = {
        "ride_id": RIDE_ID,
        "reporter_id": REPORTER_ID,
        "incident_type": "EMERGENCY",
        "latitude": 25.5941,
        "longitude": 85.1376,
        "now": NOW,
    }
    defaults.update(overrides)
    return service.trigger_sos(**defaults)  # type: ignore[arg-type]


def test_trigger_sos_creates_an_open_incident(service: SafetyService) -> None:
    incident = _trigger(service)

    assert incident.status is IncidentStatus.OPEN
    assert incident.ride_id == RIDE_ID
    assert incident.reporter_id == REPORTER_ID
    assert incident.incident_type == "EMERGENCY"
    assert incident.location is not None
    assert incident.location.latitude == 25.5941
    assert incident.resolved_at is None


def test_trigger_sos_records_an_sos_triggered_event(
    service: SafetyService, events: FakeSafetyEventRepository
) -> None:
    incident = _trigger(service)

    assert len(events.created) == 1
    assert events.created[0].event_type.value == "SOS_TRIGGERED"
    assert events.created[0].incident_id == incident.id
    assert events.created[0].actor_id == REPORTER_ID


def test_trigger_sos_normalizes_incident_type(service: SafetyService) -> None:
    incident = _trigger(service, incident_type="  emergency  ")
    assert incident.incident_type == "EMERGENCY"


def test_trigger_sos_rejects_blank_incident_type(service: SafetyService) -> None:
    with pytest.raises(InvalidIncidentTypeError):
        _trigger(service, incident_type="   ")


def test_trigger_sos_rejects_invalid_latitude(service: SafetyService) -> None:
    with pytest.raises(InvalidCoordinateError):
        _trigger(service, latitude=999.0)


def test_trigger_sos_works_without_a_ride(service: SafetyService) -> None:
    """safety.incidents.ride_id is nullable — the schema allows an
    incident with no associated ride, even though the one real HTTP
    endpoint (ride-scoped) always supplies one."""
    incident = _trigger(service, ride_id=None)
    assert incident.ride_id is None


# --- acknowledge / escalate / resolve lifecycle -----------------------------


def test_acknowledge_incident_transitions_open_to_acknowledged(
    service: SafetyService, events: FakeSafetyEventRepository
) -> None:
    incident = _trigger(service)

    acknowledged = service.acknowledge_incident(
        incident_id=incident.id, actor_id=uuid.uuid4(), now=NOW
    )

    assert acknowledged.status is IncidentStatus.ACKNOWLEDGED
    assert any(e.event_type.value == "ACKNOWLEDGED" for e in events.created)


def test_acknowledge_incident_rejects_when_not_open(service: SafetyService) -> None:
    incident = _trigger(service)
    service.acknowledge_incident(incident_id=incident.id, actor_id=None, now=NOW)

    with pytest.raises(IncidentNotAcknowledgeableError):
        service.acknowledge_incident(incident_id=incident.id, actor_id=None, now=NOW)


def test_acknowledge_incident_raises_for_unknown_incident(
    service: SafetyService,
) -> None:
    with pytest.raises(IncidentNotFoundError):
        service.acknowledge_incident(incident_id=uuid.uuid4(), actor_id=None, now=NOW)


def test_escalate_incident_transitions_acknowledged_to_in_progress(
    service: SafetyService, events: FakeSafetyEventRepository
) -> None:
    incident = _trigger(service)
    service.acknowledge_incident(incident_id=incident.id, actor_id=None, now=NOW)

    escalated = service.escalate_incident(
        incident_id=incident.id, actor_id=uuid.uuid4(), now=NOW
    )

    assert escalated.status is IncidentStatus.IN_PROGRESS
    assert any(e.event_type.value == "ESCALATED" for e in events.created)


def test_escalate_incident_rejects_when_not_acknowledged(
    service: SafetyService,
) -> None:
    incident = _trigger(service)  # still OPEN

    with pytest.raises(IncidentNotEscalatableError):
        service.escalate_incident(incident_id=incident.id, actor_id=None, now=NOW)


def test_resolve_incident_transitions_in_progress_to_resolved(
    service: SafetyService, events: FakeSafetyEventRepository
) -> None:
    incident = _trigger(service)
    service.acknowledge_incident(incident_id=incident.id, actor_id=None, now=NOW)
    service.escalate_incident(incident_id=incident.id, actor_id=None, now=NOW)

    resolved = service.resolve_incident(
        incident_id=incident.id, actor_id=uuid.uuid4(), now=NOW
    )

    assert resolved.status is IncidentStatus.RESOLVED
    assert resolved.resolved_at == NOW
    assert any(e.event_type.value == "RESOLVED" for e in events.created)


def test_resolve_incident_rejects_when_not_in_progress(service: SafetyService) -> None:
    incident = _trigger(service)  # still OPEN

    with pytest.raises(IncidentNotResolvableError):
        service.resolve_incident(incident_id=incident.id, actor_id=None, now=NOW)


def test_get_incident_returns_a_previously_created_incident(
    service: SafetyService,
) -> None:
    created = _trigger(service)
    fetched = service.get_incident(incident_id=created.id)
    assert fetched == created


def test_get_incident_raises_for_unknown_incident(service: SafetyService) -> None:
    with pytest.raises(IncidentNotFoundError):
        service.get_incident(incident_id=uuid.uuid4())
