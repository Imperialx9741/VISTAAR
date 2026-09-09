import { apiGet, apiPost } from "./client";
import type { CreateFareRuleRequest, FareRule, PaginatedEnvelope } from "./types";

/**
 * Fare Management (api-contracts.md §46.7, ADR-0042, Admin Web §4.8).
 * No sample-data fallback, same rule as every other operational screen
 * in this app.
 */

export function listFareRules(
  vehicleCategory: string,
  status: string,
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<FareRule>> {
  return apiGet<PaginatedEnvelope<FareRule>>("/api/v1/admin/fare-rules", {
    vehicle_category: vehicleCategory || undefined,
    status: status || undefined,
    page,
    page_size: pageSize,
  });
}

export function getFareRule(ruleId: string): Promise<FareRule> {
  return apiGet<FareRule>(`/api/v1/admin/fare-rules/${ruleId}`);
}

export function createFareRule(
  body: CreateFareRuleRequest,
): Promise<FareRule> {
  return apiPost<FareRule>("/api/v1/admin/fare-rules", body);
}

export function submitFareRuleForReview(ruleId: string): Promise<FareRule> {
  return apiPost<FareRule>(
    `/api/v1/admin/fare-rules/${ruleId}/submit-for-review`,
    {},
  );
}

/** `effectiveFrom` is optional — omitted means "effective now" (the
 * backend's own default), not "unset". */
export function publishFareRule(
  ruleId: string,
  effectiveFrom?: string,
): Promise<FareRule> {
  return apiPost<FareRule>(`/api/v1/admin/fare-rules/${ruleId}/publish`, {
    effective_from: effectiveFrom || undefined,
  });
}
