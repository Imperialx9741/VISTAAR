import { apiGet } from "./client";
import type {
  CustomersReport,
  DriversReport,
  FinancialReport,
  MatchingReport,
  NotificationsReport,
  PenaltiesReport,
  PromotionsReferralsReport,
  RidesReport,
  SafetySupportReport,
} from "./types";

/**
 * Reports / Analytics (api-contracts.md §46.16, ADR-0047, Admin Web
 * §4.16). Nine read-only aggregate endpoints, VIEW-only permission —
 * nothing here mutates data. `from`/`to` are optional ISO datetimes;
 * omitted, the backend defaults to the last 30 days.
 */

function reportParams(from: string, to: string) {
  return { from: from || undefined, to: to || undefined };
}

export function getRidesReport(from: string, to: string): Promise<RidesReport> {
  return apiGet<RidesReport>(
    "/api/v1/admin/reports/rides",
    reportParams(from, to),
  );
}

export function getCustomersReport(
  from: string,
  to: string,
): Promise<CustomersReport> {
  return apiGet<CustomersReport>(
    "/api/v1/admin/reports/customers",
    reportParams(from, to),
  );
}

export function getDriversReport(
  from: string,
  to: string,
): Promise<DriversReport> {
  return apiGet<DriversReport>(
    "/api/v1/admin/reports/drivers",
    reportParams(from, to),
  );
}

export function getFinancialReport(
  from: string,
  to: string,
): Promise<FinancialReport> {
  return apiGet<FinancialReport>(
    "/api/v1/admin/reports/financial",
    reportParams(from, to),
  );
}

export function getPenaltiesReport(
  from: string,
  to: string,
): Promise<PenaltiesReport> {
  return apiGet<PenaltiesReport>(
    "/api/v1/admin/reports/penalties",
    reportParams(from, to),
  );
}

export function getPromotionsReferralsReport(
  from: string,
  to: string,
): Promise<PromotionsReferralsReport> {
  return apiGet<PromotionsReferralsReport>(
    "/api/v1/admin/reports/promotions-referrals",
    reportParams(from, to),
  );
}

export function getSafetySupportReport(
  from: string,
  to: string,
): Promise<SafetySupportReport> {
  return apiGet<SafetySupportReport>(
    "/api/v1/admin/reports/safety-support",
    reportParams(from, to),
  );
}

export function getNotificationsReport(
  from: string,
  to: string,
): Promise<NotificationsReport> {
  return apiGet<NotificationsReport>(
    "/api/v1/admin/reports/notifications",
    reportParams(from, to),
  );
}

export function getMatchingReport(
  from: string,
  to: string,
): Promise<MatchingReport> {
  return apiGet<MatchingReport>(
    "/api/v1/admin/reports/matching",
    reportParams(from, to),
  );
}
