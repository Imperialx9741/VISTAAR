import { apiGet, apiPost } from "./client";
import type {
  GpsDispute,
  PaginatedEnvelope,
  SafetyIncident,
  SupportCaseDetail,
  SupportCaseSummary,
} from "./types";

/**
 * Safety/SOS (api-contracts.md §46.8, ADR-0022, Admin Web §4.13) and
 * Support/Disputes (§46.9, §4.14). No sample-data fallback, same rule
 * as every other operational screen in this app.
 */

export function searchSafetyIncidents(
  status: string,
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<SafetyIncident>> {
  return apiGet<PaginatedEnvelope<SafetyIncident>>(
    "/api/v1/admin/safety/incidents",
    { status: status || undefined, page, page_size: pageSize },
  );
}

export function getSafetyIncident(incidentId: string): Promise<SafetyIncident> {
  return apiGet<SafetyIncident>(`/api/v1/admin/safety/incidents/${incidentId}`);
}

export function acknowledgeSafetyIncident(
  incidentId: string,
): Promise<SafetyIncident> {
  return apiPost<SafetyIncident>(
    `/api/v1/admin/safety/incidents/${incidentId}/acknowledge`,
    {},
  );
}

export function escalateSafetyIncident(
  incidentId: string,
): Promise<SafetyIncident> {
  return apiPost<SafetyIncident>(
    `/api/v1/admin/safety/incidents/${incidentId}/escalate`,
    {},
  );
}

export function resolveSafetyIncident(
  incidentId: string,
): Promise<SafetyIncident> {
  return apiPost<SafetyIncident>(
    `/api/v1/admin/safety/incidents/${incidentId}/resolve`,
    {},
  );
}

export function searchSupportCases(
  status: string,
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<SupportCaseSummary>> {
  return apiGet<PaginatedEnvelope<SupportCaseSummary>>(
    "/api/v1/admin/support/cases",
    { status: status || undefined, page, page_size: pageSize },
  );
}

export function getSupportCase(caseId: string): Promise<SupportCaseDetail> {
  return apiGet<SupportCaseDetail>(`/api/v1/admin/support/cases/${caseId}`);
}

export function resolveSupportCase(
  caseId: string,
): Promise<SupportCaseSummary> {
  return apiPost<SupportCaseSummary>(
    `/api/v1/admin/support/cases/${caseId}/resolve`,
    {},
  );
}

/** GPS Dispute (api-contracts.md §77, ADR-0032, Admin Web §4.14) —
 * reuses the SUPPORT permission, same module as Support Cases above. */
export function searchGpsDisputes(
  status: string,
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<GpsDispute>> {
  return apiGet<PaginatedEnvelope<GpsDispute>>("/api/v1/admin/gps-disputes", {
    status: status || undefined,
    page,
    page_size: pageSize,
  });
}

export function getGpsDispute(disputeId: string): Promise<GpsDispute> {
  return apiGet<GpsDispute>(`/api/v1/admin/gps-disputes/${disputeId}`);
}

/** APPROVE performs the exact ride transition the original GPS
 * verification would have on a real PASS; REJECT only records the
 * decision — see the backend's own RideService.resolve_gps_dispute()
 * docstring. `reason` is required (the backend rejects an empty one). */
export function resolveGpsDispute(
  disputeId: string,
  action: "APPROVE" | "REJECT",
  reason: string,
): Promise<GpsDispute> {
  return apiPost<GpsDispute>(`/api/v1/admin/gps-disputes/${disputeId}/resolve`, {
    action,
    reason,
  });
}
