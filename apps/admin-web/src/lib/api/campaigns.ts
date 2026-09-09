import { apiGet, apiPatch, apiPost, apiUpload } from "./client";
import type {
  BulkEligibleCustomersResult,
  Campaign,
  CampaignRequest,
  PaginatedEnvelope,
} from "./types";

/**
 * Campaigns / Offers & Coupons (api-contracts.md §46.2, ADR-0041, Admin
 * Web §4.10). No sample-data fallback, same rule as every other
 * operational screen in this app.
 */

export function listCampaigns(
  status: string,
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<Campaign>> {
  return apiGet<PaginatedEnvelope<Campaign>>("/api/v1/admin/campaigns", {
    status: status || undefined,
    page,
    page_size: pageSize,
  });
}

export function getCampaign(campaignId: string): Promise<Campaign> {
  return apiGet<Campaign>(`/api/v1/admin/campaigns/${campaignId}`);
}

export function createCampaign(body: CampaignRequest): Promise<Campaign> {
  return apiPost<Campaign>("/api/v1/admin/campaigns", body);
}

/** DRAFT only — the backend rejects a PATCH on any other status
 * (INVALID_STATE_TRANSITION), not this function. */
export function updateCampaign(
  campaignId: string,
  body: CampaignRequest,
): Promise<Campaign> {
  return apiPatch<Campaign>(`/api/v1/admin/campaigns/${campaignId}`, body);
}

export function activateCampaign(campaignId: string): Promise<Campaign> {
  return apiPost<Campaign>(
    `/api/v1/admin/campaigns/${campaignId}/activate`,
    {},
  );
}

export function pauseCampaign(campaignId: string): Promise<Campaign> {
  return apiPost<Campaign>(`/api/v1/admin/campaigns/${campaignId}/pause`, {});
}

export function endCampaign(campaignId: string): Promise<Campaign> {
  return apiPost<Campaign>(`/api/v1/admin/campaigns/${campaignId}/end`, {});
}

/** CSV Bulk Customer Targeting (api-contracts.md §46.19, ADR-0041 §9)
 * — additive to the campaign's existing eligible-customer set. Only
 * valid while the campaign is DRAFT and eligible_scope='SELECTED'. */
export function bulkAddEligibleCustomers(
  campaignId: string,
  file: File,
): Promise<BulkEligibleCustomersResult> {
  return apiUpload<BulkEligibleCustomersResult>(
    `/api/v1/admin/campaigns/${campaignId}/eligible-customers/bulk`,
    file,
  );
}
