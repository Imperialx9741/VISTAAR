"use client";

import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { getAdminProfile } from "@/lib/api/dashboard";
import {
  getCustomersReport,
  getDriversReport,
  getFinancialReport,
  getMatchingReport,
  getNotificationsReport,
  getPenaltiesReport,
  getPromotionsReferralsReport,
  getRidesReport,
  getSafetySupportReport,
} from "@/lib/api/reports";
import { ApiError, NoSessionError } from "@/lib/api/client";
import type { AdminProfile } from "@/lib/api/types";
import styles from "./ReportsPage.module.css";

const CURRENCY = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 2,
});

const DATE_TIME = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

function percent(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`;
}

/** A plain <input type="date"> gives "YYYY-MM-DD" — widen to the day's
 * start/end so `from`/`to` (full ISO datetimes, inclusive on the
 * backend) act like an inclusive date range, same convention Audit
 * Logs already established. */
function toRangeParam(date: string, boundary: "start" | "end"): string {
  if (!date) return "";
  return boundary === "start"
    ? `${date}T00:00:00.000Z`
    : `${date}T23:59:59.999Z`;
}

const REPORT_TYPES = [
  { value: "rides", label: "Rides" },
  { value: "customers", label: "Customers" },
  { value: "drivers", label: "Drivers" },
  { value: "financial", label: "Financial" },
  { value: "penalties", label: "Penalties" },
  { value: "promotions-referrals", label: "Promotions & Referrals" },
  { value: "safety-support", label: "Safety & Support" },
  { value: "notifications", label: "Notifications" },
  { value: "matching", label: "Matching" },
] as const;

type ReportType = (typeof REPORT_TYPES)[number]["value"];

interface StatItem {
  label: string;
  value: string;
}

interface BreakdownItem {
  label: string;
  data: Record<string, number>;
}

interface ReportView {
  from: string;
  to: string;
  stats: StatItem[];
  breakdowns: BreakdownItem[];
}

async function loadReport(type: ReportType, from: string, to: string): Promise<ReportView> {
  const since = toRangeParam(from, "start");
  const until = toRangeParam(to, "end");

  switch (type) {
    case "rides": {
      const r = await getRidesReport(since, until);
      return {
        from: r.from,
        to: r.to,
        stats: [
          { label: "Average fare", value: CURRENCY.format(r.average_fare) },
          { label: "Completion rate", value: percent(r.completion_rate) },
        ],
        breakdowns: [
          { label: "Rides by status", data: r.rides_by_status },
          {
            label: "Rides by vehicle category",
            data: r.rides_by_vehicle_category,
          },
        ],
      };
    }
    case "customers": {
      const r = await getCustomersReport(since, until);
      return {
        from: r.from,
        to: r.to,
        stats: [
          { label: "Total customers", value: String(r.total_customers) },
          {
            label: "New in range",
            value: String(r.new_customers_in_range),
          },
        ],
        breakdowns: [],
      };
    }
    case "drivers": {
      const r = await getDriversReport(since, until);
      return {
        from: r.from,
        to: r.to,
        stats: [
          { label: "Total drivers", value: String(r.total_drivers) },
          { label: "New in range", value: String(r.new_drivers_in_range) },
        ],
        breakdowns: [
          { label: "By verification status", data: r.by_verification_status },
          { label: "By operational status", data: r.by_operational_status },
        ],
      };
    }
    case "financial": {
      const r = await getFinancialReport(since, until);
      return {
        from: r.from,
        to: r.to,
        stats: [
          {
            label: "Platform fee collected",
            value: CURRENCY.format(r.platform_fee_collected),
          },
          { label: "Fee reversals", value: CURRENCY.format(r.fee_reversals) },
          {
            label: "Driver referral bonuses paid",
            value: CURRENCY.format(r.driver_referral_bonuses_paid),
          },
          {
            label: "Advertisement payouts",
            value: CURRENCY.format(r.advertisement_payouts),
          },
        ],
        breakdowns: [
          { label: "By transaction type", data: r.by_transaction_type },
        ],
      };
    }
    case "penalties": {
      const r = await getPenaltiesReport(since, until);
      return {
        from: r.from,
        to: r.to,
        stats: [
          {
            label: "Total outstanding",
            value: CURRENCY.format(r.total_amount_outstanding),
          },
          {
            label: "Settled in range",
            value: CURRENCY.format(r.total_amount_settled_in_range),
          },
        ],
        breakdowns: [
          { label: "By status", data: r.penalties_by_status },
          { label: "By type", data: r.penalties_by_type },
        ],
      };
    }
    case "promotions-referrals": {
      const r = await getPromotionsReferralsReport(since, until);
      return {
        from: r.from,
        to: r.to,
        stats: [
          {
            label: "Entitlements used in range",
            value: String(r.entitlements_used_in_range),
          },
          {
            label: "Total discount given",
            value: CURRENCY.format(r.total_discount_given),
          },
          {
            label: "Rewards issued in range",
            value: CURRENCY.format(r.rewards_issued_in_range),
          },
        ],
        breakdowns: [
          {
            label: "Entitlements granted in range",
            data: r.entitlements_granted_in_range,
          },
          { label: "Referrals by status", data: r.referrals_by_status },
        ],
      };
    }
    case "safety-support": {
      const r = await getSafetySupportReport(since, until);
      return {
        from: r.from,
        to: r.to,
        stats: [
          {
            label: "Avg. incident resolution",
            value: `${r.average_incident_resolution_minutes.toFixed(1)} min`,
          },
          {
            label: "Avg. case resolution",
            value: `${r.average_case_resolution_minutes.toFixed(1)} min`,
          },
        ],
        breakdowns: [
          { label: "Incidents by status", data: r.incidents_by_status },
          { label: "Cases by status", data: r.cases_by_status },
        ],
      };
    }
    case "notifications": {
      const r = await getNotificationsReport(since, until);
      return {
        from: r.from,
        to: r.to,
        stats: [
          {
            label: "Delivery success rate",
            value: percent(r.delivery_success_rate),
          },
        ],
        breakdowns: [
          { label: "Deliveries by channel", data: r.deliveries_by_channel },
          { label: "Deliveries by status", data: r.deliveries_by_status },
        ],
      };
    }
    case "matching": {
      const r = await getMatchingReport(since, until);
      return {
        from: r.from,
        to: r.to,
        stats: [
          {
            label: "Offer acceptance rate",
            value: percent(r.offer_acceptance_rate),
          },
          {
            label: "Avg. time to accept",
            value: `${r.average_time_to_accept_seconds.toFixed(1)} sec`,
          },
        ],
        breakdowns: [{ label: "Offers by status", data: r.offers_by_status }],
      };
    }
  }
}

function errorMessage(error: unknown): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) {
    if (error.code === "FORBIDDEN") {
      return "Your admin account does not have access to Reports/Analytics.";
    }
    return error.message;
  }
  return "Couldn't load this report. Try again.";
}

/** Reports / Analytics (Admin Web §4.16, ADR-0047) — nine fixed-shape
 * read-only aggregate reports sharing one report-type picker and date
 * range, rather than nine separate routes; VIEW-only permission, no
 * mutations exist in this module. */
export function ReportsPage() {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [reportType, setReportType] = useState<ReportType>("rides");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const [report, setReport] = useState<ReportView | null>(null);
  const [reportLoading, setReportLoading] = useState(true);
  const [reportError, setReportError] = useState<string | null>(null);

  const load = useCallback(
    async (type: ReportType, from: string, to: string) => {
      setReportLoading(true);
      setReportError(null);
      try {
        const result = await loadReport(type, from, to);
        setReport(result);
      } catch (error) {
        setReportError(errorMessage(error));
      } finally {
        setReportLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    let ignore = false;

    async function loadProfileOnMount() {
      try {
        const result = await getAdminProfile();
        if (!ignore) setProfile(result);
      } catch {
        if (!ignore) setProfileFailed(true);
      }
    }

    async function loadReportOnMount() {
      try {
        const result = await loadReport("rides", "", "");
        if (!ignore) setReport(result);
      } catch (error) {
        if (!ignore) setReportError(errorMessage(error));
      } finally {
        if (!ignore) setReportLoading(false);
      }
    }

    loadProfileOnMount();
    loadReportOnMount();
    return () => {
      ignore = true;
    };
  }, []);

  if (profileFailed) {
    return (
      <div className={styles.fullPageMessage}>
        <p>Something went wrong loading Reports/Analytics. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Reports/Analytics…</p>
      </div>
    );
  }

  return (
    <AppShell
      title="Reports & Analytics"
      subtitle="Nine fixed-shape aggregate reports over an optional date range"
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <form
        className={styles.filterBar}
        onSubmit={(event) => {
          event.preventDefault();
          void load(reportType, dateFrom, dateTo);
        }}
      >
        <select
          value={reportType}
          onChange={(event) => {
            const value = event.target.value as ReportType;
            setReportType(value);
            void load(value, dateFrom, dateTo);
          }}
          className={styles.reportSelect}
          aria-label="Select report"
        >
          {REPORT_TYPES.map((type) => (
            <option key={type.value} value={type.value}>
              {type.label}
            </option>
          ))}
        </select>
        <input
          type="date"
          value={dateFrom}
          onChange={(event) => setDateFrom(event.target.value)}
          className={styles.filterInput}
          aria-label="From date"
        />
        <input
          type="date"
          value={dateTo}
          onChange={(event) => setDateTo(event.target.value)}
          className={styles.filterInput}
          aria-label="To date"
        />
        <button type="submit" className={styles.searchButton}>
          Apply
        </button>
      </form>

      {reportLoading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading report…
        </div>
      )}

      {!reportLoading && reportError && (
        <div className={styles.errorBanner} role="alert">
          {reportError}
        </div>
      )}

      {!reportLoading && !reportError && report && (
        <>
          <p className={styles.rangeNote}>
            {DATE_TIME.format(new Date(report.from))} –{" "}
            {DATE_TIME.format(new Date(report.to))}
          </p>

          {report.stats.length > 0 && (
            <div className={styles.statGrid}>
              {report.stats.map((stat) => (
                <div key={stat.label} className={styles.statCard}>
                  <div className={styles.statLabel}>{stat.label}</div>
                  <div className={styles.statValue}>{stat.value}</div>
                </div>
              ))}
            </div>
          )}

          {report.breakdowns.length > 0 && (
            <div className={styles.breakdownGrid}>
              {report.breakdowns.map((breakdown) => (
                <div key={breakdown.label} className={styles.breakdownCard}>
                  <div className={styles.breakdownTitle}>
                    {breakdown.label}
                  </div>
                  {Object.entries(breakdown.data).length === 0 && (
                    <div className={styles.breakdownRow}>
                      <span>No data in range</span>
                    </div>
                  )}
                  {Object.entries(breakdown.data).map(([key, count]) => (
                    <div key={key} className={styles.breakdownRow}>
                      <span>{key}</span>
                      <span className={styles.breakdownCount}>{count}</span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </AppShell>
  );
}
