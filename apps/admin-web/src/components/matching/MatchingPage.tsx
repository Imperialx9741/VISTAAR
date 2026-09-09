"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import { getOnlineDrivers, searchOffers } from "@/lib/api/matching";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdminProfile, MatchingOffer, OnlineDriversSummary } from "@/lib/api/types";
import styles from "./MatchingPage.module.css";

const PAGE_SIZE = 20;
const STATUSES = ["", "PENDING", "ACCEPTED", "REJECTED", "EXPIRED", "CANCELLED"];

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
      return "Your admin account does not have access to Matching / Offers.";
    }
    return error.message;
  }
  return "Couldn't load this. Try again.";
}

interface ListState {
  offers: MatchingOffer[];
  totalPages: number;
  page: number;
}

/** Matching / Offers (Admin Web §4.6, ADR-0054, Tier C) — online-driver
 * count plus search/detail over individual offers. Read-only; no
 * driver-location map or live coordinates anywhere here (ADR-0054 §5,
 * a separate future decision), and no mutation exists or is proposed —
 * the matching algorithm itself stays entirely driver-facing. */
export function MatchingPage() {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [onlineDrivers, setOnlineDrivers] = useState<OnlineDriversSummary | null>(
    null,
  );
  const [onlineDriversError, setOnlineDriversError] = useState<string | null>(
    null,
  );
  const [onlineDriversLoading, setOnlineDriversLoading] = useState(true);

  const [status, setStatus] = useState("");
  const [rideId, setRideId] = useState("");
  const [driverId, setDriverId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [list, setList] = useState<ListState | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const loadOffers = useCallback(
    async (
      searchStatus: string,
      searchRideId: string,
      searchDriverId: string,
      from: string,
      to: string,
      page: number,
    ) => {
      setListLoading(true);
      setListError(null);
      try {
        const result = await searchOffers(
          searchStatus,
          searchRideId,
          searchDriverId,
          from ? `${from}T00:00:00.000Z` : "",
          to ? `${to}T23:59:59.999Z` : "",
          page,
          PAGE_SIZE,
        );
        setList({
          offers: result.items,
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

    async function loadOnlineDriversOnMount() {
      try {
        const result = await getOnlineDrivers();
        if (!ignore) setOnlineDrivers(result);
      } catch (error) {
        if (!ignore) setOnlineDriversError(errorMessage(error));
      } finally {
        if (!ignore) setOnlineDriversLoading(false);
      }
    }

    async function loadOffersOnMount() {
      try {
        const result = await searchOffers("", "", "", "", "", 1, PAGE_SIZE);
        if (ignore) return;
        setList({
          offers: result.items,
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
    loadOnlineDriversOnMount();
    loadOffersOnMount();
    return () => {
      ignore = true;
    };
  }, []);

  if (profileFailed) {
    return (
      <div className={styles.fullPageMessage}>
        <p>Something went wrong loading Matching / Offers. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Matching / Offers…</p>
      </div>
    );
  }

  return (
    <AppShell
      title="Matching / Offers"
      subtitle="Online-driver counts and individual ride-offer visibility"
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <div className={styles.sectionLabel}>Online drivers</div>

      {onlineDriversLoading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading online-driver counts…
        </div>
      )}

      {!onlineDriversLoading && onlineDriversError && (
        <div className={styles.errorBanner} role="alert">
          {onlineDriversError}
        </div>
      )}

      {!onlineDriversLoading && !onlineDriversError && onlineDrivers && (
        <div className={styles.statGrid}>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>Total online</div>
            <div className={styles.statValue}>{onlineDrivers.total}</div>
          </div>
          {Object.entries(onlineDrivers.by_category).map(([category, count]) => (
            <div key={category} className={styles.statCard}>
              <div className={styles.statLabel}>{category}</div>
              <div className={styles.statValue}>{count}</div>
            </div>
          ))}
        </div>
      )}

      <div className={styles.headerRow}>
        <div className={styles.sectionLabel}>Offers</div>
      </div>

      <form
        className={styles.searchBar}
        onSubmit={(event) => {
          event.preventDefault();
          void loadOffers(status, rideId, driverId, dateFrom, dateTo, 1);
        }}
      >
        <input
          type="text"
          value={rideId}
          onChange={(event) => setRideId(event.target.value)}
          placeholder="Ride ID"
          aria-label="Filter by ride ID"
          className={styles.searchInput}
        />
        <input
          type="text"
          value={driverId}
          onChange={(event) => setDriverId(event.target.value)}
          placeholder="Driver ID"
          aria-label="Filter by driver ID"
          className={styles.searchInput}
        />
        <select
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            void loadOffers(
              event.target.value,
              rideId,
              driverId,
              dateFrom,
              dateTo,
              1,
            );
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
        <input
          type="date"
          value={dateFrom}
          onChange={(event) => setDateFrom(event.target.value)}
          className={styles.searchInput}
          aria-label="From date"
        />
        <input
          type="date"
          value={dateTo}
          onChange={(event) => setDateTo(event.target.value)}
          className={styles.searchInput}
          aria-label="To date"
        />
        <button type="submit" className={styles.searchButton}>
          Search
        </button>
      </form>

      {listLoading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading offers…
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
                <th>Ride</th>
                <th>Driver</th>
                <th>Status</th>
                <th>Created</th>
                <th aria-hidden="true" />
              </tr>
            </thead>
            <tbody>
              {list.offers.length === 0 && (
                <tr>
                  <td colSpan={5} className={styles.emptyCell}>
                    No offers found.
                  </td>
                </tr>
              )}
              {list.offers.map((offer) => (
                <tr key={offer.offer_id}>
                  <td className={styles.idCell}>{offer.ride_id}</td>
                  <td className={styles.idCell}>{offer.driver_id}</td>
                  <td>
                    <Pill tone={toneForStatus(offer.status)}>{offer.status}</Pill>
                  </td>
                  <td>{DATE_TIME.format(new Date(offer.created_at))}</td>
                  <td className={styles.actionCell}>
                    <Link
                      href={`/matching/${offer.offer_id}`}
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
              onClick={() =>
                loadOffers(status, rideId, driverId, dateFrom, dateTo, list.page - 1)
              }
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
              onClick={() =>
                loadOffers(status, rideId, driverId, dateFrom, dateTo, list.page + 1)
              }
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
