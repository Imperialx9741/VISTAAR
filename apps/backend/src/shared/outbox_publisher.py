"""Outbox Publisher — event-contracts.md §28, plus §30/§31's retry
policy and Dead Letter Topics (ADR-0071, 2026-09-04).

Reads shared.outbox_events rows due for a publish attempt and ships them
to Kafka, one topic per event-type domain (event-contracts.md §6:
"vistaar.<domain>"), partitioned by aggregate_id (§7 — preserves
ordering for events belonging to the same aggregate, e.g. every event
for one ride lands in the same partition).

ADR-0017 Decision 1 (unchanged): runs as an in-process asyncio loop (see
run_outbox_publisher_loop(), started from main.py's lifespan), not a
separate Celery/background-worker process.

ADR-0071 replaces ADR-0017 Decision 2's "leave the row unpublished,
re-poll on the next cycle forever, no backoff, no DLQ" with real,
persistent per-row retry control:

- A failed publish increments `attempt_count`, records `last_attempt_at`/
  `first_failure_at`/`last_error`, and schedules `next_attempt_at` via
  exponential backoff (settings.EVENT_RETRY_BACKOFF_*) — the row stays
  `status='PENDING'` and is simply not selected again until that time
  arrives (`publish_pending()`'s own WHERE clause), so a failing row
  never enters a tight retry loop.
- Once `attempt_count` reaches `settings.EVENT_RETRY_MAX_ATTEMPTS`, the
  row is no longer retried against its original topic — the next due
  attempt instead publishes it to `vistaar.dlq.<domain>` (event-
  contracts.md §31), carrying the original envelope untouched plus a
  `dlq_metadata` block (attempt count, first/last failure, last error).
  On success the row is marked `status='DEAD_LETTERED'`. If even the DLQ
  publish fails, the row is left `PENDING` and retried at the capped
  backoff interval forever — a failed event is never silently dropped.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from aiokafka import AIOKafkaProducer
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from core.config import settings
from core.database import SessionLocal

logger = logging.getLogger(__name__)

_TOPIC_PREFIX = "vistaar"
_DLQ_PREFIX = "vistaar.dlq"
_DEFAULT_BATCH_SIZE = 100


def topic_for_event_type(event_type: str) -> str:
    """event-contracts.md §6: "vistaar.<domain>" — <domain> is the
    event type's own dot-prefix (e.g. "ride.accepted" -> "vistaar.ride",
    matching §6's own listed topic families exactly)."""
    domain = event_type.split(".", 1)[0]
    return f"{_TOPIC_PREFIX}.{domain}"


def dlq_topic_for_event_type(event_type: str) -> str:
    """event-contracts.md §31: "vistaar.dlq.<domain>" — same domain
    extraction as topic_for_event_type(), just under the dlq prefix
    (matching §31's own listed examples, e.g. "vistaar.dlq.payment")."""
    domain = event_type.split(".", 1)[0]
    return f"{_DLQ_PREFIX}.{domain}"


def next_attempt_delay_seconds(attempt_count: int) -> float:
    """Exponential backoff: base * multiplier^(attempt_count - 1),
    capped at max. `attempt_count` is 1-indexed (the count *after* the
    failure that just occurred) — the first failure (attempt_count=1)
    waits `base` seconds, matching event-contracts.md §30's "1st failure
    -> 5 seconds" starting point. Public (not a leading-underscore
    helper) so tests can assert on the formula directly."""
    delay = settings.EVENT_RETRY_BACKOFF_BASE_SECONDS * (
        settings.EVENT_RETRY_BACKOFF_MULTIPLIER ** (attempt_count - 1)
    )
    return min(delay, settings.EVENT_RETRY_BACKOFF_MAX_SECONDS)


@dataclass(slots=True)
class PublishResult:
    """Return shape for publish_pending() — kept as two explicit counts
    rather than one combined "processed" number so a caller (or a test)
    never has to guess which outcome a given number represents."""

    published: int
    dead_lettered: int


class OutboxPublisher:
    """Wraps one AIOKafkaProducer instance, started/stopped once for the
    life of the publisher loop — not per publish call, matching
    aiokafka's own recommended usage (a producer holds its own
    connection pool/batching internally). The same producer instance is
    reused for DLQ publishes — a DLQ topic is an ordinary Kafka topic on
    the same broker, not a different piece of infrastructure."""

    def __init__(self) -> None:
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS
        )
        await self._producer.start()

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def publish_pending(
        self, *, batch_size: int = _DEFAULT_BATCH_SIZE
    ) -> PublishResult:
        """Each row is committed (published, dead-lettered, or
        rescheduled) immediately after its own outcome is known — not
        batched into one transaction — so a mid-batch Kafka failure
        never rolls back the rows that already succeeded."""
        if self._producer is None:
            raise RuntimeError("OutboxPublisher.start() must be called first.")

        db = SessionLocal()
        try:
            now = datetime.now(UTC)
            rows = db.execute(
                text(
                    "SELECT id, aggregate_id, event_type, payload, attempt_count, "
                    "first_failure_at "
                    "FROM shared.outbox_events "
                    "WHERE status = 'PENDING' AND next_attempt_at <= :now "
                    "ORDER BY created_at "
                    "LIMIT :limit"
                ),
                {"now": now, "limit": batch_size},
            ).fetchall()

            published = 0
            dead_lettered = 0
            for row in rows:
                # psycopg2 normally hands back an already-decoded JSONB
                # value as a dict even through a raw text() query, but
                # this is defensive against a driver/config combination
                # that doesn't.
                payload = row.payload
                if isinstance(payload, str):
                    payload = json.loads(payload)

                is_dlq_attempt = row.attempt_count >= settings.EVENT_RETRY_MAX_ATTEMPTS
                original_topic = topic_for_event_type(row.event_type)

                if is_dlq_attempt:
                    topic = dlq_topic_for_event_type(row.event_type)
                    send_payload = {
                        **payload,
                        "dlq_metadata": {
                            "original_topic": original_topic,
                            "attempt_count": row.attempt_count,
                            "first_failure_at": (
                                row.first_failure_at.isoformat()
                                if row.first_failure_at
                                else None
                            ),
                            "last_failure_at": now.isoformat(),
                            "failed_by": "outbox-publisher",
                        },
                    }
                else:
                    topic = original_topic
                    send_payload = payload

                try:
                    await self._producer.send_and_wait(
                        topic,
                        key=str(row.aggregate_id).encode("utf-8"),
                        value=json.dumps(send_payload, default=str).encode("utf-8"),
                    )
                except Exception as exc:
                    _record_publish_failure(
                        db,
                        row_id=row.id,
                        attempt_count=row.attempt_count,
                        is_dlq_attempt=is_dlq_attempt,
                        error=exc,
                        now=now,
                    )
                    logger.exception(
                        "Failed to publish outbox event %s (type=%s) to "
                        "topic %s (attempt %s%s).",
                        row.id,
                        row.event_type,
                        topic,
                        row.attempt_count + (0 if is_dlq_attempt else 1),
                        ", DLQ" if is_dlq_attempt else "",
                    )
                    continue

                if is_dlq_attempt:
                    db.execute(
                        text(
                            "UPDATE shared.outbox_events SET "
                            "status = 'DEAD_LETTERED', dead_lettered_at = :now "
                            "WHERE id = :id"
                        ),
                        {"now": now, "id": row.id},
                    )
                    dead_lettered += 1
                else:
                    db.execute(
                        text(
                            "UPDATE shared.outbox_events SET "
                            "status = 'PUBLISHED', published_at = :now "
                            "WHERE id = :id"
                        ),
                        {"now": now, "id": row.id},
                    )
                    published += 1
                db.commit()

            return PublishResult(published=published, dead_lettered=dead_lettered)
        finally:
            db.close()


def _record_publish_failure(
    db: DbSession,
    *,
    row_id: object,
    attempt_count: int,
    is_dlq_attempt: bool,
    error: Exception,
    now: datetime,
) -> None:
    """A row stays `status='PENDING'` on any failure — only a
    *successful* publish (to the original topic or, once exhausted, to
    the DLQ topic) ever moves it out of PENDING. This is what guarantees
    a failed event is never silently discarded: it either keeps
    retrying its original topic (while attempt_count < max) or keeps
    retrying the DLQ topic (once exhausted) — there is no third
    outcome."""
    last_error = str(error)[:4000]
    if is_dlq_attempt:
        # attempt_count is already at/above the max — do not grow it
        # further; a DLQ-publish failure just retries at the capped
        # backoff interval until Kafka accepts it.
        next_attempt_at = now + timedelta(
            seconds=settings.EVENT_RETRY_BACKOFF_MAX_SECONDS
        )
        db.execute(
            text(
                "UPDATE shared.outbox_events SET "
                "last_attempt_at = :now, last_error = :error, "
                "next_attempt_at = :next_attempt_at "
                "WHERE id = :id"
            ),
            {
                "now": now,
                "error": last_error,
                "next_attempt_at": next_attempt_at,
                "id": row_id,
            },
        )
    else:
        new_attempt_count = attempt_count + 1
        next_attempt_at = now + timedelta(
            seconds=next_attempt_delay_seconds(new_attempt_count)
        )
        db.execute(
            text(
                "UPDATE shared.outbox_events SET "
                "attempt_count = :attempt_count, last_attempt_at = :now, "
                "last_error = :error, next_attempt_at = :next_attempt_at, "
                "first_failure_at = COALESCE(first_failure_at, :now) "
                "WHERE id = :id"
            ),
            {
                "attempt_count": new_attempt_count,
                "now": now,
                "error": last_error,
                "next_attempt_at": next_attempt_at,
                "id": row_id,
            },
        )
    db.commit()


async def run_outbox_publisher_loop(
    publisher: OutboxPublisher, *, interval_seconds: float
) -> None:
    """Runs publish_pending() forever on a fixed interval. Intended to
    be wrapped in asyncio.create_task() from main.py's lifespan and
    cancelled on shutdown — asyncio.CancelledError propagates out of
    the sleep() below cleanly (not swallowed by the broad except)."""
    while True:
        try:
            await publisher.publish_pending()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Outbox publisher loop iteration failed.")
        await asyncio.sleep(interval_seconds)
