"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import { getOffer } from "@/lib/api/matching";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdminProfile, MatchingOffer } from "@/lib/api/types";
import styles from "./OfferDetailPage.module.css";

const DATE_TIME = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

function errorMessage(error: unknown): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) return error.message;
  return "Something went wrong. Try again.";
}

/** Offer detail (Admin Web §4.6, ADR-0054) — read-only, documented/safe
 * fields only. No action exists on this screen; no coordinates, no
 * Redis-derived location or availability data (ADR-0054 §5). */
export function OfferDetailPage({ offerId }: { offerId: string }) {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [offer, setOffer] = useState<MatchingOffer | null>(null);
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

    async function loadOfferOnMount() {
      try {
        const data = await getOffer(offerId);
        if (!ignore) setOffer(data);
      } catch (error) {
        if (!ignore) setLoadError(errorMessage(error));
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    loadProfileOnMount();
    loadOfferOnMount();
    return () => {
      ignore = true;
    };
  }, [offerId]);

  if (profileFailed) {
    return (
      <div className={styles.fullPageMessage}>
        <p>Something went wrong loading Matching / Offers. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Matching / Offers…</p>
      </div>
    );
  }

  return (
    <AppShell
      title="Offer"
      subtitle={offerId}
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <Link href="/matching" className={styles.backLink}>
        ← Back to Matching / Offers
      </Link>

      {loading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading offer…
        </div>
      )}

      {!loading && loadError && (
        <div className={styles.errorBanner} role="alert">
          {loadError}
        </div>
      )}

      {!loading && !loadError && offer && (
        <div className={styles.summaryCard}>
          <div>
            <div className={styles.summaryLabel}>Ride</div>
            <div className={styles.idCell}>{offer.ride_id}</div>
          </div>
          <div>
            <div className={styles.summaryLabel}>Driver</div>
            <div className={styles.idCell}>{offer.driver_id}</div>
          </div>
          <div>
            <div className={styles.summaryLabel}>Vehicle</div>
            <div className={styles.idCell}>{offer.vehicle_id}</div>
          </div>
          <div>
            <div className={styles.summaryLabel}>Status</div>
            <Pill tone={toneForStatus(offer.status)}>{offer.status}</Pill>
          </div>
          <div>
            <div className={styles.summaryLabel}>Created</div>
            <div className={styles.summaryValue}>
              {DATE_TIME.format(new Date(offer.created_at))}
            </div>
          </div>
          <div>
            <div className={styles.summaryLabel}>Expires</div>
            <div className={styles.summaryValue}>
              {DATE_TIME.format(new Date(offer.expires_at))}
            </div>
          </div>
          <div>
            <div className={styles.summaryLabel}>Responded</div>
            <div className={styles.summaryValue}>
              {offer.responded_at
                ? DATE_TIME.format(new Date(offer.responded_at))
                : "—"}
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
