"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import {
  assignAdCampaignDriver,
  endAdCampaign,
  getAdCampaign,
  pauseAdCampaign,
  resumeAdCampaign,
  searchAdAssignments,
} from "@/lib/api/advertisements";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdCampaign, AdAssignment, AdminProfile } from "@/lib/api/types";
import styles from "./CampaignDetailPage.module.css";

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
  if (error instanceof ApiError) return error.message;
  return "Something went wrong. Try again.";
}

export function CampaignDetailPage({ campaignId }: { campaignId: string }) {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [campaign, setCampaign] = useState<AdCampaign | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [assignments, setAssignments] = useState<AdAssignment[] | null>(null);
  const [assignmentsError, setAssignmentsError] = useState<string | null>(
    null,
  );

  const [isWorking, setIsWorking] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  const [driverId, setDriverId] = useState("");
  const [isAssigning, setIsAssigning] = useState(false);
  const [assignError, setAssignError] = useState<string | null>(null);

  const loadAssignments = useCallback(async () => {
    try {
      const result = await searchAdAssignments(campaignId, "", "", 1, 50);
      setAssignments(result.items);
    } catch (error) {
      setAssignmentsError(errorMessage(error));
    }
  }, [campaignId]);

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

    async function loadCampaignOnMount() {
      try {
        const data = await getAdCampaign(campaignId);
        if (!ignore) setCampaign(data);
      } catch (error) {
        if (!ignore) setLoadError(errorMessage(error));
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    async function loadAssignmentsOnMount() {
      try {
        const result = await searchAdAssignments(campaignId, "", "", 1, 50);
        if (!ignore) setAssignments(result.items);
      } catch (error) {
        if (!ignore) setAssignmentsError(errorMessage(error));
      }
    }

    loadProfileOnMount();
    loadCampaignOnMount();
    loadAssignmentsOnMount();
    return () => {
      ignore = true;
    };
  }, [campaignId]);

  async function runAction(label: string, action: () => Promise<AdCampaign>) {
    setIsWorking(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const updated = await action();
      setCampaign(updated);
      setActionSuccess(label);
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setIsWorking(false);
    }
  }

  async function handleAssign(event: React.FormEvent) {
    event.preventDefault();
    setAssignError(null);
    setIsAssigning(true);
    try {
      await assignAdCampaignDriver(campaignId, driverId);
      setDriverId("");
      await loadAssignments();
    } catch (error) {
      setAssignError(errorMessage(error));
    } finally {
      setIsAssigning(false);
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

  const canPause = campaign?.status === "ACTIVE";
  const canResume = campaign?.status === "PAUSED";
  const canEnd = campaign?.status === "ACTIVE" || campaign?.status === "PAUSED";
  const canAssign = campaign?.status === "ACTIVE";

  return (
    <AppShell
      title="Campaign"
      subtitle={campaignId}
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <Link href="/advertisements" className={styles.backLink}>
        ← Back to Advertisements
      </Link>

      {loading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading campaign…
        </div>
      )}

      {!loading && loadError && (
        <div className={styles.errorBanner} role="alert">
          {loadError}
        </div>
      )}

      {!loading && !loadError && campaign && (
        <>
          <div className={styles.summaryCard}>
            <div>
              <div className={styles.summaryLabel}>Partner</div>
              <div className={styles.summaryValue}>
                {campaign.partner_name}
              </div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Payout amount</div>
              <div className={styles.summaryValue}>
                {CURRENCY.format(campaign.payout_amount)}
              </div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Driver / VISTAAR split</div>
              <div className={styles.summaryValue}>
                {campaign.driver_share_percent}% /{" "}
                {campaign.vistaar_share_percent}%
              </div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Status</div>
              <Pill tone={toneForStatus(campaign.status)}>
                {campaign.status}
              </Pill>
            </div>
            <div>
              <div className={styles.summaryLabel}>Starts at</div>
              <div className={styles.summaryValue}>
                {campaign.starts_at
                  ? DATE_TIME.format(new Date(campaign.starts_at))
                  : "—"}
              </div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Ends at</div>
              <div className={styles.summaryValue}>
                {campaign.ends_at
                  ? DATE_TIME.format(new Date(campaign.ends_at))
                  : "—"}
              </div>
            </div>
            <div className={styles.summaryActions}>
              {canPause && (
                <button
                  type="button"
                  className={styles.secondaryButton}
                  disabled={isWorking}
                  onClick={() =>
                    runAction("Campaign paused.", () =>
                      pauseAdCampaign(campaignId),
                    )
                  }
                >
                  Pause
                </button>
              )}
              {canResume && (
                <button
                  type="button"
                  className={styles.secondaryButton}
                  disabled={isWorking}
                  onClick={() =>
                    runAction("Campaign resumed.", () =>
                      resumeAdCampaign(campaignId),
                    )
                  }
                >
                  Resume
                </button>
              )}
              {canEnd && (
                <button
                  type="button"
                  className={styles.dangerButton}
                  disabled={isWorking}
                  onClick={() =>
                    runAction("Campaign ended.", () =>
                      endAdCampaign(campaignId),
                    )
                  }
                >
                  End
                </button>
              )}
            </div>
          </div>

          {actionError && (
            <div className={styles.errorBanner} role="alert">
              {actionError}
            </div>
          )}
          {actionSuccess && (
            <div className={styles.successBanner} role="status">
              {actionSuccess}
            </div>
          )}

          <div className={styles.sectionLabel}>Assign a driver</div>
          <div className={styles.panel}>
            {canAssign ? (
              <form className={styles.reasonRow} onSubmit={handleAssign}>
                <input
                  type="text"
                  value={driverId}
                  onChange={(event) => setDriverId(event.target.value)}
                  placeholder="Driver ID (UUID)"
                  aria-label="Driver ID"
                  required
                  disabled={isAssigning}
                  className={styles.reasonInput}
                />
                <button
                  type="submit"
                  className={styles.primaryButton}
                  disabled={isAssigning || !driverId}
                >
                  {isAssigning ? "Assigning…" : "Assign driver"}
                </button>
              </form>
            ) : (
              <div className={styles.emptyState}>
                Only an ACTIVE campaign accepts new driver assignments.
              </div>
            )}
            {assignError && (
              <div className={styles.errorBanner} role="alert">
                {assignError}
              </div>
            )}
          </div>

          <div className={styles.sectionLabel}>Assignments</div>
          {assignmentsError && (
            <div className={styles.errorBanner} role="alert">
              {assignmentsError}
            </div>
          )}
          {!assignmentsError && assignments && (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Driver</th>
                  <th>Status</th>
                  <th>Verification</th>
                  <th aria-hidden="true" />
                </tr>
              </thead>
              <tbody>
                {assignments.length === 0 && (
                  <tr>
                    <td colSpan={4} className={styles.emptyState}>
                      No drivers assigned yet.
                    </td>
                  </tr>
                )}
                {assignments.map((assignment) => (
                  <tr key={assignment.assignment_id}>
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
          )}
        </>
      )}
    </AppShell>
  );
}
