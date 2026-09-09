"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { StatCard } from "./StatCard";
import { Pill } from "./Pill";
import { RidesByStatusCard } from "./RidesByStatusCard";
import { AuditFeedCard } from "./AuditFeedCard";
import {
  getAdminProfile,
  getDashboardSummary,
  getRecentAuditLog,
} from "@/lib/api/dashboard";
import type {
  AdminProfile,
  AuditLogEntry,
  DashboardSummary,
} from "@/lib/api/types";
import styles from "./DashboardPage.module.css";

const CURRENCY = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

const TIME = new Intl.DateTimeFormat("en-IN", {
  hour: "2-digit",
  minute: "2-digit",
});

/** A window-focus refresh only actually re-fetches if this long has
 * passed since the last successful load — refocusing the tab twice in
 * a few seconds shouldn't fire two real requests. No doc specifies a
 * cadence; this is an implementation default, not a business rule. */
const MIN_REFRESH_INTERVAL_MS = 15_000;

interface LoadedState {
  summary: DashboardSummary;
  profile: AdminProfile;
  auditLog: AuditLogEntry[];
  updatedAt: Date;
}

export function DashboardPage() {
  const [state, setState] = useState<LoadedState | null>(null);
  const [failed, setFailed] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const lastLoadedAt = useRef<number>(0);

  const applyLoadResult = useCallback(
    (
      result: [
        Awaited<ReturnType<typeof getDashboardSummary>>,
        Awaited<ReturnType<typeof getAdminProfile>>,
        Awaited<ReturnType<typeof getRecentAuditLog>>,
      ],
    ) => {
      const [summary, profile, auditLog] = result;
      setState({
        summary,
        profile,
        auditLog,
        updatedAt: new Date(),
      });
      lastLoadedAt.current = Date.now();
      setFailed(false);
    },
    [],
  );

  // Refresh, triggered only from event handlers below (a click, a
  // window-focus event) — never called directly from an effect body.
  const refresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      applyLoadResult(
        await Promise.all([
          getDashboardSummary(),
          getAdminProfile(),
          getRecentAuditLog(),
        ]),
      );
    } catch {
      setFailed(true);
    } finally {
      setIsRefreshing(false);
    }
  }, [applyLoadResult]);

  // Initial load — the one setState-from-an-effect case, written as the
  // React docs' own "Fetching data" pattern (an inline async IIFE with
  // an ignore flag), not via the shared `refresh` above, since calling
  // a function that transitively calls setState from an effect body is
  // exactly what react-hooks/set-state-in-effect flags.
  useEffect(() => {
    let ignore = false;
    async function loadOnMount() {
      try {
        const result = await Promise.all([
          getDashboardSummary(),
          getAdminProfile(),
          getRecentAuditLog(),
        ]);
        if (!ignore) applyLoadResult(result);
      } catch {
        if (!ignore) setFailed(true);
      }
    }
    loadOnMount();
    return () => {
      ignore = true;
    };
  }, [applyLoadResult]);

  // Window-focus refresh (owner decision: "window-focus refresh + manual
  // Refresh button" — no polling interval).
  useEffect(() => {
    function onFocus() {
      if (Date.now() - lastLoadedAt.current < MIN_REFRESH_INTERVAL_MS) return;
      refresh();
    }
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refresh]);

  if (failed && !state) {
    return (
      <div className={styles.fullPageMessage}>
        <p>Something went wrong loading the dashboard. Try reloading.</p>
      </div>
    );
  }

  if (!state) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading dashboard…</p>
      </div>
    );
  }

  const { summary, profile, auditLog, updatedAt } = state;
  const today = new Date().toLocaleDateString("en-IN", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return (
    <AppShell
      title="Dashboard"
      subtitle={`${today} · all times IST`}
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      {failed && (
        <div className={styles.refreshFailedBanner} role="status">
          Couldn&apos;t refresh — showing the last successful load.
        </div>
      )}

      <div className={styles.headerRow}>
        <div className={styles.sectionLabel}>Overview</div>
        <div className={styles.refreshControl}>
          <span className={styles.updatedAt}>
            Updated {TIME.format(updatedAt)}
          </span>
          <button
            type="button"
            className={styles.refreshButton}
            onClick={() => refresh()}
            disabled={isRefreshing}
          >
            {isRefreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      <div className={styles.statGrid}>
        <StatCard
          label="Pending driver approvals"
          value={summary.pending_driver_approvals}
          sub="Awaiting document review"
          severity={summary.pending_driver_approvals > 0 ? "warning" : "success"}
        />
        <StatCard
          label="Pending vehicle approvals"
          value={summary.pending_vehicle_approvals}
          sub="Awaiting document review"
          severity={summary.pending_vehicle_approvals > 0 ? "warning" : "success"}
        />
        <StatCard
          label="Open SOS incidents"
          value={summary.open_sos_incidents}
          sub={
            summary.open_sos_incidents > 0 ? (
              <Pill tone="danger">Needs attention</Pill>
            ) : (
              <Pill tone="success">All clear</Pill>
            )
          }
          severity={summary.open_sos_incidents > 0 ? "danger" : "success"}
        />
        <StatCard
          label="Open support cases"
          value={summary.open_support_cases}
          severity={summary.open_support_cases > 0 ? "info" : "success"}
        />
        <StatCard
          label="Open GPS disputes"
          value={summary.open_gps_disputes}
          sub="Within the 24h evidence window"
          severity={summary.open_gps_disputes > 0 ? "warning" : "success"}
        />
        <StatCard
          label="Outstanding penalties"
          value={summary.outstanding_penalties}
          sub="Unsettled records"
          severity={summary.outstanding_penalties > 0 ? "danger" : "success"}
        />
        <StatCard
          label="Online drivers"
          value={summary.online_drivers}
          sub="Currently available for dispatch"
          severity="info"
        />
        <StatCard
          label="Platform fee collected today"
          value={CURRENCY.format(summary.platform_fee_collected_today)}
          sub={<Pill tone="gold">Live per ride acceptance</Pill>}
          highlight
        />
      </div>

      <div className={styles.sectionLabel}>Today&apos;s activity</div>
      <div className={styles.lowerGrid}>
        <RidesByStatusCard byStatus={summary.rides_today_by_status} />
        <AuditFeedCard entries={auditLog} />
      </div>
    </AppShell>
  );
}
