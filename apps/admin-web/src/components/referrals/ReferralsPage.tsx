"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import { searchReferrals } from "@/lib/api/referrals";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdminProfile, Referral } from "@/lib/api/types";
import styles from "./ReferralsPage.module.css";

const PAGE_SIZE = 20;
const STATUSES = ["", "ATTACHED", "ACTIVATED"];

const DATE = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

function errorMessage(error: unknown): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) {
    if (error.code === "FORBIDDEN") {
      return "Your admin account does not have access to Referrals.";
    }
    return error.message;
  }
  return "Couldn't load referrals. Try again.";
}

interface ListState {
  referrals: Referral[];
  totalPages: number;
  page: number;
}

export function ReferralsPage() {
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
      const result = await searchReferrals(searchStatus, page, PAGE_SIZE);
      setList({
        referrals: result.items,
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
        const result = await searchReferrals("", 1, PAGE_SIZE);
        if (ignore) return;
        setList({
          referrals: result.items,
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
        <p>Something went wrong loading Referrals. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Referrals…</p>
      </div>
    );
  }

  return (
    <AppShell
      title="Referrals"
      subtitle="Referral activity and reward configuration"
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <div className={styles.headerRow}>
        <div className={styles.sectionLabel}>Referrals</div>
        <Link href="/referrals/rewards" className={styles.viewLink}>
          Manage reward configuration →
        </Link>
      </div>

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
          Loading referrals…
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
                <th>Referrer</th>
                <th>Referred</th>
                <th>Type</th>
                <th>Status</th>
                <th>Rewards</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {list.referrals.length === 0 && (
                <tr>
                  <td colSpan={6} className={styles.emptyCell}>
                    No referrals found.
                  </td>
                </tr>
              )}
              {list.referrals.map((referral) => (
                <tr key={referral.referral_id}>
                  <td className={styles.idCell}>{referral.referrer_id}</td>
                  <td className={styles.idCell}>{referral.referred_id}</td>
                  <td>{referral.referred_type}</td>
                  <td>
                    <Pill tone={toneForStatus(referral.status)}>
                      {referral.status}
                    </Pill>
                  </td>
                  <td>
                    {referral.rewards.length === 0
                      ? "—"
                      : referral.rewards.map((reward) => (
                          <Pill key={reward.reward_id} tone="gold">
                            {reward.reward_type}
                          </Pill>
                        ))}
                  </td>
                  <td>{DATE.format(new Date(referral.created_at))}</td>
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
