"""Application service (use cases) for Penalty.

PenaltyService is deliberately decoupled from modules.ride/modules.
wallet — it depends only on the ports.py Protocols. Composition happens
at modules/ride/router.py's cancellation endpoints, which already know
the customer/driver/ride ids this service needs (same one-directional
composition shape every other cross-module call in this codebase uses).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from modules.penalty.domain.entities import Penalty, PenaltyStatus, PenaltyType, Strike
from modules.penalty.domain.errors import (
    InvalidPenaltyResolutionActionError,
    PenaltyNotFoundError,
    PenaltyNotOutstandingError,
)
from modules.penalty.ports import PenaltyRepository, StrikeRepository

# api-contracts.md §48 — the only documented `action` value.
_RESOLUTION_ACTION_WAIVE = "WAIVE"

# BR-047/048: ₹0 for the first qualifying cancellation, ₹15 from the
# second onward.
_CUSTOMER_CANCELLATION_FIRST = Decimal("0")
_CUSTOMER_CANCELLATION_SUBSEQUENT = Decimal("15")


class PenaltyService:
    def __init__(
        self, *, penalties: PenaltyRepository, strikes: StrikeRepository
    ) -> None:
        self._penalties = penalties
        self._strikes = strikes

    def record_customer_cancellation(
        self, *, customer_id: uuid.UUID, ride_id: uuid.UUID, now: datetime
    ) -> Penalty:
        """BR-046-049: called only for a post-acceptance cancellation
        that is NOT within the 2-minute grace period (ADR-0015 Decision
        1 — the caller, modules/ride/router.py, decides that; a
        grace-period cancellation never calls this method at all, so it
        never creates a row or advances the qualifying-cancellation
        count). Idempotent per ride: a retried/racing call for the same
        ride_id returns the same Penalty rather than creating a second
        one (uq_penalties_ride_penalty_type, enforced in
        SqlAlchemyPenaltyRepository.create())."""
        already_qualified = self._penalties.count_by_user_and_type(
            customer_id, penalty_type=PenaltyType.CUSTOMER_CANCELLATION
        )
        amount = (
            _CUSTOMER_CANCELLATION_FIRST
            if already_qualified == 0
            else _CUSTOMER_CANCELLATION_SUBSEQUENT
        )
        penalty = Penalty.new_customer_cancellation(
            customer_id=customer_id, ride_id=ride_id, amount=amount, now=now
        )
        return self._penalties.create(penalty)

    def record_scheduled_ride_late_cancellation(
        self, *, customer_id: uuid.UUID, ride_id: uuid.UUID, now: datetime
    ) -> Penalty:
        """BR-135 (ADR-0057) — called only for a SCHEDULED-ride
        cancellation less than 3 hours before its scheduled pickup time
        (the caller, modules/ride/router.py, decides that; a ≥3h
        cancellation never calls this method at all, same "the caller
        decides when to call" shape record_customer_cancellation()
        above already uses). Always ₹30, no "first vs. second+"
        counter — unlike CUSTOMER_CANCELLATION, this penalty type has
        no qualifying-cancellation history to check."""
        penalty = Penalty.new_scheduled_ride_late_cancellation(
            customer_id=customer_id, ride_id=ride_id, now=now
        )
        return self._penalties.create(penalty)

    def record_driver_strike(
        self, *, driver_id: uuid.UUID, ride_id: uuid.UUID, reason: str, now: datetime
    ) -> Strike:
        """BR-068: every applicable driver cancellation records a
        behavioral strike, independent of and in addition to the ₹30
        wallet-debited financial penalty (processed separately by the
        caller via WalletService.debit() — technical-architecture.md
        §36: "the penalty is processed through the Wallet domain").
        Not called for the changed-pickup-pass special case (BR-071 —
        the caller skips this entirely for that reason)."""
        strike = Strike.new(
            driver_id=driver_id, ride_id=ride_id, reason=reason, now=now
        )
        return self._strikes.create(strike)

    def search_penalties(
        self,
        *,
        status: str | None,
        user_id: uuid.UUID | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Penalty], int]:
        """Phase 16 (Search Penalties, ADR-0023) — admin-only, composed
        at modules/admin/router.py. Pure pass-through to the
        repository."""
        return self._penalties.search(
            status=status, user_id=user_id, offset=offset, limit=limit
        )

    def list_strikes_for_driver(
        self, driver_id: uuid.UUID, *, offset: int, limit: int
    ) -> tuple[list[Strike], int]:
        """Driver Strike History (Admin Web §4.9, api-contracts.md
        §46.18) — admin-only, composed at modules/admin/router.py. Pure
        pass-through to the repository."""
        return self._strikes.list_for_driver(driver_id, offset=offset, limit=limit)

    def get_outstanding_penalty_total(self, *, customer_id: uuid.UUID) -> Decimal:
        """Outstanding Customer Penalty Display (ADR-0026, 2026-08-26 —
        IMPLEMENTED 2026-09-02, api-contracts.md §12's
        `outstanding_penalty`/`total_payable`). Composed at
        modules/ride/router.py's Create Ride endpoint — "the customer's
        next eligible ride booking" rule 3 requires exposing this at.
        `0` for the common case (no OUTSTANDING penalty).

        Superseded as the sole mechanism 2026-09-03 (ADR-0066) — Create
        Ride now calls attach_outstanding_penalties_to_ride() instead,
        which both computes this same total AND durably attaches it to
        the new ride. This method is kept as-is (unattached, read-only)
        for any caller that only wants the number without attaching
        anything — none exists today, but the distinction is real: this
        is a plain read, attach_outstanding_penalties_to_ride() is a
        write."""
        return self._penalties.sum_amount_outstanding_for_user(customer_id)

    def attach_outstanding_penalties_to_ride(
        self, *, customer_id: uuid.UUID, ride_id: uuid.UUID
    ) -> Decimal:
        """Customer Outstanding Penalty Settlement (ADR-0066, owner
        decision 2026-09-03) — called once, at Create Ride (booking).
        Locks every OUTSTANDING, not-yet-attached penalty this customer
        has and durably carries all of them forward to this new ride
        ("the User's next applicable ride") by setting each one's
        settlement_ride_id. Returns the total attached amount (`0` if
        none) — the same number Create Ride's response shows as
        `outstanding_penalty`/`total_payable`, except now backed by a
        real, auditable attachment rather than a live recomputation
        that could drift from what's actually settled later.

        Idempotent within one ride's lifetime by construction: once a
        penalty is attached (settlement_ride_id set), the locked query
        this method runs no longer selects it, so a retried/duplicate
        call attaches nothing further for penalties already attached
        here — though Create Ride itself only ever calls this once per
        ride, immediately after ride creation succeeds."""
        penalties = self._penalties.list_outstanding_unattached_for_user_for_update(
            customer_id
        )
        total = Decimal("0")
        for penalty in penalties:
            penalty.attach_to_ride(ride_id=ride_id)
            self._penalties.save(penalty)
            total += penalty.amount
        return total

    def release_penalties_from_cancelled_ride(self, *, ride_id: uuid.UUID) -> None:
        """Customer Outstanding Penalty Settlement (ADR-0066, owner
        decision 2026-09-03) — called from every cancellation path
        (modules/ride/router.py's cancel_ride()/driver_cancel_ride())
        after a ride that might carry an attached penalty is cancelled.
        Releases any penalty attached to this ride back to unattached-
        OUTSTANDING, so the customer's *next* actual ride can carry it
        forward instead — a ride that never completes must never
        silently lose track of an unpaid penalty. A no-op (0 rows) for
        the overwhelming common case: most cancelled rides never had a
        penalty attached to begin with."""
        penalties = self._penalties.list_by_settlement_ride_id_for_update(ride_id)
        for penalty in penalties:
            penalty.release_from_ride()
            self._penalties.save(penalty)

    def settle_penalties_for_completed_ride(
        self, *, ride_id: uuid.UUID, now: datetime
    ) -> Decimal:
        """Customer Outstanding Penalty Settlement (ADR-0066, owner
        decision 2026-09-03) — called from modules/ride/router.py's
        complete_ride(), after the ride actually reaches COMPLETED.
        "The User pays the Sarthi directly" (owner decision) — this
        method never touches money itself; it only marks every penalty
        attached to this ride as SETTLED and returns the total amount,
        which the caller then uses to debit the driver's wallet
        (WalletService.debit_or_record_as_debt(), TransactionType.
        CASH_SETTLEMENT — "Apply the corresponding Sarthi wallet/
        platform accounting"). Returns `0` (the common case) if no
        penalty was ever attached to this ride."""
        penalties = self._penalties.list_by_settlement_ride_id_for_update(ride_id)
        total = Decimal("0")
        for penalty in penalties:
            penalty.settle_via_ride(now=now)
            self._penalties.save(penalty)
            total += penalty.amount
        return total

    # --- Reports (Admin Web §4.16, ADR-0047) -------------------------

    def count_penalties_by_status(self) -> dict[str, int]:
        return self._penalties.count_by_status()

    def count_penalties_by_type(self) -> dict[str, int]:
        return self._penalties.count_by_type()

    def sum_penalty_amount_outstanding(self) -> Decimal:
        return self._penalties.sum_amount_outstanding()

    def sum_penalty_amount_settled_in_range(
        self, *, since: datetime, until: datetime
    ) -> Decimal:
        return self._penalties.sum_amount_settled_in_range(since=since, until=until)

    def resolve_penalty(
        self, *, penalty_id: uuid.UUID, action: str, reason: str | None
    ) -> Penalty:
        """Phase 16 (ResolvePenalty, ADR-0023) — admin-only, composed at
        modules/admin/router.py. `action` must be exactly "WAIVE" (the
        only value api-contracts.md §48 documents); anything else is
        InvalidPenaltyResolutionActionError, not silently accepted.
        Requires the target penalty to currently be OUTSTANDING —
        SETTLED/already-WAIVED raise PenaltyNotOutstandingError
        (INVALID_STATE_TRANSITION), the same "not in the expected
        starting state" treatment Approve/Reject Driver/Vehicle already
        give their own precondition. Row-locked via
        get_by_id_for_update() so two concurrent resolve attempts on the
        same penalty serialize rather than race."""
        if action != _RESOLUTION_ACTION_WAIVE:
            raise InvalidPenaltyResolutionActionError(
                f"Unsupported resolution action: {action!r}. Only "
                f"{_RESOLUTION_ACTION_WAIVE!r} is supported."
            )

        penalty = self._penalties.get_by_id_for_update(penalty_id)
        if penalty is None:
            raise PenaltyNotFoundError("Penalty not found.")
        if penalty.status is not PenaltyStatus.OUTSTANDING:
            raise PenaltyNotOutstandingError(
                "This penalty is not OUTSTANDING and cannot be resolved."
            )

        penalty.waive()
        self._penalties.save(penalty)
        return penalty
