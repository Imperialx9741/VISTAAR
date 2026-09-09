"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import { searchSafetyIncidents } from "@/lib/api/safety-support";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdminProfile, SafetyIncident } from "@/lib/api/types";
import styles from "./SafetyPage.module.css";

const PAGE_SIZE = 20;
const STATUSES = ["", "OPEN", "ACKNOWLEDGED", "IN_PROGRESS", "RESOLVED", "CLOSED"];

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
      return "Your admin account does not have access to Safety / SOS.";
    }
    return error.message;
  }
  return "Couldn't load safety incidents. Try again.";
}

interface ListState {
  incidents: SafetyIncident[];
  totalPages: number;
  page: number;
}

export function SafetyPage() {
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
      const result = await searchSafetyIncidents(searchStatus, page, PAGE_SIZE);
      setList({
        incidents: result.items,
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
        const result = await searchSafetyIncidents("", 1, PAGE_SIZE);
        if (ignore) return;
        setList({
          incidents: result.items,
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
        <p>Something went wrong loading Safety / SOS. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Safety / SOS…</p>
      </div>
    );
  }

  return (
    <AppShell
      title="Safety / SOS"
      subtitle="Incident queue — acknowledge, escalate, resolve"
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
          Loading incidents…
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
                <th>Incident</th>
                <th>Type</th>
                <th>Status</th>
                <th>Opened</th>
                <th aria-hidden="true" />
              </tr>
            </thead>
            <tbody>
              {list.incidents.length === 0 && (
                <tr>
                  <td colSpan={5} className={styles.emptyCell}>
                    No incidents found.
                  </td>
                </tr>
              )}
              {list.incidents.map((incident) => (
                <tr key={incident.incident_id}>
                  <td className={styles.idCell}>{incident.incident_id}</td>
                  <td>{incident.incident_type}</td>
                  <td>
                    <Pill tone={toneForStatus(incident.status)}>
                      {incident.status}
                    </Pill>
                  </td>
                  <td>{DATE_TIME.format(new Date(incident.created_at))}</td>
                  <td className={styles.actionCell}>
                    <Link
                      href={`/safety/${incident.incident_id}`}
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
