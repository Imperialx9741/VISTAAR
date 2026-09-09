"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import { getBroadcast } from "@/lib/api/notifications";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdminProfile, Broadcast } from "@/lib/api/types";
import styles from "./BroadcastDetailPage.module.css";

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

export function BroadcastDetailPage({ broadcastId }: { broadcastId: string }) {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [broadcast, setBroadcast] = useState<Broadcast | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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

    async function loadBroadcastOnMount() {
      try {
        const data = await getBroadcast(broadcastId);
        if (!ignore) setBroadcast(data);
      } catch (error) {
        if (!ignore) setLoadError(errorMessage(error));
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    loadProfileOnMount();
    loadBroadcastOnMount();
    return () => {
      ignore = true;
    };
  }, [broadcastId]);

  if (profileFailed) {
    return (
      <div className={styles.fullPageMessage}>
        <p>Something went wrong loading Notifications. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Notifications…</p>
      </div>
    );
  }

  return (
    <AppShell
      title="Broadcast"
      subtitle={broadcastId}
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <Link href="/notifications/broadcasts" className={styles.backLink}>
        ← Back to Broadcasts
      </Link>

      {loading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading broadcast…
        </div>
      )}

      {!loading && loadError && (
        <div className={styles.errorBanner} role="alert">
          {loadError}
        </div>
      )}

      {!loading && !loadError && broadcast && (
        <>
          <div className={styles.summaryCard}>
            <div>
              <div className={styles.summaryLabel}>Channel</div>
              <div className={styles.summaryValue}>{broadcast.channel}</div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Audience</div>
              <div className={styles.summaryValue}>
                {broadcast.audience_type}
                {broadcast.audience_user_ids
                  ? ` (${broadcast.audience_user_ids.length})`
                  : ""}
              </div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Status</div>
              <Pill tone={toneForStatus(broadcast.status)}>
                {broadcast.status}
              </Pill>
            </div>
            <div>
              <div className={styles.summaryLabel}>Sent / Failed</div>
              <div className={styles.summaryValue}>
                {broadcast.sent_count} / {broadcast.failed_count}
              </div>
            </div>
            <div>
              <div className={styles.summaryLabel}>
                {broadcast.status === "SCHEDULED" ? "Scheduled for" : "Sent at"}
              </div>
              <div className={styles.summaryValue}>
                {broadcast.status === "SCHEDULED"
                  ? broadcast.scheduled_at
                    ? DATE_TIME.format(new Date(broadcast.scheduled_at))
                    : "—"
                  : broadcast.sent_at
                    ? DATE_TIME.format(new Date(broadcast.sent_at))
                    : "—"}
              </div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Composed</div>
              <div className={styles.summaryValue}>
                {DATE_TIME.format(new Date(broadcast.created_at))}
              </div>
            </div>
          </div>

          <div className={styles.sectionLabel}>Message</div>
          <div className={styles.panel}>
            {broadcast.subject && (
              <p className={styles.emptyState}>
                <strong>Subject:</strong> {broadcast.subject}
              </p>
            )}
            <p className={styles.body}>{broadcast.body}</p>
          </div>
        </>
      )}
    </AppShell>
  );
}
