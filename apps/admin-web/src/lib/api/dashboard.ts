import { apiGet } from "./client";
import type {
  AdminProfile,
  AuditLogEntry,
  DashboardSummary,
  PaginatedEnvelope,
} from "./types";

/**
 * Real backend calls only — no sample-data fallback. Removed 2026-09-08
 * (owner-directed cleanup, "VISTAAR ADMIN CONSOLE — MASTER AUDIT"): this
 * file previously caught every failure (no session, network error, any
 * backend rejection) and substituted hardcoded values from mock-data.ts
 * instead, which risked a genuine outage or a real 4xx/5xx looking
 * identical to a healthy, logged-in session showing real numbers. Every
 * caller already has its own real error-handling path for exactly this
 * case (`profileFailed`/`setProfileFailed`, present in every page that
 * calls getAdminProfile — previously unreachable dead code, since this
 * file never let an error propagate that far) — removing the try/catch
 * here is what makes that existing path live. See PeopleDetail.module.css
 * consumers (DriverDetailPage, VehicleDetailPage, etc.) for the resulting
 * "Something went wrong. Try reloading." real error state.
 */

export function getDashboardSummary(): Promise<DashboardSummary> {
  return apiGet<DashboardSummary>("/api/v1/admin/dashboard/summary");
}

export function getAdminProfile(): Promise<AdminProfile> {
  return apiGet<AdminProfile>("/api/v1/admin/me");
}

export async function getRecentAuditLog(): Promise<AuditLogEntry[]> {
  const page = await apiGet<PaginatedEnvelope<AuditLogEntry>>(
    "/api/v1/admin/audit-logs",
    { page: 1, page_size: 5 },
  );
  return page.items;
}
