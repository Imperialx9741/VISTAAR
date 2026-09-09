"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import { searchSupportCases } from "@/lib/api/safety-support";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdminProfile, SupportCaseSummary } from "@/lib/api/types";
import styles from "./SupportPage.module.css";

const PAGE_SIZE = 20;
const STATUSES = [
  "",
  "OPEN",
  "ASSIGNED",
  "IN_PROGRESS",
  "WAITING_FOR_USER",
  "RESOLVED",
  "CLOSED",
];

const DATE_TIME = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

function errorMessage(error: unknown): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) {
    if (error.code === "FORBIDDEN") {
      return "Your admin account does not have access to Support / Disputes.";
    }
    return error.message;
  }
  return "Couldn't load support cases. Try again.";
}

interface ListState {
  cases: SupportCaseSummary[];
  totalPages: number;
  page: number;
}

export function SupportPage() {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [status, setStatus] = useState("");
  const [list, setList] = useState<ListState | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const loadList = useCallback(async (searchStatus: string, page: number) => {
    setListLoading(true);
    setListError(null);
    try {
      const result = await searchSupportCases(searchStatus, page, PAGE_SIZE);
      setList({
        cases: result.items,
        totalPages: Math.max(1, result.pagination.total_pages),
        page: result.pagination.page,
      });
    } catch (error) {
      setListError(errorMessage(error));
    } finally {
      setListLoading(false);
    }
  }, []);

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
        const result = await searchSupportCases("", 1, PAGE_SIZE);
        if (ignore) return;
        setList({
          cases: result.items,
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
  }, []);

  if (profileFailed) {
    return (
      <div className={styles.fullPageMessage}>
        <p>Something went wrong loading Support / Disputes. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Support / Disputes…</p>
      </div>
    );
  }

  return (
    <AppShell
      title="Support / Disputes"
      subtitle="Customer and driver support cases"
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <nav className={styles.subNav} aria-label="Support sections">
        <Link href="/support/gps-disputes" className={styles.viewLink}>
          GPS Disputes →
        </Link>
      </nav>

      <form
        className={styles.searchBar}
        onSubmit={(event) => event.preventDefault()}
      >
        <select
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            void loadList(event.target.value, 1);
          }}
          className={styles.statusSelect}
          aria-label="Filter by status"
        >
          {STATUSES.map((value) => (
            <option key={value} value={value}>
              {value === "" ? "Any status" : value}
            </option>
          ))}
        </select>
      </form>

      {listLoading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading support cases…
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
                <th>Case</th>
                <th>Priority</th>
                <th>Status</th>
                <th>Opened</th>
                <th aria-hidden="true" />
              </tr>
            </thead>
            <tbody>
              {list.cases.length === 0 && (
                <tr>
                  <td colSpan={5} className={styles.emptyCell}>
                    No support cases found.
                  </td>
                </tr>
              )}
              {list.cases.map((supportCase) => (
                <tr key={supportCase.case_id}>
                  <td className={styles.idCell}>{supportCase.case_id}</td>
                  <td>{supportCase.priority}</td>
                  <td>
                    <Pill tone={toneForStatus(supportCase.status)}>
                      {supportCase.status}
                    </Pill>
                  </td>
                  <td>{DATE_TIME.format(new Date(supportCase.created_at))}</td>
                  <td className={styles.actionCell}>
                    <Link
                      href={`/support/${supportCase.case_id}`}
                      className={styles.viewLink}
                    >
                      View
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className={styles.pagination}>
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => loadList(status, list.page - 1)}
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
              onClick={() => loadList(status, list.page + 1)}
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
