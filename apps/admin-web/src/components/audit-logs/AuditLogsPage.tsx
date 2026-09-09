"use client";

import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { getAdminProfile } from "@/lib/api/dashboard";
import { searchAuditLogs } from "@/lib/api/audit-logs";
import { ApiError, NoSessionError } from "@/lib/api/client";
import type { AdminProfile, AuditLogEntry } from "@/lib/api/types";
import styles from "./AuditLogsPage.module.css";

const PAGE_SIZE = 20;

const DATE_TIME = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

interface Filters {
  adminId: string;
  targetType: string;
  targetId: string;
  action: string;
  dateFrom: string;
  dateTo: string;
}

const EMPTY_FILTERS: Filters = {
  adminId: "",
  targetType: "",
  targetId: "",
  action: "",
  dateFrom: "",
  dateTo: "",
};

function toApiFilters(filters: Filters) {
  return {
    adminId: filters.adminId,
    targetType: filters.targetType,
    targetId: filters.targetId,
    action: filters.action,
    // A plain <input type="date"> gives "YYYY-MM-DD" — widen to the
    // day's start/end so `created_after`/`created_before` (full ISO
    // datetimes, inclusive on the backend) act like an inclusive date
    // range rather than silently excluding same-day rows.
    createdAfter: filters.dateFrom ? `${filters.dateFrom}T00:00:00.000Z` : "",
    createdBefore: filters.dateTo ? `${filters.dateTo}T23:59:59.999Z` : "",
  };
}

interface ListState {
  entries: AuditLogEntry[];
  totalPages: number;
  page: number;
}

function errorMessage(error: unknown): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) {
    if (error.code === "FORBIDDEN") {
      return "Your admin account does not have access to Audit Logs.";
    }
    return error.message;
  }
  return "Couldn't load audit logs. Try again.";
}

export function AuditLogsPage() {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [list, setList] = useState<ListState | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const loadList = useCallback(async (activeFilters: Filters, page: number) => {
    setListLoading(true);
    setListError(null);
    try {
      const result = await searchAuditLogs(
        toApiFilters(activeFilters),
        page,
        PAGE_SIZE,
      );
      setList({
        entries: result.items,
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
        const result = await searchAuditLogs(
          toApiFilters(EMPTY_FILTERS),
          1,
          PAGE_SIZE,
        );
        if (ignore) return;
        setList({
          entries: result.items,
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
        <p>Something went wrong loading Audit Logs. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Audit Logs…</p>
      </div>
    );
  }

  return (
    <AppShell
      title="Audit Logs"
      subtitle="Every privileged admin mutation, newest first"
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <form
        className={styles.filterBar}
        onSubmit={(event) => {
          event.preventDefault();
          void loadList(filters, 1);
        }}
      >
        <input
          type="text"
          placeholder="Admin ID"
          value={filters.adminId}
          onChange={(event) =>
            setFilters((f) => ({ ...f, adminId: event.target.value }))
          }
          className={styles.filterInput}
          aria-label="Filter by admin ID"
        />
        <input
          type="text"
          placeholder="Action (e.g. APPROVE_DRIVER)"
          value={filters.action}
          onChange={(event) =>
            setFilters((f) => ({ ...f, action: event.target.value }))
          }
          className={styles.filterInput}
          aria-label="Filter by action"
        />
        <input
          type="text"
          placeholder="Target type (e.g. DRIVER)"
          value={filters.targetType}
          onChange={(event) =>
            setFilters((f) => ({ ...f, targetType: event.target.value }))
          }
          className={styles.filterInput}
          aria-label="Filter by target type"
        />
        <input
          type="text"
          placeholder="Target ID"
          value={filters.targetId}
          onChange={(event) =>
            setFilters((f) => ({ ...f, targetId: event.target.value }))
          }
          className={styles.filterInput}
          aria-label="Filter by target ID"
        />
        <input
          type="date"
          value={filters.dateFrom}
          onChange={(event) =>
            setFilters((f) => ({ ...f, dateFrom: event.target.value }))
          }
          className={styles.filterInput}
          aria-label="From date"
        />
        <input
          type="date"
          value={filters.dateTo}
          onChange={(event) =>
            setFilters((f) => ({ ...f, dateTo: event.target.value }))
          }
          className={styles.filterInput}
          aria-label="To date"
        />
        <button type="submit" className={styles.searchButton}>
          Search
        </button>
        <button
          type="button"
          className={styles.clearButton}
          onClick={() => {
            setFilters(EMPTY_FILTERS);
            void loadList(EMPTY_FILTERS, 1);
          }}
        >
          Clear
        </button>
      </form>

      {listLoading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading audit logs…
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
                <th>Time</th>
                <th>Admin</th>
                <th>Action</th>
                <th>Target</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {list.entries.length === 0 && (
                <tr>
                  <td colSpan={5} className={styles.emptyCell}>
                    No audit log entries match this filter.
                  </td>
                </tr>
              )}
              {list.entries.map((entry) => (
                <tr key={entry.id}>
                  <td className={styles.timeCell}>
                    {entry.created_at
                      ? DATE_TIME.format(new Date(entry.created_at))
                      : "—"}
                  </td>
                  <td className={styles.idCell}>{entry.admin_id}</td>
                  <td>
                    <span className={styles.actionTag}>{entry.action}</span>
                  </td>
                  <td>
                    {entry.target_type ? (
                      <>
                        <div>{entry.target_type}</div>
                        {entry.target_id && (
                          <div className={styles.idCell}>{entry.target_id}</div>
                        )}
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>{entry.reason ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className={styles.pagination}>
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => loadList(filters, list.page - 1)}
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
              onClick={() => loadList(filters, list.page + 1)}
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
