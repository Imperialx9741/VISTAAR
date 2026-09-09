"""SQLAlchemy-backed implementations of Safety's ports."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from modules.safety.domain.entities import (
    Coordinates,
    IncidentStatus,
    SafetyEvent,
    SafetyEventType,
    SafetyIncident,
)
from modules.safety.models import SafetyEventORM, SafetyIncidentORM

_POINT_WKT_RE = re.compile(r"^POINT\(([-0-9.]+) ([-0-9.]+)\)$")


def _to_wkt(coordinates: Coordinates) -> str:
    # WKT/PostGIS point order is X Y, i.e. longitude then latitude —
    # same convention as modules.ride.repositories.
    return f"POINT({coordinates.longitude} {coordinates.latitude})"


def _from_wkt(wkt: str | None) -> Coordinates | None:
    if wkt is None:
        return None
    match = _POINT_WKT_RE.match(wkt)
    if not match:
        raise ValueError(f"Unexpected geometry WKT value: {wkt!r}")
    longitude, latitude = float(match.group(1)), float(match.group(2))
    return Coordinates(latitude=latitude, longitude=longitude)


def _incident_from_orm(row: SafetyIncidentORM) -> SafetyIncident:
    return SafetyIncident(
        id=row.id,
        ride_id=row.ride_id,
        reporter_id=row.reporter_id,
        incident_type=row.incident_type,
        status=IncidentStatus(row.status),
        location=_from_wkt(row.location),
        created_at=row.created_at,
        resolved_at=row.resolved_at,
    )


def _event_from_orm(row: SafetyEventORM) -> SafetyEvent:
    return SafetyEvent(
        id=row.id,
        incident_id=row.incident_id,
        event_type=SafetyEventType(row.event_type),
        actor_id=row.actor_id,
        metadata=row.event_metadata,
        created_at=row.created_at,
    )


class SqlAlchemySafetyIncidentRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, incident: SafetyIncident) -> SafetyIncident:
        row = SafetyIncidentORM(
            id=incident.id,
            ride_id=incident.ride_id,
            reporter_id=incident.reporter_id,
            incident_type=incident.incident_type,
            status=incident.status.value,
            location=_to_wkt(incident.location) if incident.location else None,
            resolved_at=incident.resolved_at,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _incident_from_orm(row)

    def get_by_id(self, incident_id: uuid.UUID) -> SafetyIncident | None:
        row = self._db.get(SafetyIncidentORM, incident_id)
        return _incident_from_orm(row) if row else None

    def get_by_id_for_update(self, incident_id: uuid.UUID) -> SafetyIncident | None:
        row = self._db.execute(
            select(SafetyIncidentORM)
            .where(SafetyIncidentORM.id == incident_id)
            .with_for_update()
        ).scalar_one_or_none()
        return _incident_from_orm(row) if row else None

    def save(self, incident: SafetyIncident) -> None:
        row = self._db.get(SafetyIncidentORM, incident.id)
        if row is None:
            raise LookupError(f"Safety incident {incident.id} not found")
        row.status = incident.status.value
        row.resolved_at = incident.resolved_at
        self._db.flush()

    def search(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[SafetyIncident], int]:
        filters = []
        if status:
            filters.append(SafetyIncidentORM.status == status)

        total = self._db.execute(
            select(func.count()).select_from(SafetyIncidentORM).where(*filters)
        ).scalar_one()
        rows = (
            self._db.execute(
                select(SafetyIncidentORM)
                .where(*filters)
                .order_by(SafetyIncidentORM.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_incident_from_orm(row) for row in rows], total

    def count_unresolved(self) -> int:
        return self._db.execute(
            select(func.count())
            .select_from(SafetyIncidentORM)
            .where(SafetyIncidentORM.status != "RESOLVED")
        ).scalar_one()

    def count_by_status(self) -> dict[str, int]:
        rows = self._db.execute(
            select(SafetyIncidentORM.status, func.count()).group_by(
                SafetyIncidentORM.status
            )
        ).all()
        return {key: value for key, value in rows}  # noqa: C416

    def average_resolution_minutes_in_range(
        self, *, since: datetime, until: datetime
    ) -> Decimal:
        minutes = (
            func.extract(
                "epoch", SafetyIncidentORM.resolved_at - SafetyIncidentORM.created_at
            )
            / 60
        )
        average = self._db.execute(
            select(func.coalesce(func.avg(minutes), 0))
            .where(SafetyIncidentORM.resolved_at.is_not(None))
            .where(SafetyIncidentORM.resolved_at >= since)
            .where(SafetyIncidentORM.resolved_at < until)
        ).scalar_one()
        return Decimal(average)


class SqlAlchemySafetyEventRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, event: SafetyEvent) -> SafetyEvent:
        row = SafetyEventORM(
            id=event.id,
            incident_id=event.incident_id,
            event_type=event.event_type.value,
            actor_id=event.actor_id,
            event_metadata=event.metadata,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _event_from_orm(row)

    def list_by_incident(self, incident_id: uuid.UUID) -> list[SafetyEvent]:
        rows = (
            self._db.execute(
                select(SafetyEventORM)
                .where(SafetyEventORM.incident_id == incident_id)
                .order_by(SafetyEventORM.created_at)
            )
            .scalars()
            .all()
        )
        return [_event_from_orm(row) for row in rows]
