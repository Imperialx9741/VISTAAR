"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import {
  acknowledgeSafetyIncident,
  escalateSafetyIncident,
  getSafetyIncident,
  resolveSafetyIncident,
} from "@/lib/api/safety-support";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdminProfile, SafetyIncident } from "@/lib/api/types";
import styles from "./IncidentDetailPage.module.css";

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

export function IncidentDetailPage({ incidentId }: { incidentId: string }) {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [incident, setIncident] = useState<SafetyIncident | null>(null);
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

    async function loadIncidentOnMount() {
      try {
        const data = await getSafetyIncident(incidentId);
        if (!ignore) setIncident(data);
      } catch (error) {
        if (!ignore) setLoadError(errorMessage(error));
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    loadProfileOnMount();
    loadIncidentOnMount();
    return () => {
      ignore = true;
    };
  }, [incidentId]);

  async function runAction(
    label: string,
    action: () => Promise<SafetyIncident>,
  ) {
    setIsWorking(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const updated = await action();
      setIncident(updated);
      setActionSuccess(label);
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setIsWorking(false);
    }
  }

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

  const canAcknowledge = incident?.status === "OPEN";
  const canEscalate = incident?.status === "ACKNOWLEDGED";
  const canResolve = incident?.status === "IN_PROGRESS";

  return (
    <AppShell
      title="Safety incident"
      subtitle={incidentId}
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <Link href="/safety" className={styles.backLink}>
        ← Back to Safety / SOS
      </Link>

      {loading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading incident…
        </div>
      )}

      {!loading && loadError && (
        <div className={styles.errorBanner} role="alert">
          {loadError}
        </div>
      )}

      {!loading && !loadError && incident && (
        <>
          <div className={styles.summaryCard}>
            <div>
              <div className={styles.summaryLabel}>Type</div>
              <div className={styles.summaryValue}>
                {incident.incident_type}
              </div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Status</div>
              <Pill tone={toneForStatus(incident.status)}>
                {incident.status}
              </Pill>
            </div>
            <div>
              <div className={styles.summaryLabel}>Reporter</div>
              <div className={styles.summaryValue}>{incident.reporter_id}</div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Ride</div>
              <div className={styles.summaryValue}>
                {incident.ride_id ?? "—"}
              </div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Location</div>
              <div className={styles.summaryValue}>
                {incident.location
                  ? `${incident.location.latitude.toFixed(4)}, ${incident.location.longitude.toFixed(4)}`
                  : "—"}
              </div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Opened</div>
              <div className={styles.summaryValue}>
                {DATE_TIME.format(new Date(incident.created_at))}
              </div>
            </div>
            <div className={styles.summaryActions}>
              {canAcknowledge && (
                <button
                  type="button"
                  className={styles.primaryButton}
                  disabled={isWorking}
                  onClick={() =>
                    runAction("Incident acknowledged.", () =>
                      acknowledgeSafetyIncident(incidentId),
                    )
                  }
                >
                  Acknowledge
                </button>
              )}
              {canEscalate && (
                <button
                  type="button"
                  className={styles.dangerButton}
                  disabled={isWorking}
                  onClick={() =>
                    runAction("Incident escalated.", () =>
                      escalateSafetyIncident(incidentId),
                    )
                  }
                >
                  Escalate
                </button>
              )}
              {canResolve && (
                <button
                  type="button"
                  className={styles.primaryButton}
                  disabled={isWorking}
                  onClick={() =>
                    runAction("Incident resolved.", () =>
                      resolveSafetyIncident(incidentId),
                    )
                  }
                >
                  Resolve
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
        </>
      )}
    </AppShell>
  );
}
