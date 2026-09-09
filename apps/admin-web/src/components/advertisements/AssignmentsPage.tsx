"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import { searchAdAssignments } from "@/lib/api/advertisements";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdAssignment, AdminProfile } from "@/lib/api/types";
import styles from "./AssignmentsPage.module.css";

const PAGE_SIZE = 20;
const STATUSES = [
  "",
  "ASSIGNED",
  "PROOF_SUBMITTED",
  "VERIFIED",
  "REJECTED",
  "PAID",
];

function errorMessage(error: unknown): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) {
    if (error.code === "FORBIDDEN") {
      return "Your admin account does not have access to Advertisements.";
    }
    return error.message;
  }
  return "Couldn't load assignments. Try again.";
}

interface ListState {
  assignments: AdAssignment[];
  totalPages: number;
  page: number;
}

/** Installation/proof review queue (Admin Web §4.15, ADR-0046) — global
 * across every campaign, filterable down to one. Per-campaign detail
 * already shows its own assignments inline; this is the cross-campaign
 * view for admins reviewing proof submissions as they come in. */
export function AssignmentsPage() {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [campaignId, setCampaignId] = useState("");
  const [driverId, setDriverId] = useState("");
  const [status, setStatus] = useState("");
  const [list, setList] = useState<ListState | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const loadList = useCallback(
    async (
      searchCampaignId: string,
      searchDriverId: string,
      searchStatus: string,
      page: number,
    ) => {
      setListLoading(true);
      setListError(null);
      try {
        const result = await searchAdAssignments(
          searchCampaignId,
          searchDriverId,
          searchStatus,
          page,
          PAGE_SIZE,
        );
        setList({
          assignments: result.items,
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
        const result = await searchAdAssignments("", "", "", 1, PAGE_SIZE);
        if (ignore) return;
        setList({
          assignments: result.items,
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
      title="Proof review queue"
      subtitle="Installation/proof submissions across every campaign"
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <nav className={styles.subNav} aria-label="Advertisements sections">
        <Link href="/advertisements" className={styles.viewLink}>
          ← Campaigns
        </Link>
        <Link href="/advertisements/payouts" className={styles.viewLink}>
          Payouts →
        </Link>
      </nav>

      <div className={styles.headerRow}>
        <div className={styles.sectionLabel}>Assignments</div>
      </div>

      <form
        className={styles.searchBar}
        onSubmit={(event) => {
          event.preventDefault();
          void loadList(campaignId, driverId, status, 1);
        }}
      >
        <input
          type="text"
          value={campaignId}
          onChange={(event) => setCampaignId(event.target.value)}
          placeholder="Campaign ID"
          aria-label="Filter by campaign ID"
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
            void loadList(campaignId, driverId, event.target.value, 1);
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
          Loading assignments…
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
                <th>Campaign</th>
                <th>Driver</th>
                <th>Status</th>
                <th>Verification</th>
                <th aria-hidden="true" />
              </tr>
            </thead>
            <tbody>
              {list.assignments.length === 0 && (
                <tr>
                  <td colSpan={5} className={styles.emptyCell}>
                    No assignments found.
                  </td>
                </tr>
              )}
              {list.assignments.map((assignment) => (
                <tr key={assignment.assignment_id}>
                  <td className={styles.idCell}>{assignment.campaign_id}</td>
                  <td className={styles.idCell}>{assignment.driver_id}</td>
                  <td>
                    <Pill tone={toneForStatus(assignment.status)}>
                      {assignment.status}
                    </Pill>
                  </td>
                  <td>
                    {assignment.verification_status ? (
                      <Pill
                        tone={toneForStatus(assignment.verification_status)}
                      >
                        {assignment.verification_status}
                      </Pill>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className={styles.actionCell}>
                    <Link
                      href={`/advertisements/assignments/${assignment.assignment_id}`}
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
                loadList(campaignId, driverId, status, list.page - 1)
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
                loadList(campaignId, driverId, status, list.page + 1)
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
