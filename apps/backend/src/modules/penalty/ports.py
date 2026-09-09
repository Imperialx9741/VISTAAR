"""Abstract interfaces (ports) the application layer depends on."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from modules.penalty.domain.entities import Penalty, PenaltyType, Strike


class PenaltyRepository(Protocol):
    def count_by_user_and_type(
        self, user_id: uuid.UUID, *, penalty_type: PenaltyType
    ) -> int:
        """Total penalty.penalties rows for this user_id/penalty_type,
        regardless of status — used to determine "first" vs. "second+
        qualifying cancellation" (BR-047/048). A grace-period
        cancellation never reaches this count (ADR-0015 Decision 1 — no
        row is ever created for one)."""
        ...

    def create(self, penalty: Penalty) -> Penalty:
        """Inserts `penalty`. Safe under concurrent double-submission of
        the same cancellation: uq_penalties_ride_penalty_type (migration
        383b55c70732) means a genuine duplicate insert for the same
        (ride_id, penalty_type) raises IntegrityError — the
        implementation catches this and returns the already-existing
        row instead (same idempotent-on-conflict shape
        modules.wallet.repositories.SqlAlchemyWalletRepository.
        get_or_create_for_update uses for its own race)."""
        ...

    def get_by_id_for_update(self, penalty_id: uuid.UUID) -> Penalty | None:
        """Phase 16 (ResolvePenalty, ADR-0023). Returns the penalty
        locked for the remainder of the current transaction (SELECT ...
        FOR UPDATE, database-design.md §42's row-locking pattern) — same
        mechanism modules.driver.service.DriverService.suspend_driver()/
        reactivate_driver() already use, so two concurrent resolve
        attempts on the same penalty serialize on this lock rather than
        both racing to waive it."""
        ...

    def list_outstanding_unattached_for_user_for_update(
        self, user_id: uuid.UUID
    ) -> list[Penalty]:
        """Customer Outstanding Penalty Settlement (owner decision,
        2026-09-03). Every OUTSTANDING penalty for this user with no
        settlement_ride_id yet, row-locked for the remainder of the
        current transaction — see
        SqlAlchemyPenaltyRepository's own docstring for why locking
        matters here."""
        ...

    def list_by_settlement_ride_id_for_update(
        self, ride_id: uuid.UUID
    ) -> list[Penalty]:
        """Customer Outstanding Penalty Settlement (owner decision,
        2026-09-03). Every OUTSTANDING penalty currently attached
        (settlement_ride_id) to this ride, row-locked — used to release
        the attachment on cancellation or settle it on completion."""
        ...

    def save(self, penalty: Penalty) -> None:
        """Phase 16 (ResolvePenalty, ADR-0023); extended 2026-09-03 for
        Customer Outstanding Penalty Settlement. Persists `penalty`'s
        current `status`/`settled_at`/`settlement_ride_id` back onto the
        already-locked row a prior `get_by_id_for_update()` (or one of
        the two list methods above) call returned in this same
        transaction."""
        ...

    def search(
        self,
        *,
        status: str | None,
        user_id: uuid.UUID | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Penalty], int]:
        """Phase 16 (Search Penalties, ADR-0023). Allow-listed filters
        only, same shape as modules.ride.ports.RideRepository.search().
        Ordered newest-first (`issued_at DESC`). Returns (page, total
        matching count)."""
        ...

    def count_by_status(self) -> dict[str, int]:
        """Admin Web §4.16 Penalties report (ADR-0047) — a current
        snapshot, not date-ranged (a penalty's status can change well
        after it was issued, so "in range" wouldn't mean what a reader
        expects)."""
        ...

    def count_by_type(self) -> dict[str, int]: ...

    def sum_amount_outstanding(self) -> Decimal:
        """Current total across every OUTSTANDING penalty, all-time."""
        ...

    def sum_amount_outstanding_for_user(self, user_id: uuid.UUID) -> Decimal:
        """Outstanding Customer Penalty Display (ADR-0026, api-contracts.md
        §12's `outstanding_penalty`/`total_payable`) — the same
        aggregate as sum_amount_outstanding() above, scoped to one
        customer. `0` if they have no OUTSTANDING row."""
        ...

    def sum_amount_settled_in_range(
        self, *, since: datetime, until: datetime
    ) -> Decimal:
        """SUM(amount) for penalties with `settled_at` in
        [since, until)."""
        ...


class StrikeRepository(Protocol):
    def create(self, strike: Strike) -> Strike:
        """Inserts `strike`. No uniqueness constraint — a driver may
        record more than one strike (database-design.md §26.2 has none
        either); duplicate-prevention for a single cancellation event is
        the caller's responsibility (the ride row lock already
        serializes concurrent cancel attempts on the same ride — see
        modules/ride/service.py::cancel_ride())."""
        ...

    def list_for_driver(
        self, driver_id: uuid.UUID, *, offset: int, limit: int
    ) -> tuple[list[Strike], int]:
        """Driver Strike History (Admin Web §4.9, api-contracts.md
        §46.18) — every strike ever recorded for this driver, newest
        first. Immutable by construction (no update/delete path exists
        for a Strike), so this is a plain read, no status/date filter
        needed the way Search Penalties/Search Offers have one."""
        ...
