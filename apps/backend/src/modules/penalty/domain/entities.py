"""Penalty domain entities.

Field shapes match docs/04-database/database-design.md §26.1
(penalty.penalties) and §26.2 (penalty.strikes) exactly.

Only what Phase 3 / Task 3.5-3.6 (post-acceptance customer cancellation,
driver cancellation) need is implemented here — see
modules/penalty/__init__.py for the full "what this deliberately does
not do yet" list (no-show charges, penalty expiry collection,
progressive-abuse escalation).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

# BR-049 (corrected 2026-09-04, owner decision — "Customer penalties in
# VISTAAR NEVER EXPIRE"): a customer penalty remains OUTSTANDING
# indefinitely until actually paid — no validity window, no automatic
# expiry, no expiry-enforcement job. This module previously computed a
# 30-day `expires_at` on every customer penalty and stored it in
# `penalty.penalties.expires_at`; that column, the `CUSTOMER_CHARGE_
# VALIDITY_DAYS` constant that fed it, and `PenaltyStatus.EXPIRED` (which
# no code path ever actually produced — confirmed by a full-codebase
# search before removing it) are all removed as of this correction, not
# just left unused. See ADR-0069 for the full account, and its own
# explicit distinction from Sarthi cancellation-penalty debt
# (`wallet.wallets.outstanding_debt`, ADR-0062) — a completely separate
# mechanism this correction does not touch.


class PenaltyType(StrEnum):
    """Exactly database-design.md §26.1's VARCHAR(50) penalty_type
    column values this codebase currently produces. No-show and other
    documented-but-not-yet-implemented penalty types are deliberately
    not enumerated here yet — added when the task that produces them
    exists, same "don't build ahead of a real caller" discipline used
    throughout this codebase (e.g. modules.wallet.domain.entities.
    TransactionType's own precedent)."""

    CUSTOMER_CANCELLATION = "CUSTOMER_CANCELLATION"
    # ADR-0057, BR-135 — a SCHEDULED ride cancelled <3 hours before its
    # scheduled pickup time. Distinct from CUSTOMER_CANCELLATION: no
    # "first vs. second+" counter, no strike, and the ≥3h/₹0 case never
    # creates a row at all (same "no row for a ₹0 charge" treatment
    # ADR-0015 Decision 2 already established for the grace-period case
    # above).
    SCHEDULED_RIDE_LATE_CANCELLATION = "SCHEDULED_RIDE_LATE_CANCELLATION"


class PenaltyStatus(StrEnum):
    """OUTSTANDING/SETTLED are database-design.md §26.1's documented
    default plus the one other state a ₹0 penalty needs. No fourth
    status was invented for a ₹0 penalty (ADR-0015 Decision 2) — SETTLED
    covers "nothing owed" too, at creation time.

    WAIVED is a different, later-added case (Phase 16, ADR-0023): it is
    NOT about a ₹0 penalty at creation — it's state-machines.md §40's
    own documented sibling of SETTLED, reached only via an admin's
    explicit `POST /api/v1/admin/penalties/{id}/resolve` action on a
    real, OUTSTANDING charge (api-contracts.md §48). The two additions
    are not in tension: ADR-0015 Decision 2 was about what
    Penalty.new_customer_cancellation() produces; WAIVED is a distinct
    later transition an admin performs on an already-created row.

    EXPIRED was removed 2026-09-04 (ADR-0069, owner decision — "Customer
    penalties in VISTAAR NEVER EXPIRE"). It was never actually produced
    by any code path even before this correction (confirmed by a
    full-codebase search) — no expiry-enforcement job was ever built —
    so removing it deletes dead code, not a behavior change."""

    OUTSTANDING = "OUTSTANDING"
    SETTLED = "SETTLED"
    WAIVED = "WAIVED"


@dataclass(slots=True)
class Penalty:
    id: uuid.UUID
    user_id: uuid.UUID
    ride_id: uuid.UUID | None
    penalty_type: PenaltyType
    amount: Decimal
    status: PenaltyStatus
    issued_at: datetime
    settled_at: datetime | None
    # Customer Outstanding Penalty Settlement (owner decision,
    # 2026-09-03: "carry it forward to the User's next applicable
    # ride... The User pays the Sarthi directly... Apply the
    # corresponding Sarthi wallet/platform accounting"). Distinct from
    # `ride_id` above, which is the ride this penalty was originally
    # INCURRED on (e.g. the cancelled ride) and never changes.
    # `settlement_ride_id` is the LATER ride carrying this penalty
    # forward — set by attach_to_ride() when that ride is booked, set
    # back to None by release_from_ride() if that ride is cancelled
    # before completion (so a future ride can attach it instead), and
    # left in place (alongside status -> SETTLED) once settle_via_ride()
    # actually settles it. Defaults to None — every existing constructor
    # below (new_customer_cancellation, new_scheduled_ride_late_
    # cancellation) creates a penalty with no settlement ride attached
    # yet, unchanged from before this field existed.
    settlement_ride_id: uuid.UUID | None = None

    @staticmethod
    def new_customer_cancellation(
        *,
        customer_id: uuid.UUID,
        ride_id: uuid.UUID,
        amount: Decimal,
        now: datetime,
    ) -> Penalty:
        """BR-047/048: amount is 0 for a first qualifying cancellation,
        15 for second+ — the caller (PenaltyService) determines which.
        A 0-amount penalty is created already SETTLED (ADR-0015
        Decision 2 — nothing owed, so immediately settled, not a
        fourth invented status); a real charge starts OUTSTANDING."""
        settled = amount == Decimal("0")
        return Penalty(
            id=uuid.uuid4(),
            user_id=customer_id,
            ride_id=ride_id,
            penalty_type=PenaltyType.CUSTOMER_CANCELLATION,
            amount=amount,
            status=PenaltyStatus.SETTLED if settled else PenaltyStatus.OUTSTANDING,
            issued_at=now,
            settled_at=now if settled else None,
        )

    @staticmethod
    def new_scheduled_ride_late_cancellation(
        *,
        customer_id: uuid.UUID,
        ride_id: uuid.UUID,
        now: datetime,
    ) -> Penalty:
        """BR-135 (ADR-0057) — always ₹30, always OUTSTANDING. Unlike
        new_customer_cancellation() above, there is no ₹0 variant to
        create SETTLED for: the caller (PenaltyService.
        record_scheduled_ride_late_cancellation()) only ever calls this
        for the <3h case — the ≥3h/₹0 case creates no row at all, same
        treatment ADR-0015 Decision 2 gives that pattern elsewhere."""
        return Penalty(
            id=uuid.uuid4(),
            user_id=customer_id,
            ride_id=ride_id,
            penalty_type=PenaltyType.SCHEDULED_RIDE_LATE_CANCELLATION,
            amount=Decimal("30"),
            status=PenaltyStatus.OUTSTANDING,
            issued_at=now,
            settled_at=None,
        )

    def attach_to_ride(self, *, ride_id: uuid.UUID) -> None:
        """Customer Outstanding Penalty Settlement (owner decision,
        2026-09-03) — called at Create Ride (booking) to durably carry
        an OUTSTANDING, not-yet-attached penalty forward to this new
        ride ("the User's next applicable ride"). Same convention as
        waive() below: this is a plain setter, no validation — the
        caller (PenaltyService.attach_outstanding_penalties_to_ride())
        checks OUTSTANDING-and-unattached via its own locked query
        before ever constructing the list of penalties to call this
        on."""
        self.settlement_ride_id = ride_id

    def release_from_ride(self) -> None:
        """The ride this penalty was attached to (attach_to_ride()) was
        cancelled before it could complete — release the attachment so
        a future ride can carry this penalty forward instead. Plain
        setter, same convention as waive()/attach_to_ride() above — the
        caller (PenaltyService.release_penalties_from_cancelled_ride())
        already scoped its query to rows attached to exactly this
        ride."""
        self.settlement_ride_id = None

    def settle_via_ride(self, *, now: datetime) -> None:
        """The ride this penalty was attached to (attach_to_ride())
        actually completed — the customer paid the Sarthi the combined
        fare-plus-penalty amount directly (owner decision, 2026-09-03),
        so this penalty is now settled. Plain setter, same convention as
        waive()/attach_to_ride() above — the caller (PenaltyService.
        settle_penalties_for_completed_ride()) already scoped its query
        to OUTSTANDING rows attached to exactly this ride; settled_at is
        stamped here since every call site needs it, the same reason
        waive() does NOT stamp one (WAIVED is deliberately not
        "settled", per that method's own docstring)."""
        self.status = PenaltyStatus.SETTLED
        self.settled_at = now

    def waive(self) -> None:
        """Phase 16 (ResolvePenalty / admin `action: "WAIVE"`, ADR-0023).
        Only a real, currently-OUTSTANDING charge can be waived — the
        caller (PenaltyService.resolve_penalty()) checks this before
        calling. `amount`/`issued_at` are left untouched
        (api-contracts.md §48: "The original penalty remains
        immutable") — only `status` changes. `settled_at` is
        deliberately NOT set: WAIVED is not "settled" (state-machines.md
        §40 lists them as separate sibling states), and no separate
        `waived_at` column is documented; the admin.audit_logs row this
        action also writes is the timestamped record of when it
        happened."""
        self.status = PenaltyStatus.WAIVED


@dataclass(slots=True)
class Strike:
    id: uuid.UUID
    driver_id: uuid.UUID
    ride_id: uuid.UUID | None
    reason: str
    created_at: datetime

    @staticmethod
    def new(
        *, driver_id: uuid.UUID, ride_id: uuid.UUID, reason: str, now: datetime
    ) -> Strike:
        return Strike(
            id=uuid.uuid4(),
            driver_id=driver_id,
            ride_id=ride_id,
            reason=reason,
            created_at=now,
        )
