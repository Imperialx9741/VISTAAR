"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import { getTemplate, publishTemplate } from "@/lib/api/notifications";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdminProfile, NotificationTemplate } from "@/lib/api/types";
import styles from "./TemplateDetailPage.module.css";

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

export function TemplateDetailPage({ templateId }: { templateId: string }) {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [template, setTemplate] = useState<NotificationTemplate | null>(null);
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

    async function loadTemplateOnMount() {
      try {
        const data = await getTemplate(templateId);
        if (!ignore) setTemplate(data);
      } catch (error) {
        if (!ignore) setLoadError(errorMessage(error));
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    loadProfileOnMount();
    loadTemplateOnMount();
    return () => {
      ignore = true;
    };
  }, [templateId]);

  async function handlePublish() {
    setIsWorking(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const updated = await publishTemplate(templateId);
      setTemplate(updated);
      setActionSuccess("Template published.");
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setIsWorking(false);
    }
  }

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

  const canPublish = template?.status === "DRAFT";

  return (
    <AppShell
      title="Notification template"
      subtitle={templateId}
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <Link href="/notifications/templates" className={styles.backLink}>
        ← Back to Templates
      </Link>

      {loading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading template…
        </div>
      )}

      {!loading && loadError && (
        <div className={styles.errorBanner} role="alert">
          {loadError}
        </div>
      )}

      {!loading && !loadError && template && (
        <>
          <div className={styles.summaryCard}>
            <div>
              <div className={styles.summaryLabel}>Template key</div>
              <div className={styles.summaryValue}>
                {template.template_key}
              </div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Channel</div>
              <div className={styles.summaryValue}>{template.channel}</div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Version</div>
              <div className={styles.summaryValue}>{template.version}</div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Status</div>
              <Pill tone={toneForStatus(template.status)}>
                {template.status}
              </Pill>
            </div>
            <div>
              <div className={styles.summaryLabel}>Event key</div>
              <div className={styles.summaryValue}>
                {template.event_key ?? "—"}
              </div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Created</div>
              <div className={styles.summaryValue}>
                {DATE_TIME.format(new Date(template.created_at))}
              </div>
            </div>
            {canPublish && (
              <div className={styles.summaryActions}>
                <button
                  type="button"
                  className={styles.primaryButton}
                  disabled={isWorking}
                  onClick={handlePublish}
                >
                  Publish
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

          <div className={styles.sectionLabel}>Content</div>
          <div className={styles.panel}>
            {template.title && (
              <p className={styles.emptyState}>
                <strong>Title:</strong> {template.title}
              </p>
            )}
            <p className={styles.body}>{template.body}</p>
          </div>
        </>
      )}
    </AppShell>
  );
}
