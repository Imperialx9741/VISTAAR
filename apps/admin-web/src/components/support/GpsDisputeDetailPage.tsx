"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import { getGpsDispute, resolveGpsDispute } from "@/lib/api/safety-support";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdminProfile, GpsDispute } from "@/lib/api/types";
import styles from "./GpsDisputeDetailPage.module.css";

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

/** GPS Dispute detail (Admin Web §4.14's own excluded row, ADR-0032) —
 * APPROVE performs the exact ride transition the original GPS
 * verification would have on a real PASS; REJECT only records the
 * decision. A required reason, same shape as every other resolve
 * action with a reason in this app (e.g. Reject Driver). */
export function GpsDisputeDetailPage({ disputeId }: { disputeId: string }) {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [dispute, setDispute] = useState<GpsDispute | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [pendingDecision, setPendingDecision] = useState<
    "APPROVE" | "REJECT" | null
  >(null);
  const [reason, setReason] = useState("");
  const [isWorking, setIsWorking] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

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

    async function loadDisputeOnMount() {
      try {
        const data = await getGpsDispute(disputeId);
        if (!ignore) setDispute(data);
      } catch (error) {
        if (!ignore) setLoadError(errorMessage(error));
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    loadProfileOnMount();
    loadDisputeOnMount();
    return () => {
      ignore = true;
    };
  }, [disputeId]);

  async function confirmDecision() {
    if (!pendingDecision || !reason.trim()) return;
    setIsWorking(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const updated = await resolveGpsDispute(
        disputeId,
        pendingDecision,
        reason.trim(),
      );
      setDispute(updated);
      setActionSuccess(
        pendingDecision === "APPROVE" ? "Dispute approved." : "Dispute rejected.",
      );
      setPendingDecision(null);
      setReason("");
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setIsWorking(false);
    }
  }

  if (profileFailed) {
    return (
      <div className={styles.fullPageMessage}>
        <p>Something went wrong loading Support / Disputes. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Support / Disputes…</p>
      </div>
    );
  }

  const canResolve = dispute?.status === "OPEN";

  return (
    <AppShell
      title="GPS dispute"
      subtitle={disputeId}
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <Link href="/support/gps-disputes" className={styles.backLink}>
        ← Back to GPS Disputes
      </Link>

      {loading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading dispute…
        </div>
      )}

      {!loading && loadError && (
        <div className={styles.errorBanner} role="alert">
          {loadError}
        </div>
      )}

      {!loading && !loadError && dispute && (
        <>
          <div className={styles.summaryCard}>
            <div>
              <div className={styles.summaryLabel}>Ride</div>
              <div className={styles.idCell}>{dispute.ride_id}</div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Type</div>
              <div className={styles.summaryValue}>
                {dispute.verification_type}
              </div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Status</div>
              <Pill tone={toneForStatus(dispute.status)}>{dispute.status}</Pill>
            </div>
            <div>
              <div className={styles.summaryLabel}>Opened</div>
              <div className={styles.summaryValue}>
                {DATE_TIME.format(new Date(dispute.opened_at))}
              </div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Evidence deadline</div>
              <div className={styles.summaryValue}>
                {DATE_TIME.format(new Date(dispute.evidence_deadline))}
              </div>
            </div>
            {dispute.decision && (
              <div>
                <div className={styles.summaryLabel}>Decision</div>
                <div className={styles.summaryValue}>
                  {dispute.decision}
                  {dispute.decided_reason ? ` — ${dispute.decided_reason}` : ""}
                </div>
              </div>
            )}
            {canResolve && (
              <div className={styles.summaryActions}>
                <button
                  type="button"
                  className={styles.dangerButton}
                  disabled={isWorking}
                  onClick={() => {
                    setPendingDecision("REJECT");
                    setActionSuccess(null);
                  }}
                >
                  Reject
                </button>
                <button
                  type="button"
                  className={styles.primaryButton}
                  disabled={isWorking}
                  onClick={() => {
                    setPendingDecision("APPROVE");
                    setActionSuccess(null);
                  }}
                >
                  Approve
                </button>
              </div>
            )}
          </div>

          {pendingDecision && (
            <div className={styles.reasonRow}>
              <input
                type="text"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder="Reason (required)"
                aria-label="Decision reason"
                disabled={isWorking}
                className={styles.reasonInput}
              />
              <button
                type="button"
                className={styles.secondaryButton}
                disabled={isWorking}
                onClick={() => {
                  setPendingDecision(null);
                  setReason("");
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                className={styles.primaryButton}
                disabled={isWorking || !reason.trim()}
                onClick={confirmDecision}
              >
                {isWorking
                  ? "Submitting…"
                  : `Confirm ${pendingDecision === "APPROVE" ? "approve" : "reject"}`}
              </button>
            </div>
          )}

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

          <div className={styles.sectionLabel}>Evidence</div>
          {dispute.evidence && dispute.evidence.length > 0 ? (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Details</th>
                  <th>Submitted</th>
                </tr>
              </thead>
              <tbody>
                {dispute.evidence.map((item, index) => (
                  <tr key={index}>
                    <td>{item.evidence_type}</td>
                    <td>
                      {item.uri ? (
                        <a
                          href={item.uri}
                          target="_blank"
                          rel="noreferrer noopener"
                          className={styles.viewLink}
                        >
                          View file →
                        </a>
                      ) : (
                        item.text_explanation
                      )}
                    </td>
                    <td>{DATE_TIME.format(new Date(item.submitted_at))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className={styles.emptyState}>No evidence submitted yet.</div>
          )}
        </>
      )}
    </AppShell>
  );
}
