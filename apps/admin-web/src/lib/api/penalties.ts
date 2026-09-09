import { apiGet, apiPost } from "./client";
import type { PaginatedEnvelope, Penalty } from "./types";

/**
 * Penalties / Strikes (api-contracts.md §48, ADR-0023, Admin Web §4.9).
 * The only documented resolve action is "WAIVE" (validated server-side,
 * not here). Driver Strike History has no endpoint yet — not wired
 * here.
 */

export function searchPenalties(
  status: string,
  userId: string,
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<Penalty>> {
  return apiGet<PaginatedEnvelope<Penalty>>("/api/v1/admin/penalties", {
    status: status || undefined,
    user_id: userId || undefined,
    page,
    page_size: pageSize,
  });
}

export function resolvePenalty(
  penaltyId: string,
  reason?: string,
): Promise<Penalty> {
  return apiPost<Penalty>(`/api/v1/admin/penalties/${penaltyId}/resolve`, {
    action: "WAIVE",
    reason: reason || undefined,
  });
}
