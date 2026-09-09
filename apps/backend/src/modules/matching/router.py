"""FastAPI routes for Matching.

Two routers, different URL prefixes (api-contracts.md §15, §16):

    location_router  POST /api/v1/drivers/me/location
    offers_router     GET /api/v1/drivers/me/ride-offers
                      POST /api/v1/drivers/me/ride-offers/{offer_id}/reject
                      POST /api/v1/drivers/me/ride-offers/{offer_id}/accept

Both live in modules/matching/ rather than modules/driver/ — domain-
design.md §10.2 assigns the driver geo index to the Matching Domain —
see modules/matching/__init__.py.

Rematch composition (dispatching a new offer after one expires or is
rejected) needs a ride's requested_vehicle_category and pickup point,
which modules.matching deliberately has no access to (see
service.py's docstring) — _dispatch_rematch() below composes
modules.ride's RideService with MatchingService.dispatch_offer(),
mirroring modules/ride/router.py's own best-effort composition pattern:
wrapped in try/except, explicit db.commit()/rollback() around it, and a
rematch failure never fails the primary response (an offer being
rejected/expired is a fact that already happened and must stay
recorded, whether or not a replacement offer could be dispatched).

accept_offer_endpoint() (Phase 3 / Task 3.4, ADR-0014) composes
modules.wallet + modules.matching + modules.ride directly here —
technical-architecture.md §18's Accept-Ride Transaction. The driver's
wallet row lock (wallet_service.get_wallet(), called first, purely for
its SELECT ... FOR UPDATE side effect) is the single serialization
point for two concurrent accept attempts on the same offer: both
necessarily belong to the same driver_id (only that driver holds the
offer), so both contend for the same wallet row — see
MatchingService.accept_offer()'s and RideService.accept_ride()'s
docstrings for why the fresh re-fetches inside them are race-safe once
called after this lock is held. Unlike reject_offer()/create_ride()'s
best-effort secondary steps, every step here is part of one
all-or-nothing transaction: any exception rolls back the whole thing
(no partial acceptance — BR-013), and only a *successful* return
reaches db.commit(). _dispatch_rematch() is deliberately NOT called
when an offer expires here (unlike GET/reject) — an expired offer at
accept time still leaves the ride SEARCHING with no active offer, but
the driver who just found out their offer expired is not the request
that should also pay for dispatching the next one; the next GET
.../ride-offers or reject from whichever driver is next will lazily
pick it up, same as any other lazily-expired offer.

Idempotency-Key handling (api-contracts.md §16) follows create_ride()'s
established pattern exactly (ADR-0010 Decision 5) — see
modules/ride/router.py's docstring — except the hash covers {"offer_id":
...} rather than a request body (this endpoint has none): the offer_id
is a path parameter, so without including it in the hash, the same key
reused against two different offer_ids would incorrectly look like a
replay of the first.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.orm import Session as DbSession

import shared.geo as geo
from core.config import settings
from core.database import get_db
from core.redis import get_redis
from modules.driver.dependencies import get_driver_service
from modules.driver.domain.entities import DriverOperationalStatus
from modules.driver.domain.errors import DriverDomainError
from modules.driver.service import DriverService
from modules.identity.dependencies import require_driver
from modules.identity.domain.entities import Account
from modules.matching.dependencies import get_matching_service
from modules.matching.domain.entities import Offer, validate_driver_coordinates
from modules.matching.domain.errors import (
    DriverNotOnlineError,
    MatchingDomainError,
    NoActiveVehicleError,
    OfferExpiredError,
    OfferNotFoundError,
)
from modules.matching.schemas import UpdateLocationBody
from modules.matching.service import MatchingService
from modules.notification.dependencies import get_notification_service
from modules.notification.domain.entities import Channel
from modules.notification.service import NotificationService
from modules.pricing.dependencies import get_pricing_service
from modules.pricing.service import PricingService
from modules.ride.dependencies import get_ride_service
from modules.ride.domain.entities import Ride, RideStatus
from modules.ride.domain.errors import RideDomainError, RideNotFoundError
from modules.ride.service import RideService
from modules.vehicle.dependencies import get_vehicle_service
from modules.vehicle.domain.entities import (
    VehicleCategory,
    VehicleOperationalStatus,
    matching_category_key,
)
from modules.vehicle.service import VehicleService
from modules.wallet.dependencies import get_wallet_service
from modules.wallet.domain.entities import LOW_BALANCE_THRESHOLD
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
from shared.rate_limit import RateLimitedError, RateLimiter, rate_limit_key

# BR-011 — Fixed Driver Platform Fee. Originally the sole source of
# truth (ADR-0014 Decision 1; values updated by ADR-0020 Decision 2 —
# was Bike ₹10 / Auto ₹20 / Cab ₹20). ADR-0045 (2026-08-26) makes this
# admin-editable via pricing.platform_fee_rules — accept_offer_endpoint
# below now reads the live PUBLISHED rule first. This dict remains only
# as a last-resort fallback for whenever no PUBLISHED rule exists yet
# for a category (production race-safety + test-infra survivability —
# resolved during ADR-0045's implementation, amending its Decision 4;
# the ADR text itself still says "no fallback kept", see that ADR's own
# implementation note for why this was revised). CAB's fee applies
# uniformly regardless of Eco/Premium/Premium+ tier (all three tiers
# charge the identical platform fee).
_PLATFORM_FEE_BY_CATEGORY: dict[VehicleCategory, Decimal] = {
    VehicleCategory.BIKE: Decimal("2"),
    VehicleCategory.AUTO: Decimal("5"),
    VehicleCategory.CAB: Decimal("10"),
}

# technical-architecture.md §14: "The production search radius and
# ranking weights remain configurable" — no candidate-count default is
# documented anywhere; an engineering choice (implementation-readiness.md
# §75), not a business one.
_CANDIDATE_LIMIT = 20

location_router = APIRouter(prefix="/api/v1/drivers/me", tags=["driver-location"])
offers_router = APIRouter(prefix="/api/v1/drivers/me/ride-offers", tags=["ride-offers"])


def _domain_error_response(
    exc: MatchingDomainError | DriverDomainError | RideDomainError | WalletDomainError,
    request_id: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=http_status_for_error_code(exc.code),
        content=error_envelope(exc.code, exc.message, request_id=request_id),
    )


@location_router.post("/location")
async def update_my_location(
    body: UpdateLocationBody,
    account: Annotated[Account, Depends(require_driver)],
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
    vehicle_service: Annotated[VehicleService, Depends(get_vehicle_service)],
    redis_client: Annotated[Redis, Depends(get_redis)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        validate_driver_coordinates(body.latitude, body.longitude)

        driver = driver_service.get_profile(account_id=account.id)
        if driver.operational_status is not DriverOperationalStatus.ONLINE:
            raise DriverNotOnlineError("Cannot update location while not ONLINE.")

        # BR-122: at most one of this driver's vehicles is ever ACTIVE.
        vehicles = vehicle_service.list_vehicles(driver_id=account.id)
        active_vehicle = next(
            (
                v
                for v in vehicles
                if v.operational_status is VehicleOperationalStatus.ACTIVE
            ),
            None,
        )
        if active_vehicle is None:
            raise NoActiveVehicleError(
                "No active vehicle to associate this location with."
            )

        await geo.upsert_driver_location(
            redis_client,
            driver_id=account.id,
            vehicle_id=active_vehicle.id,
            # ADR-0020 Decision 1: a CAB vehicle indexes under its own
            # tier (e.g. "CAB:ECO"), so tier-specific dispatch below only
            # ever finds a vehicle whose driver actually declared it.
            category=matching_category_key(
                active_vehicle.category, active_vehicle.cab_tier
            ),
            latitude=body.latitude,
            longitude=body.longitude,
        )
    except (MatchingDomainError, DriverDomainError) as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope({"status": "OK"}, request_id=request_id),
    )


def _offer_data(offer: Offer, ride: Ride | None) -> dict[str, object]:
    return {
        "offer_id": str(offer.id),
        "ride_id": str(offer.ride_id),
        "status": offer.status.value,
        "expires_at": offer.expires_at.isoformat(),
        "pickup": (
            {
                "latitude": ride.original_pickup.latitude,
                "longitude": ride.original_pickup.longitude,
            }
            if ride is not None
            else None
        ),
    }


async def _dispatch_rematch(
    ride_service: RideService,
    matching_service: MatchingService,
    ride_id: uuid.UUID,
    now: datetime,
) -> None:
    ride = ride_service.get_ride(ride_id=ride_id)
    if ride is None or ride.status is not RideStatus.SEARCHING:
        return
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
        now=now,
    )


@offers_router.get("")
async def list_my_offers(
    account: Annotated[Account, Depends(require_driver)],
    matching_service: Annotated[MatchingService, Depends(get_matching_service)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
    db: Annotated[DbSession, Depends(get_db)],
) -> JSONResponse:
    request_id = new_request_id()
    now = datetime.now(UTC)

    # ADR-0011 Decision 2: lazy expiry happens on every read.
    still_pending, newly_expired = matching_service.expire_stale_offers(
        driver_id=account.id, now=now
    )
    db.commit()

    for expired_offer in newly_expired:
        try:
            await _dispatch_rematch(
                ride_service, matching_service, expired_offer.ride_id, now
            )
            db.commit()
        except Exception:
            db.rollback()

    offers_data = [
        _offer_data(offer, ride_service.get_ride(ride_id=offer.ride_id))
        for offer in still_pending
    ]
    return JSONResponse(
        status_code=200,
        content=success_envelope({"offers": offers_data}, request_id=request_id),
    )


@offers_router.post("/{offer_id}/reject")
async def reject_offer(
    offer_id: uuid.UUID,
    account: Annotated[Account, Depends(require_driver)],
    redis_client: Annotated[Redis, Depends(get_redis)],
    matching_service: Annotated[MatchingService, Depends(get_matching_service)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
    db: Annotated[DbSession, Depends(get_db)],
) -> JSONResponse:
    request_id = new_request_id()

    try:
        await RateLimiter(redis_client).check_and_increment(
            key=rate_limit_key(
                category="ride_offer_response", identity=str(account.id)
            ),
            limit=settings.RATE_LIMIT_RIDE_OFFER_RESPONSE_PER_HOUR,
            window_seconds=3600,
        )
    except RateLimitedError as exc:
        return JSONResponse(
            status_code=429,
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    now = datetime.now(UTC)

    try:
        offer = matching_service.reject_offer(
            driver_id=account.id, offer_id=offer_id, now=now
        )
    except MatchingDomainError as exc:
        db.rollback()
        return _domain_error_response(exc, request_id)
    db.commit()

    try:
        await _dispatch_rematch(ride_service, matching_service, offer.ride_id, now)
        db.commit()
    except Exception:
        db.rollback()

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {"offer_id": str(offer.id), "status": offer.status.value},
            request_id=request_id,
        ),
    )


@offers_router.post("/{offer_id}/accept")
async def accept_offer_endpoint(
    offer_id: uuid.UUID,
    account: Annotated[Account, Depends(require_driver)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    redis_client: Annotated[Redis, Depends(get_redis)],
    matching_service: Annotated[MatchingService, Depends(get_matching_service)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
    wallet_service: Annotated[WalletService, Depends(get_wallet_service)],
    notification_service: Annotated[
        NotificationService, Depends(get_notification_service)
    ],
    pricing_service: Annotated[PricingService, Depends(get_pricing_service)],
    db: Annotated[DbSession, Depends(get_db)],
) -> JSONResponse:
    """Phase 3 / Task 3.4 (ADR-0014). See this module's docstring for
    the full transaction/locking design."""
    request_id = new_request_id()

    try:
        await RateLimiter(redis_client).check_and_increment(
            key=rate_limit_key(
                category="ride_offer_response", identity=str(account.id)
            ),
            limit=settings.RATE_LIMIT_RIDE_OFFER_RESPONSE_PER_HOUR,
            window_seconds=3600,
        )
    except RateLimitedError as exc:
        return JSONResponse(
            status_code=429,
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    now = datetime.now(UTC)
    store = IdempotencyStore(db)
    # See this module's docstring for why offer_id is part of the hash.
    request_hash = hash_request({"offer_id": str(offer_id)})

    try:
        reservation = store.reserve(
            key=idempotency_key,
            actor_id=account.id,
            operation="AcceptOffer",
            request_hash=request_hash,
        )
    except IdempotencyKeyReuseError as exc:
        return JSONResponse(
            status_code=http_status_for_error_code(exc.code),
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    if reservation.is_replay:
        return JSONResponse(
            status_code=reservation.cached_status_code or 200,
            content=reservation.cached_body,
        )

    try:
        # Unlocked peek, only to discover the ride (and its requested
        # category) this offer belongs to — real validation happens
        # after the wallet lock below. See this module's docstring.
        peeked = matching_service.get_offer_for_driver(
            driver_id=account.id, offer_id=offer_id
        )
        if peeked is None:
            raise OfferNotFoundError("Offer not found.")
        ride = ride_service.get_ride(ride_id=peeked.ride_id)
        if ride is None:
            raise RideNotFoundError("Ride not found.")

        # Lock wallet row (technical-architecture.md §18, step 1) —
        # the serialization point for a concurrent double-accept of
        # this same offer. Also enforces the Sarthi Wallet Low-Balance
        # Rule (ADR-0058, 2026-09-02, owner decision): raises
        # WalletRechargeRequiredError (caught below, same as any other
        # WalletDomainError) before any offer/ride state changes if
        # this driver's balance is at or below LOW_BALANCE_THRESHOLD
        # and they've already used their one grace-ride acceptance.
        wallet_service.enforce_low_balance_policy(driver_id=account.id, now=now)

        offer, vehicle_id = matching_service.accept_offer(
            driver_id=account.id,
            offer_id=offer_id,
            requested_category=matching_category_key(
                ride.requested_vehicle_category, ride.requested_cab_tier
            ),
            now=now,
        )
        ride = ride_service.accept_ride(
            ride_id=ride.id, driver_id=account.id, vehicle_id=vehicle_id, now=now
        )
        # ADR-0045: read the live-published platform fee rule, if one
        # exists — None falls back to this router's own last-resort
        # constant (BR-011), same contract as ADR-0043's driver-bonus
        # composition point (modules/admin/router.py::approve_driver()).
        fee_rule = pricing_service.get_active_platform_fee_rule(
            ride.requested_vehicle_category.value, now=now
        )
        fee = (
            fee_rule.fee_amount
            if fee_rule
            else _PLATFORM_FEE_BY_CATEGORY[ride.requested_vehicle_category]
        )
        transaction = wallet_service.debit(
            driver_id=account.id,
            amount=fee,
            transaction_type="PLATFORM_FEE",
            ride_id=ride.id,
            idempotency_key=f"offer:{offer.id}:platform-fee",
            now=now,
        )
        # Phase 3 / Event & Outbox Foundation (ADR-0017). event-
        # contracts.md §56: producer "Ride"/"Wallet" respectively,
        # partition keys ride_id/driver_id (§7) — both written in this
        # same atomic transaction as the state changes they describe.
        OutboxStore(db).append(
            new_envelope(
                event_type="ride.accepted",
                producer="ride-service",
                aggregate_type="ride",
                aggregate_id=ride.id,
                data={
                    "ride_id": str(ride.id),
                    "driver_id": str(account.id),
                    "vehicle_id": str(vehicle_id),
                    "offer_id": str(offer.id),
                },
                now=now,
            )
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
                    "amount": float(fee),
                    "transaction_type": "PLATFORM_FEE",
                },
                now=now,
            )
        )
    except OfferExpiredError as exc:
        # Unlike every other failure branch here, this one must NOT be
        # rolled back: MatchingService.accept_offer() already
        # transitioned the offer to EXPIRED (same accurate-history
        # treatment lazy expiry gets everywhere else in this module,
        # e.g. list_my_offers()/reject_offer()) before raising — that
        # write has to survive even though the accept attempt itself
        # failed, exactly like GET .../ride-offers lazily expiring an
        # offer is never undone by an unrelated later failure. The
        # idempotency reservation is still completed (not left
        # response-less) so a retry with the same key correctly
        # replays this same 409 rather than re-attempting the accept.
        response_body = error_envelope(exc.code, exc.message, request_id=request_id)
        store.complete(reservation, status_code=409, body=response_body)
        db.commit()
        return JSONResponse(status_code=409, content=response_body)
    except (
        MatchingDomainError,
        RideDomainError,
        WalletDomainError,
        DriverDomainError,
    ) as exc:
        # No partial acceptance (BR-013) — undoes every write above,
        # including the idempotency reservation, so a retry with the
        # same key isn't permanently blocked by a response-less row.
        db.rollback()
        return _domain_error_response(exc, request_id)

    response_body = success_envelope(
        {
            "offer_id": str(offer.id),
            "ride_id": str(ride.id),
            "status": ride.status.value,
            "wallet_balance": float(transaction.balance_after),
        },
        request_id=request_id,
    )
    store.complete(reservation, status_code=200, body=response_body)
    db.commit()

    # ADR-0034 — best-effort, same pattern _dispatch_rematch() above
    # uses: a notification failure must not roll back the already-
    # committed ride acceptance (domain-design.md §20.4), so this is a
    # separate transaction, never allowed to affect the response.
    try:
        await notification_service.send(
            user_id=ride.customer_id,
            channel=Channel.IN_APP,
            template_key="RIDE_ACCEPTED",
            recipient=None,
            event_id=None,
            now=now,
        )
        db.commit()
    except Exception:
        db.rollback()

    # Sarthi Wallet Low-Balance Rule (ADR-0058, 2026-09-02) — "notify
    # the Sarthi when the wallet reaches the ₹20 threshold." Fires once,
    # at the moment this platform-fee debit actually crosses the
    # threshold (balance_before above it, balance_after at/below it) —
    # not on every subsequent debit while already low, and not
    # derivable from wallet_service.enforce_low_balance_policy() above
    # (which runs before the fee debit, so it only ever sees the
    # pre-debit balance). Same best-effort pattern as the RIDE_ACCEPTED
    # notification above.
    if transaction.balance_before > LOW_BALANCE_THRESHOLD >= transaction.balance_after:
        try:
            await notification_service.send(
                user_id=account.id,
                channel=Channel.IN_APP,
                template_key="WALLET_LOW_BALANCE",
                recipient=None,
                event_id=None,
                now=now,
            )
            db.commit()
        except Exception:
            db.rollback()

    return JSONResponse(status_code=200, content=response_body)
