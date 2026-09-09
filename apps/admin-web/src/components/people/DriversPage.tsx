"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import { searchDrivers } from "@/lib/api/people";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdminProfile, DriverSummary } from "@/lib/api/types";
import styles from "./PeopleList.module.css";

const PAGE_SIZE = 20;

const VERIFICATION_STATUSES = ["", "PENDING", "APPROVED", "REJECTED"] as const;

function errorMessage(error: unknown): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) {
    if (error.code === "FORBIDDEN") {
      return "Your admin account does not have access to Drivers.";
    }
    return error.message;
  }
  return "Couldn't load drivers. Try again.";
}

interface ListState {
  drivers: DriverSummary[];
  totalPages: number;
  page: number;
}

export function DriversPage() {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [list, setList] = useState<ListState | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const loadList = useCallback(
    async (searchQuery: string, searchStatus: string, page: number) => {
      setListLoading(true);
      setListError(null);
      try {
        const result = await searchDrivers(
          searchQuery,
          searchStatus,
          page,
          PAGE_SIZE,
        );
        setList({
          drivers: result.items,
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
        const result = await searchDrivers("", "", 1, PAGE_SIZE);
        if (ignore) return;
        setList({
          drivers: result.items,
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
      title="Drivers"
      subtitle="Search and review driver accounts"
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <form
        className={styles.searchBar}
        onSubmit={(event) => {
          event.preventDefault();
          void loadList(query, status, 1);
        }}
      >
        <input
          type="search"
          placeholder="Search by name…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className={styles.searchInput}
          aria-label="Search drivers by name"
        />
        <select
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            void loadList(query, event.target.value, 1);
          }}
          className={styles.statusSelect}
          aria-label="Filter by verification status"
        >
          {VERIFICATION_STATUSES.map((value) => (
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
          Loading drivers…
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
                <th>Name</th>
                <th>Verification</th>
                <th>Operational</th>
                <th>Strikes</th>
                <th aria-hidden="true" />
              </tr>
            </thead>
            <tbody>
              {list.drivers.length === 0 && (
                <tr>
                  <td colSpan={5} className={styles.emptyCell}>
                    No drivers found.
                  </td>
                </tr>
              )}
              {list.drivers.map((driver) => (
                <tr key={driver.driver_id}>
                  <td>{driver.full_name}</td>
                  <td>
                    <Pill tone={toneForStatus(driver.verification_status)}>
                      {driver.verification_status}
                    </Pill>
                  </td>
                  <td>
                    <Pill tone={toneForStatus(driver.operational_status)}>
                      {driver.operational_status}
                    </Pill>
                  </td>
                  <td>{driver.strikes}</td>
                  <td className={styles.actionCell}>
                    {driver.verification_status === "PENDING" ? (
                      <Link
                        href={`/drivers/${driver.driver_id}`}
                        className={styles.reviewLink}
                      >
                        Review →
                      </Link>
                    ) : (
                      <Link
                        href={`/drivers/${driver.driver_id}`}
                        className={styles.viewLink}
                      >
                        View
                      </Link>
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
              onClick={() => loadList(query, status, list.page - 1)}
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
              onClick={() => loadList(query, status, list.page + 1)}
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
