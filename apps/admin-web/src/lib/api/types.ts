/**
 * Types mirror the real backend response shapes exactly (apps/backend/src
 * /modules/admin/router.py, docs/05-api/api-contracts.md §3/§46).
 *
 * Every field marked optional either isn't in the current backend response
 * yet (see the comment on each) or is genuinely nullable in the API itself
 * — never optional just to paper over an unfinished type.
 */

/** docs/05-api/api-contracts.md §3 — every endpoint in this codebase wraps
 * its payload in this envelope. */
export interface ApiEnvelope<T> {
  data: T | null;
  error: { code: string; message: string } | null;
  request_id: string;
}

export interface PaginatedEnvelope<T> {
  items: T[];
  pagination: {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
  };
}

/** GET /api/v1/admin/dashboard/summary — real fields only. */
export interface DashboardSummary {
  pending_driver_approvals: number;
  pending_vehicle_approvals: number;
  open_gps_disputes: number;
  open_sos_incidents: number;
  open_support_cases: number;
  outstanding_penalties: number;
  platform_fee_collected_today: number;
  /** Real since 2026-08-28 — reuses RideService.count_rides_by_status_
   * in_range() (built for Reports/Analytics, ADR-0047). Sparse: only
   * statuses with at least one matching ride appear. */
  rides_today_by_status: Record<string, number>;
  /** Real since 2026-08-28 — go_offline() now cleans up its own Redis
   * entry (modules/driver/router.py), so this is an accurate count,
   * not a forever-growing one. */
  online_drivers: number;
}

export type AdminModule =
  | "DASHBOARD"
  | "CUSTOMERS"
  | "DRIVERS"
  | "VEHICLES"
  | "VERIFICATION"
  | "RIDES"
  | "MATCHING"
  | "FINANCE"
  | "FARE_MANAGEMENT"
  | "PENALTIES"
  | "OFFERS_COUPONS"
  | "REFERRALS"
  | "NOTIFICATIONS"
  | "SAFETY"
  | "SUPPORT"
  | "ADVERTISEMENTS"
  | "REPORTS"
  | "AUDIT_LOGS"
  | "ADMIN_MANAGEMENT"
  | "SETTINGS";

export type AccessLevel = "VIEW" | "MANAGE";

export interface AdminPermission {
  module: AdminModule;
  access_level: AccessLevel;
}

/** The {admin_id, role, status, created_at, permissions} shape every
 * Admin Management response returns (api-contracts.md §46.1's
 * `_admin_data()`) — Create/List/Get/Disable/Enable Admin and Get My
 * Admin Profile all share it. `AdminProfile` below is this same shape
 * used specifically for "my own profile"; List Admin returns it with
 * `permissions: []` for every row (the list endpoint doesn't fetch each
 * admin's own permissions — Get Admin does). */
export interface AdminAccount {
  admin_id: string;
  role: "SUPER_ADMIN" | "ADMIN" | string;
  status: string;
  created_at: string;
  permissions: AdminPermission[];
}

/** GET /api/v1/admin/me */
export type AdminProfile = AdminAccount;

/** POST /api/v1/admin/admins body. */
export interface CreateAdminRequest {
  phone: string;
  permissions: AdminPermission[];
}

/** PATCH /api/v1/admin/admins/{id}/permissions body — replaces the
 * whole grant set, not an incremental add/remove (ADR-0040). */
export interface UpdatePermissionsRequest {
  permissions: AdminPermission[];
}

/** One row from GET /api/v1/admin/audit-logs */
export interface AuditLogEntry {
  id: number;
  admin_id: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
  reason: string | null;
  before_state: Record<string, unknown> | null;
  after_state: Record<string, unknown> | null;
  request_id: string | null;
  created_at: string | null;
}

// ---------------------------------------------------------------------
// Customers / Drivers / Vehicles / Verification (api-contracts.md
// §46.4, Admin Web §4.1-§4.4). Status enums copied from their real
// backend source (modules/{driver,vehicle,verification}/domain/
// entities.py) — kept in sync by hand, same as AdminModule above
// already is.
// ---------------------------------------------------------------------

export interface CustomerSummary {
  customer_id: string;
  full_name: string;
  profile_photo_uri: string | null;
  status: string;
  language: string;
  created_at: string;
  updated_at: string;
}

/** GET /api/v1/admin/customers/{id} — same shape as CustomerSummary
 * plus `phone` (identity.accounts, looked up separately — omitted on
 * the list endpoint to avoid an N+1 query per row). */
export interface CustomerDetail extends CustomerSummary {
  phone: string;
}

export type DriverVerificationStatus = "PENDING" | "APPROVED" | "REJECTED";
export type DriverOperationalStatus =
  | "OFFLINE"
  | "ONLINE"
  | "ON_RIDE"
  | "SUSPENDED"
  | "INELIGIBLE";

/** GET /api/v1/admin/drivers list rows — no `phone` (Driver Review, the
 * detail endpoint, already includes it; avoids an N+1 lookup here). */
export interface DriverSummary {
  driver_id: string;
  full_name: string;
  profile_photo_uri: string | null;
  verification_status: DriverVerificationStatus;
  operational_status: DriverOperationalStatus;
  strikes: number;
  created_at: string;
}

export type DocumentVerificationStatus =
  | "PENDING"
  | "APPROVED"
  | "REJECTED"
  | "EXPIRED";

export type VerificationCaseStatus =
  | "PENDING"
  | "PROCESSING"
  | "APPROVED"
  | "REJECTED"
  | "MANUAL_REVIEW"
  | "EXPIRED";

export interface DriverDocumentCase {
  case_id: string;
  status: VerificationCaseStatus;
}

export interface DriverDocumentSummary {
  document_id: string;
  document_type: string;
  verification_status: DocumentVerificationStatus;
  verification_cases: DriverDocumentCase[];
}

/** GET /api/v1/admin/drivers/{id} (Driver Review) — the pre-existing
 * detail endpoint, includes phone and nested documents; list rows above
 * (Search Drivers, added 2026-08-28) intentionally omit both. */
export interface DriverDetail {
  driver_id: string;
  phone: string;
  full_name: string;
  profile_photo_uri: string | null;
  verification_status: DriverVerificationStatus;
  operational_status: DriverOperationalStatus;
  strikes: number;
  created_at: string;
  updated_at: string;
  documents: DriverDocumentSummary[];
}

/** Driver Strike History (api-contracts.md §46.18, Admin Web §4.9) —
 * immutable by construction, reads `penalty.strikes` as-is. Reuses the
 * DRIVERS permission (this is driver data, not a new module).
 * `driver.drivers.strikes` (DriverDetail.strikes above) stays the
 * at-a-glance summary counter; this is the underlying detail row. */
export interface DriverStrike {
  strike_id: string;
  driver_id: string;
  ride_id: string | null;
  reason: string;
  created_at: string;
}

export type VehicleCategory = "BIKE" | "AUTO" | "CAB";
export type VehicleVerificationStatus = "PENDING" | "APPROVED" | "REJECTED";
export type VehicleOperationalStatus = "INACTIVE" | "ACTIVE";

/** Both GET /api/v1/admin/vehicles rows and GET .../vehicles/{id} share
 * this exact shape (_vehicle_data() in router.py) — unlike drivers,
 * there's no separate summary/detail split. */
export interface Vehicle {
  vehicle_id: string;
  category: VehicleCategory;
  registration_number: string;
  make: string;
  model: string;
  verification_status: VehicleVerificationStatus;
  operational_status: VehicleOperationalStatus;
  created_at: string;
  updated_at: string;
}

export interface VehicleDocument {
  document_id: string;
  vehicle_id: string;
  document_type: string;
  document_number: string;
  evidence_uri: string;
  verification_status: DocumentVerificationStatus;
  expires_at: string | null;
  created_at: string;
}

export type VerificationType =
  | "DRIVER_DOCUMENT"
  | "VEHICLE_DOCUMENT"
  | "PARKING_PROOF";

/** GET /api/v1/admin/verification/queue rows. `subject_id` is the
 * underlying document's own id (driver_documents.id /
 * vehicle_documents.id), not a driver_id/vehicle_id — there is no
 * endpoint to resolve a document back to its owning driver/vehicle, so
 * this queue is read-only/informational; it doesn't deep-link anywhere. */
export interface VerificationCase {
  case_id: string;
  subject_type: string;
  subject_id: string;
  verification_type: VerificationType;
  status: VerificationCaseStatus;
  created_at: string;
  completed_at: string | null;
}

// ---------------------------------------------------------------------
// Rides (api-contracts.md §46, ADR-0023, Admin Web §4.5). Read-only —
// no admin-side ride intervention (force-cancel, reassign) exists or
// was asked for.
// ---------------------------------------------------------------------

export type RideStatus =
  | "SEARCHING"
  | "ACCEPTED"
  | "ARRIVED"
  | "STARTED"
  | "COMPLETED"
  | "CANCELLED"
  | "CLOSED";

export interface RideFare {
  base: number;
  discount: number;
  total: number;
  currency: string;
}

export interface RideCoordinates {
  latitude: number;
  longitude: number;
}

export interface Ride {
  ride_id: string;
  status: RideStatus;
  customer_id: string;
  driver_id: string | null;
  vehicle_id: string | null;
  requested_vehicle_category: string;
  requested_cab_tier: string | null;
  pickup: RideCoordinates;
  destination: RideCoordinates;
  fare: RideFare | null;
  requested_at: string;
  accepted_at: string | null;
  arrived_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------
// Matching / Offers (api-contracts.md §46.20, ADR-0054, Admin Web
// §4.6). Read-only, Tier C — search/detail over individual offers plus
// an online-driver count. Deliberately no driver-location map/live
// coordinates anywhere here (ADR-0054 §5, a separate future decision).
// ---------------------------------------------------------------------

/** Keyed by the real matching_category_key() values (ADR-0020 Decision
 * 1) — BIKE, AUTO, CAB:ECO, CAB:PREMIUM, CAB:PREMIUM_PLUS — not a
 * coarser 3-value grouping. */
export interface OnlineDriversSummary {
  by_category: Record<string, number>;
  total: number;
}

export type MatchingOfferStatus =
  | "PENDING"
  | "ACCEPTED"
  | "REJECTED"
  | "EXPIRED"
  | "CANCELLED";

/** Documented/safe fields only (database-design.md §10.1) — no
 * coordinates, no Redis-derived location or availability data. */
export interface MatchingOffer {
  offer_id: string;
  ride_id: string;
  driver_id: string;
  vehicle_id: string;
  status: MatchingOfferStatus;
  expires_at: string;
  responded_at: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------
// Finance / Wallet (api-contracts.md §34/§47, Admin Web §4.7). No
// search-all-wallets endpoint exists by design — a wallet is looked up
// by a known driver_id, not browsed.
// ---------------------------------------------------------------------

export interface DriverWallet {
  balance: number;
  currency: string;
  outstanding_settlement: number;
}

export type WalletTransactionType =
  | "PLATFORM_FEE"
  | "WALLET_RECHARGE"
  | "JOINING_BONUS"
  | "DRIVER_REFERRAL_BONUS"
  | "ADVERTISEMENT_PAYOUT"
  | "DRIVER_PENALTY"
  | "CASH_SETTLEMENT"
  | "FEE_REVERSAL"
  | "PENALTY_REVERSAL"
  | "ADMIN_ADJUSTMENT";

export type WalletTransactionDirection = "CREDIT" | "DEBIT";

export interface WalletTransaction {
  transaction_id: string;
  ride_id: string | null;
  transaction_type: WalletTransactionType;
  amount: number;
  direction: WalletTransactionDirection;
  balance_before: number;
  balance_after: number;
  reference_type: string | null;
  reference_id: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------
// Penalties / Strikes (api-contracts.md §48, ADR-0023, Admin Web §4.9).
// Driver Strike History has its own DriverStrike type further up
// (near DriverDetail) — implemented 2026-08-29.
// ---------------------------------------------------------------------

// Customer penalties never expire (BR-049, corrected 2026-09-04,
// ADR-0069) — an OUTSTANDING penalty stays outstanding and collectible
// indefinitely until paid (SETTLED) or waived (WAIVED). There is no
// EXPIRED status and no `expires_at` field. This is unrelated to Sarthi
// cancellation-penalty debt (`wallet.wallets.outstanding_debt`,
// ADR-0062), a separate mechanism not modeled by this type.
export type PenaltyStatus = "OUTSTANDING" | "SETTLED" | "WAIVED";

/** Only one value exists today — `PenaltyType` is deliberately not
 * built ahead of a real caller, same discipline `WalletTransactionType`
 * follows. */
export type PenaltyType = "CUSTOMER_CANCELLATION";

export interface Penalty {
  penalty_id: string;
  user_id: string;
  ride_id: string | null;
  penalty_type: PenaltyType;
  amount: number;
  status: PenaltyStatus;
  issued_at: string;
  settled_at: string | null;
}

// ---------------------------------------------------------------------
// Fare Management (api-contracts.md §46.7, ADR-0042, Admin Web §4.8).
// ---------------------------------------------------------------------

export type FareRuleStatus = "DRAFT" | "IN_REVIEW" | "PUBLISHED";

/** `pricing.fare_rules.vehicle_category` is an unconstrained string on
 * the backend (modules/pricing/domain/entities.py), but the only 5
 * values `calculate_fare()` actually keys off (modules/pricing/
 * __init__.py) — CAB's three sub-tiers, not the 3-value VehicleCategory
 * enum drivers/vehicles use. */
export type FareRuleVehicleCategory =
  | "BIKE"
  | "AUTO"
  | "CAB_ECO"
  | "CAB_PREMIUM"
  | "CAB_PREMIUM_PLUS";

export interface FareRule {
  rule_id: string;
  vehicle_category: string;
  base_fare: number;
  per_km: number;
  per_minute: number;
  waiting_per_minute: number;
  minimum_fare: number;
  status: FareRuleStatus;
  effective_from: string | null;
  effective_until: string | null;
  created_at: string;
}

/** POST /api/v1/admin/fare-rules body — always starts DRAFT;
 * effective_from/until are never client-supplied here (Publish is the
 * only action that sets effective_from). */
export interface CreateFareRuleRequest {
  vehicle_category: string;
  base_fare: number;
  per_km: number;
  per_minute: number;
  waiting_per_minute: number;
  minimum_fare: number;
}

// ---------------------------------------------------------------------
// Platform Fee Management (api-contracts.md §46.14, ADR-0045, Admin
// Web §4.8 — own table/permission, same DRAFT/IN_REVIEW/PUBLISHED
// lifecycle as Fare Management above). `pricing.platform_fee_rules`
// deliberately keys off the 3-value VehicleCategory enum (BIKE/AUTO/
// CAB), not Fare Management's 5-value CAB-tier vocabulary — BR-011's
// platform fee applies uniformly across CAB's tiers.
// ---------------------------------------------------------------------

export interface PlatformFeeRule {
  rule_id: string;
  vehicle_category: string;
  fee_amount: number;
  status: FareRuleStatus;
  effective_from: string | null;
  effective_until: string | null;
  created_at: string;
}

/** POST /api/v1/admin/platform-fee-rules body — always starts DRAFT,
 * identical contract shape to Create Draft Fare Rule. */
export interface CreatePlatformFeeRuleRequest {
  vehicle_category: string;
  fee_amount: number;
}

// ---------------------------------------------------------------------
// Campaigns / Offers & Coupons (api-contracts.md §46.2, ADR-0041,
// Admin Web §4.10).
// ---------------------------------------------------------------------

export type CampaignStatus = "DRAFT" | "ACTIVE" | "PAUSED" | "ENDED";
export type DiscountType = "PERCENT" | "FLAT";
export type EligibleScope = "ALL" | "SELECTED";

export interface Campaign {
  campaign_id: string;
  code: string | null;
  name: string;
  /** null applies to every vehicle category — the 3-value
   * VehicleCategory enum (BIKE/AUTO/CAB), unlike Fare Management's
   * 5-value CAB-tier vocabulary (FareRuleVehicleCategory above). */
  vehicle_category: string | null;
  discount_type: DiscountType;
  discount_value: number;
  max_discount_amount: number | null;
  minimum_fare: number | null;
  eligible_scope: EligibleScope;
  per_customer_use_limit: number;
  total_usage_limit: number | null;
  ride_count_limit: number | null;
  starts_at: string;
  ends_at: string | null;
  status: CampaignStatus;
  created_by: string;
  created_at: string;
}

/** Shared by Create Campaign (POST) and Edit Campaign (PATCH — DRAFT
 * only, enforced server-side, not by this shape). */
export interface CampaignRequest {
  code: string | null;
  name: string;
  vehicle_category: string | null;
  discount_type: DiscountType;
  discount_value: number;
  max_discount_amount: number | null;
  minimum_fare: number | null;
  eligible_scope: EligibleScope;
  per_customer_use_limit: number;
  total_usage_limit: number | null;
  ride_count_limit: number | null;
  starts_at: string;
  ends_at: string | null;
  eligible_customer_ids: string[] | null;
}

/** CSV Bulk Customer Targeting response (api-contracts.md §46.19,
 * ADR-0041 §9) — additive to the campaign's existing eligible-customer
 * set. `unmatched` rows are reported back, not silently dropped or
 * treated as a whole-request failure. */
export interface BulkEligibleCustomersResult {
  added: number;
  already_eligible: number;
  unmatched: { row: number; phone: string; reason: string }[];
}

// ---------------------------------------------------------------------
// Safety / SOS (api-contracts.md §46.8, ADR-0022, Admin Web §4.13).
// ---------------------------------------------------------------------

export type IncidentStatus =
  | "OPEN"
  | "ACKNOWLEDGED"
  | "IN_PROGRESS"
  | "RESOLVED"
  | "CLOSED";

export interface SafetyIncident {
  incident_id: string;
  ride_id: string | null;
  reporter_id: string;
  incident_type: string;
  status: IncidentStatus;
  location: { latitude: number; longitude: number } | null;
  created_at: string;
  resolved_at: string | null;
}

// ---------------------------------------------------------------------
// Support / Disputes (api-contracts.md §46.9, Admin Web §4.14).
// ---------------------------------------------------------------------

export type SupportCaseStatus =
  | "OPEN"
  | "ASSIGNED"
  | "IN_PROGRESS"
  | "WAITING_FOR_USER"
  | "RESOLVED"
  | "CLOSED";

export interface SupportCaseSummary {
  case_id: string;
  user_id: string;
  ride_id: string | null;
  category: string | null;
  priority: string;
  status: SupportCaseStatus;
  assigned_admin_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface SupportMessage {
  message_id: string;
  sender_type: "CUSTOMER" | "DRIVER" | "ADMIN" | "AI";
  sender_id: string | null;
  message: string;
  created_at: string;
}

export interface SupportCaseDetail extends SupportCaseSummary {
  messages: SupportMessage[];
}

/** GPS Dispute (api-contracts.md §77, ADR-0032, Admin Web §4.14's own
 * excluded row — built 2026-08-29). A specific dispute type reached
 * via its own sub-route from Support/Disputes, same SUPPORT permission. */
export type GpsDisputeStatus = "OPEN" | "RESOLVED" | "EXPIRED";
export type GpsDisputeDecision = "APPROVE" | "REJECT";
export type GpsVerificationType = "ARRIVAL" | "COMPLETION" | "EARLY_DROP";
export type GpsDisputeEvidenceType = "PHOTO" | "VIDEO" | "DOCUMENT" | "TEXT";

export interface GpsDisputeEvidenceItem {
  submitted_by: string;
  evidence_type: GpsDisputeEvidenceType;
  uri: string | null;
  text_explanation: string | null;
  submitted_at: string;
}

export interface GpsDispute {
  dispute_id: string;
  ride_id: string;
  gps_verification_id: string;
  verification_type: GpsVerificationType;
  opened_at: string;
  evidence_deadline: string;
  status: GpsDisputeStatus;
  decision: GpsDisputeDecision | null;
  decided_by: string | null;
  decided_reason: string | null;
  decided_at: string | null;
  /** Only present on Get Dispute — Search Disputes' own list rows omit
   * it (list rows, not a detail view). */
  evidence?: GpsDisputeEvidenceItem[];
}

// ---------------------------------------------------------------------
// Notifications (api-contracts.md §46.10 history, §46.13 templates,
// §46.21 broadcasts, ADR-0044, ADR-0055, Admin Web §4.12).
// Device-token registration (ADR-0052) has no admin-facing frontend —
// it's a device→backend contract, not an admin screen.
// ---------------------------------------------------------------------

export type NotificationChannel = "IN_APP" | "SMS" | "PUSH" | "WHATSAPP";
export type DeliveryStatus = "PENDING" | "SENT" | "FAILED";

export interface Delivery {
  delivery_id: string;
  user_id: string;
  channel: NotificationChannel;
  template_key: string;
  event_id: string | null;
  status: DeliveryStatus;
  provider_reference: string | null;
  created_at: string;
  delivered_at: string | null;
}

export type TemplateStatus = "DRAFT" | "PUBLISHED" | "ARCHIVED";

export interface NotificationTemplate {
  template_id: string;
  template_key: string;
  channel: string;
  event_key: string | null;
  title: string | null;
  body: string;
  version: number;
  status: TemplateStatus;
  created_at: string;
}

/** POST /api/v1/admin/notifications/templates body. Always creates the
 * next version for this (template_key, channel) pair — no separate
 * Edit endpoint exists (ADR-0044 Decision 4). */
export interface CreateTemplateRequest {
  template_key: string;
  channel: string;
  event_key: string | null;
  title: string | null;
  body: string;
}

/** ADR-0055 Tier C — who a broadcast resolves to at actual send time
 * (server-side, never client-supplied beyond this type + SELECTED's own
 * id list). */
export type BroadcastAudienceType =
  | "ALL_CUSTOMERS"
  | "ALL_DRIVERS"
  | "ONLINE_DRIVERS"
  | "SELECTED";

/** No FAILED status at the broadcast level — an individual recipient's
 * send failing is tracked in failed_count, not the whole broadcast. */
export type BroadcastStatus = "SCHEDULED" | "SENT";

export interface Broadcast {
  broadcast_id: string;
  channel: NotificationChannel;
  subject: string | null;
  body: string;
  audience_type: BroadcastAudienceType;
  audience_user_ids: string[] | null;
  status: BroadcastStatus;
  scheduled_at: string | null;
  sent_count: number;
  failed_count: number;
  created_by: string;
  created_at: string;
  sent_at: string | null;
}

/** POST /api/v1/admin/notifications/broadcasts body (ADR-0055 Tier C).
 * `scheduled_at` omitted or in the past means "send now". */
export interface CreateBroadcastRequest {
  channel: string;
  subject: string | null;
  body: string;
  audience_type: string;
  audience_user_ids: string[] | null;
  scheduled_at: string | null;
}

// ---------------------------------------------------------------------
// Referrals (api-contracts.md §46.6 search, §46.12 reward
// configuration, ADR-0043, Admin Web §4.11).
// ---------------------------------------------------------------------

export type ReferralStatus = "ATTACHED" | "ACTIVATED";

export interface ReferralReward {
  reward_id: string;
  recipient_id: string;
  reward_type: "DRIVER_REFERRAL_BONUS" | "CUSTOMER_REFERRAL_PROMOTION";
  amount: number | null;
  promotion_uses: number | null;
  status: "ISSUED";
  created_at: string;
}

export interface Referral {
  referral_id: string;
  referrer_id: string;
  referred_id: string;
  referred_type: "CUSTOMER" | "DRIVER";
  status: ReferralStatus;
  activated_at: string | null;
  created_at: string;
  rewards: ReferralReward[];
}

export type RewardConfigStatus = "DRAFT" | "IN_REVIEW" | "PUBLISHED";

export interface DriverBonusRule {
  rule_id: string;
  referred_amount: number;
  referrer_amount: number;
  status: RewardConfigStatus;
  effective_from: string | null;
  effective_until: string | null;
  created_at: string;
}

/** 'REFERRAL_REFERRED' | 'REFERRAL_REFERRING' — a config-level
 * vocabulary distinct from ReferralReward's own `reward_type`
 * (DRIVER_REFERRAL_BONUS/CUSTOMER_REFERRAL_PROMOTION); the two
 * enums look similar but serve different tables (referral.reward_rules
 * vs. referral.rewards). */
export type CustomerRewardType = "REFERRAL_REFERRED" | "REFERRAL_REFERRING";

export interface CustomerRewardRule {
  rule_id: string;
  reward_type: string;
  discount_percent: number;
  total_uses: number;
  status: RewardConfigStatus;
  effective_from: string | null;
  effective_until: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------
// Advertisements (api-contracts.md §46.15, ADR-0046, Admin Web §4.15).
// `Ad`-prefixed to avoid colliding with Offers/Coupons' own `Campaign`/
// `CampaignStatus` above — same English word, two unrelated domains.
// ---------------------------------------------------------------------

export type AdCampaignStatus = "ACTIVE" | "PAUSED" | "ENDED";

export interface AdCampaign {
  campaign_id: string;
  partner_name: string;
  status: AdCampaignStatus;
  payout_amount: number;
  driver_share_percent: number;
  vistaar_share_percent: number;
  starts_at: string | null;
  ends_at: string | null;
  created_at: string;
}

/** POST /api/v1/admin/advertisements/campaigns body — always starts
 * ACTIVE, no draft/approval gate. driver_share_percent/
 * vistaar_share_percent default to the approved 80/20 split
 * server-side if omitted. */
export interface CreateAdCampaignRequest {
  partner_name: string;
  payout_amount: number;
  driver_share_percent?: number;
  vistaar_share_percent?: number;
  starts_at?: string;
  ends_at?: string;
}

/** ASSIGNED -> PROOF_SUBMITTED -> VERIFIED | REJECTED -> PAID. */
export type AdAssignmentStatus =
  | "ASSIGNED"
  | "PROOF_SUBMITTED"
  | "VERIFIED"
  | "REJECTED"
  | "PAID";

/** The manual "Admoto verification status" field (ADR-0046 Decision 2)
 * — set by an admin's Approve/Reject decision, not a live Admoto call.
 * Reuses driver/vehicle documents' own PENDING/APPROVED/REJECTED
 * vocabulary, a different field from AdAssignmentStatus above. */
export type AdVerificationStatus = "PENDING" | "APPROVED" | "REJECTED";

export interface AdAssignment {
  assignment_id: string;
  campaign_id: string;
  driver_id: string;
  status: AdAssignmentStatus;
  proof_uri: string | null;
  verification_status: AdVerificationStatus | null;
  assigned_at: string;
}

export type AdPayoutStatus = "PENDING" | "PAID";

export interface AdPayout {
  payout_id: string;
  driver_campaign_id: string;
  gross_amount: number;
  driver_amount: number;
  vistaar_amount: number;
  status: AdPayoutStatus;
  created_at: string;
}

// ---------------------------------------------------------------------
// Reports / Analytics (api-contracts.md §46.16, ADR-0047, Admin Web
// §4.16). Nine fixed-shape aggregate endpoints, each a small set of
// real COUNT/SUM/AVG numbers over an optional `from`/`to` window
// (defaults server-side to the last 30 days) — deliberately not a
// generic query builder. Every report shares `from`/`to` in its
// response (the range actually used, including the server's own
// default when the caller omits one).
// ---------------------------------------------------------------------

interface ReportRange {
  from: string;
  to: string;
}

export interface RidesReport extends ReportRange {
  rides_by_status: Record<string, number>;
  rides_by_vehicle_category: Record<string, number>;
  average_fare: number;
  completion_rate: number;
}

export interface CustomersReport extends ReportRange {
  total_customers: number;
  new_customers_in_range: number;
}

export interface DriversReport extends ReportRange {
  total_drivers: number;
  by_verification_status: Record<string, number>;
  by_operational_status: Record<string, number>;
  new_drivers_in_range: number;
}

export interface FinancialReport extends ReportRange {
  platform_fee_collected: number;
  fee_reversals: number;
  driver_referral_bonuses_paid: number;
  advertisement_payouts: number;
  by_transaction_type: Record<string, number>;
}

export interface PenaltiesReport extends ReportRange {
  penalties_by_status: Record<string, number>;
  penalties_by_type: Record<string, number>;
  total_amount_outstanding: number;
  total_amount_settled_in_range: number;
}

export interface PromotionsReferralsReport extends ReportRange {
  entitlements_granted_in_range: Record<string, number>;
  entitlements_used_in_range: number;
  total_discount_given: number;
  referrals_by_status: Record<string, number>;
  rewards_issued_in_range: number;
}

export interface SafetySupportReport extends ReportRange {
  incidents_by_status: Record<string, number>;
  average_incident_resolution_minutes: number;
  cases_by_status: Record<string, number>;
  average_case_resolution_minutes: number;
}

export interface NotificationsReport extends ReportRange {
  deliveries_by_channel: Record<string, number>;
  deliveries_by_status: Record<string, number>;
  delivery_success_rate: number;
}

export interface MatchingReport extends ReportRange {
  offers_by_status: Record<string, number>;
  offer_acceptance_rate: number;
  average_time_to_accept_seconds: number;
}

// ---------------------------------------------------------------------
// Settings (api-contracts.md §46.17, ADR-0048, Admin Web §4.19).
// SETTINGS is Super-Admin-only, never grantable to an employee admin
// (BR-126) — unlike every other module, there's no partial-access case
// to design for here. Fare/Platform Fee/Referral/Notification settings
// are NOT rows in this table — they keep their own dedicated,
// versioned screens; this table only owns what has no home elsewhere
// (ADR-0048 Decision 1).
// ---------------------------------------------------------------------

export type SettingCategory =
  | "PROMOTION_DEFAULT"
  | "OPERATIONAL_THRESHOLD"
  | "FEATURE_FLAG"
  | "GENERAL";

/** `value` is a bare JSON scalar/object, shape determined by whatever
 * the seeded key already holds (ADR-0048 §4) — no per-key schema. */
export interface Setting {
  key: string;
  value: unknown;
  category: SettingCategory;
  description: string;
  updated_by: string;
  updated_at: string;
}
