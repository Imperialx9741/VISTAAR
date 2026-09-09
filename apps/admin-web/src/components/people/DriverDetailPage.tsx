"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import {
  approveDriver,
  getDriver,
  reactivateDriver,
  rejectDriver,
  suspendDriver,
} from "@/lib/api/people";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdminProfile, DriverDetail } from "@/lib/api/types";
import styles from "./PeopleDetail.module.css";

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

export function DriverDetailPage({ driverId }: { driverId: string }) {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [driver, setDriver] = useState<DriverDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [rejectReason, setRejectReason] = useState("");
  const [showRejectField, setShowRejectField] = useState(false);
  const [suspendReason, setSuspendReason] = useState("");
  const [showSuspendField, setShowSuspendField] = useState(false);

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

    async function loadDriverOnMount() {
      try {
        const data = await getDriver(driverId);
        if (!ignore) setDriver(data);
      } catch (error) {
        if (!ignore) setLoadError(errorMessage(error));
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    loadProfileOnMount();
    loadDriverOnMount();
    return () => {
      ignore = true;
    };
  }, [driverId]);

  async function runAction<T extends Partial<DriverDetail>>(
    label: string,
    action: () => Promise<T>,
  ) {
    setIsWorking(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const updated = await action();
      setDriver((prev) => (prev ? { ...prev, ...updated } : prev));
      setActionSuccess(label);
      setShowRejectField(false);
      setShowSuspendField(false);
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setIsWorking(false);
    }
  }

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

  const canApproveOrReject = driver?.verification_status === "PENDING";
  const canSuspend =
    driver != null && driver.operational_status !== "SUSPENDED";
  const canReactivate = driver?.operational_status === "SUSPENDED";

  return (
    <AppShell
      title="Driver profile"
      subtitle={driverId}
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <Link href="/drivers" className={styles.backLink}>
        ← Back to Drivers
      </Link>

      {loading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading driver…
        </div>
      )}

      {!loading && loadError && (
        <div className={styles.errorBanner} role="alert">
          {loadError}
        </div>
      )}

      {!loading && !loadError && driver && (
        <>
          <div className={styles.summaryCard}>
            <div>
              <div className={styles.summaryLabel}>Name</div>
              <div className={styles.summaryValue}>{driver.full_name}</div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Phone</div>
              <div className={styles.summaryValue}>{driver.phone}</div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Verification</div>
              <Pill tone={toneForStatus(driver.verification_status)}>
                {driver.verification_status}
              </Pill>
            </div>
            <div>
              <div className={styles.summaryLabel}>Operational</div>
              <Pill tone={toneForStatus(driver.operational_status)}>
                {driver.operational_status}
              </Pill>
            </div>
            <div>
              <div className={styles.summaryLabel}>Strikes</div>
              <div className={styles.summaryValue}>
                {driver.strikes}
                <Link
                  href={`/drivers/${driverId}/strikes`}
                  className={styles.viewLink}
                >
                  View history →
                </Link>
              </div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Joined</div>
              <div className={styles.summaryValue}>
                {DATE_TIME.format(new Date(driver.created_at))}
              </div>
            </div>
            <div className={styles.summaryActions}>
              {canApproveOrReject && (
                <>
                  <button
                    type="button"
                    className={styles.primaryButton}
                    disabled={isWorking}
                    onClick={() =>
                      runAction("Driver approved.", () => approveDriver(driverId))
                    }
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    className={styles.dangerButton}
                    disabled={isWorking}
                    onClick={() => setShowRejectField((v) => !v)}
                  >
                    Reject
                  </button>
                </>
              )}
              {canSuspend && (
                <button
                  type="button"
                  className={styles.dangerButton}
                  disabled={isWorking}
                  onClick={() => setShowSuspendField((v) => !v)}
                >
                  Suspend
                </button>
              )}
              {canReactivate && (
                <button
                  type="button"
                  className={styles.primaryButton}
                  disabled={isWorking}
                  onClick={() =>
                    runAction("Driver reactivated.", () =>
                      reactivateDriver(driverId),
                    )
                  }
                >
                  Reactivate
                </button>
              )}
            </div>
          </div>

          {showRejectField && (
            <div className={styles.reasonRow}>
              <input
                type="text"
                placeholder="Reason (optional)"
                value={rejectReason}
                onChange={(event) => setRejectReason(event.target.value)}
                className={styles.reasonInput}
                aria-label="Rejection reason"
              />
              <button
                type="button"
                className={styles.dangerButton}
                disabled={isWorking}
                onClick={() =>
                  runAction("Driver rejected.", () =>
                    rejectDriver(driverId, rejectReason),
                  )
                }
              >
                Confirm reject
              </button>
            </div>
          )}

          {showSuspendField && (
            <div className={styles.reasonRow}>
              <input
                type="text"
                placeholder="Reason (optional)"
                value={suspendReason}
                onChange={(event) => setSuspendReason(event.target.value)}
                className={styles.reasonInput}
                aria-label="Suspension reason"
              />
              <button
                type="button"
                className={styles.dangerButton}
                disabled={isWorking}
                onClick={() =>
                  runAction("Driver suspended.", () =>
                    suspendDriver(driverId, suspendReason),
                  )
                }
              >
                Confirm suspend
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

          <div className={styles.sectionLabel}>Documents</div>
          <div className={styles.panel}>
            {driver.documents.length === 0 ? (
              <p className={styles.emptyState}>No documents submitted yet.</p>
            ) : (
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Document</th>
                    <th>Status</th>
                    <th>Verification cases</th>
                  </tr>
                </thead>
                <tbody>
                  {driver.documents.map((doc) => (
                    <tr key={doc.document_id}>
                      <td>{doc.document_type}</td>
                      <td>
                        <Pill tone={toneForStatus(doc.verification_status)}>
                          {doc.verification_status}
                        </Pill>
                      </td>
                      <td>
                        {doc.verification_cases.length === 0
                          ? "—"
                          : doc.verification_cases.map((c) => (
                              <Pill key={c.case_id} tone={toneForStatus(c.status)}>
                                {c.status}
                              </Pill>
                            ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </AppShell>
  );
}
