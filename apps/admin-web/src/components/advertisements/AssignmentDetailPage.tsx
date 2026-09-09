"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import {
  calculateAdPayout,
  getAdAssignment,
  verifyAdAssignment,
} from "@/lib/api/advertisements";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdAssignment, AdminProfile, AdPayout } from "@/lib/api/types";
import styles from "./AssignmentDetailPage.module.css";

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

export function AssignmentDetailPage({
  assignmentId,
}: {
  assignmentId: string;
}) {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [assignment, setAssignment] = useState<AdAssignment | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [isWorking, setIsWorking] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [payout, setPayout] = useState<AdPayout | null>(null);

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

    async function loadAssignmentOnMount() {
      try {
        const data = await getAdAssignment(assignmentId);
        if (!ignore) setAssignment(data);
      } catch (error) {
        if (!ignore) setLoadError(errorMessage(error));
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    loadProfileOnMount();
    loadAssignmentOnMount();
    return () => {
      ignore = true;
    };
  }, [assignmentId]);

  async function handleVerify(approved: boolean) {
    setIsWorking(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const updated = await verifyAdAssignment(assignmentId, approved);
      setAssignment(updated);
      setActionSuccess(approved ? "Proof approved." : "Proof rejected.");
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setIsWorking(false);
    }
  }

  async function handleCalculatePayout() {
    setIsWorking(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const created = await calculateAdPayout(assignmentId);
      setPayout(created);
      setActionSuccess("Payout calculated.");
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setIsWorking(false);
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

  const canVerify = assignment?.status === "PROOF_SUBMITTED";
  const canCalculatePayout = assignment?.status === "VERIFIED";

  return (
    <AppShell
      title="Assignment"
      subtitle={assignmentId}
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <Link href="/advertisements/assignments" className={styles.backLink}>
        ← Back to proof review queue
      </Link>

      {loading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading assignment…
        </div>
      )}

      {!loading && loadError && (
        <div className={styles.errorBanner} role="alert">
          {loadError}
        </div>
      )}

      {!loading && !loadError && assignment && (
        <>
          <div className={styles.summaryCard}>
            <div>
              <div className={styles.summaryLabel}>Campaign</div>
              <div className={styles.idCell}>{assignment.campaign_id}</div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Driver</div>
              <div className={styles.idCell}>{assignment.driver_id}</div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Status</div>
              <Pill tone={toneForStatus(assignment.status)}>
                {assignment.status}
              </Pill>
            </div>
            <div>
              <div className={styles.summaryLabel}>Verification</div>
              {assignment.verification_status ? (
                <Pill tone={toneForStatus(assignment.verification_status)}>
                  {assignment.verification_status}
                </Pill>
              ) : (
                <div className={styles.summaryValue}>—</div>
              )}
            </div>
            <div>
              <div className={styles.summaryLabel}>Assigned at</div>
              <div className={styles.summaryValue}>
                {DATE_TIME.format(new Date(assignment.assigned_at))}
              </div>
            </div>
            <div className={styles.summaryActions}>
              {canVerify && (
                <>
                  <button
                    type="button"
                    className={styles.dangerButton}
                    disabled={isWorking}
                    onClick={() => handleVerify(false)}
                  >
                    Reject proof
                  </button>
                  <button
                    type="button"
                    className={styles.primaryButton}
                    disabled={isWorking}
                    onClick={() => handleVerify(true)}
                  >
                    Approve proof
                  </button>
                </>
              )}
              {canCalculatePayout && (
                <button
                  type="button"
                  className={styles.primaryButton}
                  disabled={isWorking}
                  onClick={handleCalculatePayout}
                >
                  Calculate payout
                </button>
              )}
            </div>
          </div>

          <div className={styles.sectionLabel}>Installation proof</div>
          <div className={styles.panel}>
            {assignment.proof_uri ? (
              <a
                href={assignment.proof_uri}
                target="_blank"
                rel="noreferrer noopener"
                className={styles.viewLink}
              >
                View submitted proof →
              </a>
            ) : (
              <div className={styles.emptyState}>
                No proof submitted yet.
              </div>
            )}
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

          {payout && (
            <>
              <div className={styles.sectionLabel}>Payout</div>
              <div className={styles.summaryCard}>
                <div>
                  <div className={styles.summaryLabel}>Gross amount</div>
                  <div className={styles.summaryValue}>
                    {CURRENCY.format(payout.gross_amount)}
                  </div>
                </div>
                <div>
                  <div className={styles.summaryLabel}>Driver amount</div>
                  <div className={styles.summaryValue}>
                    {CURRENCY.format(payout.driver_amount)}
                  </div>
                </div>
                <div>
                  <div className={styles.summaryLabel}>VISTAAR amount</div>
                  <div className={styles.summaryValue}>
                    {CURRENCY.format(payout.vistaar_amount)}
                  </div>
                </div>
                <div>
                  <div className={styles.summaryLabel}>Status</div>
                  <Pill tone={toneForStatus(payout.status)}>
                    {payout.status}
                  </Pill>
                </div>
                <div className={styles.summaryActions}>
                  <Link
                    href="/advertisements/payouts"
                    className={styles.viewLink}
                  >
                    View in Payouts →
                  </Link>
                </div>
              </div>
            </>
          )}
        </>
      )}
    </AppShell>
  );
}
