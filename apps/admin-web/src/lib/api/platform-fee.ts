import { apiGet, apiPost } from "./client";
import type {
  CreatePlatformFeeRuleRequest,
  PaginatedEnvelope,
  PlatformFeeRule,
} from "./types";

/**
 * Platform Fee Management (api-contracts.md §46.14, ADR-0045, Admin
 * Web §4.8). Same DRAFT/IN_REVIEW/PUBLISHED CRUD shape as Fare
 * Management, own table/permission (FINANCE, not FARE_MANAGEMENT).
 * No sample-data fallback, same rule as every other operational screen
 * in this app.
 */

export function listPlatformFeeRules(
  vehicleCategory: string,
  status: string,
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<PlatformFeeRule>> {
  return apiGet<PaginatedEnvelope<PlatformFeeRule>>(
    "/api/v1/admin/platform-fee-rules",
    {
      vehicle_category: vehicleCategory || undefined,
      status: status || undefined,
      page,
      page_size: pageSize,
    },
  );
}

export function getPlatformFeeRule(ruleId: string): Promise<PlatformFeeRule> {
  return apiGet<PlatformFeeRule>(`/api/v1/admin/platform-fee-rules/${ruleId}`);
}

export function createPlatformFeeRule(
  body: CreatePlatformFeeRuleRequest,
): Promise<PlatformFeeRule> {
  return apiPost<PlatformFeeRule>("/api/v1/admin/platform-fee-rules", body);
}

export function submitPlatformFeeRuleForReview(
  ruleId: string,
): Promise<PlatformFeeRule> {
  return apiPost<PlatformFeeRule>(
    `/api/v1/admin/platform-fee-rules/${ruleId}/submit-for-review`,
    {},
  );
}

/** `effectiveFrom` is optional — omitted means "effective now" (the
 * backend's own default), not "unset". */
export function publishPlatformFeeRule(
  ruleId: string,
  effectiveFrom?: string,
): Promise<PlatformFeeRule> {
  return apiPost<PlatformFeeRule>(
    `/api/v1/admin/platform-fee-rules/${ruleId}/publish`,
    { effective_from: effectiveFrom || undefined },
  );
}
