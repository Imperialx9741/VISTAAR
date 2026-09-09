"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import { searchVehicles } from "@/lib/api/people";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdminProfile, Vehicle } from "@/lib/api/types";
import styles from "./PeopleList.module.css";

const PAGE_SIZE = 20;

const VERIFICATION_STATUSES = ["", "PENDING", "APPROVED", "REJECTED"] as const;

function errorMessage(error: unknown): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) {
    if (error.code === "FORBIDDEN") {
      return "Your admin account does not have access to Vehicles.";
    }
    return error.message;
  }
  return "Couldn't load vehicles. Try again.";
}

interface ListState {
  vehicles: Vehicle[];
  totalPages: number;
  page: number;
}

export function VehiclesPage() {
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
        const result = await searchVehicles(
          searchQuery,
          searchStatus,
          page,
          PAGE_SIZE,
        );
        setList({
          vehicles: result.items,
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
        const result = await searchVehicles("", "", 1, PAGE_SIZE);
        if (ignore) return;
        setList({
          vehicles: result.items,
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
        <p>Something went wrong loading Vehicles. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Vehicles…</p>
      </div>
    );
  }

  return (
    <AppShell
      title="Vehicles"
      subtitle="Search and review vehicle registrations"
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
          placeholder="Search by registration number…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className={styles.searchInput}
          aria-label="Search vehicles by registration number"
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
          Loading vehicles…
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
                <th>Registration</th>
                <th>Category</th>
                <th>Make / Model</th>
                <th>Verification</th>
                <th>Operational</th>
                <th aria-hidden="true" />
              </tr>
            </thead>
            <tbody>
              {list.vehicles.length === 0 && (
                <tr>
                  <td colSpan={6} className={styles.emptyCell}>
                    No vehicles found.
                  </td>
                </tr>
              )}
              {list.vehicles.map((vehicle) => (
                <tr key={vehicle.vehicle_id}>
                  <td className={styles.idCell}>{vehicle.registration_number}</td>
                  <td>{vehicle.category}</td>
                  <td>
                    {vehicle.make} {vehicle.model}
                  </td>
                  <td>
                    <Pill tone={toneForStatus(vehicle.verification_status)}>
                      {vehicle.verification_status}
                    </Pill>
                  </td>
                  <td>
                    <Pill tone={toneForStatus(vehicle.operational_status)}>
                      {vehicle.operational_status}
                    </Pill>
                  </td>
                  <td className={styles.actionCell}>
                    {vehicle.verification_status === "PENDING" ? (
                      <Link
                        href={`/vehicles/${vehicle.vehicle_id}`}
                        className={styles.reviewLink}
                      >
                        Review →
                      </Link>
                    ) : (
                      <Link
                        href={`/vehicles/${vehicle.vehicle_id}`}
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
