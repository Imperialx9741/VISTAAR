"""Integration tests: real Postgres + real Kafka, exercising
shared/outbox_publisher.py's OutboxPublisher.publish_pending() end to
end, including the ADR-0071 (2026-09-04) retry/backoff/dead-letter
behavior.

Skips ONLY when Kafka is genuinely unreachable (same exception set and
reasoning as tests/test_kafka.py's test_kafka_broker_connectivity) —
Postgres unreachability skips too, matching every other integration
test file's convention.

This file runs against the same shared dev Postgres database every
other integration test file does, with no per-test truncation — tests
that need to reason about the *set* of pending rows always scope their
assertions to a specific, freshly-seeded event_id's own row rather than
trusting aggregate counts, the same discipline
test_publish_pending_is_a_no_op_when_nothing_is_pending's own comment
already established ("drain whatever is already pending first... from
this or other tests").
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import (
    KafkaConnectionError,
    NoBrokersAvailable,
    NodeNotReadyError,
)
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from core.config import settings
from core.database import SessionLocal
from shared.outbox import OutboxStore, new_envelope
from shared.outbox_publisher import (
    OutboxPublisher,
    dlq_topic_for_event_type,
    next_attempt_delay_seconds,
    topic_for_event_type,
)


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

_KAFKA_UNREACHABLE_ERRORS = (
    NoBrokersAvailable,
    KafkaConnectionError,
    NodeNotReadyError,
    OSError,
    TimeoutError,
)


def test_topic_for_event_type_uses_the_dot_prefix_domain() -> None:
    # event-contracts.md §6's documented topic families.
    assert topic_for_event_type("ride.accepted") == "vistaar.ride"
    assert topic_for_event_type("wallet.debited") == "vistaar.wallet"
    assert topic_for_event_type("penalty.applied") == "vistaar.penalty"


def test_dlq_topic_for_event_type_uses_the_dlq_prefix() -> None:
    # event-contracts.md §31's documented naming: vistaar.dlq.<domain>.
    assert dlq_topic_for_event_type("ride.accepted") == "vistaar.dlq.ride"
    assert dlq_topic_for_event_type("wallet.debited") == "vistaar.dlq.wallet"
    assert dlq_topic_for_event_type("penalty.applied") == "vistaar.dlq.penalty"


def test_next_attempt_delay_seconds_is_exponential_and_capped() -> None:
    base = settings.EVENT_RETRY_BACKOFF_BASE_SECONDS
    multiplier = settings.EVENT_RETRY_BACKOFF_MULTIPLIER
    cap = settings.EVENT_RETRY_BACKOFF_MAX_SECONDS

    assert next_attempt_delay_seconds(1) == base
    assert next_attempt_delay_seconds(2) == base * multiplier
    assert next_attempt_delay_seconds(3) == base * multiplier**2
    # A large attempt count would compute a delay far beyond the
    # configured cap — proves the cap actually binds, not just that the
    # formula grows.
    assert next_attempt_delay_seconds(50) == cap


def _insert_pending_event() -> uuid.UUID:
    aggregate_id = uuid.uuid4()
    envelope = new_envelope(
        event_type="ride.requested",
        producer="ride-service",
        aggregate_type="ride",
        aggregate_id=aggregate_id,
        data={"ride_id": str(aggregate_id)},
        now=datetime.now(UTC),
    )
    db = SessionLocal()
    try:
        OutboxStore(db).append(envelope)
        db.commit()
    finally:
        db.close()
    return envelope.event_id


@pytest.mark.anyio
async def test_publish_pending_marks_the_event_published() -> None:
    event_id = _insert_pending_event()
    publisher = OutboxPublisher()
    try:
        await publisher.start()
    except _KAFKA_UNREACHABLE_ERRORS as exc:
        pytest.skip(
            f"Kafka broker at {settings.KAFKA_BOOTSTRAP_SERVERS} unreachable: {exc}"
        )

    try:
        result = await publisher.publish_pending()
    finally:
        await publisher.stop()

    assert result.published >= 1
    assert result.dead_lettered == 0

    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT published_at FROM shared.outbox_events WHERE id = :id"),
            {"id": str(event_id)},
        ).fetchone()
        assert row is not None
        assert row.published_at is not None
    finally:
        db.close()


@pytest.mark.anyio
async def test_publish_pending_is_a_no_op_when_nothing_is_pending() -> None:
    publisher = OutboxPublisher()
    try:
        await publisher.start()
    except _KAFKA_UNREACHABLE_ERRORS as exc:
        pytest.skip(
            f"Kafka broker at {settings.KAFKA_BOOTSTRAP_SERVERS} unreachable: {exc}"
        )

    try:
        # Drain whatever is already pending first (from this or other
        # tests), then confirm a second call publishes nothing new.
        await publisher.publish_pending()
        second_result = await publisher.publish_pending()
    finally:
        await publisher.stop()

    assert second_result.published == 0
    assert second_result.dead_lettered == 0


@pytest.mark.anyio
async def test_publish_pending_raises_if_start_was_never_called() -> None:
    publisher = OutboxPublisher()
    with pytest.raises(RuntimeError):
        await publisher.publish_pending()


# --- Retry / backoff / dead-letter (ADR-0071, 2026-09-04) ---------------


def _seed_event(
    *,
    event_type: str = "ride.requested",
    data: dict[str, Any] | None = None,
    attempt_count: int = 0,
    next_attempt_at: datetime | None = None,
    first_failure_at: datetime | None = None,
    last_error: str | None = None,
) -> uuid.UUID:
    """Raw-SQL seed, bypassing OutboxStore.append()'s all-defaults
    insert — the retry/backoff/DLQ tests below need precise control
    over attempt_count/next_attempt_at/first_failure_at that append()
    deliberately never exposes (a real producer never sets these; only
    publish_pending()'s own failure path does)."""
    aggregate_id = uuid.uuid4()
    event_id = uuid.uuid4()
    payload = {
        "event_id": str(event_id),
        "event_type": event_type,
        "event_version": 1,
        "occurred_at": datetime.now(UTC).isoformat(),
        "producer": "test-producer",
        "aggregate_type": "ride",
        "aggregate_id": str(aggregate_id),
        "correlation_id": None,
        "causation_id": None,
        "tenant_id": "vistaar",
        "data": data if data is not None else {"ride_id": str(aggregate_id)},
    }
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO shared.outbox_events "
                "(id, aggregate_type, aggregate_id, event_type, payload, "
                " attempt_count, next_attempt_at, first_failure_at, last_error) "
                "VALUES (:id, 'ride', :aggregate_id, :event_type, "
                " CAST(:payload AS jsonb), :attempt_count, :next_attempt_at, "
                " :first_failure_at, :last_error)"
            ),
            {
                "id": str(event_id),
                "aggregate_id": str(aggregate_id),
                "event_type": event_type,
                "payload": json.dumps(payload, default=str),
                "attempt_count": attempt_count,
                "next_attempt_at": next_attempt_at or datetime.now(UTC),
                "first_failure_at": first_failure_at,
                "last_error": last_error,
            },
        )
        db.commit()
    finally:
        db.close()
    return event_id


def _row(event_id: uuid.UUID) -> Any:
    db = SessionLocal()
    try:
        return db.execute(
            text(
                "SELECT status, attempt_count, last_attempt_at, next_attempt_at, "
                "first_failure_at, last_error, published_at, dead_lettered_at "
                "FROM shared.outbox_events WHERE id = :id"
            ),
            {"id": str(event_id)},
        ).fetchone()
    finally:
        db.close()


def _force_due_now(event_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE shared.outbox_events SET next_attempt_at = :now "
                "WHERE id = :id"
            ),
            {"now": datetime.now(UTC), "id": str(event_id)},
        )
        db.commit()
    finally:
        db.close()


async def _consume_until(
    topic: str, *, event_id: uuid.UUID, timeout: float = 20.0
) -> dict[str, Any]:
    """This suite has no per-test topic isolation — other tests publish
    real messages to the same shared topics concurrently/beforehand — so
    a fresh `auto_offset_reset="earliest"` consumer must scan forward
    until it finds *this* test's own event_id, not just take whatever
    message happens to be read first."""
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=f"test-consumer-{uuid.uuid4()}",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    try:
        try:
            async with asyncio.timeout(timeout):
                async for message in consumer:
                    decoded: dict[str, Any] = json.loads(
                        message.value.decode("utf-8")
                    )
                    if decoded.get("event_id") == str(event_id):
                        return decoded
        except TimeoutError:
            raise AssertionError(
                f"event_id={event_id} was never seen on topic {topic!r} "
                f"within {timeout}s"
            ) from None
        raise AssertionError(f"consumer for topic {topic!r} ended unexpectedly")
    finally:
        await consumer.stop()


@pytest.mark.anyio
async def test_publish_pending_ignores_a_row_not_yet_due() -> None:
    """next_attempt_at behavior: a row scheduled in the future must not
    be selected, regardless of how many other rows are due."""
    event_id = _seed_event(
        attempt_count=1, next_attempt_at=datetime.now(UTC) + timedelta(hours=1)
    )
    publisher = OutboxPublisher()
    try:
        await publisher.start()
    except _KAFKA_UNREACHABLE_ERRORS as exc:
        pytest.skip(
            f"Kafka broker at {settings.KAFKA_BOOTSTRAP_SERVERS} unreachable: {exc}"
        )

    try:
        await publisher.publish_pending()
    finally:
        await publisher.stop()

    row = _row(event_id)
    assert row.status == "PENDING"
    assert row.published_at is None


@pytest.mark.anyio
async def test_transient_failure_is_retried_then_succeeds() -> None:
    """Transient failure -> retry -> success, retry count increment,
    backoff scheduling, and error/first-failure capture, all in one
    real lifecycle: the first publish_pending() call fails (attempt_count
    -> 1, next_attempt_at pushed into the future, last_error/
    first_failure_at recorded); forcing the row due and calling again
    succeeds, republishing the *same* event_id (idempotent retry — no
    new event_id is ever minted for a retried row)."""
    event_id = _seed_event(event_type="ride.requested")
    publisher = OutboxPublisher()
    try:
        await publisher.start()
    except _KAFKA_UNREACHABLE_ERRORS as exc:
        pytest.skip(
            f"Kafka broker at {settings.KAFKA_BOOTSTRAP_SERVERS} unreachable: {exc}"
        )

    real_send = publisher._producer.send_and_wait
    attempts = 0

    async def _fail_once_then_send(topic: str, key: bytes, value: bytes) -> Any:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("simulated transient Kafka failure")
        return await real_send(topic, key=key, value=value)

    publisher._producer.send_and_wait = _fail_once_then_send

    before_first_attempt = datetime.now(UTC)
    await publisher.publish_pending()

    row_after_failure = _row(event_id)
    assert row_after_failure.status == "PENDING"
    assert row_after_failure.attempt_count == 1
    assert row_after_failure.last_error is not None
    assert "simulated transient Kafka failure" in row_after_failure.last_error
    assert row_after_failure.first_failure_at is not None
    assert row_after_failure.first_failure_at >= before_first_attempt
    # Backoff actually scheduled the retry into the future, not "now".
    assert row_after_failure.next_attempt_at > before_first_attempt + timedelta(
        seconds=settings.EVENT_RETRY_BACKOFF_BASE_SECONDS - 1
    )

    _force_due_now(event_id)
    try:
        await publisher.publish_pending()
    finally:
        await publisher.stop()

    row_after_success = _row(event_id)
    assert row_after_success.status == "PUBLISHED"
    assert row_after_success.published_at is not None
    assert row_after_success.attempt_count == 1  # unchanged by the successful attempt

    message = await _consume_until(
        topic_for_event_type("ride.requested"), event_id=event_id
    )
    assert message["event_id"] == str(event_id)  # same id both attempts used


@pytest.mark.anyio
async def test_failed_event_is_not_retried_before_its_next_attempt_at() -> None:
    """Failed events must not enter a tight retry loop: a second
    publish_pending() call made immediately after a failure (well before
    the computed backoff delay has elapsed) must not attempt this row
    again."""
    event_id = _seed_event()
    publisher = OutboxPublisher()
    try:
        await publisher.start()
    except _KAFKA_UNREACHABLE_ERRORS as exc:
        pytest.skip(
            f"Kafka broker at {settings.KAFKA_BOOTSTRAP_SERVERS} unreachable: {exc}"
        )

    async def _always_fail(topic: str, key: bytes, value: bytes) -> Any:
        raise RuntimeError("simulated failure")

    publisher._producer.send_and_wait = _always_fail

    try:
        await publisher.publish_pending()
        attempt_count_after_first = _row(event_id).attempt_count
        # Immediately again — next_attempt_at is safely in the future
        # (>= EVENT_RETRY_BACKOFF_BASE_SECONDS away), so this must be a
        # no-op for this row.
        await publisher.publish_pending()
    finally:
        await publisher.stop()

    assert _row(event_id).attempt_count == attempt_count_after_first


@pytest.mark.anyio
async def test_event_is_dead_lettered_after_max_attempts_and_preserves_metadata() -> (
    None
):
    """Maximum retry limit -> transition to dead-letter, published to
    the Kafka DLQ topic via the existing producer, preserving the
    original event payload plus retry-count/timestamp/error metadata."""
    original_data = {"ride_id": str(uuid.uuid4()), "note": "preserve-me"}
    first_failure_at = datetime.now(UTC) - timedelta(minutes=42)
    event_id = _seed_event(
        event_type="ride.requested",
        data=original_data,
        attempt_count=settings.EVENT_RETRY_MAX_ATTEMPTS,
        first_failure_at=first_failure_at,
        last_error="previous simulated failure",
    )
    publisher = OutboxPublisher()
    try:
        await publisher.start()
    except _KAFKA_UNREACHABLE_ERRORS as exc:
        pytest.skip(
            f"Kafka broker at {settings.KAFKA_BOOTSTRAP_SERVERS} unreachable: {exc}"
        )

    try:
        result = await publisher.publish_pending()
    finally:
        pass  # producer stays open to consume the DLQ message below

    row = _row(event_id)
    assert row.status == "DEAD_LETTERED"
    assert row.dead_lettered_at is not None
    assert row.published_at is None  # never published to its original topic
    assert result.dead_lettered >= 1

    dlq_message = await _consume_until(
        dlq_topic_for_event_type("ride.requested"), event_id=event_id
    )
    await publisher.stop()

    # Original event preserved verbatim.
    assert dlq_message["event_id"] == str(event_id)
    assert dlq_message["event_type"] == "ride.requested"
    assert dlq_message["aggregate_type"] == "ride"
    assert dlq_message["data"] == original_data
    # event-contracts.md §31: attempt count, first/last failure, error.
    meta = dlq_message["dlq_metadata"]
    assert meta["attempt_count"] == settings.EVENT_RETRY_MAX_ATTEMPTS
    assert meta["original_topic"] == "vistaar.ride"
    assert meta["first_failure_at"] is not None
    assert meta["last_failure_at"] is not None


@pytest.mark.anyio
async def test_dlq_publish_failure_leaves_the_row_pending_not_discarded() -> None:
    """Even a DLQ-bound row is never silently dropped: if the DLQ
    publish itself fails, the row stays PENDING (retryable), never
    DEAD_LETTERED, never deleted."""
    event_id = _seed_event(attempt_count=settings.EVENT_RETRY_MAX_ATTEMPTS)
    publisher = OutboxPublisher()
    try:
        await publisher.start()
    except _KAFKA_UNREACHABLE_ERRORS as exc:
        pytest.skip(
            f"Kafka broker at {settings.KAFKA_BOOTSTRAP_SERVERS} unreachable: {exc}"
        )

    async def _always_fail(topic: str, key: bytes, value: bytes) -> Any:
        raise RuntimeError("simulated DLQ publish failure")

    publisher._producer.send_and_wait = _always_fail

    before = datetime.now(UTC)
    try:
        result = await publisher.publish_pending()
    finally:
        await publisher.stop()

    row = _row(event_id)
    assert row.status == "PENDING"
    assert row.dead_lettered_at is None
    assert result.dead_lettered == 0
    assert row.next_attempt_at > before  # rescheduled, not immediate
