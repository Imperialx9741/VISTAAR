import { apiGet } from "./client";
import type { PaginatedEnvelope, Ride } from "./types";

/**
 * Rides (api-contracts.md §46, ADR-0023, Admin Web §4.5). Read-only —
 * search + full lifecycle detail, no admin-side intervention action
 * exists or was asked for.
 */

export function searchRides(
  status: string,
  driverId: string,
  customerId: string,
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<Ride>> {
  return apiGet<PaginatedEnvelope<Ride>>("/api/v1/admin/rides", {
    status: status || undefined,
    driver_id: driverId || undefined,
    customer_id: customerId || undefined,
    page,
    page_size: pageSize,
  });
}

export function getRide(rideId: string): Promise<Ride> {
  return apiGet<Ride>(`/api/v1/admin/rides/${rideId}`);
}
