"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import {
  getDriverWallet,
  listDriverWalletTransactions,
} from "@/lib/api/finance";
import { ApiError, NoSessionError } from "@/lib/api/client";
import type { AdminProfile, DriverWallet, WalletTransaction } from "@/lib/api/types";
import styles from "./DriverWalletPage.module.css";

const PAGE_SIZE = 20;
const TRANSACTION_TYPES = [
  "",
  "PLATFORM_FEE",
  "WALLET_RECHARGE",
  "JOINING_BONUS",
  "DRIVER_REFERRAL_BONUS",
  "ADVERTISEMENT_PAYOUT",
  "DRIVER_PENALTY",
  "CASH_SETTLEMENT",
  "FEE_REVERSAL",
  "PENALTY_REVERSAL",
  "ADMIN_ADJUSTMENT",
];

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
      return "Your admin account does not have access to Finance / Wallet.";
    }
    return error.message;
  }
  return "Couldn't load this wallet. Try again.";
}

interface ListState {
  transactions: WalletTransaction[];
  totalPages: number;
  page: number;
}

export function DriverWalletPage({ driverId }: { driverId: string }) {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [wallet, setWallet] = useState<DriverWallet | null>(null);
  const [walletError, setWalletError] = useState<string | null>(null);
  const [walletLoading, setWalletLoading] = useState(true);

  const [type, setType] = useState("");
  const [list, setList] = useState<ListState | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const loadTransactions = useCallback(
    async (searchType: string, page: number) => {
      setListLoading(true);
      setListError(null);
      try {
        const result = await listDriverWalletTransactions(
          driverId,
          searchType,
          page,
          PAGE_SIZE,
        );
        setList({
          transactions: result.items,
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

    async function loadWalletOnMount() {
      try {
        const data = await getDriverWallet(driverId);
        if (!ignore) setWallet(data);
      } catch (error) {
        if (!ignore) setWalletError(errorMessage(error));
      } finally {
        if (!ignore) setWalletLoading(false);
      }
    }

    async function loadTransactionsOnMount() {
      try {
        const result = await listDriverWalletTransactions(
          driverId,
          "",
          1,
          PAGE_SIZE,
        );
        if (ignore) return;
        setList({
          transactions: result.items,
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
    loadWalletOnMount();
    loadTransactionsOnMount();
    return () => {
      ignore = true;
    };
  }, [driverId]);

  if (profileFailed) {
    return (
      <div className={styles.fullPageMessage}>
        <p>Something went wrong loading Finance / Wallet. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Finance / Wallet…</p>
      </div>
    );
  }

  return (
    <AppShell
      title="Driver wallet"
      subtitle={driverId}
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <Link href="/finance" className={styles.backLink}>
        ← Look up another driver
      </Link>

      {walletLoading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading wallet…
        </div>
      )}

      {!walletLoading && walletError && (
        <div className={styles.errorBanner} role="alert">
          {walletError}
        </div>
      )}

      {!walletLoading && !walletError && wallet && (
        <div className={styles.summaryCard}>
          <div>
            <div className={styles.summaryLabel}>Balance</div>
            <div className={styles.summaryValue}>
              {CURRENCY.format(wallet.balance)}
            </div>
          </div>
          <div>
            <div className={styles.summaryLabel}>Outstanding settlement</div>
            <div className={styles.summaryValue}>
              {CURRENCY.format(wallet.outstanding_settlement)}
            </div>
          </div>
        </div>
      )}

      <div className={styles.sectionLabel}>Transaction history</div>

      <select
        value={type}
        onChange={(event) => {
          setType(event.target.value);
          void loadTransactions(event.target.value, 1);
        }}
        className={styles.reasonInput}
        aria-label="Filter by transaction type"
      >
        {TRANSACTION_TYPES.map((value) => (
          <option key={value} value={value}>
            {value === "" ? "Any type" : value}
          </option>
        ))}
      </select>

      {listLoading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading transactions…
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
                <th>Type</th>
                <th>Direction</th>
                <th>Amount</th>
                <th>Balance after</th>
                <th>Ride</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {list.transactions.length === 0 && (
                <tr>
                  <td colSpan={6} className={styles.emptyState}>
                    No transactions found.
                  </td>
                </tr>
              )}
              {list.transactions.map((transaction) => (
                <tr key={transaction.transaction_id}>
                  <td>{transaction.transaction_type}</td>
                  <td>
                    <Pill
                      tone={
                        transaction.direction === "CREDIT"
                          ? "success"
                          : "neutral"
                      }
                    >
                      {transaction.direction}
                    </Pill>
                  </td>
                  <td>{CURRENCY.format(transaction.amount)}</td>
                  <td>{CURRENCY.format(transaction.balance_after)}</td>
                  <td className={styles.idCell}>
                    {transaction.ride_id ?? "—"}
                  </td>
                  <td>{DATE_TIME.format(new Date(transaction.created_at))}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className={styles.pagination}>
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => loadTransactions(type, list.page - 1)}
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
              onClick={() => loadTransactions(type, list.page + 1)}
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
