"""Pydantic request DTOs for the Admin API.

Mirrors docs/05-api/api-contracts.md §46 (updated Phase 2 / Task 2.7A per
ADR-0009 point A), §48 (Phase 16, ADR-0023), the Admin Management section
ADR-0040/BR-126/BR-127 add, the Offers/Coupons campaign endpoints
ADR-0041 adds, and the Fare Management endpoints ADR-0042 adds.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from modules.admin.domain.entities import AccessLevel, AdminModule


class PermissionGrant(BaseModel):
    module: AdminModule
    access_level: AccessLevel


class CreateAdminBody(BaseModel):
    """Admin Management — Create Employee Admin (ADR-0040). `phone` is
    parsed/validated at the service layer (modules.identity.domain.
    phone_number.PhoneNumber.parse()), same "shape here, business rule
    in the service" split every other request DTO in this codebase
    uses. `permissions` may be empty (an admin created with no module
    access yet, granted later via Update Permissions)."""

    phone: str
    permissions: list[PermissionGrant] = []


class UpdatePermissionsBody(BaseModel):
    """Replaces the target admin's entire permission set — not an
    incremental add/remove (ADR-0040: "PATCH .../permissions replaces
    the whole set"). ADMIN_MANAGEMENT/SETTINGS are rejected at the
    service layer if present here (ModuleNotGrantableError), not
    filtered silently."""

    permissions: list[PermissionGrant]


class RejectBody(BaseModel):
    """reason is optional — no source document requires it to be
    non-blank (ADR-0009). Used by both Reject Driver and Reject
    Vehicle."""

    reason: str | None = None


class ResolvePenaltyBody(BaseModel):
    """api-contracts.md §48's documented request shape. `action` is
    validated against the single documented value ("WAIVE") at the
    service layer (modules.penalty.service.PenaltyService.
    resolve_penalty()), not here — same "shape here, business rule in
    the service" split every other request DTO in this codebase uses.
    `reason` is optional, same treatment RejectBody already gives it."""

    action: str
    reason: str | None = None


class ResolveGpsDisputeBody(BaseModel):
    """api-contracts.md §77's documented request shape (BR-124,
    ADR-0032). `action` must be exactly "APPROVE" or "REJECT" — validated
    at the service layer (modules.ride.service.RideService.
    resolve_gps_dispute()), same split as ResolvePenaltyBody above.
    Unlike ResolvePenaltyBody, `reason` is required (BR-124: "Admin
    decision: APPROVE or REJECT, with a required reason")."""

    action: str
    reason: str


class CampaignBody(BaseModel):
    """Create/Edit Campaign (ADR-0041 Decision 3). Shared by POST
    /api/v1/admin/campaigns and PATCH .../campaigns/{id} — the service
    layer rejects a PATCH outside DRAFT (InvalidCampaignStateTransitionError,
    ADR-0041 Decision 4), not this DTO. `discount_type`/`eligible_scope`
    are validated against their enums at the service layer (Campaign.new/
    apply_edit), same "shape here, business rule in the service" split
    every other request DTO in this codebase uses. `eligible_customer_ids`
    is only meaningful when eligible_scope='SELECTED'."""

    code: str | None = None
    name: str
    vehicle_category: str | None = None
    discount_type: str
    discount_value: Decimal
    max_discount_amount: Decimal | None = None
    minimum_fare: Decimal | None = None
    eligible_scope: str = "ALL"
    per_customer_use_limit: int = 1
    total_usage_limit: int | None = None
    ride_count_limit: int | None = None
    starts_at: datetime
    ends_at: datetime | None = None
    eligible_customer_ids: list[uuid.UUID] | None = None


class CreateFareRuleBody(BaseModel):
    """Create Draft Fare Rule (ADR-0042 Decision 4). Always starts
    DRAFT — `effective_from`/`effective_until` are not client-supplied
    here at all; Publish is the only action that sets `effective_from`
    (ADR-0042 Decision 2)."""

    vehicle_category: str
    base_fare: Decimal
    per_km: Decimal
    per_minute: Decimal = Decimal("0")
    waiting_per_minute: Decimal = Decimal("0")
    minimum_fare: Decimal


class PublishFareRuleBody(BaseModel):
    """Publish Fare Rule (ADR-0042 Decision 2). `effective_from` is
    optional — omitted means "effective now"; supplied means a
    scheduled future rollout (e.g. a rate change effective next
    Monday)."""

    effective_from: datetime | None = None


class CreateDriverBonusRuleBody(BaseModel):
    """Create Draft driver-bonus rule (ADR-0043 §5, api-contracts.md
    §46.12). Always starts DRAFT — Publish is the only action that
    sets `effective_from`, same contract as fare rules."""

    referred_amount: Decimal
    referrer_amount: Decimal


class CreateCustomerRewardRuleBody(BaseModel):
    """Create Draft customer-reward rule (ADR-0043 §5, api-contracts.md
    §46.12). `reward_type` is 'REFERRAL_REFERRED' or
    'REFERRAL_REFERRING' — the two independent config streams."""

    reward_type: str
    discount_percent: Decimal
    total_uses: int


class PublishRewardConfigBody(BaseModel):
    """Publish a driver-bonus or customer-reward rule (ADR-0043 §5).
    Same optional `effective_from` contract as Publish Fare Rule."""

    effective_from: datetime | None = None


class CreatePlatformFeeRuleBody(BaseModel):
    """Create Draft platform fee rule (ADR-0045 §3). Always starts
    DRAFT — Publish is the only action that sets `effective_from`,
    identical contract to Create Draft Fare Rule."""

    vehicle_category: str
    fee_amount: Decimal


class PublishPlatformFeeRuleBody(BaseModel):
    """Publish Platform Fee Rule (ADR-0045 §3). Same optional
    `effective_from` contract as Publish Fare Rule."""

    effective_from: datetime | None = None


class CreateTemplateBody(BaseModel):
    """Create Draft notification template (ADR-0044 Decision 4).
    Always the next version for this (template_key, channel) pair —
    there is no separate Edit; an edit is always a new Create."""

    template_key: str
    channel: str
    event_key: str | None = None
    title: str | None = None
    body: str


class CreateBroadcastBody(BaseModel):
    """Compose/Send Broadcast (ADR-0055, Tier C). `audience_user_ids`
    is required and non-empty only when `audience_type='SELECTED'`
    (domain-validated, not enforced here) — every other audience type
    is resolved server-side, fresh, at actual dispatch time.
    `scheduled_at` omitted or in the past means "send now"; a future
    timestamp leaves the broadcast SCHEDULED for the periodic dispatch
    task to pick up."""

    channel: str
    subject: str | None = None
    body: str
    audience_type: str
    audience_user_ids: list[uuid.UUID] | None = None
    scheduled_at: datetime | None = None


class CreateCampaignBody(BaseModel):
    """Create Campaign (ADR-0046 §5). Always starts ACTIVE — no draft/
    approval gate before a campaign is usable (ADR-0018 Decision 2,
    unchanged). driver_share_percent/vistaar_share_percent default to
    the approved 80/20 split but are exposed as-is, not modified — "do
    not invent additional ad economics" (owner instruction)."""

    partner_name: str
    payout_amount: Decimal
    driver_share_percent: Decimal = Decimal("80")
    vistaar_share_percent: Decimal = Decimal("20")
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class AssignDriverBody(BaseModel):
    """Assign Driver (ADR-0046 §5)."""

    driver_id: uuid.UUID


class VerifyAssignmentBody(BaseModel):
    """Approve/Reject installation proof (ADR-0046 §5) — sets the
    already-existing manual `verification_status` field; does not call
    Admoto or any external verification provider (ADR-0018 Item 3
    stays deferred)."""

    approved: bool


class UpdateSettingBody(BaseModel):
    """Update Setting (ADR-0048 Decision 3). `value` is a bare JSON
    scalar/object matching whatever shape the target key's seeded
    value already has (e.g. a plain number for
    welcome_discount_percent) — no per-key schema, since the set of
    keys is closed and small (Decision 2) and each key's own
    `description` documents its expected shape."""

    value: object
