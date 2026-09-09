import { apiGet, apiPost } from "./client";
import type {
  CustomerDetail,
  CustomerSummary,
  DriverDetail,
  DriverStrike,
  DriverSummary,
  PaginatedEnvelope,
  Vehicle,
  VehicleDocument,
  VerificationCase,
} from "./types";

/**
 * Customers / Drivers / Vehicles / Verification (api-contracts.md
 * §46.4, Admin Web §4.1-§4.4). Same rule as lib/api/admin-management.ts:
 * no sample-data fallback anywhere here — an operations console showing
 * a fake driver a user could then "approve" is a materially different
 * risk than the Dashboard's own read-only summary tiles.
 */

export function searchCustomers(
  query: string,
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<CustomerSummary>> {
  return apiGet<PaginatedEnvelope<CustomerSummary>>("/api/v1/admin/customers", {
    query: query || undefined,
    page,
    page_size: pageSize,
  });
}

export function getCustomer(customerId: string): Promise<CustomerDetail> {
  return apiGet<CustomerDetail>(`/api/v1/admin/customers/${customerId}`);
}

export function searchDrivers(
  query: string,
  status: string,
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<DriverSummary>> {
  return apiGet<PaginatedEnvelope<DriverSummary>>("/api/v1/admin/drivers", {
    query: query || undefined,
    status: status || undefined,
    page,
    page_size: pageSize,
  });
}

/** Driver Review — the pre-existing detail endpoint (phone + nested
 * documents), reused as Driver Detail rather than duplicated. */
export function getDriver(driverId: string): Promise<DriverDetail> {
  return apiGet<DriverDetail>(`/api/v1/admin/drivers/${driverId}`);
}

export function approveDriver(driverId: string): Promise<DriverDetail> {
  return apiPost<DriverDetail>(`/api/v1/admin/drivers/${driverId}/approve`, {});
}

/** Driver Strike History (api-contracts.md §46.18, Admin Web §4.9) —
 * the underlying detail view behind DriverDetail.strikes' at-a-glance
 * counter. */
export function listDriverStrikes(
  driverId: string,
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<DriverStrike>> {
  return apiGet<PaginatedEnvelope<DriverStrike>>(
    `/api/v1/admin/drivers/${driverId}/strikes`,
    { page, page_size: pageSize },
  );
}

export function rejectDriver(
  driverId: string,
  reason: string,
): Promise<DriverDetail> {
  return apiPost<DriverDetail>(`/api/v1/admin/drivers/${driverId}/reject`, {
    reason: reason || undefined,
  });
}

export function suspendDriver(
  driverId: string,
  reason: string,
): Promise<DriverSummary> {
  return apiPost<DriverSummary>(`/api/v1/admin/drivers/${driverId}/suspend`, {
    reason: reason || undefined,
  });
}

export function reactivateDriver(driverId: string): Promise<DriverSummary> {
  return apiPost<DriverSummary>(
    `/api/v1/admin/drivers/${driverId}/reactivate`,
    {},
  );
}

export function searchVehicles(
  query: string,
  status: string,
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<Vehicle>> {
  return apiGet<PaginatedEnvelope<Vehicle>>("/api/v1/admin/vehicles", {
    query: query || undefined,
    status: status || undefined,
    page,
    page_size: pageSize,
  });
}

export function getVehicle(vehicleId: string): Promise<Vehicle> {
  return apiGet<Vehicle>(`/api/v1/admin/vehicles/${vehicleId}`);
}

export function approveVehicle(vehicleId: string): Promise<Vehicle> {
  return apiPost<Vehicle>(`/api/v1/admin/vehicles/${vehicleId}/approve`, {});
}

export function rejectVehicle(
  vehicleId: string,
  reason: string,
): Promise<Vehicle> {
  return apiPost<Vehicle>(`/api/v1/admin/vehicles/${vehicleId}/reject`, {
    reason: reason || undefined,
  });
}

export async function listVehicleDocuments(
  vehicleId: string,
): Promise<VehicleDocument[]> {
  const result = await apiGet<{ documents: VehicleDocument[] }>(
    `/api/v1/admin/vehicles/${vehicleId}/documents`,
  );
  return result.documents;
}

export function searchVerificationQueue(
  status: string,
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<VerificationCase>> {
  return apiGet<PaginatedEnvelope<VerificationCase>>(
    "/api/v1/admin/verification/queue",
    { status: status || undefined, page, page_size: pageSize },
  );
}
