"""Transactional Outbox — shared.outbox_events.

Minimal Event & Outbox Foundation (ADR-0017), backed by
shared.outbox_events (database-design.md §34). Implements
event-contracts.md §3's documented envelope shape generically — lives
in shared/ rather than inside any one module because every module that
needs to publish a domain event needs the exact same envelope/insert
mechanism (implementation-readiness.md §22's "shared infrastructure
must not contain domain-specific business rules" — this file knows
nothing about what a ride or a wallet is, only the generic envelope/
outbox-row shape event-contracts.md documents for all of them).

This file is deliberately Kafka-free — see shared/outbox_publisher.py
for the piece that actually ships rows to Kafka. Keeping the insert-side
(this file, called synchronously inside every domain transaction) and
the publish-side (a separate, async, Kafka-aware component) apart means
a module publishing an event never needs to know or care whether Kafka
is reachable right now — event-contracts.md §2's whole point.

Usage (inside an existing db transaction, alongside the domain change
it accompanies — never called on its own):

    envelope = new_envelope(
        event_type="ride.accepted", producer="ride-service",
        aggregate_type="ride", aggregate_id=ride.id,
        data={"ride_id": str(ride.id), "driver_id": str(ride.driver_id)},
        now=now,
    )
    OutboxStore(db).append(envelope)
    # ... the caller's own db.commit() persists both the domain change
    # and this outbox row together, or rolls both back together.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

# event-contracts.md §3's example envelope hard-codes "tenant_id":
# "vistaar" — this codebase has no real multi-tenancy concept, so the
# field is included verbatim (matching the documented envelope shape
# exactly) rather than omitted or invented as something more dynamic.
_TENANT_ID = "vistaar"


@dataclass(slots=True)
class EventEnvelope:
    """event-contracts.md §3's documented envelope — every required
    field listed there, plus the optional causation_id."""

    event_id: uuid.UUID
    event_type: str
    event_version: int
    occurred_at: datetime
    producer: str
    aggregate_type: str
    aggregate_id: uuid.UUID
    correlation_id: str | None
    causation_id: str | None
    data: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "event_version": self.event_version,
            "occurred_at": self.occurred_at.isoformat(),
            "producer": self.producer,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": str(self.aggregate_id),
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "tenant_id": _TENANT_ID,
            "data": self.data,
        }


def new_envelope(
    *,
    event_type: str,
    producer: str,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    data: dict[str, Any],
    now: datetime,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    event_version: int = 1,
) -> EventEnvelope:
    """event_id is generated fresh here (event-contracts.md §4: must be
    globally unique) — a plain uuid4 rather than the recommended UUIDv7;
    no UUIDv7 generator is already a dependency of this codebase, and
    uuid4 satisfies the actual requirement (global uniqueness) event-
    contracts.md states — time-sortability is a "recommended", not
    required, property, and shared.outbox_events.created_at already
    gives the publisher a sortable read order without it."""
    return EventEnvelope(
        event_id=uuid.uuid4(),
        event_type=event_type,
        event_version=event_version,
        occurred_at=now,
        producer=producer,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
        data=data,
    )


class OutboxStore:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def append(self, envelope: EventEnvelope) -> None:
        """Inserts one shared.outbox_events row in the CALLER's existing
        transaction — never commits itself, matching
        shared/idempotency.py's IdempotencyStore and every repository in
        this codebase. This is what makes "domain change + outbox
        insert succeed together" (event-contracts.md §2/§27) true: the
        caller's own commit (already happening for the domain change
        itself) persists both, or a caller-side rollback undoes both."""
        self._db.execute(
            text(
                "INSERT INTO shared.outbox_events "
                "(id, aggregate_type, aggregate_id, event_type, "
                "event_version, payload) "
                "VALUES (:id, :aggregate_type, :aggregate_id, :event_type, "
                ":event_version, CAST(:payload AS jsonb))"
            ),
            {
                "id": str(envelope.event_id),
                "aggregate_type": envelope.aggregate_type,
                "aggregate_id": str(envelope.aggregate_id),
                "event_type": envelope.event_type,
                "event_version": envelope.event_version,
                "payload": json.dumps(envelope.as_dict(), default=str),
            },
        )
