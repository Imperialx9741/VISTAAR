import { apiGet, apiPatch, apiPost } from "./client";
import type {
  AdminAccount,
  AdminPermission,
  PaginatedEnvelope,
} from "./types";

/**
 * Admin Management (ADR-0040, BR-126/BR-127, api-contracts.md §46.1).
 * Unlike lib/api/dashboard.ts, nothing here falls back to sample data on
 * failure — see the comment on apiPost/apiPatch in lib/api/client.ts.
 * Every function throws ApiError/NoSessionError straight through; the
 * page components catch and render a real error state.
 */

export function listAdmins(
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<AdminAccount>> {
  return apiGet<PaginatedEnvelope<AdminAccount>>("/api/v1/admin/admins", {
    page,
    page_size: pageSize,
  });
}

export function getAdmin(adminId: string): Promise<AdminAccount> {
  return apiGet<AdminAccount>(`/api/v1/admin/admins/${adminId}`);
}

export function createAdmin(
  phone: string,
  permissions: AdminPermission[],
): Promise<AdminAccount> {
  return apiPost<AdminAccount>("/api/v1/admin/admins", { phone, permissions });
}

export function updatePermissions(
  adminId: string,
  permissions: AdminPermission[],
): Promise<{ permissions: AdminPermission[] }> {
  return apiPatch<{ permissions: AdminPermission[] }>(
    `/api/v1/admin/admins/${adminId}/permissions`,
    { permissions },
  );
}

export function disableAdmin(adminId: string): Promise<AdminAccount> {
  return apiPost<AdminAccount>(`/api/v1/admin/admins/${adminId}/disable`, {});
}

export function enableAdmin(adminId: string): Promise<AdminAccount> {
  return apiPost<AdminAccount>(`/api/v1/admin/admins/${adminId}/enable`, {});
}
