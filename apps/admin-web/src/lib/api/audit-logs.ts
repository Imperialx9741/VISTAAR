import { apiGet } from "./client";
import type { AuditLogEntry, PaginatedEnvelope } from "./types";

/** GET /api/v1/admin/audit-logs (api-contracts.md §46.3, Admin Web
 * §4.17). Every filter is optional and combinable; an empty string here
 * means "not applied," matching the backend's own "omitted filter"
 * contract — apiGet already drops `undefined` params from the query
 * string. `createdAfter`/`createdBefore` are full ISO 8601 datetimes
 * (the backend's own `datetime | None` query params) — the caller is
 * responsible for turning a plain date picker value into a day
 * boundary. No sample-data fallback, same rule as every other
 * operational screen in this app (lib/api/admin-management.ts,
 * lib/api/people.ts). */
export function searchAuditLogs(
  filters: {
    adminId?: string;
    targetType?: string;
    targetId?: string;
    action?: string;
    createdAfter?: string;
    createdBefore?: string;
  },
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<AuditLogEntry>> {
  return apiGet<PaginatedEnvelope<AuditLogEntry>>("/api/v1/admin/audit-logs", {
    admin_id: filters.adminId || undefined,
    target_type: filters.targetType || undefined,
    target_id: filters.targetId || undefined,
    action: filters.action || undefined,
    created_after: filters.createdAfter || undefined,
    created_before: filters.createdBefore || undefined,
    page,
    page_size: pageSize,
  });
}
