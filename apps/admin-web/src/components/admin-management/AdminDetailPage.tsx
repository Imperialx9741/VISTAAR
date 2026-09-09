"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { PermissionEditor } from "./PermissionEditor";
import { getAdminProfile } from "@/lib/api/dashboard";
import {
  disableAdmin,
  enableAdmin,
  getAdmin,
  updatePermissions,
} from "@/lib/api/admin-management";
import { ApiError, NoSessionError } from "@/lib/api/client";
import type { AdminAccount, AdminPermission, AdminProfile } from "@/lib/api/types";
import styles from "./AdminDetailPage.module.css";

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

export function AdminDetailPage({ adminId }: { adminId: string }) {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [admin, setAdmin] = useState<AdminAccount | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [draftPermissions, setDraftPermissions] = useState<AdminPermission[]>(
    [],
  );
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const [isTogglingStatus, setIsTogglingStatus] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);

  // Two independent inline async IIFEs, same reasoning as
  // AdminManagementPage's own mount effect — neither touches setState
  // until after its own await, so react-hooks/set-state-in-effect
  // doesn't flag it. loading/loadError's useState initial values already
  // cover the starting "loading, no error yet" state.
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

    async function loadAdminOnMount() {
      try {
        const data = await getAdmin(adminId);
        if (ignore) return;
        setAdmin(data);
        setDraftPermissions(data.permissions);
      } catch (error) {
        if (!ignore) setLoadError(errorMessage(error));
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    loadProfileOnMount();
    loadAdminOnMount();
    return () => {
      ignore = true;
    };
  }, [adminId]);

  const isDirty =
    JSON.stringify(
      [...draftPermissions].sort((a, b) => a.module.localeCompare(b.module)),
    ) !==
    JSON.stringify(
      [...(admin?.permissions ?? [])].sort((a, b) =>
        a.module.localeCompare(b.module),
      ),
    );

  async function handleSave() {
    setIsSaving(true);
    setSaveError(null);
    setSaveSuccess(false);
    try {
      const result = await updatePermissions(adminId, draftPermissions);
      setAdmin((prev) => (prev ? { ...prev, permissions: result.permissions } : prev));
      setDraftPermissions(result.permissions);
      setSaveSuccess(true);
    } catch (error) {
      setSaveError(errorMessage(error));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleToggleStatus() {
    if (!admin) return;
    setIsTogglingStatus(true);
    setStatusError(null);
    try {
      const updated =
        admin.status === "ACTIVE"
          ? await disableAdmin(adminId)
          : await enableAdmin(adminId);
      setAdmin(updated);
    } catch (error) {
      setStatusError(errorMessage(error));
    } finally {
      setIsTogglingStatus(false);
    }
  }

  if (profileFailed) {
    return (
      <div className={styles.fullPageMessage}>
        <p>Something went wrong loading Admin Management. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Admin Management…</p>
      </div>
    );
  }

  const isSuperAdminTarget = admin?.role === "SUPER_ADMIN";

  return (
    <AppShell
      title="Admin profile"
      subtitle={adminId}
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <Link href="/admin-management" className={styles.backLink}>
        ← Back to Admin Management
      </Link>

      {loading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading admin…
        </div>
      )}

      {!loading && loadError && (
        <div className={styles.errorBanner} role="alert">
          {loadError}
        </div>
      )}

      {!loading && !loadError && admin && (
        <>
          <div className={styles.summaryCard}>
            <div>
              <div className={styles.summaryLabel}>Admin ID</div>
              <div className={styles.summaryValue}>{admin.admin_id}</div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Role</div>
              <Pill tone={isSuperAdminTarget ? "gold" : "neutral"}>
                {admin.role}
              </Pill>
            </div>
            <div>
              <div className={styles.summaryLabel}>Status</div>
              <Pill tone={admin.status === "ACTIVE" ? "success" : "danger"}>
                {admin.status}
              </Pill>
            </div>
            <div>
              <div className={styles.summaryLabel}>Created</div>
              <div className={styles.summaryValue}>
                {DATE_TIME.format(new Date(admin.created_at))}
              </div>
            </div>
            {!isSuperAdminTarget && (
              <button
                type="button"
                className={
                  admin.status === "ACTIVE"
                    ? styles.dangerButton
                    : styles.primaryButton
                }
                onClick={handleToggleStatus}
                disabled={isTogglingStatus}
              >
                {isTogglingStatus
                  ? "Working…"
                  : admin.status === "ACTIVE"
                    ? "Disable admin"
                    : "Enable admin"}
              </button>
            )}
          </div>

          {statusError && (
            <div className={styles.errorBanner} role="alert">
              {statusError}
            </div>
          )}

          {isSuperAdminTarget ? (
            <p className={styles.hint}>
              Super Admin accounts have implicit full access and are not
              managed through this screen (ADR-0040) — they&apos;re
              provisioned out-of-band, same as this one was.
            </p>
          ) : (
            <>
              <div className={styles.sectionLabel}>Module access</div>
              <div className={styles.panel}>
                <PermissionEditor
                  value={draftPermissions}
                  onChange={(next) => {
                    setDraftPermissions(next);
                    setSaveSuccess(false);
                  }}
                  disabled={isSaving}
                />

                {saveError && (
                  <div className={styles.errorBanner} role="alert">
                    {saveError}
                  </div>
                )}
                {saveSuccess && !isDirty && (
                  <div className={styles.successBanner} role="status">
                    Permissions saved.
                  </div>
                )}

                <div className={styles.actions}>
                  <button
                    type="button"
                    className={styles.secondaryButton}
                    onClick={() => {
                      setDraftPermissions(admin.permissions);
                      setSaveError(null);
                    }}
                    disabled={isSaving || !isDirty}
                  >
                    Reset
                  </button>
                  <button
                    type="button"
                    className={styles.primaryButton}
                    onClick={handleSave}
                    disabled={isSaving || !isDirty}
                  >
                    {isSaving ? "Saving…" : "Save permissions"}
                  </button>
                </div>
              </div>
            </>
          )}
        </>
      )}
    </AppShell>
  );
}
