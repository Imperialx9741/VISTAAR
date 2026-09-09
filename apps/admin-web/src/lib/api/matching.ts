import { apiGet } from "./client";
import type { MatchingOffer, OnlineDriversSummary, PaginatedEnvelope } from "./types";

/**
 * Matching / Offers (api-contracts.md §46.20, ADR-0054, Admin Web
 * §4.6). Read-only — no mutation exists in this module, and none is
 * proposed; the matching algorithm itself stays entirely driver-facing.
 */

export function getOnlineDrivers(): Promise<OnlineDriversSummary> {
  return apiGet<OnlineDriversSummary>("/api/v1/admin/matching/online-drivers");
}

export function searchOffers(
  status: string,
  rideId: string,
  driverId: string,
  from: string,
  to: string,
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<MatchingOffer>> {
  return apiGet<PaginatedEnvelope<MatchingOffer>>("/api/v1/admin/matching/offers", {
    status: status || undefined,
    ride_id: rideId || undefined,
    driver_id: driverId || undefined,
    from: from || undefined,
    to: to || undefined,
    page,
    page_size: pageSize,
  });
}

export function getOffer(offerId: string): Promise<MatchingOffer> {
  return apiGet<MatchingOffer>(`/api/v1/admin/matching/offers/${offerId}`);
}
