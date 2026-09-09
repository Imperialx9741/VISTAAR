"""Idempotency-Key request deduplication.

Backed by shared.idempotency_keys (database-design.md §35). Implements
the documented `Idempotency-Key` header behavior
(docs/05-api/api-contracts.md, e.g. POST /api/v1/rides) generically —
lives in shared/ rather than inside modules/ride/ because every future
mutating endpoint documented with an Idempotency-Key header needs the
same mechanism (implementation-readiness.md §22: "Shared infrastructure
must not contain domain-specific business rules" — this module contains
none; it only knows the generic key/hash/response shape already
enumerated in database-design.md §35).

First consumer: modules/ride/router.py, POST /api/v1/rides (ADR-0010
Decision 5). This deliberately only protects against a *retried*
request (same key, same body) — it must never be read as, and does not
implement, a "one active ride at a time" business rule: a customer
submitting two requests with two different Idempotency-Key values
always gets two rides, by design (see ADR-0010 Decision 5's reasoning).

Usage:

    store = IdempotencyStore(db)
    reservation = store.reserve(
        key=header_value, actor_id=account.id, operation="CreateRide",
        request_hash=hash_request(body.model_dump()),
    )
    if reservation.is_replay:
        return reservation.cached_status_code, reservation.cached_body
    ... perform the actual operation, still inside the same db transaction ...
    store.complete(reservation, status_code=201, body=response_body)
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession


class IdempotencyKeyReuseError(Exception):
    """Maps to IDEMPOTENCY_KEY_REUSE (api-contracts.md §49)."""

    code = "IDEMPOTENCY_KEY_REUSE"

    def __init__(
        self, message: str = "Idempotency-Key already used with a different request."
    ) -> None:
        super().__init__(message)
        self.message = message


def hash_request(payload: dict[str, Any]) -> str:
    """A stable hash of a JSON-serializable request body — used only to
    tell a genuine retry (same key, same body) apart from a reused key
    with a different body (rejected). Not a security control."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class Reservation:
    id: uuid.UUID
    is_replay: bool
    cached_status_code: int | None = None
    cached_body: dict[str, Any] | None = None


class IdempotencyStore:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def reserve(
        self,
        *,
        key: str,
        actor_id: uuid.UUID | None,
        operation: str,
        request_hash: str,
    ) -> Reservation:
        """Claims `key` for a new operation, or returns a Reservation
        describing the earlier attempt if the key was already used.

        Uses shared.idempotency_keys.key's UNIQUE constraint as the
        concurrency-safety mechanism: two genuinely concurrent requests
        with the same key race on the INSERT itself, so exactly one can
        ever proceed as a fresh reservation, regardless of application-
        level timing."""
        record_id = uuid.uuid4()
        try:
            self._db.execute(
                text(
                    "INSERT INTO shared.idempotency_keys "
                    "(id, key, actor_id, operation, request_hash) "
                    "VALUES (:id, :key, :actor_id, :operation, :request_hash)"
                ),
                {
                    "id": str(record_id),
                    "key": key,
                    "actor_id": str(actor_id) if actor_id else None,
                    "operation": operation,
                    "request_hash": request_hash,
                },
            )
            self._db.flush()
        except IntegrityError:
            self._db.rollback()
            return self._resolve_existing(key=key, request_hash=request_hash)

        return Reservation(id=record_id, is_replay=False)

    def _resolve_existing(self, *, key: str, request_hash: str) -> Reservation:
        row = self._db.execute(
            text(
                "SELECT id, request_hash, response_code, response_body "
                "FROM shared.idempotency_keys WHERE key = :key"
            ),
            {"key": key},
        ).fetchone()

        if row is None:
            # The conflicting row from the failed INSERT above vanished
            # between then and now (only possible if that other
            # transaction itself rolled back concurrently) — refuse
            # rather than silently retrying, since we can no longer tell
            # whether it's safe to proceed as a fresh request.
            raise IdempotencyKeyReuseError(
                "Idempotency-Key state could not be resolved; retry with a new key."
            )

        if row.request_hash != request_hash:
            raise IdempotencyKeyReuseError()

        if row.response_code is None:
            # Same key, same body, but the original request hasn't
            # recorded a response yet (still in flight, or it crashed
            # before completing). Conservative by design: refuse rather
            # than risk creating a second ride concurrently.
            raise IdempotencyKeyReuseError(
                "Idempotency-Key is already in use by a request still in progress."
            )

        return Reservation(
            id=row.id,
            is_replay=True,
            cached_status_code=row.response_code,
            cached_body=row.response_body,
        )

    def complete(
        self, reservation: Reservation, *, status_code: int, body: dict[str, Any]
    ) -> None:
        self._db.execute(
            text(
                "UPDATE shared.idempotency_keys "
                "SET response_code = :status_code, "
                "response_body = CAST(:body AS jsonb) "
                "WHERE id = :id"
            ),
            {
                "status_code": status_code,
                "body": json.dumps(body, default=str),
                "id": str(reservation.id),
            },
        )
