"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import { resolvePenalty, searchPenalties } from "@/lib/api/penalties";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdminProfile, Penalty } from "@/lib/api/types";
import styles from "./PenaltiesPage.module.css";

const PAGE_SIZE = 20;
// Customer penalties never expire (BR-049, corrected 2026-09-04,
// ADR-0069) — no EXPIRED status exists any longer.
const STATUSES = ["", "OUTSTANDING", "SETTLED", "WAIVED"];

const CURRENCY = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 2,
});

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
      return "Your admin account does not have access to Penalties / Strikes.";
    }
    return error.message;
  }
  return "Couldn't load penalties. Try again.";
}

interface ListState {
  penalties: Penalty[];
  totalPages: number;
  page: number;
}

/** Penalties / Strikes (Admin Web §4.9, ADR-0023) — search + the only
 * documented resolve action, Waive. Driver Strike History has no
 * endpoint yet (NEW — SCOPED, design only) — not included here. */
export function PenaltiesPage() {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [status, setStatus] = useState("");
  const [userId, setUserId] = useState("");
  const [list, setList] = useState<ListState | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [isResolving, setIsResolving] = useState(false);
  const [resolveError, setResolveError] = useState<string | null>(null);
  const [resolveNotice, setResolveNotice] = useState<string | null>(null);

  const loadList = useCallback(
    async (searchStatus: string, searchUserId: string, page: number) => {
      setListLoading(true);
      setListError(null);
      try {
        const result = await searchPenalties(
          searchStatus,
          searchUserId,
          page,
          PAGE_SIZE,
        );
        setList({
          penalties: result.items,
          totalPages: Math.max(1, result.pagination.total_pages),
          page: result.pagination.page,
        });
      } catch (error) {
        setListError(errorMessage(error));
      } finally {
        setListLoading(false);
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

    async function loadListOnMount() {
      try {
        const result = await searchPenalties("", "", 1, PAGE_SIZE);
        if (ignore) return;
        setList({
          penalties: result.items,
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

  function startResolve(penaltyId: string) {
    setResolveNotice(null);
    setResolveError(null);
    setReason("");
    setResolvingId(penaltyId);
  }

  async function confirmResolve(penaltyId: string) {
    setIsResolving(true);
    setResolveError(null);
    try {
      await resolvePenalty(penaltyId, reason || undefined);
      setResolvingId(null);
      setResolveNotice(`Penalty ${penaltyId} waived.`);
      await loadList(status, userId, list?.page ?? 1);
    } catch (error) {
      setResolveError(errorMessage(error));
    } finally {
      setIsResolving(false);
    }
  }

  if (profileFailed) {
    return (
      <div className={styles.fullPageMessage}>
        <p>Something went wrong loading Penalties / Strikes. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Penalties / Strikes…</p>
      </div>
    );
  }

  return (
    <AppShell
      title="Penalties / Strikes"
      subtitle="Search penalties and waive an outstanding charge"
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      {resolveNotice && (
        <div className={styles.successBanner} role="status">
          {resolveNotice}
        </div>
      )}

      <form
        className={styles.searchBar}
        onSubmit={(event) => {
          event.preventDefault();
          void loadList(status, userId, 1);
        }}
      >
        <input
          type="text"
          value={userId}
          onChange={(event) => setUserId(event.target.value)}
          placeholder="User ID"
          aria-label="Filter by user ID"
          className={styles.searchInput}
        />
        <select
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            void loadList(event.target.value, userId, 1);
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
        <button type="submit" className={styles.searchButton}>
          Search
        </button>
      </form>

      {listLoading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading penalties…
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
                <th>User</th>
                <th>Type</th>
                <th>Amount</th>
                <th>Status</th>
                <th>Issued</th>
                <th aria-hidden="true" />
              </tr>
            </thead>
            <tbody>
              {list.penalties.length === 0 && (
                <tr>
                  <td colSpan={6} className={styles.emptyCell}>
                    No penalties found.
                  </td>
                </tr>
              )}
              {list.penalties.map((penalty) => (
                <Fragment key={penalty.penalty_id}>
                  <tr>
                    <td className={styles.idCell}>{penalty.user_id}</td>
                    <td>{penalty.penalty_type}</td>
                    <td>{CURRENCY.format(penalty.amount)}</td>
                    <td>
                      <Pill tone={toneForStatus(penalty.status)}>
                        {penalty.status}
                      </Pill>
                    </td>
                    <td>{DATE_TIME.format(new Date(penalty.issued_at))}</td>
                    <td className={styles.actionCell}>
                      {penalty.status === "OUTSTANDING" &&
                        resolvingId !== penalty.penalty_id && (
                          <button
                            type="button"
                            className={styles.secondaryButton}
                            onClick={() => startResolve(penalty.penalty_id)}
                          >
                            Waive
                          </button>
                        )}
                    </td>
                  </tr>
                  {resolvingId === penalty.penalty_id && (
                    <tr>
                      <td colSpan={6} className={styles.reasonCell}>
                        <div className={styles.reasonRow}>
                          <input
                            type="text"
                            value={reason}
                            onChange={(event) => setReason(event.target.value)}
                            placeholder="Reason (optional)"
                            aria-label="Waive reason"
                            disabled={isResolving}
                            className={styles.reasonInput}
                          />
                          <button
                            type="button"
                            className={styles.secondaryButton}
                            disabled={isResolving}
                            onClick={() => setResolvingId(null)}
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            className={styles.primaryButton}
                            disabled={isResolving}
                            onClick={() => confirmResolve(penalty.penalty_id)}
                          >
                            {isResolving ? "Waiving…" : "Confirm waive"}
                          </button>
                        </div>
                        {resolveError && (
                          <div className={styles.errorBanner} role="alert">
                            {resolveError}
                          </div>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>

          <div className={styles.pagination}>
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => loadList(status, userId, list.page - 1)}
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
              onClick={() => loadList(status, userId, list.page + 1)}
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
