"""FastAPI routes for Admin.

Endpoints (docs/05-api/api-contracts.md §46, extended Phase 2 / Task
2.7A per docs/14-decisions/ADR-0009-admin-approval-scope-and-open-items.md;
§46/§47/§48 further extended Phase 16 per
docs/14-decisions/ADR-0023-admin-monitoring-and-penalty-review-scope.md):

    GET  /api/v1/admin/drivers/{driver_id}            Driver Review
    POST /api/v1/admin/drivers/{driver_id}/approve     Approve Driver
    POST /api/v1/admin/drivers/{driver_id}/reject      Reject Driver   (2.7A addition)
    POST /api/v1/admin/vehicles/{vehicle_id}/approve   Approve Vehicle
    POST /api/v1/admin/vehicles/{vehicle_id}/reject    Reject Vehicle  (2.7A addition)
    GET  /api/v1/admin/rides                           Search Rides    (Phase 16)
    GET  /api/v1/admin/rides/{ride_id}                 Get Ride        (Phase 16)
    GET  /api/v1/admin/wallets/{driver_id}             Admin Wallet View (Phase 16)
    GET  /api/v1/admin/penalties                       Search Penalties  (Phase 16)
    POST /api/v1/admin/penalties/{penalty_id}/resolve  Resolve Penalty   (Phase 16)
    GET  /api/v1/admin/gps-disputes                     Search Disputes  (BR-124/125)
    GET  /api/v1/admin/gps-disputes/{dispute_id}         Get Dispute      (§4.14)
    POST /api/v1/admin/gps-disputes/{dispute_id}/resolve  Resolve Dispute  (BR-124/125)
    POST  /api/v1/admin/campaigns                Create Campaign   (ADR-0041)
    GET   /api/v1/admin/campaigns                List Campaigns    (ADR-0041)
    GET   /api/v1/admin/campaigns/{id}            Get Campaign      (ADR-0041)
    PATCH /api/v1/admin/campaigns/{id}            Edit Campaign     (ADR-0041, DRAFT)
    POST  /api/v1/admin/campaigns/{id}/activate   Activate Campaign (ADR-0041)
    POST  /api/v1/admin/campaigns/{id}/pause      Pause Campaign    (ADR-0041)
    POST  /api/v1/admin/campaigns/{id}/end        End Campaign      (ADR-0041)
    GET   /api/v1/admin/audit-logs                Search Audit Logs (Admin Web #18)
    GET   /api/v1/admin/customers                 Search Customers  (Admin Web §4.1)
    GET   /api/v1/admin/customers/{id}             Customer Detail   (Admin Web §4.1)
    GET   /api/v1/admin/drivers                    Search Drivers    (Admin Web §4.2)
    POST  /api/v1/admin/drivers/{id}/suspend        Suspend Driver    (Admin Web §4.2)
    POST  /api/v1/admin/drivers/{id}/reactivate     Reactivate Driver (Admin Web §4.2)
    GET   /api/v1/admin/vehicles                   Search Vehicles   (Admin Web §4.3)
    GET   /api/v1/admin/vehicles/{id}               Vehicle Detail    (Admin Web §4.3)
    GET   /api/v1/admin/vehicles/{id}/documents     Vehicle Documents (Admin Web §4.4)
    GET   /api/v1/admin/verification/queue          Verification Queue (Admin Web §4.4)
    GET   /api/v1/admin/wallets/{id}/transactions   Wallet Transactions (Admin Web §4.7)
    GET   /api/v1/admin/referrals                   Search Referrals  (Admin Web §4.11)
    POST  /api/v1/admin/fare-rules                  Create Draft Fare Rule (ADR-0042)
    GET   /api/v1/admin/fare-rules                  List Fare Rules   (ADR-0042)
    GET   /api/v1/admin/fare-rules/{id}              Get Fare Rule     (ADR-0042)
    POST  /api/v1/admin/fare-rules/{id}/submit-for-review  Submit for Review (ADR-0042)
    POST  /api/v1/admin/fare-rules/{id}/publish      Publish Fare Rule (ADR-0042)
    GET   /api/v1/admin/safety/incidents            Incident Queue    (Admin Web §4.13)
    GET   /api/v1/admin/safety/incidents/{id}        Incident Detail   (Admin Web §4.13)
    POST  /api/v1/admin/safety/incidents/{id}/acknowledge  Acknowledge (Admin Web §4.13)
    POST  /api/v1/admin/safety/incidents/{id}/escalate     Escalate    (Admin Web §4.13)
    POST  /api/v1/admin/safety/incidents/{id}/resolve      Resolve     (Admin Web §4.13)
    GET   /api/v1/admin/support/cases               Search Cases      (Admin Web §4.14)
    GET   /api/v1/admin/support/cases/{id}           Case Detail       (Admin Web §4.14)
    POST  /api/v1/admin/support/cases/{id}/resolve   Resolve Case      (Admin Web §4.14)
    GET   /api/v1/admin/notifications/deliveries    Notification History (§4.12)
    GET   /api/v1/admin/settings                    List Settings     (§4.19, ADR-0048)
    GET   /api/v1/admin/settings/{key}              Get Setting       (§4.19, ADR-0048)
    PATCH /api/v1/admin/settings/{key}              Update Setting    (§4.19, ADR-0048)
    GET   /api/v1/admin/dashboard/summary           Dashboard Summary (Admin Web §3)
    GET   /api/v1/admin/matching/online-drivers     Online Driver Count (§4.6, ADR-0054)
    GET   /api/v1/admin/matching/offers             Search Offers      (§4.6, ADR-0054)
    GET   /api/v1/admin/matching/offers/{id}        Get Offer          (§4.6, ADR-0054)
    GET   /api/v1/admin/drivers/{id}/strikes        Driver Strike History (§4.9, §46.18)
    POST  /api/v1/admin/campaigns/{id}/eligible-customers/bulk  CSV Bulk (§4.10)
    POST  /api/v1/admin/notifications/broadcasts    Compose/Send Broadcast (§4.12)
    GET   /api/v1/admin/notifications/broadcasts    Broadcast History      (§4.12)
    GET   /api/v1/admin/notifications/broadcasts/{id}  Get Broadcast       (§4.12)

Vehicle Review (GET .../vehicles/{id}) and a pending-review list/search
endpoint are NOT implemented — neither is documented anywhere (ADR-0009).
Nor are `GET /api/v1/admin/payments/{payment_id}` / `GET
/api/v1/admin/settlements` (§47) — no Payment domain/module exists
anywhere in this codebase (Phase 10, blocked) and "settlements" has no
backing concept documented anywhere either (ADR-0023 Decision 3).

Every route composes modules.admin (authz + audit) with
modules.driver/modules.vehicle's own ApproveDriver/RejectDriver/
ApproveVehicle/RejectVehicle-equivalent service methods, and, for Driver
Review, modules.identity (phone), modules.driver (documents), and
modules.verification (cases) — the same API-layer-composition pattern
used throughout this codebase. No domain/service-layer code in any other
module imports modules.admin, and modules.admin's own domain/service
layer never imports theirs.

Approve Driver additionally composes modules.referral/modules.wallet
(ADR-0019 Decision 4, BR-022/023): if the driver being approved was ever
attached as the referred party in a driver referral, this is the point
that qualifies it and pays out the ₹100/₹100 wallet bonus to both
sides — a no-op for the common case of a driver who was never referred.

Search Rides / Get Ride additionally compose modules.pricing (a ride's
active fare quote, if one exists) — read-only, same one-directional
composition shape. Admin Wallet View composes modules.driver (the same
driver.drivers-row precondition check `GET /api/v1/drivers/me/wallet`
already performs for itself) and modules.wallet. All of Search Rides /
Get Ride / Admin Wallet View / Search Penalties are pure reads: none of
them writes an admin.audit_logs row (matching Driver Review's existing
precedent — only admin *mutations* are audited). Resolve Penalty is a
mutation and is audited, same shape as Approve/Reject Driver/Vehicle.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.orm import Session as DbSession

from core.config import settings
from core.database import get_db
from core.redis import get_redis
from modules.admin.dependencies import (
    enforce_admin_api_rate_limit,
    get_admin_service,
)
from modules.admin.domain.entities import (
    AccessLevel,
    AdminModule,
    AdminUser,
    AuditLog,
    Permission,
    Setting,
    SettingCategory,
)
from modules.admin.domain.errors import AdminDomainError
from modules.admin.schemas import (
    AssignDriverBody,
    CampaignBody,
    CreateAdminBody,
    CreateBroadcastBody,
    CreateCampaignBody,
    CreateCustomerRewardRuleBody,
    CreateDriverBonusRuleBody,
    CreateFareRuleBody,
    CreatePlatformFeeRuleBody,
    CreateTemplateBody,
    PermissionGrant,
    PublishFareRuleBody,
    PublishPlatformFeeRuleBody,
    PublishRewardConfigBody,
    RejectBody,
    ResolveGpsDisputeBody,
    ResolvePenaltyBody,
    UpdatePermissionsBody,
    UpdateSettingBody,
    VerifyAssignmentBody,
)
from modules.admin.service import AdminService
from modules.advertisement.dependencies import get_advertisement_service
from modules.advertisement.domain.entities import Campaign as AdCampaign
from modules.advertisement.domain.entities import CampaignStatus as AdCampaignStatus
from modules.advertisement.domain.entities import DriverCampaign, Payout, PayoutStatus
from modules.advertisement.domain.errors import AdvertisementDomainError
from modules.advertisement.service import AdvertisementService
from modules.customer.dependencies import get_customer_service
from modules.customer.domain.entities import Customer
from modules.customer.domain.errors import CustomerDomainError
from modules.customer.service import CustomerService
from modules.driver.dependencies import get_driver_document_service, get_driver_service
from modules.driver.domain.entities import Driver, DriverDocument
from modules.driver.domain.errors import DriverDomainError
from modules.driver.service import DriverDocumentService, DriverService
from modules.identity.dependencies import get_account_repository, require_admin
from modules.identity.domain.entities import Account
from modules.identity.domain.errors import InvalidPhoneNumberError
from modules.identity.domain.phone_number import PhoneNumber
from modules.identity.repositories import SqlAlchemyAccountRepository
from modules.matching.dependencies import get_matching_service
from modules.matching.domain.entities import Offer, OfferStatus
from modules.matching.domain.errors import MatchingDomainError, OfferNotFoundError
from modules.matching.service import MatchingService
from modules.notification.broadcast_dispatch import dispatch_broadcast
from modules.notification.dependencies import get_notification_service
from modules.notification.domain.entities import (
    AudienceType,
    Broadcast,
    BroadcastStatus,
    Channel,
    Delivery,
    DeliveryStatus,
    Template,
    TemplateStatus,
)
from modules.notification.domain.errors import NotificationDomainError
from modules.notification.service import NotificationService
from modules.penalty.dependencies import get_penalty_service
from modules.penalty.domain.entities import Penalty, PenaltyStatus, Strike
from modules.penalty.domain.errors import PenaltyDomainError
from modules.penalty.service import PenaltyService
from modules.pricing.dependencies import get_pricing_service
from modules.pricing.domain.entities import (
    FareQuote,
    FareRule,
    FareRuleStatus,
    PlatformFeeRule,
)
from modules.pricing.domain.errors import PricingDomainError
from modules.pricing.service import PricingService
from modules.promotion.dependencies import get_promotion_service
from modules.promotion.domain.entities import Campaign, CampaignStatus
from modules.promotion.domain.errors import PromotionDomainError
from modules.promotion.service import PromotionService
from modules.referral.dependencies import get_referral_service
from modules.referral.domain.entities import (
    CustomerRewardRule,
    DriverBonusRule,
    OwnerType,
    Referral,
    ReferralStatus,
    Reward,
    RewardConfigStatus,
    RewardType,
)
from modules.referral.domain.errors import ReferralDomainError
from modules.referral.service import ReferralService
from modules.ride.dependencies import get_ride_service
from modules.ride.domain.entities import (
    GpsDispute,
    GpsDisputeEvidence,
    GpsDisputeStatus,
    Ride,
    RideStatus,
)
from modules.ride.domain.errors import RideDomainError, RideNotFoundError
from modules.ride.service import RideService
from modules.safety.dependencies import get_safety_service
from modules.safety.domain.entities import SafetyIncident
from modules.safety.domain.errors import SafetyDomainError
from modules.safety.service import SafetyService
from modules.support.dependencies import get_support_service
from modules.support.domain.entities import SupportCase, SupportMessage
from modules.support.domain.errors import SupportDomainError
from modules.support.service import SupportService
from modules.vehicle.dependencies import (
    get_vehicle_document_service,
    get_vehicle_service,
)
from modules.vehicle.domain.entities import (
    ALL_MATCHING_CATEGORY_KEYS,
    Vehicle,
    VehicleCategory,
    VehicleDocument,
)
from modules.vehicle.domain.errors import VehicleDomainError
from modules.vehicle.service import VehicleDocumentService, VehicleService
from modules.verification.dependencies import get_verification_service
from modules.verification.domain.entities import VerificationCase
from modules.verification.domain.errors import VerificationDomainError
from modules.verification.service import VerificationService
from modules.wallet.dependencies import get_wallet_service
from modules.wallet.domain.entities import TransactionType, Wallet, WalletTransaction
from modules.wallet.domain.errors import WalletDomainError
from modules.wallet.service import WalletService
from shared import geo
from shared.api_envelope import (
    error_envelope,
    http_status_for_error_code,
    new_request_id,
    success_envelope,
)
from shared.outbox import OutboxStore, new_envelope
from shared.pagination import PageParams, pagination_envelope

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    # Admin APIs' blanket rate limit (security.md §20; security-review-
    # 2026-09-02.md finding 4.1) — applied once here, at the router
    # level, rather than per-endpoint: see enforce_admin_api_rate_limit's
    # own docstring for why one blanket limit is the right shape for
    # this router specifically.
    dependencies=[Depends(enforce_admin_api_rate_limit)],
)

_AnyDomainError = (
    AdminDomainError,
    DriverDomainError,
    VehicleDomainError,
    ReferralDomainError,
    WalletDomainError,
    RideDomainError,
    PricingDomainError,
    PenaltyDomainError,
    PromotionDomainError,
    CustomerDomainError,
    VerificationDomainError,
    SafetyDomainError,
    SupportDomainError,
    NotificationDomainError,
    AdvertisementDomainError,
    MatchingDomainError,
)


def _domain_error_response(
    exc: AdminDomainError
    | DriverDomainError
    | VehicleDomainError
    | ReferralDomainError
    | WalletDomainError
    | RideDomainError
    | PricingDomainError
    | PenaltyDomainError
    | PromotionDomainError
    | CustomerDomainError
    | VerificationDomainError
    | SafetyDomainError
    | SupportDomainError
    | NotificationDomainError
    | AdvertisementDomainError
    | MatchingDomainError,
    request_id: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=http_status_for_error_code(exc.code),
        content=error_envelope(exc.code, exc.message, request_id=request_id),
    )


def _driver_data(account: Account, driver: Driver) -> dict[str, object]:
    return {
        "driver_id": str(driver.id),
        "phone": account.phone,
        "full_name": driver.full_name,
        "profile_photo_uri": driver.profile_photo_uri,
        "verification_status": driver.verification_status.value,
        "operational_status": driver.operational_status.value,
        "strikes": driver.strikes,
        "created_at": driver.created_at.isoformat(),
        "updated_at": driver.updated_at.isoformat(),
    }


def _vehicle_data(vehicle: Vehicle) -> dict[str, object]:
    return {
        "vehicle_id": str(vehicle.id),
        "category": vehicle.category.value,
        "registration_number": vehicle.registration_number,
        "make": vehicle.make,
        "model": vehicle.model,
        "verification_status": vehicle.verification_status.value,
        "operational_status": vehicle.operational_status.value,
        "created_at": vehicle.created_at.isoformat(),
        "updated_at": vehicle.updated_at.isoformat(),
    }


def _admin_fare_data(quote: FareQuote) -> dict[str, object]:
    # Same shape modules/ride/router.py's own _fare_data() produces
    # (api-contracts.md §12, ADR-0020 Decision 6) — duplicated here
    # rather than imported, matching this router's existing pattern of
    # defining its own presentation helpers (_driver_data/_vehicle_data)
    # instead of reaching into another module's router.
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


def _admin_ride_data(ride: Ride, quote: FareQuote | None) -> dict[str, object]:
    # Phase 16 (Search Rides / Get Ride, ADR-0023) — response shape
    # filled in, since api-contracts.md §46 documents no body for either
    # route (same "shape not documented, filled in as an implementation
    # decision" precedent Phase 14 set for GET Support Case).
    return {
        "ride_id": str(ride.id),
        "status": ride.status.value,
        "customer_id": str(ride.customer_id),
        "driver_id": str(ride.driver_id) if ride.driver_id is not None else None,
        "vehicle_id": str(ride.vehicle_id) if ride.vehicle_id is not None else None,
        "requested_vehicle_category": ride.requested_vehicle_category.value,
        "requested_cab_tier": (
            ride.requested_cab_tier.value
            if ride.requested_cab_tier is not None
            else None
        ),
        "pickup": {
            "latitude": ride.current_pickup.latitude,
            "longitude": ride.current_pickup.longitude,
        },
        "destination": {
            "latitude": ride.current_destination.latitude,
            "longitude": ride.current_destination.longitude,
        },
        "fare": _admin_fare_data(quote) if quote is not None else None,
        "requested_at": ride.requested_at.isoformat(),
        "accepted_at": ride.accepted_at.isoformat() if ride.accepted_at else None,
        "arrived_at": ride.arrived_at.isoformat() if ride.arrived_at else None,
        "started_at": ride.started_at.isoformat() if ride.started_at else None,
        "completed_at": ride.completed_at.isoformat() if ride.completed_at else None,
        "cancelled_at": ride.cancelled_at.isoformat() if ride.cancelled_at else None,
        "closed_at": ride.closed_at.isoformat() if ride.closed_at else None,
        "created_at": ride.created_at.isoformat(),
        "updated_at": ride.updated_at.isoformat(),
    }


def _admin_wallet_data(wallet: Wallet) -> dict[str, object]:
    # Same shape modules/wallet/router.py's own _wallet_data() produces
    # (api-contracts.md §34) — duplicated here for the same reason
    # _admin_fare_data() is above.
    return {
        "balance": float(wallet.balance),
        "currency": "INR",
        "outstanding_settlement": 0,
    }


def _penalty_data(penalty: Penalty) -> dict[str, object]:
    # No "expires_at" — removed 2026-09-04 (BR-049 correction, ADR-0069,
    # owner decision): customer penalties never expire, so there is no
    # expiry date to report. Was previously a real, misleading value
    # here (a computed 30-days-out timestamp nothing ever enforced).
    return {
        "penalty_id": str(penalty.id),
        "user_id": str(penalty.user_id),
        "ride_id": str(penalty.ride_id) if penalty.ride_id is not None else None,
        "penalty_type": penalty.penalty_type.value,
        "amount": float(penalty.amount),
        "status": penalty.status.value,
        "issued_at": penalty.issued_at.isoformat(),
        "settled_at": penalty.settled_at.isoformat() if penalty.settled_at else None,
    }


def _document_summary(
    document: DriverDocument, verification_service: VerificationService
) -> dict[str, object]:
    cases = verification_service.list_cases_for_subject(
        subject_type="DRIVER_DOCUMENT", subject_id=document.id
    )
    return {
        "document_id": str(document.id),
        "document_type": document.document_type,
        "verification_status": document.verification_status.value,
        "verification_cases": [
            {"case_id": str(case.id), "status": case.status.value} for case in cases
        ],
    }


@router.get("/drivers/{driver_id}")
async def review_driver(
    driver_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
    document_service: Annotated[
        DriverDocumentService, Depends(get_driver_document_service)
    ],
    verification_service: Annotated[
        VerificationService, Depends(get_verification_service)
    ],
    accounts: Annotated[SqlAlchemyAccountRepository, Depends(get_account_repository)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.DRIVERS,
            level=AccessLevel.VIEW,
        )
        driver = driver_service.get_profile(account_id=driver_id)
        driver_account = accounts.get_by_id(driver_id)
        if driver_account is None:
            return JSONResponse(
                status_code=404,
                content=error_envelope(
                    "RESOURCE_NOT_FOUND",
                    "Driver account not found.",
                    request_id=request_id,
                ),
            )
        documents = document_service.list_documents(driver_id=driver_id)
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    data = _driver_data(driver_account, driver)
    data["documents"] = [
        _document_summary(doc, verification_service) for doc in documents
    ]
    return JSONResponse(
        status_code=200, content=success_envelope(data, request_id=request_id)
    )


_DRIVER_REFERRAL_BONUS_AMOUNT = Decimal("100")  # BR-022


@router.post("/drivers/{driver_id}/approve")
async def approve_driver(
    driver_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
    document_service: Annotated[
        DriverDocumentService, Depends(get_driver_document_service)
    ],
    accounts: Annotated[SqlAlchemyAccountRepository, Depends(get_account_repository)],
    referral_service: Annotated[ReferralService, Depends(get_referral_service)],
    wallet_service: Annotated[WalletService, Depends(get_wallet_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.DRIVERS,
            level=AccessLevel.MANAGE,
        )
        # BR-123 (Task 2.6C): the caller loads the driver's documents;
        # approve_driver() decides whether they satisfy the required set.
        # Raising here (DriverRequiredDocumentsNotValidError) happens
        # before record_audit_log() below, so a blocked attempt never
        # writes a "successful approval" audit row.
        documents = document_service.list_documents(driver_id=driver_id)
        driver = driver_service.approve_driver(driver_id=driver_id, documents=documents)
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="APPROVE_DRIVER",
            target_type="DRIVER",
            target_id=driver_id,
            reason=None,
            before_state={"verification_status": "PENDING"},
            after_state={"verification_status": "APPROVED"},
            request_id=request_id,
        )
        driver_account = accounts.get_by_id(driver_id)
        if driver_account is None:
            return JSONResponse(
                status_code=404,
                content=error_envelope(
                    "RESOURCE_NOT_FOUND",
                    "Driver account not found.",
                    request_id=request_id,
                ),
            )

        # ADR-0019 Decision 4 / BR-022/023: a driver referral (if one was
        # attached via POST /api/v1/referrals/attach) only activates
        # here, at approval — not at attach time. Most drivers were never
        # referred, so this is a no-op for the common case.
        referral = referral_service.get_referral_by_referred_id(driver_id)
        if referral is not None and referral.referred_type is OwnerType.DRIVER:
            referral = referral_service.qualify_driver_referral(
                referral_id=referral.id, now=datetime.now(UTC)
            )
            # ADR-0043: read the live-published driver-bonus rule, if
            # one exists — None falls back to this router's own
            # last-resort constant (BR-022), same contract as the
            # customer side (modules/referral/router.py::attach_referral).
            bonus_rule = referral_service.get_active_driver_bonus_rule(
                now=datetime.now(UTC)
            )
            for recipient_id, key_suffix, amount in (
                (
                    referral.referred_id,
                    "referred",
                    bonus_rule.referred_amount
                    if bonus_rule
                    else _DRIVER_REFERRAL_BONUS_AMOUNT,
                ),
                (
                    referral.referrer_id,
                    "referrer",
                    bonus_rule.referrer_amount
                    if bonus_rule
                    else _DRIVER_REFERRAL_BONUS_AMOUNT,
                ),
            ):
                wallet_service.credit(
                    driver_id=recipient_id,
                    amount=amount,
                    transaction_type=TransactionType.DRIVER_REFERRAL_BONUS.value,
                    ride_id=None,
                    idempotency_key=f"referral:{referral.id}:{key_suffix}",
                    now=datetime.now(UTC),
                )
                referral_service.record_reward(
                    referral_id=referral.id,
                    recipient_id=recipient_id,
                    reward_type=RewardType.DRIVER_REFERRAL_BONUS,
                    amount=amount,
                    promotion_uses=None,
                    idempotency_key=f"referral:{referral.id}:{key_suffix}",
                    now=datetime.now(UTC),
                )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            _driver_data(driver_account, driver), request_id=request_id
        ),
    )


@router.post("/drivers/{driver_id}/reject")
async def reject_driver(
    driver_id: uuid.UUID,
    body: RejectBody,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
    accounts: Annotated[SqlAlchemyAccountRepository, Depends(get_account_repository)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.DRIVERS,
            level=AccessLevel.MANAGE,
        )
        driver = driver_service.reject_driver(driver_id=driver_id, reason=body.reason)
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="REJECT_DRIVER",
            target_type="DRIVER",
            target_id=driver_id,
            reason=body.reason,
            before_state={"verification_status": "PENDING"},
            after_state={"verification_status": "REJECTED"},
            request_id=request_id,
        )
        driver_account = accounts.get_by_id(driver_id)
        if driver_account is None:
            return JSONResponse(
                status_code=404,
                content=error_envelope(
                    "RESOURCE_NOT_FOUND",
                    "Driver account not found.",
                    request_id=request_id,
                ),
            )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            _driver_data(driver_account, driver), request_id=request_id
        ),
    )


@router.post("/vehicles/{vehicle_id}/approve")
async def approve_vehicle(
    vehicle_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    vehicle_service: Annotated[VehicleService, Depends(get_vehicle_service)],
    document_service: Annotated[
        VehicleDocumentService, Depends(get_vehicle_document_service)
    ],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.VEHICLES,
            level=AccessLevel.MANAGE,
        )
        # BR-123 (Task 2.6C) — same composition shape as approve_driver().
        documents = document_service.list_documents(vehicle_id=vehicle_id)
        vehicle = vehicle_service.approve_vehicle(
            vehicle_id=vehicle_id, documents=documents
        )
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="APPROVE_VEHICLE",
            target_type="VEHICLE",
            target_id=vehicle_id,
            reason=None,
            before_state={"verification_status": "PENDING"},
            after_state={"verification_status": "APPROVED"},
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_vehicle_data(vehicle), request_id=request_id),
    )


@router.post("/vehicles/{vehicle_id}/reject")
async def reject_vehicle(
    vehicle_id: uuid.UUID,
    body: RejectBody,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    vehicle_service: Annotated[VehicleService, Depends(get_vehicle_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.VEHICLES,
            level=AccessLevel.MANAGE,
        )
        vehicle = vehicle_service.reject_vehicle(
            vehicle_id=vehicle_id, reason=body.reason
        )
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="REJECT_VEHICLE",
            target_type="VEHICLE",
            target_id=vehicle_id,
            reason=body.reason,
            before_state={"verification_status": "PENDING"},
            after_state={"verification_status": "REJECTED"},
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_vehicle_data(vehicle), request_id=request_id),
    )


def _fetch_active_quote(
    pricing_service: PricingService, ride: Ride
) -> FareQuote | None:
    if ride.active_fare_quote_id is None:
        return None
    return pricing_service.get_fare_quote(fare_quote_id=ride.active_fare_quote_id)


_VALID_RIDE_STATUSES = frozenset(status.value for status in RideStatus)
_VALID_PENALTY_STATUSES = frozenset(status.value for status in PenaltyStatus)
_VALID_GPS_DISPUTE_STATUSES = frozenset(status.value for status in GpsDisputeStatus)


@router.get("/rides")
async def search_rides(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
    pricing_service: Annotated[PricingService, Depends(get_pricing_service)],
    status: Annotated[str | None, Query()] = None,
    driver_id: Annotated[uuid.UUID | None, Query()] = None,
    customer_id: Annotated[uuid.UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """Search Rides (api-contracts.md §46, ADR-0023). `status` is
    validated against the documented RideStatus enum — an unrecognized
    value is a genuine client mistake (a typo would otherwise silently
    return zero rows), not shape-only validated the way an undocumented
    enum elsewhere in this codebase would be."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.RIDES,
            level=AccessLevel.VIEW,
        )
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
            page=page,
            page_size=page_size,
            max_page_size=settings.MAX_PAGE_SIZE,
        )
        rides, total = ride_service.search_rides(
            status=status,
            driver_id=driver_id,
            customer_id=customer_id,
            offset=params.offset,
            limit=params.page_size,
        )
        items = [
            _admin_ride_data(ride, _fetch_active_quote(pricing_service, ride))
            for ride in rides
        ]
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(items, params=params, total=total),
            request_id=request_id,
        ),
    )


@router.get("/rides/{ride_id}")
async def get_ride(
    ride_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
    pricing_service: Annotated[PricingService, Depends(get_pricing_service)],
) -> JSONResponse:
    """Get Ride (admin) — api-contracts.md §46, ADR-0023. Distinct from
    the still-unbuilt customer/driver-facing `GET /api/v1/rides/{id}`
    (§13): no ownership restriction, admin-only."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.RIDES,
            level=AccessLevel.VIEW,
        )
        ride = ride_service.get_ride(ride_id=ride_id)
        if ride is None:
            raise RideNotFoundError("Ride not found.")
        quote = _fetch_active_quote(pricing_service, ride)
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_admin_ride_data(ride, quote), request_id=request_id),
    )


@router.get("/wallets/{driver_id}")
async def get_driver_wallet(
    driver_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
    wallet_service: Annotated[WalletService, Depends(get_wallet_service)],
) -> JSONResponse:
    """Admin Wallet View (api-contracts.md §47, ADR-0023). Same response
    shape as the driver-facing `GET /api/v1/drivers/me/wallet` (§34) —
    no transaction history folded in (that's the separate `GET
    /api/v1/admin/wallets/{driver_id}/transactions` below, Admin Web
    §4.7)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.FINANCE,
            level=AccessLevel.VIEW,
        )
        # Same driver.drivers-row precondition GET /api/v1/drivers/me/
        # wallet already checks for itself (database-design.md §17.1's
        # wallet.wallets.driver_id foreign key) — an admin looking up a
        # driver_id with no driver.drivers row gets RESOURCE_NOT_FOUND
        # here rather than a wallet auto-created for a nonexistent driver.
        driver_service.get_profile(account_id=driver_id)
        wallet = wallet_service.get_wallet(driver_id=driver_id, now=datetime.now(UTC))
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_admin_wallet_data(wallet), request_id=request_id),
    )


_VALID_TRANSACTION_TYPES = frozenset(t.value for t in TransactionType)


def _admin_transaction_data(transaction: WalletTransaction) -> dict[str, object]:
    # Same shape modules/wallet/router.py's own _transaction_data()
    # produces — duplicated here for the same reason _admin_wallet_data()
    # above duplicates _wallet_data().
    return {
        "transaction_id": str(transaction.id),
        "ride_id": str(transaction.ride_id) if transaction.ride_id else None,
        "transaction_type": transaction.transaction_type.value,
        "amount": float(transaction.amount),
        "direction": transaction.direction.value,
        "balance_before": float(transaction.balance_before),
        "balance_after": float(transaction.balance_after),
        "reference_type": transaction.reference_type,
        "reference_id": (
            str(transaction.reference_id) if transaction.reference_id else None
        ),
        "created_at": transaction.created_at.isoformat(),
    }


@router.get("/wallets/{driver_id}/transactions")
async def list_driver_wallet_transactions(
    driver_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
    wallet_service: Annotated[WalletService, Depends(get_wallet_service)],
    type: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """Wallet Transaction History (Admin Web §4.7) — the admin-side
    equivalent of the driver-facing `GET /api/v1/drivers/me/wallet/
    transactions` (§34, Phase 11/ADR-0024), for any `driver_id` rather
    than the caller's own. Both share `WalletService.list_transactions()`,
    same "one service method, two routes" precedent every other admin
    read endpoint here already follows."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.FINANCE,
            level=AccessLevel.VIEW,
        )
        driver_service.get_profile(account_id=driver_id)
        if type is not None and type not in _VALID_TRANSACTION_TYPES:
            return JSONResponse(
                status_code=422,
                content=error_envelope(
                    "VALIDATION_FAILED",
                    f"Unknown transaction type: {type!r}.",
                    request_id=request_id,
                ),
            )
        params = PageParams.clamp(
            page=page,
            page_size=page_size,
            max_page_size=settings.MAX_PAGE_SIZE,
        )
        transactions, total = wallet_service.list_transactions(
            driver_id=driver_id,
            transaction_type=type,
            offset=params.offset,
            limit=params.page_size,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_admin_transaction_data(t) for t in transactions],
                params=params,
                total=total,
            ),
            request_id=request_id,
        ),
    )


@router.get("/penalties")
async def search_penalties(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    penalty_service: Annotated[PenaltyService, Depends(get_penalty_service)],
    status: Annotated[str | None, Query()] = None,
    user_id: Annotated[uuid.UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """Search Penalties (api-contracts.md §48, ADR-0023). §48 names no
    filters explicitly — `status`/`user_id` are modeled on Search
    Rides' own filter shape."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.PENALTIES,
            level=AccessLevel.VIEW,
        )
        if status is not None and status not in _VALID_PENALTY_STATUSES:
            return JSONResponse(
                status_code=422,
                content=error_envelope(
                    "VALIDATION_FAILED",
                    f"Unknown penalty status: {status!r}.",
                    request_id=request_id,
                ),
            )
        params = PageParams.clamp(
            page=page,
            page_size=page_size,
            max_page_size=settings.MAX_PAGE_SIZE,
        )
        penalties, total = penalty_service.search_penalties(
            status=status,
            user_id=user_id,
            offset=params.offset,
            limit=params.page_size,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_penalty_data(penalty) for penalty in penalties],
                params=params,
                total=total,
            ),
            request_id=request_id,
        ),
    )


@router.post("/penalties/{penalty_id}/resolve")
async def resolve_penalty(
    penalty_id: uuid.UUID,
    body: ResolvePenaltyBody,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    penalty_service: Annotated[PenaltyService, Depends(get_penalty_service)],
) -> JSONResponse:
    """Resolve Penalty (api-contracts.md §48, ADR-0023) — the only
    documented action is "WAIVE" (validated at the service layer). The
    "reversal/waiver record" §48 asks for is the admin.audit_logs row
    written below, in the same transaction — no second table exists for
    this (ADR-0023 Decision 4)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.PENALTIES,
            level=AccessLevel.MANAGE,
        )
        penalty = penalty_service.resolve_penalty(
            penalty_id=penalty_id, action=body.action, reason=body.reason
        )
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="RESOLVE_PENALTY",
            target_type="PENALTY",
            target_id=penalty_id,
            reason=body.reason,
            before_state={"status": "OUTSTANDING"},
            after_state={"status": penalty.status.value},
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_penalty_data(penalty), request_id=request_id),
    )


def _gps_dispute_data(
    dispute: GpsDispute, evidence: list[GpsDisputeEvidence] | None = None
) -> dict[str, object]:
    data: dict[str, object] = {
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
    }
    if evidence is not None:
        data["evidence"] = [
            {
                "submitted_by": str(e.submitted_by),
                "evidence_type": e.evidence_type.value,
                "uri": e.uri,
                "text_explanation": e.text_explanation,
                "submitted_at": e.submitted_at.isoformat(),
            }
            for e in evidence
        ]
    return data


@router.get("/gps-disputes")
async def search_gps_disputes(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
    status: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """Search Disputes (api-contracts.md §77, BR-124/BR-125, ADR-0032) —
    same allow-listed-filter/pagination shape as Search Penalties above."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.SUPPORT,
            level=AccessLevel.VIEW,
        )
        if status is not None and status not in _VALID_GPS_DISPUTE_STATUSES:
            return JSONResponse(
                status_code=422,
                content=error_envelope(
                    "VALIDATION_FAILED",
                    f"Unknown GPS dispute status: {status!r}.",
                    request_id=request_id,
                ),
            )
        params = PageParams.clamp(
            page=page,
            page_size=page_size,
            max_page_size=settings.MAX_PAGE_SIZE,
        )
        disputes, total = ride_service.search_gps_disputes(
            status=status, offset=params.offset, limit=params.page_size
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_gps_dispute_data(dispute) for dispute in disputes],
                params=params,
                total=total,
            ),
            request_id=request_id,
        ),
    )


@router.get("/gps-disputes/{dispute_id}")
async def get_gps_dispute(
    dispute_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
) -> JSONResponse:
    """Get Dispute (Admin Web §4.14, api-contracts.md §77, ADR-0032) —
    the admin-facing counterpart modules/ride/router.py's own customer/
    driver-scoped get_gps_dispute() endpoint already anticipates in its
    own docstring: same RideService.get_gps_dispute(), just with
    is_admin=True. Includes evidence (photos/text explanations) — the
    admin needs to see what was submitted to decide APPROVE/REJECT,
    unlike Search Disputes above which omits it (list rows, not a
    detail view)."""
    request_id = new_request_id()
    now = datetime.now(UTC)
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.SUPPORT,
            level=AccessLevel.VIEW,
        )
        dispute, evidence = ride_service.get_gps_dispute(
            dispute_id=dispute_id,
            account_id=admin_account.id,
            is_admin=True,
            now=now,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            _gps_dispute_data(dispute, list(evidence)), request_id=request_id
        ),
    )


@router.post("/gps-disputes/{dispute_id}/resolve")
async def resolve_gps_dispute(
    dispute_id: uuid.UUID,
    body: ResolveGpsDisputeBody,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
    db: Annotated[DbSession, Depends(get_db)],
) -> JSONResponse:
    """Resolve Dispute (api-contracts.md §77, BR-124, ADR-0032). APPROVE
    performs the exact ride transition the original GPS verification
    would have on a real PASS; REJECT only records the decision — see
    RideService.resolve_gps_dispute()'s own docstring. A mutation, so
    audited, same shape as Resolve Penalty. Unlike every other admin
    mutation in this file, this one also publishes an outbox event
    (`ride.gps_dispute_resolved`, event-contracts.md §10.11) — the one
    place this router departs from its own "admin mutations are audited,
    never published" precedent, because ADR-0032/event-contracts.md
    explicitly document this event; `db` is injected only for that
    reason (it's the same session ride_service's own DI-injected session
    already is, per FastAPI's per-request dependency caching, so no
    separate commit is needed — get_db's implicit commit-on-return covers
    both writes together)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.SUPPORT,
            level=AccessLevel.MANAGE,
        )
        now = datetime.now(UTC)
        dispute, ride = ride_service.resolve_gps_dispute(
            dispute_id=dispute_id,
            admin_id=admin_account.id,
            action=body.action,
            reason=body.reason,
            otp_expiry_seconds=settings.RIDE_OTP_EXPIRY_SECONDS,
            otp_hash_pepper=settings.RIDE_OTP_HASH_SECRET,
            now=now,
        )
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="RESOLVE_GPS_DISPUTE",
            target_type="GPS_DISPUTE",
            target_id=dispute_id,
            reason=body.reason,
            before_state={"status": "OPEN"},
            after_state={"status": dispute.status.value, "decision": body.action},
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    # event-contracts.md §10.11 — exact documented payload shape.
    OutboxStore(db).append(
        new_envelope(
            event_type="ride.gps_dispute_resolved",
            producer="ride-service",
            aggregate_type="ride",
            aggregate_id=dispute.ride_id,
            data={
                "dispute_id": str(dispute.id),
                "ride_id": str(dispute.ride_id),
                "decision": dispute.decision.value if dispute.decision else None,
                "decided_by": str(dispute.decided_by),
                "decided_at": dispute.decided_at.isoformat()
                if dispute.decided_at
                else None,
            },
            now=now,
        )
    )

    data = _gps_dispute_data(dispute)
    data["ride_status"] = ride.status.value if ride is not None else None
    return JSONResponse(
        status_code=200,
        content=success_envelope(data, request_id=request_id),
    )


# ----------------------------------------------------------------------
# Admin Management (ADR-0040, BR-126/BR-127) — every route below
# requires ADMIN_MANAGEMENT access, which is never grantable to an
# employee admin (AdminService._grant()) — so require_permission() here
# is, in practice, a Super-Admin-only gate, without a separate
# "is this a Super Admin" check duplicating that rule.
# ----------------------------------------------------------------------


def _admin_data(admin: AdminUser, permissions: list[Permission]) -> dict[str, object]:
    return {
        "admin_id": str(admin.id),
        "role": admin.role,
        "status": admin.status,
        "created_at": admin.created_at.isoformat(),
        "permissions": [_permission_data(p) for p in permissions],
    }


def _permission_data(permission: Permission) -> dict[str, object]:
    return {
        "module": permission.module.value,
        "access_level": permission.access_level.value,
    }


def _grants_from_body(
    permissions: list[PermissionGrant],
) -> list[tuple[AdminModule, AccessLevel]]:
    return [(g.module, g.access_level) for g in permissions]


@router.post("/admins")
async def create_admin(
    body: CreateAdminBody,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
) -> JSONResponse:
    """Create Employee Admin (ADR-0040, BR-126/BR-127). The created
    account authenticates through the ordinary phone+OTP flow, same as
    scripts/provision_admin.py's own script — no credential is
    generated or returned here."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.ADMIN_MANAGEMENT,
            level=AccessLevel.MANAGE,
        )
        now = datetime.now(UTC)
        admin, permissions = admin_service.create_employee_admin(
            phone_raw=body.phone,
            grants=_grants_from_body(list(body.permissions)),
            now=now,
        )
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="CREATE_ADMIN",
            target_type="ADMIN",
            target_id=admin.id,
            reason=None,
            before_state=None,
            after_state=_admin_data(admin, permissions),
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=201,
        content=success_envelope(
            _admin_data(admin, permissions), request_id=request_id
        ),
    )


@router.get("/admins")
async def list_admins(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.ADMIN_MANAGEMENT,
            level=AccessLevel.VIEW,
        )
        params = PageParams.clamp(
            page=page, page_size=page_size, max_page_size=settings.MAX_PAGE_SIZE
        )
        admins, total = admin_service.list_admins(
            offset=params.offset, limit=params.page_size
        )
        # List doesn't fetch each admin's own permissions individually
        # (an N+1 query pattern) — Get Admin (below) is where the full
        # permission set for one admin is surfaced.
        items = [_admin_data(a, []) for a in admins]
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(items, params=params, total=total),
            request_id=request_id,
        ),
    )


@router.get("/admins/{target_admin_id}")
async def get_admin(
    target_admin_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.ADMIN_MANAGEMENT,
            level=AccessLevel.VIEW,
        )
        admin, permissions = admin_service.get_admin(target_admin_id)
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            _admin_data(admin, permissions), request_id=request_id
        ),
    )


@router.patch("/admins/{target_admin_id}/permissions")
async def update_admin_permissions(
    target_admin_id: uuid.UUID,
    body: UpdatePermissionsBody,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
) -> JSONResponse:
    """Replaces the target admin's entire permission set (ADR-0040) —
    not an incremental add/remove."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.ADMIN_MANAGEMENT,
            level=AccessLevel.MANAGE,
        )
        before = admin_service.get_admin(target_admin_id)[1]
        permissions = admin_service.update_permissions(
            admin_id=target_admin_id,
            grants=_grants_from_body(list(body.permissions)),
            now=datetime.now(UTC),
        )
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="UPDATE_ADMIN_PERMISSIONS",
            target_type="ADMIN",
            target_id=target_admin_id,
            reason=None,
            before_state={"permissions": [_permission_data(p) for p in before]},
            after_state={"permissions": [_permission_data(p) for p in permissions]},
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {"permissions": [_permission_data(p) for p in permissions]},
            request_id=request_id,
        ),
    )


@router.post("/admins/{target_admin_id}/disable")
async def disable_admin(
    target_admin_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.ADMIN_MANAGEMENT,
            level=AccessLevel.MANAGE,
        )
        admin = admin_service.disable_admin(target_admin_id)
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="DISABLE_ADMIN",
            target_type="ADMIN",
            target_id=target_admin_id,
            reason=None,
            before_state={"status": "ACTIVE"},
            after_state={"status": admin.status},
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_admin_data(admin, []), request_id=request_id),
    )


@router.post("/admins/{target_admin_id}/enable")
async def enable_admin(
    target_admin_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.ADMIN_MANAGEMENT,
            level=AccessLevel.MANAGE,
        )
        admin = admin_service.enable_admin(target_admin_id)
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="ENABLE_ADMIN",
            target_type="ADMIN",
            target_id=target_admin_id,
            reason=None,
            before_state={"status": "DISABLED"},
            after_state={"status": admin.status},
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_admin_data(admin, []), request_id=request_id),
    )


@router.get("/me")
async def get_my_admin_profile(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
) -> JSONResponse:
    """Not gated by require_permission() — every active admin may read
    their own profile/permission set (the Admin Web plan's own §2.2:
    the frontend reads this once at login to gate its own nav/controls;
    the actual enforcement is still server-side on every other route
    regardless of what this returns)."""
    request_id = new_request_id()
    try:
        admin = admin_service.require_active_admin(account_id=admin_account.id)
        _, permissions = admin_service.get_admin(admin_account.id)
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            _admin_data(admin, permissions), request_id=request_id
        ),
    )


# ----------------------------------------------------------------------
# Offers/Coupons — Campaign authoring (ADR-0041). Composes
# modules.promotion, same one-directional composition shape as every
# other module this router composes; modules.promotion's own domain/
# service layer never imports modules.admin.
# ----------------------------------------------------------------------

_VALID_CAMPAIGN_STATUSES = frozenset(status.value for status in CampaignStatus)


def _campaign_data(campaign: Campaign) -> dict[str, object]:
    return {
        "campaign_id": str(campaign.id),
        "code": campaign.code,
        "name": campaign.name,
        "vehicle_category": (
            campaign.vehicle_category.value if campaign.vehicle_category else None
        ),
        "discount_type": campaign.discount_type.value,
        "discount_value": float(campaign.discount_value),
        "max_discount_amount": (
            float(campaign.max_discount_amount)
            if campaign.max_discount_amount is not None
            else None
        ),
        "minimum_fare": (
            float(campaign.minimum_fare) if campaign.minimum_fare is not None else None
        ),
        "eligible_scope": campaign.eligible_scope.value,
        "per_customer_use_limit": campaign.per_customer_use_limit,
        "total_usage_limit": campaign.total_usage_limit,
        "ride_count_limit": campaign.ride_count_limit,
        "starts_at": campaign.starts_at.isoformat(),
        "ends_at": campaign.ends_at.isoformat() if campaign.ends_at else None,
        "status": campaign.status.value,
        "created_by": str(campaign.created_by),
        "created_at": campaign.created_at.isoformat(),
    }


def _vehicle_category_from_body(value: str | None) -> VehicleCategory | None:
    if value is None:
        return None
    return VehicleCategory(value)


@router.post("/campaigns")
async def create_campaign(
    body: CampaignBody,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    promotion_service: Annotated[PromotionService, Depends(get_promotion_service)],
) -> JSONResponse:
    """Create Campaign (ADR-0041 Decision 3) — always starts DRAFT
    (Campaign.new()); Activate Campaign below is the separate step that
    makes it redeemable."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.OFFERS_COUPONS,
            level=AccessLevel.MANAGE,
        )
        campaign = promotion_service.create_campaign(
            code=body.code,
            name=body.name,
            vehicle_category=_vehicle_category_from_body(body.vehicle_category),
            discount_type=body.discount_type,
            discount_value=body.discount_value,
            max_discount_amount=body.max_discount_amount,
            minimum_fare=body.minimum_fare,
            eligible_scope=body.eligible_scope,
            per_customer_use_limit=body.per_customer_use_limit,
            total_usage_limit=body.total_usage_limit,
            ride_count_limit=body.ride_count_limit,
            starts_at=body.starts_at,
            ends_at=body.ends_at,
            eligible_customer_ids=body.eligible_customer_ids,
            created_by=admin_account.id,
            now=datetime.now(UTC),
        )
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="CREATE_CAMPAIGN",
            target_type="CAMPAIGN",
            target_id=campaign.id,
            reason=None,
            before_state=None,
            after_state=_campaign_data(campaign),
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=201,
        content=success_envelope(_campaign_data(campaign), request_id=request_id),
    )


@router.get("/campaigns")
async def list_campaigns(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    promotion_service: Annotated[PromotionService, Depends(get_promotion_service)],
    status: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.OFFERS_COUPONS,
            level=AccessLevel.VIEW,
        )
        if status is not None and status not in _VALID_CAMPAIGN_STATUSES:
            return JSONResponse(
                status_code=422,
                content=error_envelope(
                    "VALIDATION_FAILED",
                    f"Unknown campaign status: {status!r}.",
                    request_id=request_id,
                ),
            )
        params = PageParams.clamp(
            page=page,
            page_size=page_size,
            max_page_size=settings.MAX_PAGE_SIZE,
        )
        campaigns, total = promotion_service.list_campaigns(
            status=CampaignStatus(status) if status else None,
            offset=params.offset,
            limit=params.page_size,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_campaign_data(c) for c in campaigns], params=params, total=total
            ),
            request_id=request_id,
        ),
    )


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    promotion_service: Annotated[PromotionService, Depends(get_promotion_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.OFFERS_COUPONS,
            level=AccessLevel.VIEW,
        )
        campaign = promotion_service.get_campaign(campaign_id)
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_campaign_data(campaign), request_id=request_id),
    )


@router.patch("/campaigns/{campaign_id}")
async def update_campaign(
    campaign_id: uuid.UUID,
    body: CampaignBody,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    promotion_service: Annotated[PromotionService, Depends(get_promotion_service)],
) -> JSONResponse:
    """Edit Campaign — DRAFT only (ADR-0041 Decision 4). Once ACTIVE/
    PAUSED, only status transitions (activate/pause/end below) remain
    available, never the discount terms — same "never rewrite history"
    principle Fare Management applies to published fares."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.OFFERS_COUPONS,
            level=AccessLevel.MANAGE,
        )
        before = promotion_service.get_campaign(campaign_id)
        campaign = promotion_service.update_campaign(
            campaign_id=campaign_id,
            code=body.code,
            name=body.name,
            vehicle_category=_vehicle_category_from_body(body.vehicle_category),
            discount_type=body.discount_type,
            discount_value=body.discount_value,
            max_discount_amount=body.max_discount_amount,
            minimum_fare=body.minimum_fare,
            eligible_scope=body.eligible_scope,
            per_customer_use_limit=body.per_customer_use_limit,
            total_usage_limit=body.total_usage_limit,
            ride_count_limit=body.ride_count_limit,
            starts_at=body.starts_at,
            ends_at=body.ends_at,
            eligible_customer_ids=body.eligible_customer_ids,
        )
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="UPDATE_CAMPAIGN",
            target_type="CAMPAIGN",
            target_id=campaign_id,
            reason=None,
            before_state=_campaign_data(before),
            after_state=_campaign_data(campaign),
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_campaign_data(campaign), request_id=request_id),
    )


def _transition_campaign(
    *,
    campaign_id: uuid.UUID,
    admin_account: Account,
    admin_service: AdminService,
    promotion_service: PromotionService,
    action: str,
    request_id: str,
) -> Campaign:
    admin_service.require_permission(
        account_id=admin_account.id,
        module=AdminModule.OFFERS_COUPONS,
        level=AccessLevel.MANAGE,
    )
    before = promotion_service.get_campaign(campaign_id)
    if action == "activate":
        campaign = promotion_service.activate_campaign(campaign_id=campaign_id)
    elif action == "pause":
        campaign = promotion_service.pause_campaign(campaign_id=campaign_id)
    else:
        campaign = promotion_service.end_campaign(campaign_id=campaign_id)
    admin_service.record_audit_log(
        admin_id=admin_account.id,
        action=f"{action.upper()}_CAMPAIGN",
        target_type="CAMPAIGN",
        target_id=campaign_id,
        reason=None,
        before_state={"status": before.status.value},
        after_state={"status": campaign.status.value},
        request_id=request_id,
    )
    return campaign


@router.post("/campaigns/{campaign_id}/activate")
async def activate_campaign(
    campaign_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    promotion_service: Annotated[PromotionService, Depends(get_promotion_service)],
) -> JSONResponse:
    """DRAFT/PAUSED -> ACTIVE (ADR-0041 Decision 3)."""
    request_id = new_request_id()
    try:
        campaign = _transition_campaign(
            campaign_id=campaign_id,
            admin_account=admin_account,
            admin_service=admin_service,
            promotion_service=promotion_service,
            action="activate",
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_campaign_data(campaign), request_id=request_id),
    )


@router.post("/campaigns/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    promotion_service: Annotated[PromotionService, Depends(get_promotion_service)],
) -> JSONResponse:
    """ACTIVE -> PAUSED (ADR-0041 Decision 3)."""
    request_id = new_request_id()
    try:
        campaign = _transition_campaign(
            campaign_id=campaign_id,
            admin_account=admin_account,
            admin_service=admin_service,
            promotion_service=promotion_service,
            action="pause",
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_campaign_data(campaign), request_id=request_id),
    )


@router.post("/campaigns/{campaign_id}/end")
async def end_campaign(
    campaign_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    promotion_service: Annotated[PromotionService, Depends(get_promotion_service)],
) -> JSONResponse:
    """DRAFT/ACTIVE/PAUSED -> ENDED, terminal (ADR-0041 Decision 3)."""
    request_id = new_request_id()
    try:
        campaign = _transition_campaign(
            campaign_id=campaign_id,
            admin_account=admin_account,
            admin_service=admin_service,
            promotion_service=promotion_service,
            action="end",
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_campaign_data(campaign), request_id=request_id),
    )


@router.post("/campaigns/{campaign_id}/eligible-customers/bulk")
async def bulk_add_eligible_customers(
    campaign_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    promotion_service: Annotated[PromotionService, Depends(get_promotion_service)],
    customer_service: Annotated[CustomerService, Depends(get_customer_service)],
    account_repository: Annotated[
        SqlAlchemyAccountRepository, Depends(get_account_repository)
    ],
    file: Annotated[UploadFile, File()],
) -> JSONResponse:
    """CSV Bulk Customer Targeting (Admin Web §4.10, ADR-0041 §9) —
    additive to the campaign's existing eligible-customer set, unlike
    `eligible_customer_ids` on Create/Edit (which replaces the whole
    set). Each row is resolved to a customer_id via the same two-step
    check Customer Detail's own composition already performs
    (identity.accounts phone lookup, then a customer.customers
    existence check) — an unmatched row is reported back, not silently
    dropped or treated as a whole-request failure (a 100-row CSV with
    3 typos should not force re-uploading the other 97)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.OFFERS_COUPONS,
            level=AccessLevel.MANAGE,
        )

        raw = await file.read()
        try:
            csv_text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return JSONResponse(
                status_code=422,
                content=error_envelope(
                    "VALIDATION_FAILED",
                    "CSV file must be UTF-8 encoded.",
                    request_id=request_id,
                ),
            )

        reader = csv.DictReader(io.StringIO(csv_text))
        if reader.fieldnames is None or "phone" not in reader.fieldnames:
            return JSONResponse(
                status_code=422,
                content=error_envelope(
                    "VALIDATION_FAILED",
                    "CSV must have a header row with a 'phone' column.",
                    request_id=request_id,
                ),
            )

        matched: set[uuid.UUID] = set()
        unmatched: list[dict[str, object]] = []
        # Row numbering includes the header line as row 1 (matching what
        # an admin sees opening the raw file in a text editor/
        # spreadsheet), so the first data row is row 2.
        for row_number, row in enumerate(reader, start=2):
            raw_phone = (row.get("phone") or "").strip()
            try:
                phone = PhoneNumber.parse(raw_phone)
            except InvalidPhoneNumberError:
                unmatched.append(
                    {
                        "row": row_number,
                        "phone": raw_phone,
                        "reason": "invalid phone number",
                    }
                )
                continue

            account = account_repository.get_by_phone(str(phone))
            if account is None:
                unmatched.append(
                    {
                        "row": row_number,
                        "phone": str(phone),
                        "reason": "no customer account",
                    }
                )
                continue

            try:
                customer_service.get_customer_for_admin(account.id)
            except CustomerDomainError:
                unmatched.append(
                    {
                        "row": row_number,
                        "phone": str(phone),
                        "reason": "no customer account",
                    }
                )
                continue

            matched.add(account.id)

        newly_added = promotion_service.bulk_add_eligible_customers(
            campaign_id=campaign_id, customer_ids=list(matched)
        )
        result = {
            "added": len(newly_added),
            "already_eligible": len(matched) - len(newly_added),
            "unmatched": unmatched,
        }
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="BULK_ADD_ELIGIBLE_CUSTOMERS",
            target_type="CAMPAIGN",
            target_id=campaign_id,
            reason=None,
            before_state=None,
            after_state=result,
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(result, request_id=request_id),
    )


# ----------------------------------------------------------------------
# Audit Logs (Admin Web module #18) — read-only search over the
# admin.audit_logs rows every mutating route above already writes via
# record_audit_log(). Not itself audited (same "reads aren't audited"
# precedent Search Rides/Search Penalties already established).
# ----------------------------------------------------------------------


def _audit_log_data(entry: AuditLog) -> dict[str, object]:
    return {
        "id": entry.id,
        "admin_id": str(entry.admin_id),
        "action": entry.action,
        "target_type": entry.target_type,
        "target_id": str(entry.target_id) if entry.target_id else None,
        "reason": entry.reason,
        "before_state": entry.before_state,
        "after_state": entry.after_state,
        "request_id": entry.request_id,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


@router.get("/audit-logs")
async def search_audit_logs(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    admin_id: Annotated[uuid.UUID | None, Query()] = None,
    target_type: Annotated[str | None, Query()] = None,
    target_id: Annotated[uuid.UUID | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    created_after: Annotated[datetime | None, Query()] = None,
    created_before: Annotated[datetime | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """Search Audit Logs — filters match the Admin Web plan's own §4.17
    scoping exactly ("by admin, action, target, date range");
    `target_type`/`target_id` are split rather than one combined
    `target` param, same allow-listed-filter shape Search Rides/Search
    Penalties already use. Newest first."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.AUDIT_LOGS,
            level=AccessLevel.VIEW,
        )
        params = PageParams.clamp(
            page=page,
            page_size=page_size,
            max_page_size=settings.MAX_PAGE_SIZE,
        )
        entries, total = admin_service.search_audit_logs(
            admin_id=admin_id,
            target_type=target_type,
            target_id=target_id,
            action=action,
            created_after=created_after,
            created_before=created_before,
            offset=params.offset,
            limit=params.page_size,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_audit_log_data(e) for e in entries], params=params, total=total
            ),
            request_id=request_id,
        ),
    )


# ----------------------------------------------------------------------
# Customers (Admin Web §4.1) — no admin read surface over
# customer.customers existed at all before this; composes
# modules.customer.
# ----------------------------------------------------------------------


def _customer_data(
    customer: Customer, *, phone: str | None = None
) -> dict[str, object]:
    data: dict[str, object] = {
        "customer_id": str(customer.id),
        "full_name": customer.full_name,
        "profile_photo_uri": customer.profile_photo_uri,
        "status": customer.status.value,
        "language": customer.language,
        "created_at": customer.created_at.isoformat(),
        "updated_at": customer.updated_at.isoformat(),
    }
    if phone is not None:
        data["phone"] = phone
    return data


@router.get("/customers")
async def search_customers(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    customer_service: Annotated[CustomerService, Depends(get_customer_service)],
    query: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """Search/list customers (Admin Web §4.1). `query` matches
    `full_name` only — phone lives in identity.accounts, a separate
    module (see CustomerRepository.search()'s own docstring); list rows
    omit phone for the same reason (no N+1 per-row account lookup),
    Customer Detail below includes it."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.CUSTOMERS,
            level=AccessLevel.VIEW,
        )
        params = PageParams.clamp(
            page=page,
            page_size=page_size,
            max_page_size=settings.MAX_PAGE_SIZE,
        )
        customers, total = customer_service.search_customers(
            query=query, offset=params.offset, limit=params.page_size
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_customer_data(c) for c in customers], params=params, total=total
            ),
            request_id=request_id,
        ),
    )


@router.get("/customers/{customer_id}")
async def get_customer(
    customer_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    customer_service: Annotated[CustomerService, Depends(get_customer_service)],
    account_repository: Annotated[
        SqlAlchemyAccountRepository, Depends(get_account_repository)
    ],
) -> JSONResponse:
    """Customer Detail (Admin Web §4.1). Ride history is the separate,
    already-existing `GET /api/v1/admin/rides?customer_id=` (§46, Search
    Rides) — not duplicated here."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.CUSTOMERS,
            level=AccessLevel.VIEW,
        )
        customer = customer_service.get_customer_for_admin(customer_id)
        account = account_repository.get_by_id(customer_id)
        phone = account.phone if account is not None else None
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            _customer_data(customer, phone=phone), request_id=request_id
        ),
    )


# ----------------------------------------------------------------------
# Drivers / Vehicles / Verification search (Admin Web §4.2/§4.3/§4.4) —
# the plan's own "biggest immediate gap": Driver Review/Approve/Reject
# already existed, but only reachable by an admin who already has the
# id. Suspend/Reactivate compose DriverService methods already built and
# tested (ADR-0021) with no HTTP route until now.
# ----------------------------------------------------------------------


def _driver_summary_data(driver: Driver) -> dict[str, object]:
    # No `phone` (unlike _driver_data above) — avoids an N+1 account
    # lookup per row on a list endpoint; Driver Review (the existing
    # detail endpoint) already includes it.
    return {
        "driver_id": str(driver.id),
        "full_name": driver.full_name,
        "profile_photo_uri": driver.profile_photo_uri,
        "verification_status": driver.verification_status.value,
        "operational_status": driver.operational_status.value,
        "strikes": driver.strikes,
        "created_at": driver.created_at.isoformat(),
    }


@router.get("/drivers")
async def search_drivers(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
    query: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """Search/list drivers (Admin Web §4.2). `status` matches
    verification_status."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.DRIVERS,
            level=AccessLevel.VIEW,
        )
        params = PageParams.clamp(
            page=page,
            page_size=page_size,
            max_page_size=settings.MAX_PAGE_SIZE,
        )
        drivers, total = driver_service.search_drivers(
            query=query, status=status, offset=params.offset, limit=params.page_size
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_driver_summary_data(d) for d in drivers], params=params, total=total
            ),
            request_id=request_id,
        ),
    )


@router.post("/drivers/{driver_id}/suspend")
async def suspend_driver(
    driver_id: uuid.UUID,
    body: RejectBody,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
) -> JSONResponse:
    """Suspend Driver (Admin Web §4.2, ADR-0021) — the service method
    already existed and was tested; only the HTTP route was missing."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.DRIVERS,
            level=AccessLevel.MANAGE,
        )
        driver = driver_service.suspend_driver(driver_id=driver_id, reason=body.reason)
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="SUSPEND_DRIVER",
            target_type="DRIVER",
            target_id=driver_id,
            reason=body.reason,
            before_state=None,
            after_state={"operational_status": driver.operational_status.value},
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_driver_summary_data(driver), request_id=request_id),
    )


@router.post("/drivers/{driver_id}/reactivate")
async def reactivate_driver(
    driver_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
) -> JSONResponse:
    """Reactivate Driver (Admin Web §4.2, ADR-0021) — always lands on
    OFFLINE, never directly ONLINE (see DriverService.reactivate_driver()
    docstring)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.DRIVERS,
            level=AccessLevel.MANAGE,
        )
        driver = driver_service.reactivate_driver(driver_id=driver_id)
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="REACTIVATE_DRIVER",
            target_type="DRIVER",
            target_id=driver_id,
            reason=None,
            before_state={"operational_status": "SUSPENDED"},
            after_state={"operational_status": driver.operational_status.value},
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_driver_summary_data(driver), request_id=request_id),
    )


def _strike_admin_data(strike: Strike) -> dict[str, object]:
    return {
        "strike_id": str(strike.id),
        "driver_id": str(strike.driver_id),
        "ride_id": str(strike.ride_id) if strike.ride_id is not None else None,
        "reason": strike.reason,
        "created_at": strike.created_at.isoformat(),
    }


@router.get("/drivers/{driver_id}/strikes")
async def get_driver_strikes(
    driver_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
    penalty_service: Annotated[PenaltyService, Depends(get_penalty_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """Driver Strike History (Admin Web §4.9, api-contracts.md §46.18)
    — reuses the DRIVERS module (this is driver data, not a new
    module), same reasoning Wallet Transaction History already gives
    for reusing FINANCE. `driver.drivers.strikes` (Driver Review, §46)
    stays the at-a-glance summary counter; this is the underlying
    detail view — a plain read, no status/date filter, since a strike
    is immutable by construction (no update/delete path exists for
    one)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.DRIVERS,
            level=AccessLevel.VIEW,
        )
        # Same existence check Admin Wallet View already does for an
        # unknown driver_id — a driver-scoped detail view should 404,
        # not silently return an empty page for a nonexistent driver.
        driver_service.get_profile(account_id=driver_id)
        params = PageParams.clamp(
            page=page,
            page_size=page_size,
            max_page_size=settings.MAX_PAGE_SIZE,
        )
        strikes, total = penalty_service.list_strikes_for_driver(
            driver_id, offset=params.offset, limit=params.page_size
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_strike_admin_data(s) for s in strikes], params=params, total=total
            ),
            request_id=request_id,
        ),
    )


@router.get("/vehicles")
async def search_vehicles(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    vehicle_service: Annotated[VehicleService, Depends(get_vehicle_service)],
    query: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """Search/list vehicles (Admin Web §4.3). `query` matches
    registration_number; `status` matches verification_status."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.VEHICLES,
            level=AccessLevel.VIEW,
        )
        params = PageParams.clamp(
            page=page,
            page_size=page_size,
            max_page_size=settings.MAX_PAGE_SIZE,
        )
        vehicles, total = vehicle_service.search_vehicles(
            query=query, status=status, offset=params.offset, limit=params.page_size
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_vehicle_data(v) for v in vehicles], params=params, total=total
            ),
            request_id=request_id,
        ),
    )


@router.get("/vehicles/{vehicle_id}")
async def get_vehicle(
    vehicle_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    vehicle_service: Annotated[VehicleService, Depends(get_vehicle_service)],
) -> JSONResponse:
    """Vehicle Detail (Admin Web §4.3) — no ownership restriction,
    admin-only, same shape as Get Ride's own relationship to the
    driver/customer-facing equivalents."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.VEHICLES,
            level=AccessLevel.VIEW,
        )
        vehicle = vehicle_service.get_vehicle_for_admin(vehicle_id)
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_vehicle_data(vehicle), request_id=request_id),
    )


def _vehicle_document_data(document: VehicleDocument) -> dict[str, object]:
    return {
        "document_id": str(document.id),
        "vehicle_id": str(document.vehicle_id),
        "document_type": document.document_type,
        "document_number": document.document_number,
        "evidence_uri": document.evidence_uri,
        "verification_status": document.verification_status.value,
        "expires_at": document.expires_at.isoformat() if document.expires_at else None,
        "created_at": document.created_at.isoformat(),
    }


@router.get("/vehicles/{vehicle_id}/documents")
async def list_vehicle_documents(
    vehicle_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    vehicle_service: Annotated[VehicleService, Depends(get_vehicle_service)],
    vehicle_document_service: Annotated[
        VehicleDocumentService, Depends(get_vehicle_document_service)
    ],
) -> JSONResponse:
    """Vehicle document list (Admin Web §4.4) — vehicle documents had no
    admin visibility anywhere before this; driver documents are already
    nested inside Driver Review."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.VERIFICATION,
            level=AccessLevel.VIEW,
        )
        vehicle_service.get_vehicle_for_admin(vehicle_id)  # 404s an unknown id
        documents = vehicle_document_service.list_documents(vehicle_id=vehicle_id)
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {"documents": [_vehicle_document_data(d) for d in documents]},
            request_id=request_id,
        ),
    )


def _verification_case_data(case: VerificationCase) -> dict[str, object]:
    return {
        "case_id": str(case.id),
        "subject_type": case.subject_type,
        "subject_id": str(case.subject_id),
        "verification_type": case.verification_type.value,
        "status": case.status.value,
        "created_at": case.created_at.isoformat(),
        "completed_at": case.completed_at.isoformat() if case.completed_at else None,
    }


@router.get("/verification/queue")
async def search_verification_queue(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    verification_service: Annotated[
        VerificationService, Depends(get_verification_service)
    ],
    status: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """Pending-review queue (Admin Web §4.4), across every subject
    (driver + vehicle documents) — `status` omitted returns every case;
    the Admin Web's own screen is expected to default to status=PENDING
    client-side."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.VERIFICATION,
            level=AccessLevel.VIEW,
        )
        params = PageParams.clamp(
            page=page,
            page_size=page_size,
            max_page_size=settings.MAX_PAGE_SIZE,
        )
        cases, total = verification_service.search_cases(
            status=status, offset=params.offset, limit=params.page_size
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_verification_case_data(c) for c in cases], params=params, total=total
            ),
            request_id=request_id,
        ),
    )


# ----------------------------------------------------------------------
# Referrals (Admin Web §4.11) — no admin read surface over
# referral.referrals existed at all before this; composes
# modules.referral.
# ----------------------------------------------------------------------

_VALID_REFERRAL_STATUSES = frozenset(status.value for status in ReferralStatus)


def _reward_summary_data(reward: Reward) -> dict[str, object]:
    return {
        "reward_id": str(reward.id),
        "recipient_id": str(reward.recipient_id),
        "reward_type": reward.reward_type.value,
        "amount": float(reward.amount) if reward.amount is not None else None,
        "promotion_uses": reward.promotion_uses,
        "status": reward.status.value,
        "created_at": reward.created_at.isoformat(),
    }


def _referral_data(referral: Referral, rewards: list[Reward]) -> dict[str, object]:
    return {
        "referral_id": str(referral.id),
        "referrer_id": str(referral.referrer_id),
        "referred_id": str(referral.referred_id),
        "referred_type": referral.referred_type.value,
        "status": referral.status.value,
        "activated_at": referral.activated_at.isoformat()
        if referral.activated_at
        else None,
        "created_at": referral.created_at.isoformat(),
        "rewards": [_reward_summary_data(r) for r in rewards],
    }


@router.get("/referrals")
async def search_referrals(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    referral_service: Annotated[ReferralService, Depends(get_referral_service)],
    status: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """Search/list referrals (Admin Web §4.11) — each row's own reward(s)
    composed in (typically zero or one; RecordReward is idempotent per
    key but nothing prevents two distinct rewards existing for one
    referral over time, e.g. a re-triggered composition with a new
    key)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.REFERRALS,
            level=AccessLevel.VIEW,
        )
        if status is not None and status not in _VALID_REFERRAL_STATUSES:
            return JSONResponse(
                status_code=422,
                content=error_envelope(
                    "VALIDATION_FAILED",
                    f"Unknown referral status: {status!r}.",
                    request_id=request_id,
                ),
            )
        params = PageParams.clamp(
            page=page,
            page_size=page_size,
            max_page_size=settings.MAX_PAGE_SIZE,
        )
        referrals, total = referral_service.search_referrals(
            status=ReferralStatus(status) if status else None,
            offset=params.offset,
            limit=params.page_size,
        )
        items = [
            _referral_data(r, referral_service.list_rewards_for_referral(r.id))
            for r in referrals
        ]
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(items, params=params, total=total),
            request_id=request_id,
        ),
    )


# ----------------------------------------------------------------------
# Referral Reward Configuration (Admin Web §4.11, ADR-0043,
# api-contracts.md §46.12). Two independent config streams — a driver
# bonus rule (single global policy) and a customer reward rule (one per
# reward_type) — sharing the same DRAFT -> IN_REVIEW -> PUBLISHED
# lifecycle Fare Management (§4.8) established. Only Create/List/Get/
# Submit-for-Review/Publish are built; no Edit/Reject, same as Fare
# Management.
# ----------------------------------------------------------------------

_VALID_REWARD_CONFIG_STATUSES = frozenset(status.value for status in RewardConfigStatus)


def _driver_bonus_rule_data(rule: DriverBonusRule) -> dict[str, object]:
    return {
        "rule_id": str(rule.id),
        "referred_amount": float(rule.referred_amount),
        "referrer_amount": float(rule.referrer_amount),
        "status": rule.status.value,
        "effective_from": rule.effective_from.isoformat()
        if rule.effective_from
        else None,
        "effective_until": rule.effective_until.isoformat()
        if rule.effective_until
        else None,
        "created_at": rule.created_at.isoformat(),
    }


def _customer_reward_rule_data(rule: CustomerRewardRule) -> dict[str, object]:
    return {
        "rule_id": str(rule.id),
        "reward_type": rule.reward_type,
        "discount_percent": float(rule.discount_percent),
        "total_uses": rule.total_uses,
        "status": rule.status.value,
        "effective_from": rule.effective_from.isoformat()
        if rule.effective_from
        else None,
        "effective_until": rule.effective_until.isoformat()
        if rule.effective_until
        else None,
        "created_at": rule.created_at.isoformat(),
    }


@router.post("/referral-config/driver-bonus")
async def create_driver_bonus_rule(
    body: CreateDriverBonusRuleBody,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    referral_service: Annotated[ReferralService, Depends(get_referral_service)],
) -> JSONResponse:
    """Create Draft driver-bonus rule (Admin Web §4.11, ADR-0043)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.REFERRALS,
            level=AccessLevel.MANAGE,
        )
        rule = referral_service.create_driver_bonus_rule(
            referred_amount=body.referred_amount,
            referrer_amount=body.referrer_amount,
            created_by=admin_account.id,
            now=datetime.now(UTC),
        )
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="CREATE_DRIVER_BONUS_RULE",
            target_type="DRIVER_BONUS_RULE",
            target_id=rule.id,
            reason=None,
            before_state=None,
            after_state=_driver_bonus_rule_data(rule),
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=201,
        content=success_envelope(_driver_bonus_rule_data(rule), request_id=request_id),
    )


@router.get("/referral-config/driver-bonus")
async def list_driver_bonus_rules(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    referral_service: Annotated[ReferralService, Depends(get_referral_service)],
    status: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """List driver-bonus rules, with version history (Admin Web §4.11)
    — every status, not just PUBLISHED."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.REFERRALS,
            level=AccessLevel.VIEW,
        )
        if status is not None and status not in _VALID_REWARD_CONFIG_STATUSES:
            return JSONResponse(
                status_code=422,
                content=error_envelope(
                    "VALIDATION_FAILED",
                    f"Unknown reward config status: {status!r}.",
                    request_id=request_id,
                ),
            )
        params = PageParams.clamp(
            page=page,
            page_size=page_size,
            max_page_size=settings.MAX_PAGE_SIZE,
        )
        rules, total = referral_service.list_driver_bonus_rules(
            status=status, offset=params.offset, limit=params.page_size
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_driver_bonus_rule_data(r) for r in rules],
                params=params,
                total=total,
            ),
            request_id=request_id,
        ),
    )


@router.get("/referral-config/driver-bonus/{rule_id}")
async def get_driver_bonus_rule(
    rule_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    referral_service: Annotated[ReferralService, Depends(get_referral_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.REFERRALS,
            level=AccessLevel.VIEW,
        )
        rule = referral_service.get_driver_bonus_rule(rule_id)
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_driver_bonus_rule_data(rule), request_id=request_id),
    )


@router.post("/referral-config/driver-bonus/{rule_id}/submit-for-review")
async def submit_driver_bonus_rule_for_review(
    rule_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    referral_service: Annotated[ReferralService, Depends(get_referral_service)],
) -> JSONResponse:
    """DRAFT -> IN_REVIEW (Admin Web §4.11, ADR-0043)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.REFERRALS,
            level=AccessLevel.MANAGE,
        )
        rule = referral_service.submit_driver_bonus_rule_for_review(rule_id)
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="SUBMIT_DRIVER_BONUS_RULE_FOR_REVIEW",
            target_type="DRIVER_BONUS_RULE",
            target_id=rule_id,
            reason=None,
            before_state={"status": "DRAFT"},
            after_state={"status": rule.status.value},
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_driver_bonus_rule_data(rule), request_id=request_id),
    )


@router.post("/referral-config/driver-bonus/{rule_id}/publish")
async def publish_driver_bonus_rule(
    rule_id: uuid.UUID,
    body: PublishRewardConfigBody,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    referral_service: Annotated[ReferralService, Depends(get_referral_service)],
) -> JSONResponse:
    """(DRAFT or IN_REVIEW) -> PUBLISHED (Admin Web §4.11, ADR-0043) —
    closes out the previously-published driver-bonus rule (there is
    only ever one global policy), if one exists."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.REFERRALS,
            level=AccessLevel.MANAGE,
        )
        before = referral_service.get_driver_bonus_rule(rule_id)
        rule = referral_service.publish_driver_bonus_rule(
            rule_id=rule_id,
            effective_from=body.effective_from,
            now=datetime.now(UTC),
        )
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="PUBLISH_DRIVER_BONUS_RULE",
            target_type="DRIVER_BONUS_RULE",
            target_id=rule_id,
            reason=None,
            before_state={"status": before.status.value},
            after_state=_driver_bonus_rule_data(rule),
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_driver_bonus_rule_data(rule), request_id=request_id),
    )


@router.post("/referral-config/customer-rewards")
async def create_customer_reward_rule(
    body: CreateCustomerRewardRuleBody,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    referral_service: Annotated[ReferralService, Depends(get_referral_service)],
) -> JSONResponse:
    """Create Draft customer-reward rule (Admin Web §4.11, ADR-0043)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.REFERRALS,
            level=AccessLevel.MANAGE,
        )
        rule = referral_service.create_customer_reward_rule(
            reward_type=body.reward_type,
            discount_percent=body.discount_percent,
            total_uses=body.total_uses,
            created_by=admin_account.id,
            now=datetime.now(UTC),
        )
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="CREATE_CUSTOMER_REWARD_RULE",
            target_type="CUSTOMER_REWARD_RULE",
            target_id=rule.id,
            reason=None,
            before_state=None,
            after_state=_customer_reward_rule_data(rule),
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=201,
        content=success_envelope(
            _customer_reward_rule_data(rule), request_id=request_id
        ),
    )


@router.get("/referral-config/customer-rewards")
async def list_customer_reward_rules(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    referral_service: Annotated[ReferralService, Depends(get_referral_service)],
    reward_type: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """List customer-reward rules, with version history (Admin Web
    §4.11) — every status, not just PUBLISHED."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.REFERRALS,
            level=AccessLevel.VIEW,
        )
        if status is not None and status not in _VALID_REWARD_CONFIG_STATUSES:
            return JSONResponse(
                status_code=422,
                content=error_envelope(
                    "VALIDATION_FAILED",
                    f"Unknown reward config status: {status!r}.",
                    request_id=request_id,
                ),
            )
        params = PageParams.clamp(
            page=page,
            page_size=page_size,
            max_page_size=settings.MAX_PAGE_SIZE,
        )
        rules, total = referral_service.list_customer_reward_rules(
            reward_type=reward_type,
            status=status,
            offset=params.offset,
            limit=params.page_size,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_customer_reward_rule_data(r) for r in rules],
                params=params,
                total=total,
            ),
            request_id=request_id,
        ),
    )


@router.get("/referral-config/customer-rewards/{rule_id}")
async def get_customer_reward_rule(
    rule_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    referral_service: Annotated[ReferralService, Depends(get_referral_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.REFERRALS,
            level=AccessLevel.VIEW,
        )
        rule = referral_service.get_customer_reward_rule(rule_id)
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            _customer_reward_rule_data(rule), request_id=request_id
        ),
    )


@router.post("/referral-config/customer-rewards/{rule_id}/submit-for-review")
async def submit_customer_reward_rule_for_review(
    rule_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    referral_service: Annotated[ReferralService, Depends(get_referral_service)],
) -> JSONResponse:
    """DRAFT -> IN_REVIEW (Admin Web §4.11, ADR-0043)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.REFERRALS,
            level=AccessLevel.MANAGE,
        )
        rule = referral_service.submit_customer_reward_rule_for_review(rule_id)
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="SUBMIT_CUSTOMER_REWARD_RULE_FOR_REVIEW",
            target_type="CUSTOMER_REWARD_RULE",
            target_id=rule_id,
            reason=None,
            before_state={"status": "DRAFT"},
            after_state={"status": rule.status.value},
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            _customer_reward_rule_data(rule), request_id=request_id
        ),
    )


@router.post("/referral-config/customer-rewards/{rule_id}/publish")
async def publish_customer_reward_rule(
    rule_id: uuid.UUID,
    body: PublishRewardConfigBody,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    referral_service: Annotated[ReferralService, Depends(get_referral_service)],
) -> JSONResponse:
    """(DRAFT or IN_REVIEW) -> PUBLISHED (Admin Web §4.11, ADR-0043) —
    closes out the previously-published rule for the same reward_type,
    if one exists."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.REFERRALS,
            level=AccessLevel.MANAGE,
        )
        before = referral_service.get_customer_reward_rule(rule_id)
        rule = referral_service.publish_customer_reward_rule(
            rule_id=rule_id,
            effective_from=body.effective_from,
            now=datetime.now(UTC),
        )
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="PUBLISH_CUSTOMER_REWARD_RULE",
            target_type="CUSTOMER_REWARD_RULE",
            target_id=rule_id,
            reason=None,
            before_state={"status": before.status.value},
            after_state=_customer_reward_rule_data(rule),
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            _customer_reward_rule_data(rule), request_id=request_id
        ),
    )


# ----------------------------------------------------------------------
# Fare Management (Admin Web §4.8, ADR-0042). Composes modules.pricing.
# No source document names an "Edit"/"Reject" action for a fare rule —
# only Create (DRAFT) -> Submit for Review -> Publish are built, exactly
# ADR-0042 Decision 3's scope.
# ----------------------------------------------------------------------

_VALID_FARE_RULE_STATUSES = frozenset(status.value for status in FareRuleStatus)


def _fare_rule_data(rule: FareRule) -> dict[str, object]:
    return {
        "rule_id": str(rule.id),
        "vehicle_category": rule.vehicle_category,
        "base_fare": float(rule.base_fare),
        "per_km": float(rule.per_km),
        "per_minute": float(rule.per_minute),
        "waiting_per_minute": float(rule.waiting_per_minute),
        "minimum_fare": float(rule.minimum_fare),
        "status": rule.status.value,
        "effective_from": rule.effective_from.isoformat()
        if rule.effective_from
        else None,
        "effective_until": rule.effective_until.isoformat()
        if rule.effective_until
        else None,
        "created_at": rule.created_at.isoformat(),
    }


@router.post("/fare-rules")
async def create_fare_rule(
    body: CreateFareRuleBody,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    pricing_service: Annotated[PricingService, Depends(get_pricing_service)],
) -> JSONResponse:
    """Create Draft Fare Rule (Admin Web §4.8, ADR-0042)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.FARE_MANAGEMENT,
            level=AccessLevel.MANAGE,
        )
        rule = pricing_service.create_fare_rule(
            vehicle_category=body.vehicle_category,
            base_fare=body.base_fare,
            per_km=body.per_km,
            per_minute=body.per_minute,
            waiting_per_minute=body.waiting_per_minute,
            minimum_fare=body.minimum_fare,
            now=datetime.now(UTC),
        )
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="CREATE_FARE_RULE",
            target_type="FARE_RULE",
            target_id=rule.id,
            reason=None,
            before_state=None,
            after_state=_fare_rule_data(rule),
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=201,
        content=success_envelope(_fare_rule_data(rule), request_id=request_id),
    )


@router.get("/fare-rules")
async def list_fare_rules(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    pricing_service: Annotated[PricingService, Depends(get_pricing_service)],
    vehicle_category: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """List Fare Rules, with version history (Admin Web §4.8, ADR-0042
    Decision 4) — every status, not just PUBLISHED."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.FARE_MANAGEMENT,
            level=AccessLevel.VIEW,
        )
        if status is not None and status not in _VALID_FARE_RULE_STATUSES:
            return JSONResponse(
                status_code=422,
                content=error_envelope(
                    "VALIDATION_FAILED",
                    f"Unknown fare rule status: {status!r}.",
                    request_id=request_id,
                ),
            )
        params = PageParams.clamp(
            page=page,
            page_size=page_size,
            max_page_size=settings.MAX_PAGE_SIZE,
        )
        rules, total = pricing_service.list_fare_rules(
            vehicle_category=vehicle_category,
            status=status,
            offset=params.offset,
            limit=params.page_size,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_fare_rule_data(r) for r in rules], params=params, total=total
            ),
            request_id=request_id,
        ),
    )


@router.get("/fare-rules/{rule_id}")
async def get_fare_rule(
    rule_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    pricing_service: Annotated[PricingService, Depends(get_pricing_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.FARE_MANAGEMENT,
            level=AccessLevel.VIEW,
        )
        rule = pricing_service.get_fare_rule(rule_id)
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_fare_rule_data(rule), request_id=request_id),
    )


@router.post("/fare-rules/{rule_id}/submit-for-review")
async def submit_fare_rule_for_review(
    rule_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    pricing_service: Annotated[PricingService, Depends(get_pricing_service)],
) -> JSONResponse:
    """DRAFT -> IN_REVIEW (Admin Web §4.8, ADR-0042)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.FARE_MANAGEMENT,
            level=AccessLevel.MANAGE,
        )
        rule = pricing_service.submit_fare_rule_for_review(rule_id)
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="SUBMIT_FARE_RULE_FOR_REVIEW",
            target_type="FARE_RULE",
            target_id=rule_id,
            reason=None,
            before_state={"status": "DRAFT"},
            after_state={"status": rule.status.value},
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_fare_rule_data(rule), request_id=request_id),
    )


@router.post("/fare-rules/{rule_id}/publish")
async def publish_fare_rule(
    rule_id: uuid.UUID,
    body: PublishFareRuleBody,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    pricing_service: Annotated[PricingService, Depends(get_pricing_service)],
) -> JSONResponse:
    """(DRAFT or IN_REVIEW) -> PUBLISHED (Admin Web §4.8, ADR-0042
    Decision 2/3) — closes out the previously-published rule for the
    same vehicle_category, if one exists."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.FARE_MANAGEMENT,
            level=AccessLevel.MANAGE,
        )
        before = pricing_service.get_fare_rule(rule_id)
        now = datetime.now(UTC)
        rule = pricing_service.publish_fare_rule(
            rule_id=rule_id, effective_from=body.effective_from, now=now
        )
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="PUBLISH_FARE_RULE",
            target_type="FARE_RULE",
            target_id=rule_id,
            reason=None,
            before_state={"status": before.status.value},
            after_state=_fare_rule_data(rule),
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_fare_rule_data(rule), request_id=request_id),
    )


# ----------------------------------------------------------------------
# Platform Fee Management (Admin Web §4.8's own new row, ADR-0045).
# Composes modules.pricing — identical DRAFT -> IN_REVIEW -> PUBLISHED
# lifecycle and endpoint shape to Fare Management above, a separate
# table (driver economics, not customer fare). Permission key FINANCE,
# not FARE_MANAGEMENT (ADR-0045 Decision 3) — an admin who can already
# see/adjust a driver's wallet needs this same trust level, and fare
# vs. platform-fee access are deliberately independent levers.
# ----------------------------------------------------------------------

_VALID_PLATFORM_FEE_RULE_STATUSES = frozenset(status.value for status in FareRuleStatus)


def _platform_fee_rule_data(rule: PlatformFeeRule) -> dict[str, object]:
    return {
        "rule_id": str(rule.id),
        "vehicle_category": rule.vehicle_category,
        "fee_amount": float(rule.fee_amount),
        "status": rule.status.value,
        "effective_from": rule.effective_from.isoformat()
        if rule.effective_from
        else None,
        "effective_until": rule.effective_until.isoformat()
        if rule.effective_until
        else None,
        "created_at": rule.created_at.isoformat(),
    }


@router.post("/platform-fee-rules")
async def create_platform_fee_rule(
    body: CreatePlatformFeeRuleBody,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    pricing_service: Annotated[PricingService, Depends(get_pricing_service)],
) -> JSONResponse:
    """Create Draft Platform Fee Rule (Admin Web §4.8, ADR-0045)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.FINANCE,
            level=AccessLevel.MANAGE,
        )
        rule = pricing_service.create_platform_fee_rule(
            vehicle_category=body.vehicle_category,
            fee_amount=body.fee_amount,
            created_by=admin_account.id,
            now=datetime.now(UTC),
        )
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="CREATE_PLATFORM_FEE_RULE",
            target_type="PLATFORM_FEE_RULE",
            target_id=rule.id,
            reason=None,
            before_state=None,
            after_state=_platform_fee_rule_data(rule),
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=201,
        content=success_envelope(_platform_fee_rule_data(rule), request_id=request_id),
    )


@router.get("/platform-fee-rules")
async def list_platform_fee_rules(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    pricing_service: Annotated[PricingService, Depends(get_pricing_service)],
    vehicle_category: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """List platform fee rules, with version history (Admin Web §4.8)
    — every status, not just PUBLISHED."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.FINANCE,
            level=AccessLevel.VIEW,
        )
        if status is not None and status not in _VALID_PLATFORM_FEE_RULE_STATUSES:
            return JSONResponse(
                status_code=422,
                content=error_envelope(
                    "VALIDATION_FAILED",
                    f"Unknown platform fee rule status: {status!r}.",
                    request_id=request_id,
                ),
            )
        params = PageParams.clamp(
            page=page,
            page_size=page_size,
            max_page_size=settings.MAX_PAGE_SIZE,
        )
        rules, total = pricing_service.list_platform_fee_rules(
            vehicle_category=vehicle_category,
            status=status,
            offset=params.offset,
            limit=params.page_size,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_platform_fee_rule_data(r) for r in rules],
                params=params,
                total=total,
            ),
            request_id=request_id,
        ),
    )


@router.get("/platform-fee-rules/{rule_id}")
async def get_platform_fee_rule(
    rule_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    pricing_service: Annotated[PricingService, Depends(get_pricing_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.FINANCE,
            level=AccessLevel.VIEW,
        )
        rule = pricing_service.get_platform_fee_rule(rule_id)
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_platform_fee_rule_data(rule), request_id=request_id),
    )


@router.post("/platform-fee-rules/{rule_id}/submit-for-review")
async def submit_platform_fee_rule_for_review(
    rule_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    pricing_service: Annotated[PricingService, Depends(get_pricing_service)],
) -> JSONResponse:
    """DRAFT -> IN_REVIEW (Admin Web §4.8, ADR-0045)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.FINANCE,
            level=AccessLevel.MANAGE,
        )
        rule = pricing_service.submit_platform_fee_rule_for_review(rule_id)
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="SUBMIT_PLATFORM_FEE_RULE_FOR_REVIEW",
            target_type="PLATFORM_FEE_RULE",
            target_id=rule_id,
            reason=None,
            before_state={"status": "DRAFT"},
            after_state={"status": rule.status.value},
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_platform_fee_rule_data(rule), request_id=request_id),
    )


@router.post("/platform-fee-rules/{rule_id}/publish")
async def publish_platform_fee_rule(
    rule_id: uuid.UUID,
    body: PublishPlatformFeeRuleBody,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    pricing_service: Annotated[PricingService, Depends(get_pricing_service)],
) -> JSONResponse:
    """(DRAFT or IN_REVIEW) -> PUBLISHED (Admin Web §4.8, ADR-0045) —
    closes out the previously-published rule for the same
    vehicle_category, if one exists."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.FINANCE,
            level=AccessLevel.MANAGE,
        )
        before = pricing_service.get_platform_fee_rule(rule_id)
        now = datetime.now(UTC)
        rule = pricing_service.publish_platform_fee_rule(
            rule_id=rule_id, effective_from=body.effective_from, now=now
        )
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="PUBLISH_PLATFORM_FEE_RULE",
            target_type="PLATFORM_FEE_RULE",
            target_id=rule_id,
            reason=None,
            before_state={"status": before.status.value},
            after_state=_platform_fee_rule_data(rule),
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_platform_fee_rule_data(rule), request_id=request_id),
    )


# ----------------------------------------------------------------------
# Safety / SOS (Admin Web §4.13). Composes modules.safety —
# Acknowledge/Escalate/Resolve already existed at the service layer and
# were fully tested (ADR-0022); only the HTTP routes were missing, same
# "service exists, no route" gap as Driver Suspension.
# ----------------------------------------------------------------------

_VALID_INCIDENT_STATUSES = frozenset(
    {"OPEN", "ACKNOWLEDGED", "IN_PROGRESS", "RESOLVED", "CLOSED"}
)


def _safety_incident_data(incident: SafetyIncident) -> dict[str, object]:
    return {
        "incident_id": str(incident.id),
        "ride_id": str(incident.ride_id) if incident.ride_id else None,
        "reporter_id": str(incident.reporter_id),
        "incident_type": incident.incident_type,
        "status": incident.status.value,
        "location": (
            {
                "latitude": incident.location.latitude,
                "longitude": incident.location.longitude,
            }
            if incident.location
            else None
        ),
        "created_at": incident.created_at.isoformat(),
        "resolved_at": incident.resolved_at.isoformat()
        if incident.resolved_at
        else None,
    }


@router.get("/safety/incidents")
async def search_safety_incidents(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    safety_service: Annotated[SafetyService, Depends(get_safety_service)],
    status: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """Incident Queue (Admin Web §4.13)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.SAFETY,
            level=AccessLevel.VIEW,
        )
        if status is not None and status not in _VALID_INCIDENT_STATUSES:
            return JSONResponse(
                status_code=422,
                content=error_envelope(
                    "VALIDATION_FAILED",
                    f"Unknown incident status: {status!r}.",
                    request_id=request_id,
                ),
            )
        params = PageParams.clamp(
            page=page,
            page_size=page_size,
            max_page_size=settings.MAX_PAGE_SIZE,
        )
        incidents, total = safety_service.search_incidents(
            status=status, offset=params.offset, limit=params.page_size
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_safety_incident_data(i) for i in incidents],
                params=params,
                total=total,
            ),
            request_id=request_id,
        ),
    )


@router.get("/safety/incidents/{incident_id}")
async def get_safety_incident(
    incident_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    safety_service: Annotated[SafetyService, Depends(get_safety_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.SAFETY,
            level=AccessLevel.VIEW,
        )
        incident = safety_service.get_incident(incident_id=incident_id)
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            _safety_incident_data(incident), request_id=request_id
        ),
    )


def _transition_safety_incident(
    *,
    incident_id: uuid.UUID,
    admin_account: Account,
    admin_service: AdminService,
    safety_service: SafetyService,
    action: str,
    request_id: str,
) -> SafetyIncident:
    admin_service.require_permission(
        account_id=admin_account.id,
        module=AdminModule.SAFETY,
        level=AccessLevel.MANAGE,
    )
    before = safety_service.get_incident(incident_id=incident_id)
    now = datetime.now(UTC)
    if action == "acknowledge":
        incident = safety_service.acknowledge_incident(
            incident_id=incident_id, actor_id=admin_account.id, now=now
        )
    elif action == "escalate":
        incident = safety_service.escalate_incident(
            incident_id=incident_id, actor_id=admin_account.id, now=now
        )
    else:
        incident = safety_service.resolve_incident(
            incident_id=incident_id, actor_id=admin_account.id, now=now
        )
    admin_service.record_audit_log(
        admin_id=admin_account.id,
        action=f"{action.upper()}_SAFETY_INCIDENT",
        target_type="SAFETY_INCIDENT",
        target_id=incident_id,
        reason=None,
        before_state={"status": before.status.value},
        after_state={"status": incident.status.value},
        request_id=request_id,
    )
    return incident


@router.post("/safety/incidents/{incident_id}/acknowledge")
async def acknowledge_safety_incident(
    incident_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    safety_service: Annotated[SafetyService, Depends(get_safety_service)],
) -> JSONResponse:
    """OPEN -> ACKNOWLEDGED (Admin Web §4.13, state-machines.md §45)."""
    request_id = new_request_id()
    try:
        incident = _transition_safety_incident(
            incident_id=incident_id,
            admin_account=admin_account,
            admin_service=admin_service,
            safety_service=safety_service,
            action="acknowledge",
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            _safety_incident_data(incident), request_id=request_id
        ),
    )


@router.post("/safety/incidents/{incident_id}/escalate")
async def escalate_safety_incident(
    incident_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    safety_service: Annotated[SafetyService, Depends(get_safety_service)],
) -> JSONResponse:
    """ACKNOWLEDGED -> IN_PROGRESS (Admin Web §4.13, ADR-0022 Decision 3).
    Never contacts a real emergency service — see SafetyService's own
    docstring."""
    request_id = new_request_id()
    try:
        incident = _transition_safety_incident(
            incident_id=incident_id,
            admin_account=admin_account,
            admin_service=admin_service,
            safety_service=safety_service,
            action="escalate",
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            _safety_incident_data(incident), request_id=request_id
        ),
    )


@router.post("/safety/incidents/{incident_id}/resolve")
async def resolve_safety_incident(
    incident_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    safety_service: Annotated[SafetyService, Depends(get_safety_service)],
) -> JSONResponse:
    """IN_PROGRESS -> RESOLVED (Admin Web §4.13)."""
    request_id = new_request_id()
    try:
        incident = _transition_safety_incident(
            incident_id=incident_id,
            admin_account=admin_account,
            admin_service=admin_service,
            safety_service=safety_service,
            action="resolve",
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            _safety_incident_data(incident), request_id=request_id
        ),
    )


# ----------------------------------------------------------------------
# Support / Disputes (Admin Web §4.14). Composes modules.support.
# Resolve Case already existed at the service layer (turned out the
# plan's own "NEEDS SCOPING" note predates it) — only Search and Case
# Detail are genuinely new. "Assign case" is NOT built here: no source
# document names it as an Admin Web screen (§4.14's table lists only
# Search/Detail/Resolve/GPS-Dispute), even though
# SupportService.assign_case() also already exists.
# ----------------------------------------------------------------------

_VALID_SUPPORT_CASE_STATUSES = frozenset(
    {"OPEN", "ASSIGNED", "IN_PROGRESS", "WAITING_FOR_USER", "RESOLVED", "CLOSED"}
)


def _support_case_data(
    case: SupportCase, messages: list[SupportMessage] | None = None
) -> dict[str, object]:
    data: dict[str, object] = {
        "case_id": str(case.id),
        "user_id": str(case.user_id),
        "ride_id": str(case.ride_id) if case.ride_id else None,
        "category": case.category,
        "priority": case.priority,
        "status": case.status.value,
        "assigned_admin_id": (
            str(case.assigned_admin_id) if case.assigned_admin_id else None
        ),
        "created_at": case.created_at.isoformat(),
        "updated_at": case.updated_at.isoformat(),
    }
    if messages is not None:
        data["messages"] = [
            {
                "message_id": str(m.id),
                "sender_type": m.sender_type.value,
                "sender_id": str(m.sender_id) if m.sender_id else None,
                "message": m.message,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ]
    return data


@router.get("/support/cases")
async def search_support_cases(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    support_service: Annotated[SupportService, Depends(get_support_service)],
    status: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """Search/list all support cases (Admin Web §4.14)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.SUPPORT,
            level=AccessLevel.VIEW,
        )
        if status is not None and status not in _VALID_SUPPORT_CASE_STATUSES:
            return JSONResponse(
                status_code=422,
                content=error_envelope(
                    "VALIDATION_FAILED",
                    f"Unknown support case status: {status!r}.",
                    request_id=request_id,
                ),
            )
        params = PageParams.clamp(
            page=page,
            page_size=page_size,
            max_page_size=settings.MAX_PAGE_SIZE,
        )
        cases, total = support_service.search_cases(
            status=status, offset=params.offset, limit=params.page_size
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_support_case_data(c) for c in cases], params=params, total=total
            ),
            request_id=request_id,
        ),
    )


@router.get("/support/cases/{case_id}")
async def get_support_case(
    case_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    support_service: Annotated[SupportService, Depends(get_support_service)],
) -> JSONResponse:
    """Case Detail (Admin Web §4.14) — distinct from the existing
    owner-only `GET /cases/{id}`, which an admin using their own
    admin_id would fail the IDOR ownership check against."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.SUPPORT,
            level=AccessLevel.VIEW,
        )
        case, messages = support_service.get_case_with_messages(case_id=case_id)
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            _support_case_data(case, messages), request_id=request_id
        ),
    )


@router.post("/support/cases/{case_id}/resolve")
async def resolve_support_case(
    case_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    support_service: Annotated[SupportService, Depends(get_support_service)],
) -> JSONResponse:
    """Resolve/close case (Admin Web §4.14) — valid from any status
    except already RESOLVED/CLOSED."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.SUPPORT,
            level=AccessLevel.MANAGE,
        )
        before, _messages = support_service.get_case_with_messages(case_id=case_id)
        case = support_service.resolve_case(case_id=case_id, now=datetime.now(UTC))
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="RESOLVE_SUPPORT_CASE",
            target_type="SUPPORT_CASE",
            target_id=case_id,
            reason=None,
            before_state={"status": before.status.value},
            after_state={"status": case.status.value},
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_support_case_data(case), request_id=request_id),
    )


# ----------------------------------------------------------------------
# Notifications (Admin Web §4.12). Composes modules.notification.
# "Notification history / delivery status" is read-only:
# `notification.deliveries` already exists and is populated by real
# triggers (ride.rides accepted/arrived events via the Kafka consumer,
# ADR-0034/ADR-0038). Notification Template Management (ADR-0044) is
# now also built — Create Draft (next version) -> Publish, no Edit-in-
# place. Compose/Send/Schedule Broadcast, Audience Selection, and
# device-token registration remain NOT built and NEEDS SCOPING
# (ADR-0034 Decision 2; ADR-0044 §6) — Templates makes message
# *content* editable, it does not add a way to send an ad hoc
# admin-composed message.
# ----------------------------------------------------------------------

_VALID_DELIVERY_CHANNELS = frozenset(c.value for c in Channel)
_VALID_DELIVERY_STATUSES = frozenset(s.value for s in DeliveryStatus)


def _delivery_data(delivery: Delivery) -> dict[str, object]:
    return {
        "delivery_id": str(delivery.id),
        "user_id": str(delivery.user_id),
        "channel": delivery.channel.value,
        "template_key": delivery.template_key,
        "event_id": str(delivery.event_id) if delivery.event_id else None,
        "status": delivery.status.value,
        "provider_reference": delivery.provider_reference,
        "created_at": delivery.created_at.isoformat(),
        "delivered_at": delivery.delivered_at.isoformat()
        if delivery.delivered_at
        else None,
        # ADR-0075 — 0 (never retried) or 1 (retried once, whichever way
        # it landed); the only observable, admin-visible signal that the
        # bounded FAILED-SMS/PUSH retry task actually ran for this row.
        "retry_count": delivery.retry_count,
    }


@router.get("/notifications/deliveries")
async def search_notification_deliveries(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    notification_service: Annotated[
        NotificationService, Depends(get_notification_service)
    ],
    user_id: Annotated[uuid.UUID | None, Query()] = None,
    channel: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """Notification history / delivery status (Admin Web §4.12)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.NOTIFICATIONS,
            level=AccessLevel.VIEW,
        )
        if channel is not None and channel not in _VALID_DELIVERY_CHANNELS:
            return JSONResponse(
                status_code=422,
                content=error_envelope(
                    "VALIDATION_FAILED",
                    f"Unknown channel: {channel!r}.",
                    request_id=request_id,
                ),
            )
        if status is not None and status not in _VALID_DELIVERY_STATUSES:
            return JSONResponse(
                status_code=422,
                content=error_envelope(
                    "VALIDATION_FAILED",
                    f"Unknown delivery status: {status!r}.",
                    request_id=request_id,
                ),
            )
        params = PageParams.clamp(
            page=page,
            page_size=page_size,
            max_page_size=settings.MAX_PAGE_SIZE,
        )
        deliveries, total = notification_service.search_deliveries(
            user_id=user_id,
            channel=channel,
            status=status,
            offset=params.offset,
            limit=params.page_size,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_delivery_data(d) for d in deliveries], params=params, total=total
            ),
            request_id=request_id,
        ),
    )


_VALID_TEMPLATE_STATUSES = frozenset(status.value for status in TemplateStatus)


def _template_data(template: Template) -> dict[str, object]:
    return {
        "template_id": str(template.id),
        "template_key": template.template_key,
        "channel": template.channel,
        "event_key": template.event_key,
        "title": template.title,
        "body": template.body,
        "version": template.version,
        "status": template.status.value,
        "created_at": template.created_at.isoformat(),
    }


@router.post("/notifications/templates")
async def create_template(
    body: CreateTemplateBody,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    notification_service: Annotated[
        NotificationService, Depends(get_notification_service)
    ],
) -> JSONResponse:
    """Create Draft — version 1, or the next version of an existing
    (template_key, channel) pair (Admin Web §4.12, ADR-0044)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.NOTIFICATIONS,
            level=AccessLevel.MANAGE,
        )
        template = notification_service.create_template(
            template_key=body.template_key,
            channel=body.channel,
            event_key=body.event_key,
            title=body.title,
            body=body.body,
            created_by=admin_account.id,
            now=datetime.now(UTC),
        )
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="CREATE_NOTIFICATION_TEMPLATE",
            target_type="NOTIFICATION_TEMPLATE",
            target_id=template.id,
            reason=None,
            before_state=None,
            after_state=_template_data(template),
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=201,
        content=success_envelope(_template_data(template), request_id=request_id),
    )


@router.get("/notifications/templates")
async def list_templates(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    notification_service: Annotated[
        NotificationService, Depends(get_notification_service)
    ],
    template_key: Annotated[str | None, Query()] = None,
    channel: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """Version history (Admin Web §4.12) — every version, not only
    PUBLISHED, by default."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.NOTIFICATIONS,
            level=AccessLevel.VIEW,
        )
        if channel is not None and channel not in _VALID_DELIVERY_CHANNELS:
            return JSONResponse(
                status_code=422,
                content=error_envelope(
                    "VALIDATION_FAILED",
                    f"Unknown channel: {channel!r}.",
                    request_id=request_id,
                ),
            )
        if status is not None and status not in _VALID_TEMPLATE_STATUSES:
            return JSONResponse(
                status_code=422,
                content=error_envelope(
                    "VALIDATION_FAILED",
                    f"Unknown template status: {status!r}.",
                    request_id=request_id,
                ),
            )
        params = PageParams.clamp(
            page=page,
            page_size=page_size,
            max_page_size=settings.MAX_PAGE_SIZE,
        )
        templates, total = notification_service.list_templates(
            template_key=template_key,
            channel=channel,
            status=status,
            offset=params.offset,
            limit=params.page_size,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_template_data(t) for t in templates], params=params, total=total
            ),
            request_id=request_id,
        ),
    )


@router.get("/notifications/templates/{template_id}")
async def get_template(
    template_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    notification_service: Annotated[
        NotificationService, Depends(get_notification_service)
    ],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.NOTIFICATIONS,
            level=AccessLevel.VIEW,
        )
        template = notification_service.get_template(template_id)
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_template_data(template), request_id=request_id),
    )


@router.post("/notifications/templates/{template_id}/publish")
async def publish_template(
    template_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    notification_service: Annotated[
        NotificationService, Depends(get_notification_service)
    ],
) -> JSONResponse:
    """DRAFT -> PUBLISHED; archives (not deletes) the prior PUBLISHED
    version for the same (template_key, channel), if any (Admin Web
    §4.12, ADR-0044)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.NOTIFICATIONS,
            level=AccessLevel.MANAGE,
        )
        before = notification_service.get_template(template_id)
        template = notification_service.publish_template(template_id)
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="PUBLISH_NOTIFICATION_TEMPLATE",
            target_type="NOTIFICATION_TEMPLATE",
            target_id=template_id,
            reason=None,
            before_state={"status": before.status.value},
            after_state=_template_data(template),
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_template_data(template), request_id=request_id),
    )


_VALID_BROADCAST_CHANNELS = frozenset(
    channel.value for channel in Channel if channel is not Channel.WHATSAPP
)
_VALID_AUDIENCE_TYPES = frozenset(audience.value for audience in AudienceType)
_VALID_BROADCAST_STATUSES = frozenset(status.value for status in BroadcastStatus)


def _broadcast_data(broadcast: Broadcast) -> dict[str, object]:
    return {
        "broadcast_id": str(broadcast.id),
        "channel": broadcast.channel.value,
        "subject": broadcast.subject,
        "body": broadcast.body,
        "audience_type": broadcast.audience_type.value,
        "audience_user_ids": [str(uid) for uid in broadcast.audience_user_ids]
        if broadcast.audience_user_ids
        else None,
        "status": broadcast.status.value,
        "scheduled_at": broadcast.scheduled_at.isoformat()
        if broadcast.scheduled_at
        else None,
        "sent_count": broadcast.sent_count,
        "failed_count": broadcast.failed_count,
        "created_by": str(broadcast.created_by),
        "created_at": broadcast.created_at.isoformat(),
        "sent_at": broadcast.sent_at.isoformat() if broadcast.sent_at else None,
    }


@router.post("/notifications/broadcasts")
async def create_broadcast(
    body: CreateBroadcastBody,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    notification_service: Annotated[
        NotificationService, Depends(get_notification_service)
    ],
    customer_service: Annotated[CustomerService, Depends(get_customer_service)],
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
    accounts: Annotated[SqlAlchemyAccountRepository, Depends(get_account_repository)],
    redis_client: Annotated[Redis, Depends(get_redis)],
) -> JSONResponse:
    """Compose/Send Broadcast + Audience Selection (Admin Web §4.12,
    ADR-0055, Tier C). Publishes a broadcast-only Template under the
    hood (ADR-0044's own "manual/admin-broadcast use only" case), then
    — when `scheduled_at` resolves to "now" — dispatches immediately,
    synchronously, in this same request (audience resolution + a
    NotificationService.send() call per recipient); a future
    `scheduled_at` instead leaves the broadcast SCHEDULED for the
    periodic Celery Beat task (modules/notification/tasks.py) to
    dispatch later. Requires MANAGE — this sends real messages to real
    users, the same bar Template create/publish already sets."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.NOTIFICATIONS,
            level=AccessLevel.MANAGE,
        )
        if body.channel not in _VALID_BROADCAST_CHANNELS:
            return JSONResponse(
                status_code=422,
                content=error_envelope(
                    "VALIDATION_FAILED",
                    f"Unknown or unavailable channel: {body.channel!r}.",
                    request_id=request_id,
                ),
            )
        if body.audience_type not in _VALID_AUDIENCE_TYPES:
            return JSONResponse(
                status_code=422,
                content=error_envelope(
                    "VALIDATION_FAILED",
                    f"Unknown audience_type: {body.audience_type!r}.",
                    request_id=request_id,
                ),
            )
        now = datetime.now(UTC)
        broadcast = notification_service.create_broadcast(
            channel=Channel(body.channel),
            subject=body.subject,
            body=body.body,
            audience_type=AudienceType(body.audience_type),
            audience_user_ids=body.audience_user_ids,
            scheduled_at=body.scheduled_at,
            created_by=admin_account.id,
            now=now,
        )
        if broadcast.scheduled_at is None:
            sent_count, failed_count = await dispatch_broadcast(
                broadcast=broadcast,
                notification_service=notification_service,
                accounts=accounts,
                customer_service=customer_service,
                driver_service=driver_service,
                redis_client=redis_client,
                now=now,
            )
            broadcast = notification_service.mark_broadcast_sent(
                broadcast.id,
                sent_count=sent_count,
                failed_count=failed_count,
                now=datetime.now(UTC),
            )
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="CREATE_NOTIFICATION_BROADCAST",
            target_type="NOTIFICATION_BROADCAST",
            target_id=broadcast.id,
            reason=None,
            before_state=None,
            # Recipient count, not the full id list — keeps the audit
            # row bounded even for an "all customers"-sized audience
            # (ADR-0055 §5).
            after_state={
                "channel": broadcast.channel.value,
                "audience_type": broadcast.audience_type.value,
                "status": broadcast.status.value,
                "sent_count": broadcast.sent_count,
                "failed_count": broadcast.failed_count,
            },
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=201,
        content=success_envelope(_broadcast_data(broadcast), request_id=request_id),
    )


@router.get("/notifications/broadcasts")
async def search_broadcasts(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    notification_service: Annotated[
        NotificationService, Depends(get_notification_service)
    ],
    status: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """Broadcast history (Admin Web §4.12, ADR-0055) — newest first."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.NOTIFICATIONS,
            level=AccessLevel.VIEW,
        )
        if status is not None and status not in _VALID_BROADCAST_STATUSES:
            return JSONResponse(
                status_code=422,
                content=error_envelope(
                    "VALIDATION_FAILED",
                    f"Unknown broadcast status: {status!r}.",
                    request_id=request_id,
                ),
            )
        params = PageParams.clamp(
            page=page,
            page_size=page_size,
            max_page_size=settings.MAX_PAGE_SIZE,
        )
        broadcasts, total = notification_service.search_broadcasts(
            status=status,
            offset=params.offset,
            limit=params.page_size,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_broadcast_data(b) for b in broadcasts], params=params, total=total
            ),
            request_id=request_id,
        ),
    )


@router.get("/notifications/broadcasts/{broadcast_id}")
async def get_broadcast(
    broadcast_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    notification_service: Annotated[
        NotificationService, Depends(get_notification_service)
    ],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.NOTIFICATIONS,
            level=AccessLevel.VIEW,
        )
        broadcast = notification_service.get_broadcast(broadcast_id)
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_broadcast_data(broadcast), request_id=request_id),
    )


# ----------------------------------------------------------------------
# Advertisements (Admin Web §4.15, ADR-0046). Composes the already-
# implemented modules.advertisement.AdvertisementService (ADR-0018) —
# no domain/service logic changes beyond the new PAUSED/ENDED campaign
# statuses (Decision 1). "Admoto verification status" means exposing
# the existing manual `verification_status` field through
# .../assignments/{id}/verify — it does not call Admoto or any external
# provider (ADR-0018 Item 3 stays deferred, see Decision 2). A driver-
# facing proof-*submission* endpoint is NOT built here — this is the
# admin surface only (Decision 4).
# ----------------------------------------------------------------------

_VALID_AD_CAMPAIGN_STATUSES = frozenset(status.value for status in AdCampaignStatus)
_VALID_AD_PAYOUT_STATUSES = frozenset(status.value for status in PayoutStatus)


def _ad_campaign_data(campaign: AdCampaign) -> dict[str, object]:
    return {
        "campaign_id": str(campaign.id),
        "partner_name": campaign.partner_name,
        "status": campaign.status.value,
        "payout_amount": float(campaign.payout_amount),
        "driver_share_percent": float(campaign.driver_share_percent),
        "vistaar_share_percent": float(campaign.vistaar_share_percent),
        "starts_at": campaign.starts_at.isoformat() if campaign.starts_at else None,
        "ends_at": campaign.ends_at.isoformat() if campaign.ends_at else None,
        "created_at": campaign.created_at.isoformat(),
    }


def _ad_assignment_data(assignment: DriverCampaign) -> dict[str, object]:
    return {
        "assignment_id": str(assignment.id),
        "campaign_id": str(assignment.campaign_id),
        "driver_id": str(assignment.driver_id),
        "status": assignment.status.value,
        "proof_uri": assignment.proof_uri,
        "verification_status": assignment.verification_status.value
        if assignment.verification_status
        else None,
        "assigned_at": assignment.assigned_at.isoformat(),
    }


def _ad_payout_data(payout: Payout) -> dict[str, object]:
    return {
        "payout_id": str(payout.id),
        "driver_campaign_id": str(payout.driver_campaign_id),
        "gross_amount": float(payout.gross_amount),
        "driver_amount": float(payout.driver_amount),
        "vistaar_amount": float(payout.vistaar_amount),
        "status": payout.status.value,
        "created_at": payout.created_at.isoformat(),
    }


@router.post("/advertisements/campaigns")
async def create_ad_campaign(
    body: CreateCampaignBody,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    ad_service: Annotated[AdvertisementService, Depends(get_advertisement_service)],
) -> JSONResponse:
    """Create Campaign (Admin Web §4.15, ADR-0046) — always starts
    ACTIVE, no draft/approval gate (ADR-0018 Decision 2, unchanged)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.ADVERTISEMENTS,
            level=AccessLevel.MANAGE,
        )
        campaign = ad_service.create_campaign(
            partner_name=body.partner_name,
            payout_amount=body.payout_amount,
            driver_share_percent=body.driver_share_percent,
            vistaar_share_percent=body.vistaar_share_percent,
            starts_at=body.starts_at,
            ends_at=body.ends_at,
            now=datetime.now(UTC),
        )
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="CREATE_AD_CAMPAIGN",
            target_type="AD_CAMPAIGN",
            target_id=campaign.id,
            reason=None,
            before_state=None,
            after_state=_ad_campaign_data(campaign),
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=201,
        content=success_envelope(_ad_campaign_data(campaign), request_id=request_id),
    )


@router.get("/advertisements/campaigns")
async def list_ad_campaigns(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    ad_service: Annotated[AdvertisementService, Depends(get_advertisement_service)],
    status: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """List/Search campaigns (Admin Web §4.15)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.ADVERTISEMENTS,
            level=AccessLevel.VIEW,
        )
        if status is not None and status not in _VALID_AD_CAMPAIGN_STATUSES:
            return JSONResponse(
                status_code=422,
                content=error_envelope(
                    "VALIDATION_FAILED",
                    f"Unknown campaign status: {status!r}.",
                    request_id=request_id,
                ),
            )
        params = PageParams.clamp(
            page=page,
            page_size=page_size,
            max_page_size=settings.MAX_PAGE_SIZE,
        )
        campaigns, total = ad_service.list_campaigns(
            status=status, offset=params.offset, limit=params.page_size
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_ad_campaign_data(c) for c in campaigns], params=params, total=total
            ),
            request_id=request_id,
        ),
    )


@router.get("/advertisements/campaigns/{campaign_id}")
async def get_ad_campaign(
    campaign_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    ad_service: Annotated[AdvertisementService, Depends(get_advertisement_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.ADVERTISEMENTS,
            level=AccessLevel.VIEW,
        )
        campaign = ad_service.get_campaign(campaign_id)
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_ad_campaign_data(campaign), request_id=request_id),
    )


async def _transition_ad_campaign(
    *,
    campaign_id: uuid.UUID,
    admin_account: Account,
    admin_service: AdminService,
    ad_service: AdvertisementService,
    action: str,
    audit_action: str,
) -> JSONResponse:
    """Shared body for pause/resume/end — same handler shape, only the
    service method and audit action name differ."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.ADVERTISEMENTS,
            level=AccessLevel.MANAGE,
        )
        before = ad_service.get_campaign(campaign_id)
        transition = {
            "pause": ad_service.pause_campaign,
            "resume": ad_service.resume_campaign,
            "end": ad_service.end_campaign,
        }[action]
        campaign = transition(campaign_id)
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action=audit_action,
            target_type="AD_CAMPAIGN",
            target_id=campaign_id,
            reason=None,
            before_state={"status": before.status.value},
            after_state=_ad_campaign_data(campaign),
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_ad_campaign_data(campaign), request_id=request_id),
    )


@router.post("/advertisements/campaigns/{campaign_id}/pause")
async def pause_ad_campaign(
    campaign_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    ad_service: Annotated[AdvertisementService, Depends(get_advertisement_service)],
) -> JSONResponse:
    """ACTIVE -> PAUSED (Admin Web §4.15, ADR-0046 Decision 1) — stops
    new driver assignments; assignments already in flight are
    unaffected."""
    return await _transition_ad_campaign(
        campaign_id=campaign_id,
        admin_account=admin_account,
        admin_service=admin_service,
        ad_service=ad_service,
        action="pause",
        audit_action="PAUSE_AD_CAMPAIGN",
    )


@router.post("/advertisements/campaigns/{campaign_id}/resume")
async def resume_ad_campaign(
    campaign_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    ad_service: Annotated[AdvertisementService, Depends(get_advertisement_service)],
) -> JSONResponse:
    """PAUSED -> ACTIVE (Admin Web §4.15, ADR-0046 Decision 1)."""
    return await _transition_ad_campaign(
        campaign_id=campaign_id,
        admin_account=admin_account,
        admin_service=admin_service,
        ad_service=ad_service,
        action="resume",
        audit_action="RESUME_AD_CAMPAIGN",
    )


@router.post("/advertisements/campaigns/{campaign_id}/end")
async def end_ad_campaign(
    campaign_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    ad_service: Annotated[AdvertisementService, Depends(get_advertisement_service)],
) -> JSONResponse:
    """(ACTIVE or PAUSED) -> ENDED, terminal (Admin Web §4.15, ADR-0046
    Decision 1)."""
    return await _transition_ad_campaign(
        campaign_id=campaign_id,
        admin_account=admin_account,
        admin_service=admin_service,
        ad_service=ad_service,
        action="end",
        audit_action="END_AD_CAMPAIGN",
    )


@router.post("/advertisements/campaigns/{campaign_id}/assignments")
async def assign_ad_campaign_driver(
    campaign_id: uuid.UUID,
    body: AssignDriverBody,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    ad_service: Annotated[AdvertisementService, Depends(get_advertisement_service)],
) -> JSONResponse:
    """Assign Driver (Admin Web §4.15, ADR-0046) — rejected
    (CampaignNotActiveError, 409) if the campaign is PAUSED/ENDED."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.ADVERTISEMENTS,
            level=AccessLevel.MANAGE,
        )
        assignment = ad_service.assign_driver(
            campaign_id=campaign_id, driver_id=body.driver_id, now=datetime.now(UTC)
        )
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="ASSIGN_AD_CAMPAIGN_DRIVER",
            target_type="AD_ASSIGNMENT",
            target_id=assignment.id,
            reason=None,
            before_state=None,
            after_state=_ad_assignment_data(assignment),
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=201,
        content=success_envelope(
            _ad_assignment_data(assignment), request_id=request_id
        ),
    )


@router.get("/advertisements/assignments")
async def search_ad_assignments(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    ad_service: Annotated[AdvertisementService, Depends(get_advertisement_service)],
    campaign_id: Annotated[uuid.UUID | None, Query()] = None,
    driver_id: Annotated[uuid.UUID | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """Installation/proof review queue (Admin Web §4.15)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.ADVERTISEMENTS,
            level=AccessLevel.VIEW,
        )
        params = PageParams.clamp(
            page=page,
            page_size=page_size,
            max_page_size=settings.MAX_PAGE_SIZE,
        )
        assignments, total = ad_service.search_assignments(
            campaign_id=campaign_id,
            driver_id=driver_id,
            status=status,
            offset=params.offset,
            limit=params.page_size,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_ad_assignment_data(a) for a in assignments],
                params=params,
                total=total,
            ),
            request_id=request_id,
        ),
    )


@router.get("/advertisements/assignments/{assignment_id}")
async def get_ad_assignment(
    assignment_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    ad_service: Annotated[AdvertisementService, Depends(get_advertisement_service)],
) -> JSONResponse:
    """Includes `proof_uri`/`verification_status` — the field
    colloquially called "Admoto verification status" (ADR-0046 Decision
    2); set manually here, not by a live Admoto call."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.ADVERTISEMENTS,
            level=AccessLevel.VIEW,
        )
        assignment = ad_service.get_assignment(assignment_id)
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            _ad_assignment_data(assignment), request_id=request_id
        ),
    )


@router.post("/advertisements/assignments/{assignment_id}/verify")
async def verify_ad_assignment(
    assignment_id: uuid.UUID,
    body: VerifyAssignmentBody,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    ad_service: Annotated[AdvertisementService, Depends(get_advertisement_service)],
) -> JSONResponse:
    """Approve/Reject proof (Admin Web §4.15, ADR-0046 Decision 2) — a
    manual admin decision, not a live Admoto call."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.ADVERTISEMENTS,
            level=AccessLevel.MANAGE,
        )
        before = ad_service.get_assignment(assignment_id)
        assignment = ad_service.verify_advertisement(
            assignment_id=assignment_id,
            approved=body.approved,
            now=datetime.now(UTC),
        )
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="VERIFY_AD_ASSIGNMENT",
            target_type="AD_ASSIGNMENT",
            target_id=assignment_id,
            reason=None,
            before_state={"status": before.status.value},
            after_state=_ad_assignment_data(assignment),
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            _ad_assignment_data(assignment), request_id=request_id
        ),
    )


@router.post("/advertisements/assignments/{assignment_id}/payouts/calculate")
async def calculate_ad_payout(
    assignment_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    ad_service: Annotated[AdvertisementService, Depends(get_advertisement_service)],
) -> JSONResponse:
    """CalculatePayout (Admin Web §4.15) — only a VERIFIED assignment
    can have a payout calculated; at most one payout per assignment
    (uq_payouts_driver_campaign)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.ADVERTISEMENTS,
            level=AccessLevel.MANAGE,
        )
        payout = ad_service.calculate_payout(
            assignment_id=assignment_id, now=datetime.now(UTC)
        )
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="CALCULATE_AD_PAYOUT",
            target_type="AD_PAYOUT",
            target_id=payout.id,
            reason=None,
            before_state=None,
            after_state=_ad_payout_data(payout),
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=201,
        content=success_envelope(_ad_payout_data(payout), request_id=request_id),
    )


@router.get("/advertisements/payouts")
async def list_ad_payouts(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    ad_service: Annotated[AdvertisementService, Depends(get_advertisement_service)],
    status: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """Payout/settlement monitoring (Admin Web §4.15)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.ADVERTISEMENTS,
            level=AccessLevel.VIEW,
        )
        if status is not None and status not in _VALID_AD_PAYOUT_STATUSES:
            return JSONResponse(
                status_code=422,
                content=error_envelope(
                    "VALIDATION_FAILED",
                    f"Unknown payout status: {status!r}.",
                    request_id=request_id,
                ),
            )
        params = PageParams.clamp(
            page=page,
            page_size=page_size,
            max_page_size=settings.MAX_PAGE_SIZE,
        )
        payouts, total = ad_service.list_payouts(
            status=status, offset=params.offset, limit=params.page_size
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_ad_payout_data(p) for p in payouts], params=params, total=total
            ),
            request_id=request_id,
        ),
    )


@router.post("/advertisements/payouts/{payout_id}/settle")
async def settle_ad_payout(
    payout_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    ad_service: Annotated[AdvertisementService, Depends(get_advertisement_service)],
    wallet_service: Annotated[WalletService, Depends(get_wallet_service)],
) -> JSONResponse:
    """Composes WalletService.credit(ADVERTISEMENT_PAYOUT) then
    mark_payout_paid() (Admin Web §4.15, ADR-0046 Decision 4) — the
    exact sequence tests/test_advertisement_integration.py's own
    worked-example test already demonstrates."""
    request_id = new_request_id()
    now = datetime.now(UTC)
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.ADVERTISEMENTS,
            level=AccessLevel.MANAGE,
        )
        payout = ad_service.get_payout(payout_id)
        assignment = ad_service.get_assignment(payout.driver_campaign_id)
        wallet_service.credit(
            driver_id=assignment.driver_id,
            amount=payout.driver_amount,
            transaction_type=TransactionType.ADVERTISEMENT_PAYOUT.value,
            ride_id=None,
            idempotency_key=f"advertisement-payout:{payout.id}",
            now=now,
        )
        settled = ad_service.mark_payout_paid(payout_id=payout_id)
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="SETTLE_AD_PAYOUT",
            target_type="AD_PAYOUT",
            target_id=payout_id,
            reason=None,
            before_state={"status": payout.status.value},
            after_state=_ad_payout_data(settled),
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_ad_payout_data(settled), request_id=request_id),
    )


# ----------------------------------------------------------------------
# Settings (Admin Web §4.19, ADR-0048). A fixed, closed vocabulary of
# keys seeded by migration f2c6a819e3b4 — no Create/Delete endpoint
# (Decision 3). PATCH is the only mutation and is always audited, same
# shape as every other admin mutation in this file.
# ----------------------------------------------------------------------


def _setting_data(setting: Setting) -> dict[str, object]:
    return {
        "key": setting.key,
        "value": setting.value,
        "category": setting.category.value,
        "description": setting.description,
        "updated_by": str(setting.updated_by),
        "updated_at": setting.updated_at.isoformat(),
    }


@router.get("/settings")
async def list_settings(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    category: Annotated[str | None, Query()] = None,
) -> JSONResponse:
    """List Settings, grouped by category (Admin Web §4.19)."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.SETTINGS,
            level=AccessLevel.VIEW,
        )
        if category is not None and category not in set(SettingCategory):
            return JSONResponse(
                status_code=422,
                content=error_envelope(
                    "VALIDATION_FAILED",
                    f"Unknown setting category: {category!r}.",
                    request_id=request_id,
                ),
            )
        rules = admin_service.list_settings(category=category)
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            [_setting_data(r) for r in rules], request_id=request_id
        ),
    )


@router.get("/settings/{key}")
async def get_setting(
    key: str,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.SETTINGS,
            level=AccessLevel.VIEW,
        )
        setting = admin_service.get_setting(key)
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_setting_data(setting), request_id=request_id),
    )


@router.patch("/settings/{key}")
async def update_setting(
    key: str,
    body: UpdateSettingBody,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
) -> JSONResponse:
    """Update Setting (Admin Web §4.19, ADR-0048 Decision 3) — an
    overwrite, not a lifecycle transition (no draft/review/publish,
    unlike Fare/Platform Fee Management): nothing reads admin.settings
    live at the moment of a financial transaction, so there's no
    "previous version stays authoritative until published" concern
    here."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.SETTINGS,
            level=AccessLevel.MANAGE,
        )
        before = admin_service.get_setting(key)
        setting = admin_service.update_setting(
            key=key,
            value=body.value,
            updated_by=admin_account.id,
            now=datetime.now(UTC),
        )
        admin_service.record_audit_log(
            admin_id=admin_account.id,
            action="UPDATE_SETTING",
            target_type="SETTING",
            target_id=None,
            reason=None,
            before_state=_setting_data(before),
            after_state=_setting_data(setting),
            request_id=request_id,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_setting_data(setting), request_id=request_id),
    )


# ----------------------------------------------------------------------
# Reports / Analytics (Admin Web §4.16, ADR-0047). Nine fixed-shape
# aggregate endpoints, each a small set of real COUNT/SUM/AVG numbers
# over an optional `from`/`to` date range — deliberately NOT a generic
# query builder (Decision 1: that would be the "separate data
# warehouse" the owner said not to build). No new table, no new
# schema — every number composes a narrowly-scoped aggregate method
# added to each domain's own existing repository this same task. VIEW
# only; nothing here mutates data, so no audit logging (matching every
# other pure-read admin endpoint in this file, e.g. list_fare_rules).
# "Online drivers"/real-time operational state is NOT included here
# either, for the identical Redis-staleness reason the Dashboard
# excludes it (Decision 2).
# ----------------------------------------------------------------------

_DEFAULT_REPORT_WINDOW_DAYS = 30


def _report_range(
    *, from_: datetime | None, to: datetime | None, now: datetime
) -> tuple[datetime, datetime]:
    """`to` defaults to now; `from_` defaults to
    `_DEFAULT_REPORT_WINDOW_DAYS` before that — an implementation
    detail (ADR-0047 §2), not a business rule."""
    until = to if to is not None else now
    since = (
        from_
        if from_ is not None
        else until - timedelta(days=_DEFAULT_REPORT_WINDOW_DAYS)
    )
    return since, until


def _rate(numerator: int, denominator: int) -> float:
    """0 if there's nothing to divide by — never a ZeroDivisionError,
    matching every "rate" field ADR-0047 §2 documents (e.g.
    completion_rate, delivery_success_rate)."""
    return numerator / denominator if denominator else 0.0


@router.get("/reports/rides")
async def get_rides_report(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
    pricing_service: Annotated[PricingService, Depends(get_pricing_service)],
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.REPORTS,
            level=AccessLevel.VIEW,
        )
        since, until = _report_range(from_=from_, to=to, now=datetime.now(UTC))
        rides_by_status = ride_service.count_rides_by_status_in_range(
            since=since, until=until
        )
        rides_by_vehicle_category = (
            ride_service.count_rides_by_vehicle_category_in_range(
                since=since, until=until
            )
        )
        fare_quote_ids = ride_service.list_active_fare_quote_ids_for_closed_in_range(
            since=since, until=until
        )
        average_fare = pricing_service.average_fare_total_for_ids(fare_quote_ids)
        closed = rides_by_status.get("CLOSED", 0)
        cancelled = rides_by_status.get("CANCELLED", 0)
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "from": since.isoformat(),
                "to": until.isoformat(),
                "rides_by_status": rides_by_status,
                "rides_by_vehicle_category": rides_by_vehicle_category,
                "average_fare": float(average_fare),
                "completion_rate": _rate(closed, closed + cancelled),
            },
            request_id=request_id,
        ),
    )


@router.get("/reports/customers")
async def get_customers_report(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    customer_service: Annotated[CustomerService, Depends(get_customer_service)],
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.REPORTS,
            level=AccessLevel.VIEW,
        )
        since, until = _report_range(from_=from_, to=to, now=datetime.now(UTC))
        total_customers = customer_service.count_total_customers()
        new_customers_in_range = customer_service.count_new_customers_in_range(
            since=since, until=until
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "from": since.isoformat(),
                "to": until.isoformat(),
                "total_customers": total_customers,
                "new_customers_in_range": new_customers_in_range,
            },
            request_id=request_id,
        ),
    )


@router.get("/reports/drivers")
async def get_drivers_report(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.REPORTS,
            level=AccessLevel.VIEW,
        )
        since, until = _report_range(from_=from_, to=to, now=datetime.now(UTC))
        total_drivers = driver_service.count_total_drivers()
        by_verification_status = driver_service.count_drivers_by_verification_status()
        by_operational_status = driver_service.count_drivers_by_operational_status()
        new_drivers_in_range = driver_service.count_new_drivers_in_range(
            since=since, until=until
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "from": since.isoformat(),
                "to": until.isoformat(),
                "total_drivers": total_drivers,
                "by_verification_status": by_verification_status,
                "by_operational_status": by_operational_status,
                "new_drivers_in_range": new_drivers_in_range,
            },
            request_id=request_id,
        ),
    )


@router.get("/reports/financial")
async def get_financial_report(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    wallet_service: Annotated[WalletService, Depends(get_wallet_service)],
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.REPORTS,
            level=AccessLevel.VIEW,
        )
        since, until = _report_range(from_=from_, to=to, now=datetime.now(UTC))
        platform_fee_collected = wallet_service.sum_by_type_and_direction_in_range(
            transaction_type=TransactionType.PLATFORM_FEE.value,
            direction="DEBIT",
            since=since,
            until=until,
        )
        fee_reversals = wallet_service.sum_by_type_and_direction_in_range(
            transaction_type=TransactionType.FEE_REVERSAL.value,
            direction="CREDIT",
            since=since,
            until=until,
        )
        driver_referral_bonuses_paid = (
            wallet_service.sum_by_type_and_direction_in_range(
                transaction_type=TransactionType.DRIVER_REFERRAL_BONUS.value,
                direction="CREDIT",
                since=since,
                until=until,
            )
        )
        advertisement_payouts = wallet_service.sum_by_type_and_direction_in_range(
            transaction_type=TransactionType.ADVERTISEMENT_PAYOUT.value,
            direction="CREDIT",
            since=since,
            until=until,
        )
        by_transaction_type = wallet_service.count_transactions_by_type_in_range(
            since=since, until=until
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "from": since.isoformat(),
                "to": until.isoformat(),
                "platform_fee_collected": float(platform_fee_collected),
                "fee_reversals": float(fee_reversals),
                "driver_referral_bonuses_paid": float(driver_referral_bonuses_paid),
                "advertisement_payouts": float(advertisement_payouts),
                "by_transaction_type": by_transaction_type,
            },
            request_id=request_id,
        ),
    )


@router.get("/reports/penalties")
async def get_penalties_report(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    penalty_service: Annotated[PenaltyService, Depends(get_penalty_service)],
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.REPORTS,
            level=AccessLevel.VIEW,
        )
        since, until = _report_range(from_=from_, to=to, now=datetime.now(UTC))
        penalties_by_status = penalty_service.count_penalties_by_status()
        penalties_by_type = penalty_service.count_penalties_by_type()
        total_amount_outstanding = penalty_service.sum_penalty_amount_outstanding()
        total_amount_settled_in_range = (
            penalty_service.sum_penalty_amount_settled_in_range(
                since=since, until=until
            )
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "from": since.isoformat(),
                "to": until.isoformat(),
                "penalties_by_status": penalties_by_status,
                "penalties_by_type": penalties_by_type,
                "total_amount_outstanding": float(total_amount_outstanding),
                "total_amount_settled_in_range": float(total_amount_settled_in_range),
            },
            request_id=request_id,
        ),
    )


@router.get("/reports/promotions-referrals")
async def get_promotions_referrals_report(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    promotion_service: Annotated[PromotionService, Depends(get_promotion_service)],
    referral_service: Annotated[ReferralService, Depends(get_referral_service)],
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.REPORTS,
            level=AccessLevel.VIEW,
        )
        since, until = _report_range(from_=from_, to=to, now=datetime.now(UTC))
        entitlements_granted_in_range = (
            promotion_service.count_entitlements_by_type_in_range(
                since=since, until=until
            )
        )
        entitlements_used_in_range = promotion_service.count_usage_consumed_in_range(
            since=since, until=until
        )
        total_discount_given = promotion_service.sum_discount_given_in_range(
            since=since, until=until
        )
        referrals_by_status = referral_service.count_referrals_by_status()
        rewards_issued_in_range = referral_service.sum_rewards_issued_in_range(
            since=since, until=until
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "from": since.isoformat(),
                "to": until.isoformat(),
                "entitlements_granted_in_range": entitlements_granted_in_range,
                "entitlements_used_in_range": entitlements_used_in_range,
                "total_discount_given": float(total_discount_given),
                "referrals_by_status": referrals_by_status,
                "rewards_issued_in_range": float(rewards_issued_in_range),
            },
            request_id=request_id,
        ),
    )


@router.get("/reports/safety-support")
async def get_safety_support_report(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    safety_service: Annotated[SafetyService, Depends(get_safety_service)],
    support_service: Annotated[SupportService, Depends(get_support_service)],
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.REPORTS,
            level=AccessLevel.VIEW,
        )
        since, until = _report_range(from_=from_, to=to, now=datetime.now(UTC))
        incidents_by_status = safety_service.count_incidents_by_status()
        average_incident_resolution_minutes = (
            safety_service.average_incident_resolution_minutes_in_range(
                since=since, until=until
            )
        )
        cases_by_status = support_service.count_cases_by_status()
        average_case_resolution_minutes = (
            support_service.average_case_resolution_minutes_in_range(
                since=since, until=until
            )
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "from": since.isoformat(),
                "to": until.isoformat(),
                "incidents_by_status": incidents_by_status,
                "average_incident_resolution_minutes": float(
                    average_incident_resolution_minutes
                ),
                "cases_by_status": cases_by_status,
                "average_case_resolution_minutes": float(
                    average_case_resolution_minutes
                ),
            },
            request_id=request_id,
        ),
    )


@router.get("/reports/notifications")
async def get_notifications_report(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    notification_service: Annotated[
        NotificationService, Depends(get_notification_service)
    ],
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.REPORTS,
            level=AccessLevel.VIEW,
        )
        since, until = _report_range(from_=from_, to=to, now=datetime.now(UTC))
        deliveries_by_channel = (
            notification_service.count_deliveries_by_channel_in_range(
                since=since, until=until
            )
        )
        deliveries_by_status = notification_service.count_deliveries_by_status_in_range(
            since=since, until=until
        )
        sent = deliveries_by_status.get("SENT", 0)
        failed = deliveries_by_status.get("FAILED", 0)
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "from": since.isoformat(),
                "to": until.isoformat(),
                "deliveries_by_channel": deliveries_by_channel,
                "deliveries_by_status": deliveries_by_status,
                "delivery_success_rate": _rate(sent, sent + failed),
            },
            request_id=request_id,
        ),
    )


@router.get("/reports/matching")
async def get_matching_report(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    matching_service: Annotated[MatchingService, Depends(get_matching_service)],
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.REPORTS,
            level=AccessLevel.VIEW,
        )
        since, until = _report_range(from_=from_, to=to, now=datetime.now(UTC))
        offers_by_status = matching_service.count_offers_by_status_in_range(
            since=since, until=until
        )
        average_time_to_accept_seconds = (
            matching_service.average_time_to_accept_seconds_in_range(
                since=since, until=until
            )
        )
        accepted = offers_by_status.get("ACCEPTED", 0)
        total_offers = sum(offers_by_status.values())
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "from": since.isoformat(),
                "to": until.isoformat(),
                "offers_by_status": offers_by_status,
                "offer_acceptance_rate": _rate(accepted, total_offers),
                "average_time_to_accept_seconds": float(average_time_to_accept_seconds),
            },
            request_id=request_id,
        ),
    )


# ----------------------------------------------------------------------
# Dashboard (Admin Web §3, 2026-08-26). One aggregate endpoint computing
# every cleanly-sourceable widget server-side in one round trip, per the
# plan's own recommendation — rather than the Admin Web firing several
# separate requests on every dashboard load.
#
# "Online drivers" is now included (2026-08-28): shared/geo.py's
# driver:online:{id}/geo:drivers:{category} entries used to outlive a
# driver's session indefinitely (go_offline() never called
# remove_driver_location() — see modules/driver/router.py's go_offline
# endpoint, fixed the same day), which would have made a raw count
# overcount forever. With that fixed, geo.count_online_drivers() summed
# across vehicle.domain.entities.ALL_MATCHING_CATEGORY_KEYS is a real,
# accurate figure — closing §4.6's "NEW — NEEDS SCOPING" flag.
#
# "Today's rides (by status)" is now included too — reuses
# RideService.count_rides_by_status_in_range() (built for
# Reports/Analytics, ADR-0047) over [today_start, now) rather than the
# plan's original "client-side aggregation over Search Rides" idea,
# which would have meant paging through every ride requested today just
# to count them. One added field, no new query shape.
# ----------------------------------------------------------------------


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
    vehicle_service: Annotated[VehicleService, Depends(get_vehicle_service)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
    penalty_service: Annotated[PenaltyService, Depends(get_penalty_service)],
    safety_service: Annotated[SafetyService, Depends(get_safety_service)],
    support_service: Annotated[SupportService, Depends(get_support_service)],
    wallet_service: Annotated[WalletService, Depends(get_wallet_service)],
    redis_client: Annotated[Redis, Depends(get_redis)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.DASHBOARD,
            level=AccessLevel.VIEW,
        )
        now = datetime.now(UTC)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        _drivers, pending_driver_approvals = driver_service.search_drivers(
            query=None, status="PENDING", offset=0, limit=1
        )
        _vehicles, pending_vehicle_approvals = vehicle_service.search_vehicles(
            query=None, status="PENDING", offset=0, limit=1
        )
        _disputes, open_gps_disputes = ride_service.search_gps_disputes(
            status="OPEN", offset=0, limit=1
        )
        _penalties, outstanding_penalties = penalty_service.search_penalties(
            status="OUTSTANDING", user_id=None, offset=0, limit=1
        )
        open_sos_incidents = safety_service.count_unresolved_incidents()
        open_support_cases = support_service.count_unresolved_cases()
        platform_fee_collected_today = wallet_service.sum_debits_since(
            transaction_type="PLATFORM_FEE", since=today_start
        )
        rides_today_by_status = ride_service.count_rides_by_status_in_range(
            since=today_start, until=now
        )
        online_drivers = await geo.count_online_drivers(
            redis_client, category_keys=ALL_MATCHING_CATEGORY_KEYS
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "pending_driver_approvals": pending_driver_approvals,
                "pending_vehicle_approvals": pending_vehicle_approvals,
                "open_gps_disputes": open_gps_disputes,
                "open_sos_incidents": open_sos_incidents,
                "open_support_cases": open_support_cases,
                "outstanding_penalties": outstanding_penalties,
                "platform_fee_collected_today": float(platform_fee_collected_today),
                "rides_today_by_status": rides_today_by_status,
                "online_drivers": online_drivers,
            },
            request_id=request_id,
        ),
    )


# ----------------------------------------------------------------------
# Matching / Offers (Admin Web §4.6, ADR-0054, 2026-08-29). VIEW-only —
# Tier C of ADR-0054's own scoping options: online-driver count (total
# and by category) plus search/detail over individual
# matching.ride_offers rows. Deliberately does NOT expose live driver
# location or any Redis-derived per-driver detail beyond the count —
# ADR-0054 explicitly defers a driver-location map to a separate future
# decision. No mutation exists here and none is proposed: the matching
# algorithm itself stays entirely driver-facing (modules/matching/
# router.py); this is read-only visibility into what it already did.
# ----------------------------------------------------------------------

_VALID_OFFER_STATUSES = frozenset(status.value for status in OfferStatus)


def _offer_admin_data(offer: Offer) -> dict[str, object]:
    # Documented/safe fields only (database-design.md §10.1) — no
    # coordinates, no Redis-derived location or availability data
    # (ADR-0054 §5: that's a separate, not-yet-decided surface).
    return {
        "offer_id": str(offer.id),
        "ride_id": str(offer.ride_id),
        "driver_id": str(offer.driver_id),
        "vehicle_id": str(offer.vehicle_id),
        "status": offer.status.value,
        "expires_at": offer.expires_at.isoformat(),
        "responded_at": offer.responded_at.isoformat() if offer.responded_at else None,
        "created_at": offer.created_at.isoformat(),
    }


@router.get("/matching/online-drivers")
async def get_online_drivers(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    redis_client: Annotated[Redis, Depends(get_redis)],
) -> JSONResponse:
    """Online driver count, total and by vehicle category (Admin Web
    §4.6, ADR-0054) — the same accurate count Dashboard's summary
    already sums (geo.count_online_drivers(), real since the ADR-0011
    go_offline-cleanup fix), broken down per real matching_category_key
    (BIKE/AUTO/CAB:ECO/CAB:PREMIUM/CAB:PREMIUM_PLUS) instead of
    collapsed into one total."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.MATCHING,
            level=AccessLevel.VIEW,
        )
        by_category = await geo.count_online_drivers_by_category(
            redis_client, category_keys=ALL_MATCHING_CATEGORY_KEYS
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {"by_category": by_category, "total": sum(by_category.values())},
            request_id=request_id,
        ),
    )


@router.get("/matching/offers")
async def search_offers(
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    matching_service: Annotated[MatchingService, Depends(get_matching_service)],
    status: Annotated[str | None, Query()] = None,
    ride_id: Annotated[uuid.UUID | None, Query()] = None,
    driver_id: Annotated[uuid.UUID | None, Query()] = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """Search matching.ride_offers (Admin Web §4.6, ADR-0054) — every
    filter optional and independent, unlike the driver-facing endpoints
    in modules/matching/router.py which are always scoped to the
    calling driver. `from`/`to` filter on created_at with no default
    range (unlike Reports' own 30-day default) — this is a search
    screen, not a report; an omitted bound means "no filter on that
    side", matching Search Rides'/Search Penalties' own treatment of
    optional filters."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.MATCHING,
            level=AccessLevel.VIEW,
        )
        if status is not None and status not in _VALID_OFFER_STATUSES:
            return JSONResponse(
                status_code=422,
                content=error_envelope(
                    "VALIDATION_FAILED",
                    f"Unknown offer status: {status!r}.",
                    request_id=request_id,
                ),
            )
        params = PageParams.clamp(
            page=page,
            page_size=page_size,
            max_page_size=settings.MAX_PAGE_SIZE,
        )
        offers, total = matching_service.search_offers(
            status=status,
            ride_id=ride_id,
            driver_id=driver_id,
            since=from_,
            until=to,
            offset=params.offset,
            limit=params.page_size,
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_offer_admin_data(o) for o in offers], params=params, total=total
            ),
            request_id=request_id,
        ),
    )


@router.get("/matching/offers/{offer_id}")
async def get_offer(
    offer_id: uuid.UUID,
    admin_account: Annotated[Account, Depends(require_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    matching_service: Annotated[MatchingService, Depends(get_matching_service)],
) -> JSONResponse:
    """Get Offer (Admin Web §4.6, ADR-0054) — admin-only, no
    driver-ownership restriction, same "no ownership restriction,
    admin-only" split Get Ride already establishes relative to the
    driver/customer-facing ride lookup."""
    request_id = new_request_id()
    try:
        admin_service.require_permission(
            account_id=admin_account.id,
            module=AdminModule.MATCHING,
            level=AccessLevel.VIEW,
        )
        offer = matching_service.get_offer(offer_id)
        if offer is None:
            raise OfferNotFoundError("Offer not found.")
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_offer_admin_data(offer), request_id=request_id),
    )
