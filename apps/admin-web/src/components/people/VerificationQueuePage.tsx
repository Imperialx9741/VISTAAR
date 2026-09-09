"use client";

import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import { searchVerificationQueue } from "@/lib/api/people";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdminProfile, VerificationCase } from "@/lib/api/types";
import styles from "./PeopleList.module.css";

const PAGE_SIZE = 20;

// api-contracts.md §46.4: "the Admin Web's own screen is expected to
// default its query to status=PENDING client-side" — the API itself
// returns every case when status is omitted.
const CASE_STATUSES = [
  "PENDING",
  "",
  "PROCESSING",
  "APPROVED",
  "REJECTED",
  "MANUAL_REVIEW",
  "EXPIRED",
] as const;

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
      return "Your admin account does not have access to Verification.";
    }
    return error.message;
  }
  return "Couldn't load the verification queue. Try again.";
}

interface ListState {
  cases: VerificationCase[];
  totalPages: number;
  page: number;
}

export function VerificationQueuePage() {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [status, setStatus] = useState<string>("PENDING");
  const [list, setList] = useState<ListState | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const loadList = useCallback(async (searchStatus: string, page: number) => {
    setListLoading(true);
    setListError(null);
    try {
      const result = await searchVerificationQueue(
        searchStatus,
        page,
        PAGE_SIZE,
      );
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
        const result = await searchVerificationQueue("PENDING", 1, PAGE_SIZE);
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
        <p>Something went wrong loading Verification. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Verification…</p>
      </div>
    );
  }

  return (
    <AppShell
      title="Verification"
      subtitle="Pending-review queue across driver and vehicle documents"
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
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
          aria-label="Filter by case status"
        >
          {CASE_STATUSES.map((value) => (
            <option key={value} value={value}>
              {value === "" ? "Any status" : value}
            </option>
          ))}
        </select>
      </form>

      {listLoading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading verification cases…
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
                <th>Subject</th>
                <th>Type</th>
                <th>Status</th>
                <th>Opened</th>
                <th>Completed</th>
              </tr>
            </thead>
            <tbody>
              {list.cases.length === 0 && (
                <tr>
                  <td colSpan={5} className={styles.emptyCell}>
                    No verification cases for this filter.
                  </td>
                </tr>
              )}
              {list.cases.map((verificationCase) => (
                <tr key={verificationCase.case_id}>
                  <td>
                    <div>{verificationCase.subject_type}</div>
                    <div className={styles.idCell}>
                      {verificationCase.subject_id}
                    </div>
                  </td>
                  <td>{verificationCase.verification_type}</td>
                  <td>
                    <Pill tone={toneForStatus(verificationCase.status)}>
                      {verificationCase.status}
                    </Pill>
                  </td>
                  <td>{DATE_TIME.format(new Date(verificationCase.created_at))}</td>
                  <td>
                    {verificationCase.completed_at
                      ? DATE_TIME.format(new Date(verificationCase.completed_at))
                      : "—"}
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
