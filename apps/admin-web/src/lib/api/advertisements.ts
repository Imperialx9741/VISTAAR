import { apiGet, apiPost } from "./client";
import type {
  AdAssignment,
  AdCampaign,
  AdPayout,
  CreateAdCampaignRequest,
  PaginatedEnvelope,
} from "./types";

/**
 * Advertisements (api-contracts.md §46.15, ADR-0046, Admin Web §4.15).
 * Three independent resources sharing one permission (ADVERTISEMENTS):
 * campaigns, driver assignments (installation/proof review), and
 * payouts. No sample-data fallback, same rule as every other
 * operational screen in this app.
 */

export function listAdCampaigns(
  status: string,
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<AdCampaign>> {
  return apiGet<PaginatedEnvelope<AdCampaign>>(
    "/api/v1/admin/advertisements/campaigns",
    { status: status || undefined, page, page_size: pageSize },
  );
}

export function getAdCampaign(campaignId: string): Promise<AdCampaign> {
  return apiGet<AdCampaign>(
    `/api/v1/admin/advertisements/campaigns/${campaignId}`,
  );
}

export function createAdCampaign(
  body: CreateAdCampaignRequest,
): Promise<AdCampaign> {
  return apiPost<AdCampaign>("/api/v1/admin/advertisements/campaigns", body);
}

export function pauseAdCampaign(campaignId: string): Promise<AdCampaign> {
  return apiPost<AdCampaign>(
    `/api/v1/admin/advertisements/campaigns/${campaignId}/pause`,
    {},
  );
}

export function resumeAdCampaign(campaignId: string): Promise<AdCampaign> {
  return apiPost<AdCampaign>(
    `/api/v1/admin/advertisements/campaigns/${campaignId}/resume`,
    {},
  );
}

export function endAdCampaign(campaignId: string): Promise<AdCampaign> {
  return apiPost<AdCampaign>(
    `/api/v1/admin/advertisements/campaigns/${campaignId}/end`,
    {},
  );
}

export function assignAdCampaignDriver(
  campaignId: string,
  driverId: string,
): Promise<AdAssignment> {
  return apiPost<AdAssignment>(
    `/api/v1/admin/advertisements/campaigns/${campaignId}/assignments`,
    { driver_id: driverId },
  );
}

export function searchAdAssignments(
  campaignId: string,
  driverId: string,
  status: string,
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<AdAssignment>> {
  return apiGet<PaginatedEnvelope<AdAssignment>>(
    "/api/v1/admin/advertisements/assignments",
    {
      campaign_id: campaignId || undefined,
      driver_id: driverId || undefined,
      status: status || undefined,
      page,
      page_size: pageSize,
    },
  );
}

export function getAdAssignment(assignmentId: string): Promise<AdAssignment> {
  return apiGet<AdAssignment>(
    `/api/v1/admin/advertisements/assignments/${assignmentId}`,
  );
}

/** Approve/Reject installation proof — sets the manual
 * verification_status field, not a live Admoto call (ADR-0046
 * Decision 2). */
export function verifyAdAssignment(
  assignmentId: string,
  approved: boolean,
): Promise<AdAssignment> {
  return apiPost<AdAssignment>(
    `/api/v1/admin/advertisements/assignments/${assignmentId}/verify`,
    { approved },
  );
}

export function calculateAdPayout(assignmentId: string): Promise<AdPayout> {
  return apiPost<AdPayout>(
    `/api/v1/admin/advertisements/assignments/${assignmentId}/payouts/calculate`,
    {},
  );
}

export function listAdPayouts(
  status: string,
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<AdPayout>> {
  return apiGet<PaginatedEnvelope<AdPayout>>(
    "/api/v1/admin/advertisements/payouts",
    { status: status || undefined, page, page_size: pageSize },
  );
}

/** Composes WalletService.credit(ADVERTISEMENT_PAYOUT) then
 * mark_payout_paid() server-side (ADR-0046 Decision 4) — one call from
 * this side. */
export function settleAdPayout(payoutId: string): Promise<AdPayout> {
  return apiPost<AdPayout>(
    `/api/v1/admin/advertisements/payouts/${payoutId}/settle`,
    {},
  );
}
