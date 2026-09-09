"""FastAPI routes for Ride.

Endpoints (docs/05-api/api-contracts.md §12, §12.1, §13, §17, §18, §19,
§20, §28):

    GET  /api/v1/rides                          List My Rides (ADR-0057)
    POST /api/v1/rides                          Create Ride Request
        (extended by ADR-0057, 2026-08-31, with optional
        `scheduled_for`/`linked_contact` — Schedule a Ride / Book for
        Someone Else)
    GET  /api/v1/rides/{ride_id}                Get Ride (Phase 04, ADR-0024)
    POST /api/v1/rides/{ride_id}/cancel         Customer Cancellation
        (extended by ADR-0057 to also accept a SCHEDULED ride)
    POST /api/v1/rides/{ride_id}/driver-cancel  Driver Cancellation
    POST /api/v1/rides/{ride_id}/arrived        Driver Arrival (Phase 06/07)
    POST /api/v1/rides/{ride_id}/otp/refresh    Generate/Refresh Ride OTP (Phase 06/07;
        extended by ADR-0057 to also SMS the linked contact, if any)
    POST /api/v1/rides/{ride_id}/start          Start Ride (Phase 06/07, ADR-0028)
    POST /api/v1/rides/{ride_id}/complete       Ride Completion (Phase 06/07)
    POST /api/v1/rides/{ride_id}/early-drop         Request Early Drop (Phase 08)
    POST /api/v1/rides/{ride_id}/early-drop/confirm Confirm Early Drop (Phase 08)
    POST /api/v1/rides/{ride_id}/pickup-change            Pickup Change
        (ADR-0033; simplified to a 100m hard threshold, no driver
        decision, by ADR-0056, 2026-08-31 — the old driver-decision/
        customer-confirmation endpoints this once listed are removed)
    POST /api/v1/rides/{ride_id}/destination-change
        Destination Change (ADR-0033)
    POST /api/v1/rides/{ride_id}/destination-change/confirm
        Destination Change Confirmation (ADR-0033)

Schedule a Ride (ADR-0057) needed no new matching engineering: a
SCHEDULED ride (state-machines.md §3.9) skips the matching-dispatch
call this router's create_ride() already makes for an immediate ride
(the `if ride.status is RideStatus.SEARCHING:` guard below), and a new
Celery Beat task (modules/ride/tasks.py) later promotes it to SEARCHING
and makes that same dispatch call itself, at which point it's
indistinguishable from any other SEARCHING ride to every endpoint
below. Fare-locking needed no new code either — calculate_fare() below
already runs unconditionally right after ride creation, so a SCHEDULED
ride's fare is locked at scheduling time simply by virtue of that call
happening before matching, not because of it.

See modules/ride/__init__.py for the full list of what this module
deliberately does not do (fare calculation itself, promotion, any other
ride-lifecycle command beyond AssignDriver/cancellation).

mark_arrived()/start_ride()/complete_ride() (Phase 06/07, ADR-0028) are
unlike every other explicit-commit endpoint above: a *caught* domain
error still `db.commit()`s, never `db.rollback()`s — because, unlike
create_ride()'s idempotency-reservation write or cancel_ride()'s
wallet/penalty composition, the write RideService already made before
raising (the ride.gps_verifications audit row on a GPS FAIL; the
incremented attempts/EXPIRED status on a bad/expired OTP) is exactly
the state this design wants kept, not undone — see each endpoint's own
`except RideDomainError` comment for why. A success writes the
documented outbox event, then commits once, same as everywhere else.
refresh_ride_otp() has no side effect worth an outbox event of its own
(event-contracts.md documents none for it) and every domain error it
can raise happens before any write, so it never touches
`db.commit()`/`db.rollback()` explicitly — get_db's default
commit-on-return handles it, same as get_ride_status().

get_ride_status() (Phase 04, ADR-0024) reuses RideService.get_ride()
(added Phase 3 / Task 3.2, previously internal-only) and is the one
place this router composes modules.driver + modules.vehicle for their
own sake (not just modules.vehicle's domain entities/errors, as
elsewhere in this file) — read-only, same one-directional composition
shape as everywhere else. Distinct from the admin-only `GET
/api/v1/admin/rides/{ride_id}` (ADR-0023): this one is ownership-
restricted (IDOR-safe — same response for missing and unauthorized) and
lives under this router's own `/api/v1/rides` prefix.

cancel_ride() (Task 3.3, ADR-0012; extended Task 3.5, ADR-0015) follows
the same explicit-commit pattern create_ride() established, branching on
`previous_status`:

- SEARCHING: unchanged from Task 3.3 — the cancellation is committed
  first, then cancelling any outstanding matching offer is attempted
  best-effort in its own try/except (a failure to cancel the offer must
  never undo the ride's own, already-successful cancellation).
- ACCEPTED/ARRIVED (Task 3.5): a *different*, fully-atomic shape — the
  cancellation, the driver's platform-fee refund (modules.wallet), and
  the customer's qualifying-cancellation penalty (modules.penalty, only
  when outside the 2-minute grace period) all happen inside the SAME
  transaction as one unit, then commit once. This is real money moving
  (a wallet credit) and a financial charge record, unlike the
  best-effort offer-cancellation step above — BR-013-style atomicity
  applies, not the "never let a secondary step undo the primary one"
  looseness Task 3.3's offer-cancellation step uses. RideService.
  cancel_ride() already holds a row lock on the ride
  (get_by_id_for_update(), ADR-0015) for the whole composition below,
  serializing a concurrent second cancel attempt on the same ride the
  same way modules/matching/router.py's accept-offer composition
  serializes a concurrent double-accept.

driver_cancel_ride() (Task 3.6, ADR-0016) implements exactly the
documented ACCEPTED → CANCELLED transition, the ₹30 wallet penalty
(BR-067, technical-architecture.md §36 — "processed through the Wallet
domain", a plain WalletService.debit(), no new primitive needed), the
behavioral strike (BR-068), and the BR-071 changed-pickup-pass
exemption (no penalty, no strike). BR-070's "automatic rematch, no new
booking needed" is explicitly NOT implemented — ADR-0016 Item 2, a
genuine ambiguity between two authoritative documents, flagged rather
than guessed past.

Idempotency-Key handling (ADR-0010 Decision 5) does its own explicit
db.rollback()/commit() around the ride-creation transaction, unlike this
codebase's other routers (which rely entirely on core.database.get_db's
implicit commit-on-return/rollback-on-exception): this endpoint writes
to the database twice before create_ride() can raise a validation error
— the idempotency reservation (IdempotencyStore.reserve()) and the
auto-provisioned customer.customers row (CustomerService.get_profile())
— so, unlike every existing router (where a domain error is always
raised before any write happens), a caught domain error here can follow
a real partial write that must be undone explicitly rather than
committed by get_db's default behavior.

Phase 3 / Task 3.2 adds a best-effort matching dispatch after the ride
is durably created: the ride is explicitly committed first, then
modules.matching.MatchingService.dispatch_offer() is attempted in its
own try/except with its own explicit commit/rollback. A matching failure
(no eligible driver found, or a genuine error) must never roll back or
fail the already-successful ride-creation response — the ride staying
SEARCHING with no active offer is a legitimate outcome (ADR-0011 Item
5), and this module has no business re-litigating whether the ride
itself should exist just because dispatch had trouble. This is why ride
creation is no longer a single implicit transaction the way it looked in
Task 3.1 — see ADR-0011 for the full reasoning. This is the one place
modules/ride/ imports modules/matching/ (a narrow, one-directional
dependency at the router/composition layer only, same shape as every
other cross-module composition in this codebase).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.orm import Session as DbSession

from core.config import settings
from core.database import get_db
from core.redis import get_redis
from modules.customer.dependencies import get_customer_service
from modules.customer.service import CustomerService
from modules.driver.dependencies import get_driver_service
from modules.driver.domain.entities import Driver
from modules.driver.domain.errors import DriverDomainError
from modules.driver.service import DriverService
from modules.identity.dependencies import (
    get_sms_provider_dependency,
    require_customer,
    require_customer_or_driver,
    require_driver,
)
from modules.identity.domain.entities import Account, AccountType
from modules.identity.ports import SmsProvider
from modules.matching.dependencies import get_matching_service
from modules.matching.service import MatchingService
from modules.notification.dependencies import get_notification_service
from modules.notification.domain.entities import Channel
from modules.notification.service import NotificationService
from modules.penalty.dependencies import get_penalty_service
from modules.penalty.domain.errors import PenaltyDomainError
from modules.penalty.service import PenaltyService
from modules.pricing.dependencies import get_pricing_service
from modules.pricing.domain.entities import FareQuote
from modules.pricing.domain.errors import PricingDomainError
from modules.pricing.service import PricingService
from modules.promotion.dependencies import get_promotion_service
from modules.promotion.domain.entities import Entitlement
from modules.promotion.domain.errors import PromotionDomainError
from modules.promotion.service import PromotionService
from modules.ride.dependencies import get_gps_dispute_object_storage, get_ride_service
from modules.ride.domain.entities import (
    GpsDispute,
    GpsDisputeEvidence,
    Ride,
    RideStatus,
)
from modules.ride.domain.errors import (
    GpsVerificationFailedError,
    RideDomainError,
    RideNotFoundError,
)
from modules.ride.schemas import (
    CancelRideBody,
    ConfirmDestinationChangeBody,
    ConfirmEarlyDropBody,
    CreateRideBody,
    GpsDisputeEvidenceUploadUrlBody,
    GpsVerificationBody,
    RequestDestinationChangeBody,
    RequestEarlyDropBody,
    RequestPickupChangeBody,
    StartRideBody,
    SubmitGpsDisputeEvidenceBody,
)
from modules.ride.service import RideService
from modules.vehicle.dependencies import get_vehicle_service
from modules.vehicle.domain.entities import Vehicle, matching_category_key
from modules.vehicle.domain.errors import VehicleDomainError
from modules.vehicle.service import VehicleService
from modules.wallet.dependencies import get_wallet_service
from modules.wallet.domain.errors import WalletDomainError
from modules.wallet.service import WalletService
from shared.api_envelope import (
    error_envelope,
    http_status_for_error_code,
    new_request_id,
    success_envelope,
)
from shared.idempotency import IdempotencyKeyReuseError, IdempotencyStore, hash_request
from shared.outbox import OutboxStore, new_envelope
from shared.pagination import PageParams, pagination_envelope
from shared.rate_limit import RateLimitedError, RateLimiter, rate_limit_key
from shared.storage import ObjectStorage, UnsupportedContentTypeError

# See modules/matching/router.py's identical constant for the same
# "engineering choice, not documented" reasoning.
_CANDIDATE_LIMIT = 20

# BR-046: the 2-minute cancellation grace period after driver acceptance.
_CANCELLATION_GRACE_PERIOD = timedelta(minutes=2)

# BR-067: the driver cancellation penalty. BR-071's changed-pickup-pass
# reason (api-contracts.md §20) is exempt from it.
_DRIVER_CANCELLATION_PENALTY = Decimal("30")
_CHANGED_PICKUP_PASS_REASON = "CHANGED_PICKUP_OVER_250M"

# BR-135 (ADR-0057) — a SCHEDULED ride's own cancellation window,
# distinct from BR-046's 2-minute post-acceptance grace period.
_SCHEDULED_RIDE_CANCELLATION_WINDOW = timedelta(hours=3)

# ADR-0057 — List My Rides' own `status` query param validation, same
# "an unrecognized value is a genuine client mistake" reasoning
# modules/admin/router.py's own _VALID_RIDE_STATUSES already applies to
# Search Rides (a separate constant — this one is customer-facing, that
# one admin-facing; kept apart rather than shared across routers,
# matching this codebase's general avoid-cross-router-imports style).
_VALID_RIDE_STATUSES = frozenset(status.value for status in RideStatus)

router = APIRouter(prefix="/api/v1/rides", tags=["rides"])


def _fare_data(quote: FareQuote) -> dict[str, object]:
    # api-contracts.md §12's documented future shape (ADR-0020 Decision
    # 6, closing ADR-0010 Decision 1's `fare: null` placeholder). "base"
    # is every pre-discount line item summed — domain-design.md §11.3's
    # full formula, not just base_fare — so this stays correct once
    # time/waiting/parking/toll/tax charges are ever non-zero.
    pre_discount = (
        quote.base_fare
        + quote.distance_charge
        + quote.time_charge
        + quote.waiting_charge
        + quote.parking_charge
        + quote.toll_charge
        + quote.tax_amount
        + quote.additional_charge
    )
    return {
        "base": float(pre_discount),
        "discount": float(quote.promotion_discount),
        "total": float(quote.total),
        "currency": "INR",
    }


def _ride_data(
    ride: Ride, quote: FareQuote | None, *, outstanding_penalty: Decimal
) -> dict[str, object]:
    """Create Ride's own response shape (api-contracts.md §12) — not
    reused by any other endpoint (unlike _ride_status_data below),
    since `outstanding_penalty`/`total_payable` are specifically "the
    customer's next eligible ride booking" fields (ADR-0026 rule 3), not
    a general ride-status concept."""
    outstanding_penalty_data = (
        {"amount": float(outstanding_penalty), "currency": "INR"}
        if outstanding_penalty > 0
        else None
    )
    total_payable_data = None
    if quote is not None:
        total_payable_data = {
            "ride_fare": float(quote.total),
            "outstanding_penalty": float(outstanding_penalty),
            "total": float(quote.total + outstanding_penalty),
            "currency": "INR",
        }
    return {
        "ride_id": str(ride.id),
        "status": ride.status.value,
        "fare": _fare_data(quote) if quote is not None else None,
        "outstanding_penalty": outstanding_penalty_data,
        "total_payable": total_payable_data,
    }


def _get_ride_driver_data(driver: Driver) -> dict[str, object]:
    # ADR-0024 Decision 1 — deliberately excludes phone number; see the
    # ADR for why.
    return {
        "driver_id": str(driver.id),
        "full_name": driver.full_name,
        "profile_photo_uri": driver.profile_photo_uri,
    }


def _get_ride_vehicle_data(vehicle: Vehicle) -> dict[str, object]:
    return {
        "vehicle_id": str(vehicle.id),
        "category": vehicle.category.value,
        "registration_number": vehicle.registration_number,
        "make": vehicle.make,
        "model": vehicle.model,
    }


def _ride_status_data(
    ride: Ride,
    quote: FareQuote | None,
    driver: Driver | None,
    vehicle: Vehicle | None,
) -> dict[str, object]:
    # api-contracts.md §13 (Get Ride, ADR-0024). `payment` stays `null`
    # — no Payment domain exists anywhere in this codebase (Phase 10,
    # blocked) — the same "genuinely unknown, not fabricated" treatment
    # ADR-0010 Decision 1 originally gave `fare: null`.
    return {
        "ride_id": str(ride.id),
        "status": ride.status.value,
        # ADR-0057 — null for every ride except a SCHEDULED one, so a
        # customer viewing their own scheduled ride's detail can see
        # when it's actually for, not just that it's "SCHEDULED".
        "scheduled_for": (
            ride.scheduled_for.isoformat() if ride.scheduled_for is not None else None
        ),
        "pickup": {
            "latitude": ride.current_pickup.latitude,
            "longitude": ride.current_pickup.longitude,
        },
        "destination": {
            "latitude": ride.current_destination.latitude,
            "longitude": ride.current_destination.longitude,
        },
        "driver": _get_ride_driver_data(driver) if driver is not None else None,
        "vehicle": _get_ride_vehicle_data(vehicle) if vehicle is not None else None,
        "fare": _fare_data(quote) if quote is not None else None,
        "payment": None,
    }


def _ride_list_item_data(ride: Ride) -> dict[str, object]:
    # ADR-0057, api-contracts.md §12.1 (List My Rides). Deliberately
    # lighter than _ride_status_data() above — no driver/vehicle/fare
    # composition (each item here would otherwise need its own extra
    # queries; a customer who wants full detail already has
    # GET /rides/{ride_id}, §13, for that). Enough to browse and pick
    # which upcoming scheduled ride to open next.
    return {
        "ride_id": str(ride.id),
        "status": ride.status.value,
        "scheduled_for": (
            ride.scheduled_for.isoformat() if ride.scheduled_for is not None else None
        ),
        "pickup": {
            "latitude": ride.current_pickup.latitude,
            "longitude": ride.current_pickup.longitude,
        },
        "destination": {
            "latitude": ride.current_destination.latitude,
            "longitude": ride.current_destination.longitude,
        },
    }


def _domain_error_response(
    exc: RideDomainError
    | VehicleDomainError
    | WalletDomainError
    | PenaltyDomainError
    | PricingDomainError
    | PromotionDomainError
    | DriverDomainError,
    request_id: str,
) -> JSONResponse:
    # ADR-0032: a GPS_VERIFICATION_FAILED error carries the dispute it
    # just opened (BR-124/BR-125) — surfaced via `details` so the caller
    # can discover and act on it; no other error in this codebase's
    # domain-error hierarchy carries this attribute.
    details = (
        {"dispute_id": str(exc.dispute_id)}
        if isinstance(exc, GpsVerificationFailedError) and exc.dispute_id is not None
        else None
    )
    return JSONResponse(
        status_code=http_status_for_error_code(exc.code),
        content=error_envelope(
            exc.code, exc.message, request_id=request_id, details=details
        ),
    )


def _publish_gps_dispute_opened_if_any(
    db: DbSession,
    exc: RideDomainError,
    *,
    ride_service: RideService,
    ride_id: uuid.UUID,
    driver_id: uuid.UUID,
    now: datetime,
) -> None:
    """ADR-0032 Decision 6 — publishes `ride.gps_dispute_opened`
    (event-contracts.md §10.10) exactly when mark_arrived()/
    complete_ride() just opened one (a GpsVerificationFailedError with a
    dispute_id, per ADR-0032 Decision 2) — a no-op for every other
    RideDomainError this router's except blocks also catch. Re-fetches
    the dispute via get_gps_dispute() (the driver who just opened it
    always owns it, so this ownership check always passes) rather than
    carrying the full entity on the exception itself, which would need
    modules.ride.domain.errors importing modules.ride.domain.entities —
    a circular import, since entities.py already imports errors.py."""
    if not (isinstance(exc, GpsVerificationFailedError) and exc.dispute_id is not None):
        return
    dispute, _evidence = ride_service.get_gps_dispute(
        dispute_id=exc.dispute_id, account_id=driver_id, is_admin=False, now=now
    )
    OutboxStore(db).append(
        new_envelope(
            event_type="ride.gps_dispute_opened",
            producer="ride-service",
            aggregate_type="ride",
            aggregate_id=ride_id,
            data={
                "dispute_id": str(dispute.id),
                "ride_id": str(ride_id),
                "gps_verification_id": str(dispute.gps_verification_id),
                "verification_type": dispute.verification_type.value,
                "evidence_deadline": dispute.evidence_deadline.isoformat(),
            },
            now=now,
        )
    )


@router.get("")
async def list_my_rides(
    account: Annotated[Account, Depends(require_customer)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
    status: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """List My Rides (api-contracts.md §12.1, ADR-0057) — added
    specifically to make Schedule a Ride usable: a customer can
    otherwise only ever fetch a ride by an id they already have (§13),
    with no way to browse upcoming scheduled rides booked in an earlier
    session. Reuses RideService.search_rides() (Phase 16/ADR-0023's
    admin Search Rides implementation) with `customer_id` forced to the
    caller and `driver_id` always None — the same repository method,
    just IDOR-safe instead of admin-arbitrary."""
    request_id = new_request_id()
    if status is not None and status not in _VALID_RIDE_STATUSES:
        return JSONResponse(
            status_code=422,
            content=error_envelope(
                "VALIDATION_FAILED",
                f"Unknown ride status: {status!r}.",
                request_id=request_id,
            ),
        )
    params = PageParams.clamp(
        page=page, page_size=page_size, max_page_size=settings.MAX_PAGE_SIZE
    )
    rides, total = ride_service.search_rides(
        status=status,
        driver_id=None,
        customer_id=account.id,
        offset=params.offset,
        limit=params.page_size,
    )
    items = [_ride_list_item_data(ride) for ride in rides]

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(items, params=params, total=total),
            request_id=request_id,
        ),
    )


@router.post("")
async def create_ride(
    body: CreateRideBody,
    account: Annotated[Account, Depends(require_customer)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Annotated[DbSession, Depends(get_db)],
    redis_client: Annotated[Redis, Depends(get_redis)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
    customer_service: Annotated[CustomerService, Depends(get_customer_service)],
    matching_service: Annotated[MatchingService, Depends(get_matching_service)],
    pricing_service: Annotated[PricingService, Depends(get_pricing_service)],
    promotion_service: Annotated[PromotionService, Depends(get_promotion_service)],
    penalty_service: Annotated[PenaltyService, Depends(get_penalty_service)],
) -> JSONResponse:
    request_id = new_request_id()

    # Rate limiting (security.md §20, security-review-2026-09-02.md
    # finding 4.1) — before the idempotency reservation, same "reject
    # cheaply before any real work" ordering the wallet low-balance gate
    # (ADR-0058) uses in modules/matching/router.py. Per-customer, not
    # per-IP: this endpoint always requires a real access token first.
    try:
        await RateLimiter(redis_client).check_and_increment(
            key=rate_limit_key(category="ride_create", identity=str(account.id)),
            limit=settings.RATE_LIMIT_RIDE_CREATE_PER_HOUR,
            window_seconds=3600,
        )
    except RateLimitedError as exc:
        return JSONResponse(
            status_code=429,
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    now = datetime.now(UTC)
    store = IdempotencyStore(db)
    request_hash = hash_request(body.model_dump())

    try:
        # IdempotencyStore.reserve() already rolls back internally on
        # both branches below (a fresh reservation succeeded, so there's
        # nothing to undo; or it hit an existing key, in which case it
        # rolls back its own failed INSERT before resolving the existing
        # row) — no further rollback needed here for either outcome.
        reservation = store.reserve(
            key=idempotency_key,
            actor_id=account.id,
            operation="CreateRide",
            request_hash=request_hash,
        )
    except IdempotencyKeyReuseError as exc:
        return JSONResponse(
            status_code=http_status_for_error_code(exc.code),
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    if reservation.is_replay:
        return JSONResponse(
            status_code=reservation.cached_status_code or 201,
            content=reservation.cached_body,
        )

    try:
        # Establishes the customer.customers row exists — required by
        # ride.rides.customer_id's foreign key (database-design.md
        # §9.1). Auto-provisions; same API-layer composition pattern
        # modules/vehicle/router.py uses for driver.drivers.
        customer_service.get_profile(account_id=account.id)

        ride = ride_service.create_ride(
            customer_id=account.id,
            pickup_latitude=body.pickup.latitude,
            pickup_longitude=body.pickup.longitude,
            destination_latitude=body.destination.latitude,
            destination_longitude=body.destination.longitude,
            vehicle_category=body.vehicle_category,
            cab_tier=body.cab_tier,
            scheduled_for=body.scheduled_for,
            linked_contact_name=(
                body.linked_contact.name if body.linked_contact is not None else None
            ),
            linked_contact_phone=(
                body.linked_contact.phone if body.linked_contact is not None else None
            ),
        )

        # ADR-0020 Decision 6 / api-contracts.md §12: "Calculate fare ->
        # Apply eligible promotion", right after the ride itself exists
        # (pricing.fare_quotes.ride_id is a NOT NULL FK). Reserving a
        # promotion is soft-fail, not this endpoint's business to error
        # out over — a losing race against another concurrent ride for
        # the same entitlement's last remaining use just means this ride
        # gets no discount, not a failed ride creation.
        reserved_entitlement: Entitlement | None = None
        for entitlement in sorted(
            promotion_service.list_entitlements(customer_id=account.id, now=now),
            key=lambda e: e.expires_at,
        ):
            try:
                # Named promo_reservation, not `reservation` — that name
                # is already the outer IdempotencyStore reservation this
                # whole endpoint completes at the very end
                # (store.complete(reservation, ...)); shadowing it here
                # would silently corrupt that call.
                promo_reservation = promotion_service.reserve_entitlement(
                    customer_id=account.id,
                    entitlement_id=entitlement.id,
                    ride_id=ride.id,
                    now=now,
                )
            except PromotionDomainError:
                continue
            reserved_entitlement = entitlement
            OutboxStore(db).append(
                new_envelope(
                    event_type="promotion.reserved",
                    producer="promotion-service",
                    aggregate_type="entitlement",
                    aggregate_id=entitlement.id,
                    data={
                        "entitlement_id": str(entitlement.id),
                        "ride_id": str(ride.id),
                        "reservation_id": str(promo_reservation.id),
                    },
                    now=now,
                )
            )
            break

        quote = pricing_service.calculate_fare(
            ride_id=ride.id,
            vehicle_category=ride.requested_vehicle_category.value,
            cab_tier=(
                ride.requested_cab_tier.value
                if ride.requested_cab_tier is not None
                else None
            ),
            pickup_latitude=body.pickup.latitude,
            pickup_longitude=body.pickup.longitude,
            destination_latitude=body.destination.latitude,
            destination_longitude=body.destination.longitude,
            promotion_discount_percent=(
                reserved_entitlement.discount_percent
                if reserved_entitlement is not None
                else None
            ),
            promotion_max_discount_amount=(
                reserved_entitlement.max_discount_amount
                if reserved_entitlement is not None
                else None
            ),
            now=now,
        )
        ride_service.set_active_fare_quote(ride_id=ride.id, fare_quote_id=quote.id)
    except (RideDomainError, VehicleDomainError, PricingDomainError) as exc:
        # See this module's docstring for why this explicit rollback is
        # necessary here (unlike this codebase's other routers): undoes
        # both the idempotency reservation above and any customer
        # auto-provision, so a retry with the same Idempotency-Key isn't
        # permanently blocked by a reservation row that never got a
        # response recorded against it.
        db.rollback()
        return _domain_error_response(exc, request_id)

    # Phase 3 / Event & Outbox Foundation (ADR-0017). event-contracts.md
    # §56's registry: producer "Ride", consumers Matching/Notification —
    # only Matching exists in this codebase; the outbox row is written
    # either way (a consumer's existence is not this producer's concern).
    OutboxStore(db).append(
        new_envelope(
            event_type="ride.requested",
            producer="ride-service",
            aggregate_type="ride",
            aggregate_id=ride.id,
            data={
                "ride_id": str(ride.id),
                "customer_id": str(ride.customer_id),
                "status": ride.status.value,
                "requested_vehicle_category": ride.requested_vehicle_category.value,
                "requested_cab_tier": (
                    ride.requested_cab_tier.value
                    if ride.requested_cab_tier is not None
                    else None
                ),
            },
            now=ride.requested_at,
        )
    )
    # event-contracts.md §12.1 — exact documented payload shape.
    OutboxStore(db).append(
        new_envelope(
            event_type="pricing.fare_calculated",
            producer="pricing-service",
            aggregate_type="fare_quote",
            aggregate_id=quote.id,
            data={
                "fare_quote_id": str(quote.id),
                "ride_id": str(ride.id),
                "version": quote.version,
                "total": float(quote.total),
                "currency": "INR",
                "reason": quote.reason,
            },
            now=now,
        )
    )

    # The ride is durably created from here on, independent of whatever
    # happens next — see this module's docstring.
    db.commit()

    # ADR-0057 Decision 1 — a SCHEDULED ride's fare is locked right now
    # (the calculate_fare() call above already ran unconditionally, same
    # as an immediate ride), but matching itself does not begin yet: the
    # scheduled-ride Beat task (modules/ride/tasks.py) promotes this
    # ride to SEARCHING and dispatches matching once its lock_in_at is
    # reached, not this request.
    if ride.status is RideStatus.SEARCHING:
        try:
            await matching_service.dispatch_offer(
                ride_id=ride.id,
                requested_category=matching_category_key(
                    ride.requested_vehicle_category, ride.requested_cab_tier
                ),
                pickup_latitude=ride.original_pickup.latitude,
                pickup_longitude=ride.original_pickup.longitude,
                search_radius_km=settings.MATCHING_SEARCH_RADIUS_KM,
                offer_ttl_seconds=settings.MATCHING_OFFER_TTL_SECONDS,
                candidate_limit=_CANDIDATE_LIMIT,
                now=datetime.now(UTC),
            )
            db.commit()
        except Exception:
            db.rollback()

    # Customer Outstanding Penalty Settlement (ADR-0066, owner decision
    # 2026-09-03) — "carry it forward to the User's next applicable
    # ride." Attaches (not just reads) every OUTSTANDING, unattached
    # penalty this customer has to this new ride — durable, not a live
    # recomputation later; see PenaltyService.
    # attach_outstanding_penalties_to_ride()'s own docstring. Never
    # blocks/fails ride creation, which is already durably committed
    # above (BR-057 — booking is never blocked by an unpaid outstanding
    # charge) — same best-effort-past-the-point-of-no-return treatment
    # as matching_service.dispatch_offer() above: a real failure here
    # must not turn an already-created ride into a 500 response: worst
    # case, the penalty stays unattached and a later ride attaches it
    # instead (get_outstanding_penalty_total() below is the read-only
    # fallback so the response still shows the correct total either
    # way).
    try:
        outstanding_penalty = penalty_service.attach_outstanding_penalties_to_ride(
            customer_id=account.id, ride_id=ride.id
        )
        db.commit()
    except Exception:
        db.rollback()
        outstanding_penalty = penalty_service.get_outstanding_penalty_total(
            customer_id=account.id
        )
    response_body = success_envelope(
        _ride_data(ride, quote, outstanding_penalty=outstanding_penalty),
        request_id=request_id,
    )
    store.complete(reservation, status_code=201, body=response_body)
    db.commit()

    return JSONResponse(status_code=201, content=response_body)


def _post_acceptance_cancellation_charge(
    *,
    ride: Ride,
    customer_id: uuid.UUID,
    now: datetime,
    wallet_service: WalletService,
    penalty_service: PenaltyService,
    db: DbSession,
) -> dict[str, object]:
    """Phase 3 / Task 3.5 (ADR-0015). Refunds the driver's platform fee
    (BR-046 — always, regardless of grace/qualifying status) and, only
    outside the 2-minute grace period, records the customer's
    qualifying-cancellation penalty (BR-047/048). Called from inside
    cancel_ride()'s single atomic transaction — see this module's
    docstring."""
    assert ride.driver_id is not None  # guaranteed for ACCEPTED/ARRIVED

    original_fee = wallet_service.get_debit_for_ride(
        ride_id=ride.id, transaction_type="PLATFORM_FEE"
    )
    if original_fee is not None:
        wallet_service.credit(
            driver_id=ride.driver_id,
            amount=original_fee.amount,
            transaction_type="FEE_REVERSAL",
            ride_id=ride.id,
            idempotency_key=f"ride:{ride.id}:platform-fee-reversal",
            now=now,
            reference_type="wallet_transaction",
            reference_id=original_fee.id,
        )
        # event-contracts.md §56: producer "Wallet", partition key =
        # driver_id (§7).
        OutboxStore(db).append(
            new_envelope(
                event_type="wallet.credited",
                producer="wallet-service",
                aggregate_type="wallet",
                aggregate_id=ride.driver_id,
                data={
                    "driver_id": str(ride.driver_id),
                    "ride_id": str(ride.id),
                    "amount": float(original_fee.amount),
                    "transaction_type": "FEE_REVERSAL",
                },
                now=now,
            )
        )

    within_grace = (
        ride.accepted_at is not None
        and (now - ride.accepted_at) <= _CANCELLATION_GRACE_PERIOD
    )
    if within_grace:
        # ADR-0015 Decision 1: no penalty.penalties row for a
        # grace-period cancellation — it doesn't count toward the
        # qualifying-cancellation history either.
        return {"amount": 0, "currency": "INR"}

    penalty = penalty_service.record_customer_cancellation(
        customer_id=customer_id, ride_id=ride.id, now=now
    )
    if penalty.amount > 0:
        # state-machines.md §12: "Event: penalty.applied, only when a
        # penalty actually exists" — read as governing *publication*,
        # not row creation (ADR-0015 §3): the ₹0 first-qualifying case
        # still gets a penalty.penalties row (to make "second+" provable
        # later) but no event, since ₹0 is not really a penalty from an
        # outside observer's perspective.
        OutboxStore(db).append(
            new_envelope(
                event_type="penalty.applied",
                producer="penalty-service",
                aggregate_type="penalty",
                aggregate_id=penalty.id,
                data={
                    "penalty_id": str(penalty.id),
                    "user_id": str(penalty.user_id),
                    "ride_id": str(ride.id),
                    "amount": float(penalty.amount),
                    "penalty_type": penalty.penalty_type.value,
                },
                now=now,
            )
        )
    return {
        "amount": float(penalty.amount),
        "currency": "INR",
        # No "expires_at" — removed 2026-09-04 (BR-049 correction,
        # ADR-0069): customer penalties never expire, so `Penalty` no
        # longer has this field at all.
        # ADR-0029 Decision 3 — the customer's own reference for a future
        # dispute filed via POST /api/v1/support/cases (category:
        # "PENALTY_DISPUTE"). Present whenever this branch runs (a real
        # penalty.penalties row always exists here, even the ₹0
        # first-qualifying case — ADR-0015 Decision 2); absent only for
        # the grace-period/SEARCHING cases above, which never create one.
        "penalty_id": str(penalty.id),
    }


def _scheduled_ride_cancellation_charge(
    *,
    ride: Ride,
    customer_id: uuid.UUID,
    now: datetime,
    penalty_service: PenaltyService,
    db: DbSession,
) -> dict[str, object]:
    """ADR-0057, BR-135 — a SCHEDULED ride cancelled before its
    lock_in_at was reached (no driver was ever assigned, so unlike
    _post_acceptance_cancellation_charge() above there is no platform
    fee to refund). Charged against `scheduled_for`, not `accepted_at`:
    ≥3 hours before → ₹0, no row at all (same "no row for a ₹0 charge"
    treatment ADR-0015 Decision 2 established); <3 hours → ₹30, always
    OUTSTANDING, no "first vs. second+" counter and no strike."""
    assert ride.scheduled_for is not None  # guaranteed for SCHEDULED

    if now <= ride.scheduled_for - _SCHEDULED_RIDE_CANCELLATION_WINDOW:
        return {"amount": 0, "currency": "INR"}

    penalty = penalty_service.record_scheduled_ride_late_cancellation(
        customer_id=customer_id, ride_id=ride.id, now=now
    )
    # state-machines.md §12's "penalty.applied, only when a penalty
    # actually exists" — this branch always has one (₹30, never ₹0), so
    # the event is always published here, unlike the post-acceptance
    # helper's own conditional check.
    OutboxStore(db).append(
        new_envelope(
            event_type="penalty.applied",
            producer="penalty-service",
            aggregate_type="penalty",
            aggregate_id=penalty.id,
            data={
                "penalty_id": str(penalty.id),
                "user_id": str(penalty.user_id),
                "ride_id": str(ride.id),
                "amount": float(penalty.amount),
                "penalty_type": penalty.penalty_type.value,
            },
            now=now,
        )
    )
    return {
        "amount": float(penalty.amount),
        "currency": "INR",
        # No "expires_at" — see _post_acceptance_cancellation_charge()'s
        # own comment above.
        "penalty_id": str(penalty.id),
    }


@router.post("/{ride_id}/cancel")
async def cancel_ride(
    ride_id: uuid.UUID,
    body: CancelRideBody,
    account: Annotated[Account, Depends(require_customer)],
    db: Annotated[DbSession, Depends(get_db)],
    redis_client: Annotated[Redis, Depends(get_redis)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
    matching_service: Annotated[MatchingService, Depends(get_matching_service)],
    wallet_service: Annotated[WalletService, Depends(get_wallet_service)],
    penalty_service: Annotated[PenaltyService, Depends(get_penalty_service)],
    promotion_service: Annotated[PromotionService, Depends(get_promotion_service)],
) -> JSONResponse:
    request_id = new_request_id()

    try:
        await RateLimiter(redis_client).check_and_increment(
            key=rate_limit_key(category="ride_cancel", identity=str(account.id)),
            limit=settings.RATE_LIMIT_RIDE_CANCEL_PER_HOUR,
            window_seconds=3600,
        )
    except RateLimitedError as exc:
        return JSONResponse(
            status_code=429,
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    now = datetime.now(UTC)
    charge: dict[str, object] | None = None

    try:
        ride, previous_status = ride_service.cancel_ride(
            ride_id=ride_id, customer_id=account.id, reason=body.reason, now=now
        )
        if previous_status in (RideStatus.ACCEPTED, RideStatus.ARRIVED):
            charge = _post_acceptance_cancellation_charge(
                ride=ride,
                customer_id=account.id,
                now=now,
                wallet_service=wallet_service,
                penalty_service=penalty_service,
                db=db,
            )
        elif previous_status is RideStatus.SCHEDULED:
            charge = _scheduled_ride_cancellation_charge(
                ride=ride,
                customer_id=account.id,
                now=now,
                penalty_service=penalty_service,
                db=db,
            )
        OutboxStore(db).append(
            new_envelope(
                event_type="ride.cancelled",
                producer="ride-service",
                aggregate_type="ride",
                aggregate_id=ride.id,
                data={
                    "ride_id": str(ride.id),
                    "cancelled_by": "CUSTOMER",
                    "previous_status": previous_status.value,
                    "reason": body.reason,
                },
                now=now,
            )
        )
    except (
        RideDomainError,
        VehicleDomainError,
        WalletDomainError,
        PenaltyDomainError,
    ) as exc:
        # No partial cancellation for the ACCEPTED/ARRIVED path (BR-013-
        # style atomicity — see this module's docstring); for SEARCHING
        # there is nothing beyond the cancellation itself to undo.
        db.rollback()
        return _domain_error_response(exc, request_id)

    # Durable from here on.
    db.commit()

    if previous_status is RideStatus.SEARCHING:
        # Unchanged from Task 3.3 — see this module's docstring for why
        # this one step stays best-effort/separate.
        try:
            matching_service.cancel_pending_offers_for_ride(ride_id=ride.id, now=now)
            db.commit()
        except Exception:
            db.rollback()

    # Customer Outstanding Penalty Settlement (ADR-0066, owner decision
    # 2026-09-03) — this ride will never complete now, so release any
    # penalty it was carrying forward (attached at its own Create Ride)
    # back to unattached-OUTSTANDING, so the customer's next actual ride
    # can attach it instead. Best-effort, same pattern as the matching
    # cleanup above — the cancellation itself is already durable.
    try:
        penalty_service.release_penalties_from_cancelled_ride(ride_id=ride.id)
        db.commit()
    except Exception:
        db.rollback()

    # Promotion consume/restore integration (ADR-0070, Phase 12 item
    # closed 2026-09-04) — this ride will never complete now, so restore
    # any promotion entitlement it reserved at Create Ride (BR-065; see
    # PromotionService.restore_reservation_for_ride()'s own docstring for
    # why every cancellation restores unconditionally rather than
    # inventing BR-065/066's still-TBD early/late boundary). Best-effort,
    # past the point of no return, same pattern as the penalty release
    # immediately above.
    try:
        restored = promotion_service.restore_reservation_for_ride(
            ride_id=ride.id, now=now
        )
        if restored is not None:
            OutboxStore(db).append(
                new_envelope(
                    event_type="promotion.restored",
                    producer="promotion-service",
                    aggregate_type="entitlement",
                    aggregate_id=restored.entitlement_id,
                    data={
                        "entitlement_id": str(restored.entitlement_id),
                        "ride_id": str(ride.id),
                        "reason": "RIDE_CANCELLED",
                    },
                    now=now,
                )
            )
        db.commit()
    except Exception:
        db.rollback()

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {"ride_status": ride.status.value, "charge": charge},
            request_id=request_id,
        ),
    )


@router.post("/{ride_id}/driver-cancel")
async def driver_cancel_ride(
    ride_id: uuid.UUID,
    body: CancelRideBody,
    account: Annotated[Account, Depends(require_driver)],
    db: Annotated[DbSession, Depends(get_db)],
    redis_client: Annotated[Redis, Depends(get_redis)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
    wallet_service: Annotated[WalletService, Depends(get_wallet_service)],
    penalty_service: Annotated[PenaltyService, Depends(get_penalty_service)],
    promotion_service: Annotated[PromotionService, Depends(get_promotion_service)],
) -> JSONResponse:
    """Phase 3 / Task 3.6 (ADR-0016). See this module's docstring for
    scope (BR-070's automatic rematch is explicitly not implemented)."""
    request_id = new_request_id()

    try:
        await RateLimiter(redis_client).check_and_increment(
            key=rate_limit_key(category="ride_cancel", identity=str(account.id)),
            limit=settings.RATE_LIMIT_RIDE_CANCEL_PER_HOUR,
            window_seconds=3600,
        )
    except RateLimitedError as exc:
        return JSONResponse(
            status_code=429,
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    now = datetime.now(UTC)

    try:
        ride = ride_service.driver_cancel_ride(
            ride_id=ride_id, driver_id=account.id, reason=body.reason, now=now
        )
        if body.reason != _CHANGED_PICKUP_PASS_REASON:
            # Sarthi Unpaid Cancellation-Penalty Recovery (ADR-0062,
            # 2026-09-03, owner decision) — debit_or_record_as_debt(),
            # not plain debit(): a driver whose balance can't cover this
            # penalty must still be allowed to cancel (the ride-status
            # transition and strike below are never blocked by this),
            # with the unpaid amount tracked as wallet.outstanding_debt
            # and recovered automatically from a future wallet recharge
            # instead. See WalletService.debit_or_record_as_debt()'s own
            # docstring for the full behavior.
            wallet_service.debit_or_record_as_debt(
                driver_id=account.id,
                amount=_DRIVER_CANCELLATION_PENALTY,
                transaction_type="DRIVER_PENALTY",
                ride_id=ride.id,
                idempotency_key=f"ride:{ride.id}:driver-cancellation-penalty",
                now=now,
            )
            OutboxStore(db).append(
                new_envelope(
                    event_type="wallet.debited",
                    producer="wallet-service",
                    aggregate_type="wallet",
                    aggregate_id=account.id,
                    data={
                        "driver_id": str(account.id),
                        "ride_id": str(ride.id),
                        "amount": float(_DRIVER_CANCELLATION_PENALTY),
                        "transaction_type": "DRIVER_PENALTY",
                    },
                    now=now,
                )
            )
            strike = penalty_service.record_driver_strike(
                driver_id=account.id, ride_id=ride.id, reason=body.reason, now=now
            )
            OutboxStore(db).append(
                new_envelope(
                    event_type="penalty.strike_recorded",
                    producer="penalty-service",
                    aggregate_type="strike",
                    aggregate_id=strike.id,
                    data={
                        "strike_id": str(strike.id),
                        "driver_id": str(account.id),
                        "ride_id": str(ride.id),
                        "reason": strike.reason,
                    },
                    now=now,
                )
            )
        OutboxStore(db).append(
            new_envelope(
                event_type="ride.cancelled",
                producer="ride-service",
                aggregate_type="ride",
                aggregate_id=ride.id,
                data={
                    "ride_id": str(ride.id),
                    "cancelled_by": "DRIVER",
                    "previous_status": "ACCEPTED",
                    "reason": body.reason,
                },
                now=now,
            )
        )
    except (RideDomainError, WalletDomainError, PenaltyDomainError) as exc:
        db.rollback()
        return _domain_error_response(exc, request_id)

    db.commit()

    # Customer Outstanding Penalty Settlement (ADR-0066, owner decision
    # 2026-09-03) — same reasoning as cancel_ride() above: this ride
    # will never complete now, so release any penalty it was carrying
    # forward back to unattached-OUTSTANDING for a future ride to pick
    # up. Best-effort, past the point of no return.
    try:
        penalty_service.release_penalties_from_cancelled_ride(ride_id=ride.id)
        db.commit()
    except Exception:
        db.rollback()

    # Promotion consume/restore integration (ADR-0070, Phase 12 item
    # closed 2026-09-04) — same reasoning as cancel_ride() above: restore
    # any promotion this ride reserved at Create Ride. Best-effort, past
    # the point of no return.
    try:
        restored = promotion_service.restore_reservation_for_ride(
            ride_id=ride.id, now=now
        )
        if restored is not None:
            OutboxStore(db).append(
                new_envelope(
                    event_type="promotion.restored",
                    producer="promotion-service",
                    aggregate_type="entitlement",
                    aggregate_id=restored.entitlement_id,
                    data={
                        "entitlement_id": str(restored.entitlement_id),
                        "ride_id": str(ride.id),
                        "reason": "RIDE_CANCELLED",
                    },
                    now=now,
                )
            )
        db.commit()
    except Exception:
        db.rollback()

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {"ride_status": ride.status.value}, request_id=request_id
        ),
    )


@router.get("/{ride_id}")
async def get_ride_status(
    ride_id: uuid.UUID,
    account: Annotated[Account, Depends(require_customer_or_driver)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
    vehicle_service: Annotated[VehicleService, Depends(get_vehicle_service)],
    pricing_service: Annotated[PricingService, Depends(get_pricing_service)],
) -> JSONResponse:
    """Get Ride (api-contracts.md §13, ADR-0024). "Customer may access
    their own ride. Driver may access rides assigned to them." — same
    response for missing and unauthorized (IDOR-safe), matching every
    other ownership check in this codebase."""
    request_id = new_request_id()
    try:
        ride = ride_service.get_ride(ride_id=ride_id)
        is_owner = ride is not None and (
            (
                account.account_type is AccountType.CUSTOMER
                and ride.customer_id == account.id
            )
            or (
                account.account_type is AccountType.DRIVER
                and ride.driver_id == account.id
            )
        )
        if not is_owner:
            raise RideNotFoundError("Ride not found.")
        assert ride is not None  # narrowed by is_owner above

        quote = (
            pricing_service.get_fare_quote(fare_quote_id=ride.active_fare_quote_id)
            if ride.active_fare_quote_id is not None
            else None
        )
        driver = (
            driver_service.get_profile(account_id=ride.driver_id)
            if ride.driver_id is not None
            else None
        )
        vehicle = (
            vehicle_service.get_vehicle(
                driver_id=ride.driver_id, vehicle_id=ride.vehicle_id
            )
            if ride.driver_id is not None and ride.vehicle_id is not None
            else None
        )
    except (
        RideDomainError,
        DriverDomainError,
        VehicleDomainError,
        PricingDomainError,
    ) as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            _ride_status_data(ride, quote, driver, vehicle), request_id=request_id
        ),
    )


@router.post("/{ride_id}/arrived")
async def mark_arrived(
    ride_id: uuid.UUID,
    body: GpsVerificationBody,
    account: Annotated[Account, Depends(require_driver)],
    db: Annotated[DbSession, Depends(get_db)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
    notification_service: Annotated[
        NotificationService, Depends(get_notification_service)
    ],
) -> JSONResponse:
    """Driver Arrival (api-contracts.md §17, ADR-0028). Driver-only,
    ownership-checked inside RideService.mark_arrived(). A PASS also
    auto-issues the ride-start OTP (discarded here — see the service
    method's own docstring for why)."""
    request_id = new_request_id()
    now = datetime.now(UTC)

    try:
        ride, verification = ride_service.mark_arrived(
            ride_id=ride_id,
            driver_id=account.id,
            latitude=body.latitude,
            longitude=body.longitude,
            radius_meters=settings.RIDE_ARRIVAL_GPS_RADIUS_METERS,
            max_attempts_before_review=settings.RIDE_GPS_MAX_ATTEMPTS_BEFORE_REVIEW,
            dispute_evidence_window_seconds=(
                settings.RIDE_GPS_DISPUTE_EVIDENCE_WINDOW_SECONDS
            ),
            otp_expiry_seconds=settings.RIDE_OTP_EXPIRY_SECONDS,
            otp_hash_pepper=settings.RIDE_OTP_HASH_SECRET,
            now=now,
        )
    except RideDomainError as exc:
        # Deliberately NOT db.rollback(): mark_arrived() writes the
        # ride.gps_verifications row for THIS attempt (pass or fail)
        # before ever raising (its own "audit-trail-first design" —
        # see the service method's docstring) — a FAIL still needs that
        # row committed, or the next attempt's already_failed count
        # would never see it and the 3-strikes-before-manual-review
        # logic (ADR-0028 Decision 1) would never trigger. The
        # not-found/wrong-state checks that raise before any write
        # commit a harmless no-op transaction here, same as
        # get_ride_status()'s equivalent branch.
        _publish_gps_dispute_opened_if_any(
            db,
            exc,
            ride_service=ride_service,
            ride_id=ride_id,
            driver_id=account.id,
            now=now,
        )
        db.commit()
        return _domain_error_response(exc, request_id)

    # event-contracts.md §10.3 — exact documented payload shape.
    OutboxStore(db).append(
        new_envelope(
            event_type="ride.arrived",
            producer="ride-service",
            aggregate_type="ride",
            aggregate_id=ride.id,
            data={
                "ride_id": str(ride.id),
                "driver_id": str(ride.driver_id),
                "arrived_at": ride.arrived_at.isoformat() if ride.arrived_at else None,
                "gps_verified": True,
            },
            now=now,
        )
    )
    db.commit()

    # ADR-0034 — best-effort, same pattern used throughout this
    # codebase for secondary steps that must never affect the primary
    # response: a notification failure must not roll back the already-
    # committed arrival (domain-design.md §20.4).
    try:
        await notification_service.send(
            user_id=ride.customer_id,
            channel=Channel.IN_APP,
            template_key="RIDE_ARRIVED",
            recipient=None,
            event_id=None,
            now=now,
        )
        db.commit()
    except Exception:
        db.rollback()

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "status": ride.status.value,
                "waiting_started_at": (
                    ride.arrived_at.isoformat() if ride.arrived_at else None
                ),
            },
            request_id=request_id,
        ),
    )


@router.post("/{ride_id}/otp/refresh")
async def refresh_ride_otp(
    ride_id: uuid.UUID,
    account: Annotated[Account, Depends(require_customer)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
    sms_provider: Annotated[SmsProvider, Depends(get_sms_provider_dependency)],
) -> JSONResponse:
    """Generate/Refresh OTP (api-contracts.md §18, ADR-0028). Customer-
    only — see RideService.refresh_otp()'s docstring for why this is the
    ONLY endpoint that ever returns the plaintext OTP; no request body
    (nothing to submit, only a fresh code to receive).

    ADR-0057, BR-139 (Book for Someone Else): when this ride has a
    `linked_contact_phone`, the same plaintext is also sent to it by SMS
    (modules.identity.sms's already-built send_otp() adapter, composed
    here for the first time — every prior ride-start OTP use was
    reveal-in-app only, api-contracts.md §18's own "no notification
    channel exists" note predates SMS/MSG91 being wired at all,
    ADR-0031). Best-effort: a delivery failure never fails this request
    — the booker already has the code in the response body either
    way — same "external send, don't let it block a successful domain
    outcome" treatment every other best-effort SMS/notification call in
    this codebase gets."""
    request_id = new_request_id()
    now = datetime.now(UTC)

    try:
        _otp, plaintext = ride_service.refresh_otp(
            ride_id=ride_id,
            customer_id=account.id,
            otp_expiry_seconds=settings.RIDE_OTP_EXPIRY_SECONDS,
            otp_hash_pepper=settings.RIDE_OTP_HASH_SECRET,
            now=now,
        )
    except RideDomainError as exc:
        return _domain_error_response(exc, request_id)

    ride = ride_service.get_ride(ride_id=ride_id)
    if ride is not None and ride.linked_contact_phone is not None:
        try:
            await sms_provider.send_otp(ride.linked_contact_phone, plaintext)
        except Exception:
            pass

    return JSONResponse(
        status_code=200,
        content=success_envelope({"otp": plaintext}, request_id=request_id),
    )


@router.post("/{ride_id}/start")
async def start_ride(
    ride_id: uuid.UUID,
    body: StartRideBody,
    account: Annotated[Account, Depends(require_driver)],
    db: Annotated[DbSession, Depends(get_db)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
) -> JSONResponse:
    """Start Ride (api-contracts.md §18, ADR-0028). Driver-only,
    ownership-checked inside RideService.start_ride()."""
    request_id = new_request_id()
    now = datetime.now(UTC)

    try:
        ride = ride_service.start_ride(
            ride_id=ride_id,
            driver_id=account.id,
            otp=body.otp,
            max_attempts=settings.RIDE_OTP_MAX_ATTEMPTS,
            otp_hash_pepper=settings.RIDE_OTP_HASH_SECRET,
            now=now,
        )
    except RideDomainError as exc:
        # Deliberately NOT db.rollback(): a wrong/expired OTP still
        # writes its consequence before raising — start_ride() saves
        # active_otp with status=EXPIRED (expired case) or
        # attempts += 1 (wrong-code case) before ever raising
        # RideOtpExpiredError/RideOtpInvalidError — losing that write
        # would let the same expired code be retried forever, or reset
        # the attempt counter on every wrong guess, defeating
        # RIDE_OTP_MAX_ATTEMPTS entirely. The not-found/wrong-state/
        # no-active-OTP/max-attempts checks that raise before any write
        # commit a harmless no-op transaction here.
        db.commit()
        return _domain_error_response(exc, request_id)

    # event-contracts.md §10.4 — exact documented payload shape.
    OutboxStore(db).append(
        new_envelope(
            event_type="ride.started",
            producer="ride-service",
            aggregate_type="ride",
            aggregate_id=ride.id,
            data={
                "ride_id": str(ride.id),
                "driver_id": str(ride.driver_id),
                "started_at": ride.started_at.isoformat() if ride.started_at else None,
            },
            now=now,
        )
    )
    db.commit()

    return JSONResponse(
        status_code=200,
        content=success_envelope({"status": ride.status.value}, request_id=request_id),
    )


@router.post("/{ride_id}/complete")
async def complete_ride(
    ride_id: uuid.UUID,
    body: GpsVerificationBody,
    account: Annotated[Account, Depends(require_driver)],
    db: Annotated[DbSession, Depends(get_db)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
    wallet_service: Annotated[WalletService, Depends(get_wallet_service)],
    penalty_service: Annotated[PenaltyService, Depends(get_penalty_service)],
    promotion_service: Annotated[PromotionService, Depends(get_promotion_service)],
    pricing_service: Annotated[PricingService, Depends(get_pricing_service)],
) -> JSONResponse:
    """Ride Completion (api-contracts.md §28, ADR-0028). Driver-only,
    ownership-checked inside RideService.complete_ride(). Transitions
    STARTED -> COMPLETED -> CLOSED in the same request (ADR-0028
    Decision 3: CLOSED is automatic/immediate, no separate trigger).

    Customer Outstanding Penalty Settlement (ADR-0066, owner decision
    2026-09-03): also settles any penalty this ride was carrying
    forward — "the User pays the Sarthi directly" for fare-plus-penalty
    combined, and VISTAAR recovers its own share via the Sarthi's
    wallet, the same "collect from the driver's wallet what the driver
    physically received on VISTAAR's behalf" shape TransactionType.
    CASH_SETTLEMENT was always documented for (database-design.md §17.2
    — dormant since ADR-0025, real again now).

    Promotion consume/restore integration (ADR-0070, Phase 12 item
    closed 2026-09-04): also consumes any promotion this ride reserved
    at Create Ride (BR-066), with `discount_amount` read from the ride's
    own final fare quote (`FareQuote.promotion_discount`) — the same
    amount actually applied, not re-derived."""
    request_id = new_request_id()
    now = datetime.now(UTC)

    try:
        ride, verification = ride_service.complete_ride(
            ride_id=ride_id,
            driver_id=account.id,
            latitude=body.latitude,
            longitude=body.longitude,
            radius_meters=settings.RIDE_COMPLETION_GPS_RADIUS_METERS,
            max_attempts_before_review=settings.RIDE_GPS_MAX_ATTEMPTS_BEFORE_REVIEW,
            dispute_evidence_window_seconds=(
                settings.RIDE_GPS_DISPUTE_EVIDENCE_WINDOW_SECONDS
            ),
            now=now,
        )
    except RideDomainError as exc:
        # Deliberately NOT db.rollback() — same audit-trail-first
        # reasoning as mark_arrived() above: complete_ride() writes the
        # ride.gps_verifications row for this attempt before ever
        # raising, and that row must survive a FAIL response so the
        # next attempt's already_failed count is correct.
        _publish_gps_dispute_opened_if_any(
            db,
            exc,
            ride_service=ride_service,
            ride_id=ride_id,
            driver_id=account.id,
            now=now,
        )
        db.commit()
        return _domain_error_response(exc, request_id)

    # event-contracts.md §10.8 — exact documented payload shape.
    # customer_id/vehicle_id/final_fare_quote_id/completion_location are
    # all already on hand from `ride` — no extra lookups needed.
    OutboxStore(db).append(
        new_envelope(
            event_type="ride.completed",
            producer="ride-service",
            aggregate_type="ride",
            aggregate_id=ride.id,
            data={
                "ride_id": str(ride.id),
                "customer_id": str(ride.customer_id),
                "driver_id": str(ride.driver_id),
                "vehicle_id": str(ride.vehicle_id) if ride.vehicle_id else None,
                "final_fare_quote_id": (
                    str(ride.active_fare_quote_id)
                    if ride.active_fare_quote_id
                    else None
                ),
                "completion_location": {
                    "latitude": body.latitude,
                    "longitude": body.longitude,
                },
                "gps_verified": True,
                "completed_at": (
                    ride.completed_at.isoformat() if ride.completed_at else None
                ),
            },
            now=now,
        )
    )
    db.commit()

    # Customer Outstanding Penalty Settlement (ADR-0066, owner decision
    # 2026-09-03) — best-effort, past the point of no return: the ride
    # itself is already durably COMPLETED above, and a failure settling
    # a carried-forward penalty must never turn a successful completion
    # into an error response to the driver. Settlement + the wallet
    # debit that pays VISTAAR back happen together in one transaction —
    # unlike the driver-cancellation-penalty debit (ADR-0062), this is
    # never something a client retries, so no separate outer
    # idempotency concern beyond debit_or_record_as_debt()'s own
    # idempotency-key guard.
    settled_amount: Decimal = Decimal("0")
    try:
        settled_amount = penalty_service.settle_penalties_for_completed_ride(
            ride_id=ride.id, now=now
        )
        if settled_amount > 0:
            assert ride.driver_id is not None  # guaranteed once COMPLETED
            wallet_service.debit_or_record_as_debt(
                driver_id=ride.driver_id,
                amount=settled_amount,
                transaction_type="CASH_SETTLEMENT",
                ride_id=ride.id,
                idempotency_key=f"ride:{ride.id}:customer-penalty-settlement",
                now=now,
            )
            OutboxStore(db).append(
                new_envelope(
                    event_type="wallet.debited",
                    producer="wallet-service",
                    aggregate_type="wallet",
                    aggregate_id=ride.driver_id,
                    data={
                        "driver_id": str(ride.driver_id),
                        "ride_id": str(ride.id),
                        "amount": float(settled_amount),
                        "transaction_type": "CASH_SETTLEMENT",
                    },
                    now=now,
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        settled_amount = Decimal("0")

    # Promotion consume/restore integration (ADR-0070, Phase 12 item
    # closed 2026-09-04) — best-effort, past the point of no return, same
    # reasoning as the penalty settlement immediately above: consume any
    # promotion this ride reserved at Create Ride, using the actual
    # discount applied on the ride's own final fare quote. A no-op for
    # the common case of a ride with no reservation (most rides never
    # had a promotion applied) — see
    # PromotionService.consume_reservation_for_ride()'s own docstring.
    try:
        quote = (
            pricing_service.get_fare_quote(fare_quote_id=ride.active_fare_quote_id)
            if ride.active_fare_quote_id is not None
            else None
        )
        if quote is not None:
            consumed = promotion_service.consume_reservation_for_ride(
                ride_id=ride.id, discount_amount=quote.promotion_discount, now=now
            )
            if consumed is not None:
                OutboxStore(db).append(
                    new_envelope(
                        event_type="promotion.consumed",
                        producer="promotion-service",
                        aggregate_type="entitlement",
                        aggregate_id=consumed.entitlement_id,
                        data={
                            "entitlement_id": str(consumed.entitlement_id),
                            "ride_id": str(ride.id),
                            "discount_amount": float(consumed.discount_amount),
                        },
                        now=now,
                    )
                )
        db.commit()
    except Exception:
        db.rollback()

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "status": ride.status.value,
                "customer_penalty_settled": (
                    float(settled_amount) if settled_amount > 0 else None
                ),
            },
            request_id=request_id,
        ),
    )


@router.post("/{ride_id}/early-drop")
async def request_early_drop(
    ride_id: uuid.UUID,
    body: RequestEarlyDropBody,
    account: Annotated[Account, Depends(require_customer)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
) -> JSONResponse:
    """Request Early Drop (api-contracts.md §27, ADR-0030). Customer-
    only (BR-088: "Customer requests early drop"). No write happens
    before any possible domain error here, so a caught one needs no
    explicit rollback — get_db's default handles it, same as
    get_ride_status()."""
    request_id = new_request_id()
    now = datetime.now(UTC)

    try:
        ride_service.request_early_drop(
            ride_id=ride_id, customer_id=account.id, reason=body.reason, now=now
        )
    except RideDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=201,
        content=success_envelope({"status": "REQUESTED"}, request_id=request_id),
    )


@router.post("/{ride_id}/early-drop/confirm")
async def confirm_early_drop(
    ride_id: uuid.UUID,
    body: ConfirmEarlyDropBody,
    account: Annotated[Account, Depends(require_customer_or_driver)],
    db: Annotated[DbSession, Depends(get_db)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
) -> JSONResponse:
    """Confirm Early Drop (api-contracts.md §27, ADR-0030). Customer-or-
    driver, ownership-checked inside RideService.confirm_early_drop().
    `confirmed: false` rejects/discards the pending request — no write
    happens before any possible domain error here either, so a caught
    one needs no explicit rollback."""
    request_id = new_request_id()
    now = datetime.now(UTC)

    try:
        ride, request = ride_service.confirm_early_drop(
            ride_id=ride_id,
            account_id=account.id,
            confirmed=body.confirmed,
            latitude=body.latitude,
            longitude=body.longitude,
            now=now,
        )
    except RideDomainError as exc:
        return _domain_error_response(exc, request_id)

    if ride is None:
        # Either rejected (confirmed: false) or only this caller's own
        # side is confirmed so far — the other party still needs to call
        # this same endpoint.
        return JSONResponse(
            status_code=200,
            content=success_envelope(
                {"status": "PENDING" if body.confirmed else "REJECTED"},
                request_id=request_id,
            ),
        )

    # event-contracts.md §10.7 — exact documented payload shape.
    OutboxStore(db).append(
        new_envelope(
            event_type="ride.early_drop_confirmed",
            producer="ride-service",
            aggregate_type="ride",
            aggregate_id=ride.id,
            data={
                "ride_id": str(ride.id),
                "customer_id": str(ride.customer_id),
                "driver_id": str(ride.driver_id),
                "gps_location": (
                    {
                        "latitude": request.gps_location.latitude,
                        "longitude": request.gps_location.longitude,
                    }
                    if request.gps_location is not None
                    else None
                ),
                "customer_confirmed": request.customer_confirmed,
                "driver_confirmed": request.driver_confirmed,
                "timestamp": now.isoformat(),
            },
            now=now,
        )
    )
    db.commit()

    return JSONResponse(
        status_code=200,
        content=success_envelope({"status": ride.status.value}, request_id=request_id),
    )


@router.post("/{ride_id}/pickup-change")
async def request_pickup_change(
    ride_id: uuid.UUID,
    body: RequestPickupChangeBody,
    account: Annotated[Account, Depends(require_customer)],
    redis_client: Annotated[Redis, Depends(get_redis)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
) -> JSONResponse:
    """Pickup Change (api-contracts.md §22, ADR-0033; simplified by
    ADR-0056, 2026-08-31 — owner decision). Customer-only (BR-072). A
    ≤threshold change (BR-073, now 100m) is applied immediately —
    `applied: true`. A >threshold change (BR-074) is now rejected
    outright (`PICKUP_CHANGE_TOO_FAR`) — no driver decision exists
    anymore; the customer must cancel this ride and book a new one
    instead. No write happens before any possible domain error here, so
    a caught one needs no explicit rollback."""
    request_id = new_request_id()

    try:
        await RateLimiter(redis_client).check_and_increment(
            key=rate_limit_key(category="fare_change", identity=str(account.id)),
            limit=settings.RATE_LIMIT_FARE_CHANGE_PER_HOUR,
            window_seconds=3600,
        )
    except RateLimitedError as exc:
        return JSONResponse(
            status_code=429,
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    now = datetime.now(UTC)

    try:
        _ride, distance_meters = ride_service.request_pickup_change(
            ride_id=ride_id,
            customer_id=account.id,
            latitude=body.latitude,
            longitude=body.longitude,
            threshold_meters=settings.RIDE_PICKUP_CHANGE_THRESHOLD_METERS,
            now=now,
        )
    except RideDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {"applied": True, "distance_meters": distance_meters},
            request_id=request_id,
        ),
    )


@router.post("/{ride_id}/destination-change")
async def request_destination_change(
    ride_id: uuid.UUID,
    body: RequestDestinationChangeBody,
    account: Annotated[Account, Depends(require_customer)],
    redis_client: Annotated[Redis, Depends(get_redis)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
    pricing_service: Annotated[PricingService, Depends(get_pricing_service)],
) -> JSONResponse:
    """Destination Change (api-contracts.md §25, ADR-0033 Decision 9).
    Customer-only (BR-079/080/081), STARTED-only. Composes PricingService.
    calculate_destination_change_fare() (which classifies the case and,
    for BEYOND_ORIGINAL/DIFFERENT_ROUTE, computes the quote) before
    calling RideService.apply_destination_change() — quote-then-decide,
    the same order ride creation itself uses for its own initial quote
    (ADR-0020). A WITHIN_ROUTE change is applied immediately
    (`applied: true`); the other two cases create a pending request the
    customer must confirm (`applied: false`) — no driver-decision step
    exists for destination change anywhere in the documented flow (and,
    as of ADR-0056, none exists for pickup change anymore either — see
    that endpoint's own docstring)."""
    request_id = new_request_id()

    try:
        await RateLimiter(redis_client).check_and_increment(
            key=rate_limit_key(category="fare_change", identity=str(account.id)),
            limit=settings.RATE_LIMIT_FARE_CHANGE_PER_HOUR,
            window_seconds=3600,
        )
    except RateLimitedError as exc:
        return JSONResponse(
            status_code=429,
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    now = datetime.now(UTC)

    try:
        ride = ride_service.get_ride_for_destination_change(
            ride_id=ride_id, customer_id=account.id
        )
        quote, case = pricing_service.calculate_destination_change_fare(
            ride_id=ride_id,
            vehicle_category=ride.requested_vehicle_category.value,
            cab_tier=(
                ride.requested_cab_tier.value
                if ride.requested_cab_tier is not None
                else None
            ),
            original_pickup_latitude=ride.original_pickup.latitude,
            original_pickup_longitude=ride.original_pickup.longitude,
            original_destination_latitude=ride.original_destination.latitude,
            original_destination_longitude=ride.original_destination.longitude,
            new_destination_latitude=body.latitude,
            new_destination_longitude=body.longitude,
            # ADR-0033 Decision 9's documented interpretation of "current
            # location" — no live per-ride GPS tracking exists anywhere
            # in this codebase to read a truer value from.
            current_latitude=ride.current_pickup.latitude,
            current_longitude=ride.current_pickup.longitude,
            route_deviation_threshold_meters=(
                settings.RIDE_DESTINATION_ROUTE_DEVIATION_METERS
            ),
            destination_extension_rate_per_km=Decimal(
                settings.RIDE_DESTINATION_EXTENSION_RATE_PER_KM
            ),
            now=now,
        )
        change_request, _ride_after = ride_service.apply_destination_change(
            ride_id=ride_id,
            customer_id=account.id,
            new_destination_latitude=body.latitude,
            new_destination_longitude=body.longitude,
            case=case.value,
            fare_quote_id=quote.id if quote is not None else None,
            now=now,
        )
    except (RideDomainError, PricingDomainError) as exc:
        return _domain_error_response(exc, request_id)

    if change_request is None:
        return JSONResponse(
            status_code=200,
            content=success_envelope(
                {"applied": True, "case": case.value}, request_id=request_id
            ),
        )

    return JSONResponse(
        status_code=201,
        content=success_envelope(
            {
                "applied": False,
                "case": case.value,
                "change_request_id": str(change_request.id),
                "status": change_request.status.value,
                "requested_at": change_request.created_at.isoformat(),
            },
            request_id=request_id,
        ),
    )


@router.post("/{ride_id}/destination-change/confirm")
async def confirm_destination_change(
    ride_id: uuid.UUID,
    body: ConfirmDestinationChangeBody,
    account: Annotated[Account, Depends(require_customer)],
    db: Annotated[DbSession, Depends(get_db)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
    pricing_service: Annotated[PricingService, Depends(get_pricing_service)],
) -> JSONResponse:
    """Destination Change Confirmation (api-contracts.md §26, BR-082,
    ADR-0033 Decision 9). Customer-only. `change_request_id` (documented
    in the request body, unlike pickup change's confirm) is checked
    against the ride's own currently-pending request as a consistency
    check — RideService.confirm_destination_change() is still ride_id-
    scoped internally (see schemas.py::ConfirmDestinationChangeBody)."""
    request_id = new_request_id()
    now = datetime.now(UTC)

    try:
        change_request, ride, old_destination = ride_service.confirm_destination_change(
            ride_id=ride_id,
            customer_id=account.id,
            confirmed=body.confirmed,
            now=now,
        )
    except RideDomainError as exc:
        return _domain_error_response(exc, request_id)

    if str(change_request.id) != body.change_request_id:
        return JSONResponse(
            status_code=422,
            content=error_envelope(
                "VALIDATION_FAILED",
                "change_request_id does not match the pending request for this ride.",
                request_id=request_id,
            ),
        )

    if not body.confirmed:
        return JSONResponse(
            status_code=200,
            content=success_envelope(
                {"status": "REJECTED", "ride_status": ride.status.value},
                request_id=request_id,
            ),
        )

    assert change_request.new_fare_quote_id is not None
    quote = pricing_service.get_fare_quote(
        fare_quote_id=change_request.new_fare_quote_id
    )
    assert quote is not None
    previous_quote = (
        pricing_service.get_fare_quote(fare_quote_id=change_request.old_fare_quote_id)
        if change_request.old_fare_quote_id is not None
        else None
    )
    previous_total = float(previous_quote.total) if previous_quote is not None else None

    # event-contracts.md §10.6 — exact documented payload shape.
    OutboxStore(db).append(
        new_envelope(
            event_type="ride.destination_changed",
            producer="ride-service",
            aggregate_type="ride",
            aggregate_id=ride.id,
            data={
                "ride_id": str(ride.id),
                "old_destination": {
                    "latitude": old_destination.latitude,
                    "longitude": old_destination.longitude,
                },
                "new_destination": {
                    "latitude": ride.current_destination.latitude,
                    "longitude": ride.current_destination.longitude,
                },
                "fare_revision_id": str(quote.id),
                "additional_charge": float(quote.additional_charge),
                "customer_confirmed": True,
            },
            now=now,
        )
    )
    db.commit()

    # api-contracts.md §26's exact documented response shape.
    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "fare": {
                    "previous_total": previous_total,
                    "additional_charge": float(quote.additional_charge),
                    "new_total": float(quote.total),
                    "currency": "INR",
                },
                "status": "CONFIRMED",
                "ride_status": ride.status.value,
            },
            request_id=request_id,
        ),
    )


def _gps_dispute_data(
    dispute: GpsDispute, evidence: list[GpsDisputeEvidence]
) -> dict[str, object]:
    return {
        "dispute_id": str(dispute.id),
        "ride_id": str(dispute.ride_id),
        "gps_verification_id": str(dispute.gps_verification_id),
        "verification_type": dispute.verification_type.value,
        "opened_at": dispute.opened_at.isoformat(),
        "evidence_deadline": dispute.evidence_deadline.isoformat(),
        "status": dispute.status.value,
        "decision": dispute.decision.value if dispute.decision else None,
        "decided_by": str(dispute.decided_by) if dispute.decided_by else None,
        "decided_reason": dispute.decided_reason,
        "decided_at": dispute.decided_at.isoformat() if dispute.decided_at else None,
        "evidence": [
            {
                "submitted_by": str(e.submitted_by),
                "evidence_type": e.evidence_type.value,
                "uri": e.uri,
                "text_explanation": e.text_explanation,
                "submitted_at": e.submitted_at.isoformat(),
            }
            for e in evidence
        ],
    }


@router.get("/{ride_id}/gps-disputes")
async def list_gps_disputes(
    ride_id: uuid.UUID,
    account: Annotated[Account, Depends(require_customer_or_driver)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
) -> JSONResponse:
    """List GPS Disputes for a Ride (ADR-0074, 2026-09-04) — the
    discovery endpoint a customer needs, since (unlike the driver, who
    receives a dispute_id directly in the GPS_VERIFICATION_FAILED error
    that opened it) nothing else tells a customer a dispute exists on
    their ride. Not paginated — a ride has at most two GPS
    verifications (pickup, destination) and therefore at most two
    disputes ever."""
    request_id = new_request_id()
    now = datetime.now(UTC)
    try:
        disputes = ride_service.list_gps_disputes_for_ride(
            ride_id=ride_id, account_id=account.id, is_admin=False, now=now
        )
    except RideDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "disputes": [
                    _gps_dispute_data(dispute, list(evidence))
                    for dispute, evidence in disputes
                ]
            },
            request_id=request_id,
        ),
    )


@router.get("/{ride_id}/gps-disputes/{dispute_id}")
async def get_gps_dispute(
    ride_id: uuid.UUID,
    dispute_id: uuid.UUID,
    account: Annotated[Account, Depends(require_customer_or_driver)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
) -> JSONResponse:
    """Get Dispute (api-contracts.md §77, ADR-0032). Customer/driver, own
    ride only — the admin-facing view is composed separately at
    modules/admin/router.py (still the same RideService.get_gps_dispute(),
    just with is_admin=True)."""
    request_id = new_request_id()
    now = datetime.now(UTC)
    try:
        dispute, evidence = ride_service.get_gps_dispute(
            dispute_id=dispute_id, account_id=account.id, is_admin=False, now=now
        )
        if dispute.ride_id != ride_id:
            raise RideNotFoundError("Ride not found.")
    except RideDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            _gps_dispute_data(dispute, list(evidence)), request_id=request_id
        ),
    )


@router.post("/{ride_id}/gps-disputes/{dispute_id}/evidence/upload-url")
async def request_gps_dispute_evidence_upload_url(
    ride_id: uuid.UUID,
    dispute_id: uuid.UUID,
    body: GpsDisputeEvidenceUploadUrlBody,
    account: Annotated[Account, Depends(require_customer_or_driver)],
    redis_client: Annotated[Redis, Depends(get_redis)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
    storage: Annotated[ObjectStorage, Depends(get_gps_dispute_object_storage)],
) -> JSONResponse:
    """ADR-0031/ADR-0032; presigned POST since 2026-09-03 (owner
    decision — see shared/storage.py's own docstring). Customer/driver,
    own ride — ownership is checked via a Get Dispute call rather than
    duplicating the check inline, so this endpoint and get_gps_dispute()
    can never drift on what "owns this dispute" means. Returns a
    presigned S3 POST target (URL + form fields), not a single PUT URL —
    see modules/driver/router.py's request_upload_url() for the same
    shape."""
    request_id = new_request_id()

    try:
        await RateLimiter(redis_client).check_and_increment(
            key=rate_limit_key(category="evidence_upload", identity=str(account.id)),
            limit=settings.RATE_LIMIT_EVIDENCE_UPLOAD_PER_HOUR,
            window_seconds=3600,
        )
    except RateLimitedError as exc:
        return JSONResponse(
            status_code=429,
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    now = datetime.now(UTC)
    try:
        dispute, _evidence = ride_service.get_gps_dispute(
            dispute_id=dispute_id, account_id=account.id, is_admin=False, now=now
        )
        if dispute.ride_id != ride_id:
            raise RideNotFoundError("Ride not found.")
        target = storage.create_upload_url(content_type=body.content_type)
    except (RideDomainError, UnsupportedContentTypeError) as exc:
        return JSONResponse(
            status_code=http_status_for_error_code(exc.code),
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "upload_url": target.upload_url,
                "upload_fields": target.upload_fields,
                "uri": target.object_uri,
                "expires_at": target.expires_at.isoformat(),
            },
            request_id=request_id,
        ),
    )


@router.post("/{ride_id}/gps-disputes/{dispute_id}/evidence")
async def submit_gps_dispute_evidence(
    ride_id: uuid.UUID,
    dispute_id: uuid.UUID,
    body: SubmitGpsDisputeEvidenceBody,
    account: Annotated[Account, Depends(require_customer_or_driver)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
) -> JSONResponse:
    """Submit Evidence (api-contracts.md §77, BR-125, ADR-0032). Checks
    ride_id/dispute_id consistency and ownership via a Get Dispute call
    first (same pattern as the upload-url endpoint above) before
    submitting — RideService.submit_gps_dispute_evidence() itself also
    re-validates ownership independently (via the dispute's own
    ride_id), so this is belt-and-suspenders, not the only check. No
    write happens before any possible domain error here, so a caught one
    needs no explicit rollback — get_db's default handles it."""
    request_id = new_request_id()
    now = datetime.now(UTC)

    try:
        dispute, _evidence = ride_service.get_gps_dispute(
            dispute_id=dispute_id, account_id=account.id, is_admin=False, now=now
        )
        if dispute.ride_id != ride_id:
            raise RideNotFoundError("Ride not found.")
        evidence = ride_service.submit_gps_dispute_evidence(
            dispute_id=dispute_id,
            account_id=account.id,
            evidence_type=body.evidence_type,
            uri=body.uri,
            text=body.text,
            now=now,
        )
    except RideDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=201,
        content=success_envelope(
            {
                "submitted_by": str(evidence.submitted_by),
                "evidence_type": evidence.evidence_type.value,
                "uri": evidence.uri,
                "text_explanation": evidence.text_explanation,
                "submitted_at": evidence.submitted_at.isoformat(),
            },
            request_id=request_id,
        ),
    )
