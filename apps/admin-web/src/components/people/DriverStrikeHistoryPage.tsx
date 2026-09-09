"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { getAdminProfile } from "@/lib/api/dashboard";
import { listDriverStrikes } from "@/lib/api/people";
import { ApiError, NoSessionError } from "@/lib/api/client";
import type { AdminProfile, DriverStrike } from "@/lib/api/types";
import styles from "./DriverStrikeHistoryPage.module.css";

const PAGE_SIZE = 20;

const DATE_TIME = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

function errorMessage(error: unknown): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) {
    if (error.code === "FORBIDDEN") {
      return "Your admin account does not have access to Drivers.";
    }
    if (error.code === "RESOURCE_NOT_FOUND") {
      return "No driver found.";
    }
    return error.message;
  }
  return "Couldn't load strike history. Try again.";
}

interface ListState {
  strikes: DriverStrike[];
  totalPages: number;
  page: number;
}

/** Driver Strike History (Admin Web §4.9, api-contracts.md §46.18) —
 * read-only, no action exists on this screen. `driver.drivers.strikes`
 * (shown on Driver Detail as an at-a-glance counter) is the summary;
 * this is the underlying detail view, one row per recorded strike. */
export function DriverStrikeHistoryPage({ driverId }: { driverId: string }) {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [list, setList] = useState<ListState | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const loadList = useCallback(
    async (page: number) => {
      setListLoading(true);
      setListError(null);
      try {
        const result = await listDriverStrikes(driverId, page, PAGE_SIZE);
        setList({
          strikes: result.items,
          totalPages: Math.max(1, result.pagination.total_pages),
          page: result.pagination.page,
        });
      } catch (error) {
        setListError(errorMessage(error));
      } finally {
        setListLoading(false);
      }
    },
    [driverId],
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

    async function loadListOnMount() {
      try {
        const result = await listDriverStrikes(driverId, 1, PAGE_SIZE);
        if (ignore) return;
        setList({
          strikes: result.items,
          totalPages: Math.max(1, result.pagination.total_pages),
          page: result.pagination.page,
        });
      } catch (error) {
        if (!ignore) setListError(errorMessage(error));
      } finally {
        if (!ignore) setListLoading(false);
      }
    }

    loadProfileOnMount();
    loadListOnMount();
    return () => {
      ignore = true;
    };
  }, [driverId]);

  if (profileFailed) {
    return (
      <div className={styles.fullPageMessage}>
        <p>Something went wrong loading Drivers. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Drivers…</p>
      </div>
    );
  }

  return (
    <AppShell
      title="Strike history"
      subtitle={driverId}
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <Link href={`/drivers/${driverId}`} className={styles.backLink}>
        ← Back to driver
      </Link>

      {listLoading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading strike history…
        </div>
      )}

      {!listLoading && listError && (
        <div className={styles.errorBanner} role="alert">
          {listError}
        </div>
      )}

      {!listLoading && !listError && list && (
        <>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Reason</th>
                <th>Ride</th>
                <th>Recorded</th>
              </tr>
            </thead>
            <tbody>
              {list.strikes.length === 0 && (
                <tr>
                  <td colSpan={3} className={styles.emptyCell}>
                    No strikes recorded for this driver.
                  </td>
                </tr>
              )}
              {list.strikes.map((strike) => (
                <tr key={strike.strike_id}>
                  <td>{strike.reason}</td>
                  <td className={styles.idCell}>{strike.ride_id ?? "—"}</td>
                  <td>{DATE_TIME.format(new Date(strike.created_at))}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className={styles.pagination}>
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => loadList(list.page - 1)}
              disabled={list.page <= 1}
            >
              Previous
            </button>
            <span className={styles.pageIndicator}>
              Page {list.page} of {list.totalPages}
            </span>
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => loadList(list.page + 1)}
              disabled={list.page >= list.totalPages}
            >
              Next
            </button>
          </div>
        </>
      )}
    </AppShell>
  );
}
