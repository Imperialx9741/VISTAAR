type Tone = "neutral" | "info" | "success" | "warning" | "danger" | "gold";

/** One shared status→Pill-tone mapping for every status string used
 * across Customers/Drivers/Vehicles/Verification/Fare
 * Management/Offers-Coupons/Safety/Support/Referrals/Notifications/
 * Advertisements/Rides/Penalties — these enums (DriverVerificationStatus,
 * DriverOperationalStatus, VehicleVerificationStatus,
 * VehicleOperationalStatus, DocumentVerificationStatus,
 * VerificationCaseStatus, FareRuleStatus, IncidentStatus,
 * SupportCaseStatus, ReferralStatus, RewardConfigStatus, DeliveryStatus,
 * TemplateStatus, CampaignStatus, DriverCampaignStatus,
 * VerificationStatus, PayoutStatus, RideStatus, PenaltyStatus) never
 * share a single TypeScript type, but their values don't collide, so
 * one function covers all of them rather than one switch per screen.
 * `ENDED` (Ad campaigns) and `CLOSED` (Safety incidents, Rides) are
 * deliberately left unmapped — a terminal-but-not-bad state falls to
 * the default `neutral`. */
export function toneForStatus(status: string): Tone {
  switch (status) {
    case "APPROVED":
    case "ACTIVE":
    case "ACTIVATED":
    case "ONLINE":
    case "PUBLISHED":
    case "RESOLVED":
    case "SENT":
    case "VERIFIED":
    case "PAID":
    case "ACCEPTED":
    case "COMPLETED":
    case "SETTLED":
    case "WAIVED":
      return "success";
    case "REJECTED":
    case "SUSPENDED":
    case "EXPIRED":
    case "INELIGIBLE":
    case "FAILED":
    case "CANCELLED":
      return "danger";
    case "ON_RIDE":
    case "MANUAL_REVIEW":
    case "PROCESSING":
    case "IN_REVIEW":
    case "IN_PROGRESS":
    case "WAITING_FOR_USER":
    case "PAUSED":
    case "PROOF_SUBMITTED":
    case "STARTED":
      return "warning";
    case "PENDING":
    case "OPEN":
    case "ASSIGNED":
    case "ACKNOWLEDGED":
    case "SEARCHING":
    case "ARRIVED":
    case "OUTSTANDING":
    case "SCHEDULED":
      return "info";
    default:
      return "neutral";
  }
}
