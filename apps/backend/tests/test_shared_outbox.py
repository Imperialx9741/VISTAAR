"""Integration tests: real Postgres, exercising shared/outbox.py's
OutboxStore/new_envelope end-to-end against shared.outbox_events.

Deliberately Kafka-free — the whole point of the outbox pattern
(event-contracts.md §2) is that writing the row never depends on Kafka
being reachable; see test_outbox_publisher.py for the Kafka-dependent
publish-side tests.

Skips (not fails) when Postgres is genuinely unreachable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from core.database import SessionLocal
from shared.outbox import OutboxStore, new_envelope


def _infra_available() -> bool:
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except OperationalError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _infra_available(),
    reason="Postgres is offline/unreachable (start docker-compose.dev.yml)",
)


def test_append_persists_an_unpublished_row_with_the_full_envelope() -> None:
    aggregate_id = uuid.uuid4()
    now = datetime.now(UTC)
    envelope = new_envelope(
        event_type="ride.requested",
        producer="ride-service",
        aggregate_type="ride",
        aggregate_id=aggregate_id,
        data={"ride_id": str(aggregate_id), "status": "SEARCHING"},
        now=now,
        correlation_id="req_test123",
    )

    db = SessionLocal()
    try:
        OutboxStore(db).append(envelope)
        db.commit()
    finally:
        db.close()

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT aggregate_type, aggregate_id, event_type, event_version, "
                "payload, published_at, status, attempt_count, last_attempt_at, "
                "first_failure_at, next_attempt_at, last_error, dead_lettered_at "
                "FROM shared.outbox_events WHERE id = :id"
            ),
            {"id": str(envelope.event_id)},
        ).fetchone()
        assert row is not None
        assert row.aggregate_type == "ride"
        assert str(row.aggregate_id) == str(aggregate_id)
        assert row.event_type == "ride.requested"
        assert row.event_version == 1
        assert row.published_at is None  # unpublished until the publisher runs
        assert row.payload["event_type"] == "ride.requested"
        assert row.payload["producer"] == "ride-service"
        assert row.payload["correlation_id"] == "req_test123"
        assert row.payload["causation_id"] is None
        assert row.payload["tenant_id"] == "vistaar"
        assert row.payload["data"] == {
            "ride_id": str(aggregate_id),
            "status": "SEARCHING",
        }
        # ADR-0071 (2026-09-04) retry/backoff/DLQ columns — a fresh row is
        # immediately due for its first publish attempt, with nothing
        # failed yet.
        assert row.status == "PENDING"
        assert row.attempt_count == 0
        assert row.last_attempt_at is None
        assert row.first_failure_at is None
        assert row.next_attempt_at <= datetime.now(UTC)
        assert row.last_error is None
        assert row.dead_lettered_at is None
    finally:
        db.close()


def test_append_is_rolled_back_with_the_rest_of_its_transaction() -> None:
    """The outbox insert is never its own transaction — event-contracts.md
    §2's "domain change + outbox insert succeed together" — proven here
    by rolling back after append() and confirming nothing persisted."""
    aggregate_id = uuid.uuid4()
    envelope = new_envelope(
        event_type="ride.requested",
        producer="ride-service",
        aggregate_type="ride",
        aggregate_id=aggregate_id,
        data={},
        now=datetime.now(UTC),
    )

    db = SessionLocal()
    try:
        OutboxStore(db).append(envelope)
        db.rollback()
    finally:
        db.close()

    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT id FROM shared.outbox_events WHERE id = :id"),
            {"id": str(envelope.event_id)},
        ).fetchone()
        assert row is None
    finally:
        db.close()


def test_new_envelope_generates_a_fresh_unique_event_id() -> None:
    aggregate_id = uuid.uuid4()
    now = datetime.now(UTC)
    first = new_envelope(
        event_type="ride.requested",
        producer="ride-service",
        aggregate_type="ride",
        aggregate_id=aggregate_id,
        data={},
        now=now,
    )
    second = new_envelope(
        event_type="ride.requested",
        producer="ride-service",
        aggregate_type="ride",
        aggregate_id=aggregate_id,
        data={},
        now=now,
    )
    assert first.event_id != second.event_id
