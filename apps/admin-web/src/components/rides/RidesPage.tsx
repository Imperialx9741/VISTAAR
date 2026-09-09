"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import { searchRides } from "@/lib/api/rides";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdminProfile, Ride } from "@/lib/api/types";
import styles from "./RidesPage.module.css";

const PAGE_SIZE = 20;
const STATUSES = [
  "",
  "SEARCHING",
  "ACCEPTED",
  "ARRIVED",
  "STARTED",
  "COMPLETED",
  "CANCELLED",
  "CLOSED",
];

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
      return "Your admin account does not have access to Rides.";
    }
    return error.message;
  }
  return "Couldn't load rides. Try again.";
}

interface ListState {
  rides: Ride[];
  totalPages: number;
  page: number;
}

/** Rides (Admin Web §4.5, ADR-0023) — read-only search + lifecycle
 * detail. No admin-side ride intervention (force-cancel, reassign)
 * exists or was asked for, so this screen never mutates anything. */
export function RidesPage() {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [status, setStatus] = useState("");
  const [driverId, setDriverId] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [list, setList] = useState<ListState | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const loadList = useCallback(
    async (
      searchStatus: string,
      searchDriverId: string,
      searchCustomerId: string,
      page: number,
    ) => {
      setListLoading(true);
      setListError(null);
      try {
        const result = await searchRides(
          searchStatus,
          searchDriverId,
          searchCustomerId,
          page,
          PAGE_SIZE,
        );
        setList({
          rides: result.items,
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
        const result = await searchRides("", "", "", 1, PAGE_SIZE);
        if (ignore) return;
        setList({
          rides: result.items,
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
        <p>Something went wrong loading Rides. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Rides…</p>
      </div>
    );
  }

  return (
    <AppShell
      title="Rides"
      subtitle="Search rides and inspect their full lifecycle"
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <form
        className={styles.searchBar}
        onSubmit={(event) => {
          event.preventDefault();
          void loadList(status, driverId, customerId, 1);
        }}
      >
        <input
          type="text"
          value={driverId}
          onChange={(event) => setDriverId(event.target.value)}
          placeholder="Driver ID"
          aria-label="Filter by driver ID"
          className={styles.searchInput}
        />
        <input
          type="text"
          value={customerId}
          onChange={(event) => setCustomerId(event.target.value)}
          placeholder="Customer ID"
          aria-label="Filter by customer ID"
          className={styles.searchInput}
        />
        <select
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            void loadList(event.target.value, driverId, customerId, 1);
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
          Loading rides…
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
                <th>Requested</th>
                <th>Category</th>
                <th>Customer</th>
                <th>Driver</th>
                <th>Status</th>
                <th aria-hidden="true" />
              </tr>
            </thead>
            <tbody>
              {list.rides.length === 0 && (
                <tr>
                  <td colSpan={6} className={styles.emptyCell}>
                    No rides found.
                  </td>
                </tr>
              )}
              {list.rides.map((ride) => (
                <tr key={ride.ride_id}>
                  <td>{DATE_TIME.format(new Date(ride.requested_at))}</td>
                  <td>
                    {ride.requested_vehicle_category}
                    {ride.requested_cab_tier ? ` (${ride.requested_cab_tier})` : ""}
                  </td>
                  <td className={styles.idCell}>{ride.customer_id}</td>
                  <td className={styles.idCell}>{ride.driver_id ?? "—"}</td>
                  <td>
                    <Pill tone={toneForStatus(ride.status)}>{ride.status}</Pill>
                  </td>
                  <td className={styles.actionCell}>
                    <Link
                      href={`/rides/${ride.ride_id}`}
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
              onClick={() => loadList(status, driverId, customerId, list.page - 1)}
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
              onClick={() => loadList(status, driverId, customerId, list.page + 1)}
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
