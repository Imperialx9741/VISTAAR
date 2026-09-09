"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import { getSupportCase, resolveSupportCase } from "@/lib/api/safety-support";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdminProfile, SupportCaseDetail } from "@/lib/api/types";
import styles from "./CaseDetailPage.module.css";

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

export function CaseDetailPage({ caseId }: { caseId: string }) {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [supportCase, setSupportCase] = useState<SupportCaseDetail | null>(
    null,
  );
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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

    async function loadCaseOnMount() {
      try {
        const data = await getSupportCase(caseId);
        if (!ignore) setSupportCase(data);
      } catch (error) {
        if (!ignore) setLoadError(errorMessage(error));
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    loadProfileOnMount();
    loadCaseOnMount();
    return () => {
      ignore = true;
    };
  }, [caseId]);

  async function handleResolve() {
    setIsWorking(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const updated = await resolveSupportCase(caseId);
      setSupportCase((prev) => (prev ? { ...prev, ...updated } : prev));
      setActionSuccess("Case resolved.");
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

  const canResolve =
    supportCase != null &&
    supportCase.status !== "RESOLVED" &&
    supportCase.status !== "CLOSED";

  return (
    <AppShell
      title="Support case"
      subtitle={caseId}
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <Link href="/support" className={styles.backLink}>
        ← Back to Support / Disputes
      </Link>

      {loading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading case…
        </div>
      )}

      {!loading && loadError && (
        <div className={styles.errorBanner} role="alert">
          {loadError}
        </div>
      )}

      {!loading && !loadError && supportCase && (
        <>
          <div className={styles.summaryCard}>
            <div>
              <div className={styles.summaryLabel}>User</div>
              <div className={styles.summaryValue}>{supportCase.user_id}</div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Category</div>
              <div className={styles.summaryValue}>
                {supportCase.category ?? "—"}
              </div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Priority</div>
              <div className={styles.summaryValue}>{supportCase.priority}</div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Status</div>
              <Pill tone={toneForStatus(supportCase.status)}>
                {supportCase.status}
              </Pill>
            </div>
            <div>
              <div className={styles.summaryLabel}>Opened</div>
              <div className={styles.summaryValue}>
                {DATE_TIME.format(new Date(supportCase.created_at))}
              </div>
            </div>
            {canResolve && (
              <div className={styles.summaryActions}>
                <button
                  type="button"
                  className={styles.primaryButton}
                  disabled={isWorking}
                  onClick={handleResolve}
                >
                  Resolve case
                </button>
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

          <div className={styles.sectionLabel}>Conversation</div>
          <div className={styles.panel}>
            {supportCase.messages.length === 0 ? (
              <p className={styles.emptyState}>No messages yet.</p>
            ) : (
              <div className={styles.messageList}>
                {supportCase.messages.map((message) => (
                  <div key={message.message_id} className={styles.message}>
                    <div className={styles.messageHeader}>
                      <span className={styles.messageSender}>
                        {message.sender_type}
                      </span>
                      <span className={styles.messageTime}>
                        {DATE_TIME.format(new Date(message.created_at))}
                      </span>
                    </div>
                    <div className={styles.messageBody}>{message.message}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </AppShell>
  );
}
