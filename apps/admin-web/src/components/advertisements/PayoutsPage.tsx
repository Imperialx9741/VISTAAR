"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import { listAdPayouts, settleAdPayout } from "@/lib/api/advertisements";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdminProfile, AdPayout } from "@/lib/api/types";
import styles from "./PayoutsPage.module.css";

const PAGE_SIZE = 20;
const STATUSES = ["", "PENDING", "PAID"];

const CURRENCY = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 2,
});

function errorMessage(error: unknown): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) {
    if (error.code === "FORBIDDEN") {
      return "Your admin account does not have access to Advertisements.";
    }
    return error.message;
  }
  return "Couldn't load payouts. Try again.";
}

interface ListState {
  payouts: AdPayout[];
  totalPages: number;
  page: number;
}

/** Payout/settlement monitoring (Admin Web §4.15, ADR-0046) — Settle
 * composes WalletService.credit(ADVERTISEMENT_PAYOUT) then
 * mark_payout_paid() server-side, one call from this side. */
export function PayoutsPage() {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [status, setStatus] = useState("");
  const [list, setList] = useState<ListState | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [settlingId, setSettlingId] = useState<string | null>(null);
  const [settleError, setSettleError] = useState<string | null>(null);
  const [settleNotice, setSettleNotice] = useState<string | null>(null);

  const loadList = useCallback(async (searchStatus: string, page: number) => {
    setListLoading(true);
    setListError(null);
    try {
      const result = await listAdPayouts(searchStatus, page, PAGE_SIZE);
      setList({
        payouts: result.items,
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
        const result = await listAdPayouts("", 1, PAGE_SIZE);
        if (ignore) return;
        setList({
          payouts: result.items,
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

  async function handleSettle(payoutId: string) {
    setSettlingId(payoutId);
    setSettleError(null);
    setSettleNotice(null);
    try {
      await settleAdPayout(payoutId);
      setSettleNotice(`Payout ${payoutId} settled.`);
      await loadList(status, list?.page ?? 1);
    } catch (error) {
      setSettleError(errorMessage(error));
    } finally {
      setSettlingId(null);
    }
  }

  if (profileFailed) {
    return (
      <div className={styles.fullPageMessage}>
        <p>Something went wrong loading Advertisements. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Advertisements…</p>
      </div>
    );
  }

  return (
    <AppShell
      title="Payouts"
      subtitle="Advertisement payout and settlement monitoring"
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <nav className={styles.subNav} aria-label="Advertisements sections">
        <Link href="/advertisements" className={styles.viewLink}>
          ← Campaigns
        </Link>
        <Link href="/advertisements/assignments" className={styles.viewLink}>
          Proof review queue →
        </Link>
      </nav>

      <div className={styles.headerRow}>
        <div className={styles.sectionLabel}>Payouts</div>
      </div>

      {settleNotice && (
        <div className={styles.successBanner} role="status">
          {settleNotice}
        </div>
      )}
      {settleError && (
        <div className={styles.errorBanner} role="alert">
          {settleError}
        </div>
      )}

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
          Loading payouts…
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
                <th>Gross</th>
                <th>Driver</th>
                <th>VISTAAR</th>
                <th>Status</th>
                <th aria-hidden="true" />
              </tr>
            </thead>
            <tbody>
              {list.payouts.length === 0 && (
                <tr>
                  <td colSpan={5} className={styles.emptyCell}>
                    No payouts found.
                  </td>
                </tr>
              )}
              {list.payouts.map((payout) => (
                <tr key={payout.payout_id}>
                  <td>{CURRENCY.format(payout.gross_amount)}</td>
                  <td>{CURRENCY.format(payout.driver_amount)}</td>
                  <td>{CURRENCY.format(payout.vistaar_amount)}</td>
                  <td>
                    <Pill tone={toneForStatus(payout.status)}>
                      {payout.status}
                    </Pill>
                  </td>
                  <td className={styles.actionCell}>
                    {payout.status === "PENDING" && (
                      <button
                        type="button"
                        className={styles.secondaryButton}
                        disabled={settlingId === payout.payout_id}
                        onClick={() => handleSettle(payout.payout_id)}
                      >
                        {settlingId === payout.payout_id
                          ? "Settling…"
                          : "Settle"}
                      </button>
                    )}
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
