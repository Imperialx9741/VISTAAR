"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import { getRide } from "@/lib/api/rides";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdminProfile, Ride } from "@/lib/api/types";
import styles from "./RideDetailPage.module.css";

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
  second: "2-digit",
});

function errorMessage(error: unknown): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) return error.message;
  return "Something went wrong. Try again.";
}

function formatCoordinates(latitude: number, longitude: number): string {
  return `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`;
}

interface TimelineStep {
  label: string;
  at: string | null;
}

/** Ride detail (Admin Web §4.5) — read-only lifecycle timeline. No
 * action exists on this screen; every field is a plain fact about a
 * ride that already happened or is in progress. */
export function RideDetailPage({ rideId }: { rideId: string }) {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [ride, setRide] = useState<Ride | null>(null);
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

    async function loadRideOnMount() {
      try {
        const data = await getRide(rideId);
        if (!ignore) setRide(data);
      } catch (error) {
        if (!ignore) setLoadError(errorMessage(error));
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    loadProfileOnMount();
    loadRideOnMount();
    return () => {
      ignore = true;
    };
  }, [rideId]);

  if (profileFailed) {
    return (
      <div className={styles.fullPageMessage}>
        <p>Something went wrong loading Rides. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Rides…</p>
      </div>
    );
  }

  const timeline: TimelineStep[] = ride
    ? [
        { label: "Requested", at: ride.requested_at },
        { label: "Accepted", at: ride.accepted_at },
        { label: "Driver arrived", at: ride.arrived_at },
        { label: "Started", at: ride.started_at },
        { label: "Completed", at: ride.completed_at },
        { label: "Cancelled", at: ride.cancelled_at },
        { label: "Closed", at: ride.closed_at },
      ]
    : [];

  return (
    <AppShell
      title="Ride"
      subtitle={rideId}
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <Link href="/rides" className={styles.backLink}>
        ← Back to Rides
      </Link>

      {loading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading ride…
        </div>
      )}

      {!loading && loadError && (
        <div className={styles.errorBanner} role="alert">
          {loadError}
        </div>
      )}

      {!loading && !loadError && ride && (
        <>
          <div className={styles.summaryCard}>
            <div>
              <div className={styles.summaryLabel}>Status</div>
              <Pill tone={toneForStatus(ride.status)}>{ride.status}</Pill>
            </div>
            <div>
              <div className={styles.summaryLabel}>Vehicle category</div>
              <div className={styles.summaryValue}>
                {ride.requested_vehicle_category}
                {ride.requested_cab_tier ? ` (${ride.requested_cab_tier})` : ""}
              </div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Customer</div>
              <div className={styles.idCell}>{ride.customer_id}</div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Driver</div>
              <div className={styles.idCell}>{ride.driver_id ?? "—"}</div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Vehicle</div>
              <div className={styles.idCell}>{ride.vehicle_id ?? "—"}</div>
            </div>
          </div>

          <div className={styles.summaryCard}>
            <div>
              <div className={styles.summaryLabel}>Pickup</div>
              <div className={styles.summaryValue}>
                {formatCoordinates(ride.pickup.latitude, ride.pickup.longitude)}
              </div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Destination</div>
              <div className={styles.summaryValue}>
                {formatCoordinates(
                  ride.destination.latitude,
                  ride.destination.longitude,
                )}
              </div>
            </div>
          </div>

          <div className={styles.sectionLabel}>Fare</div>
          {ride.fare ? (
            <div className={styles.summaryCard}>
              <div>
                <div className={styles.summaryLabel}>Base</div>
                <div className={styles.summaryValue}>
                  {CURRENCY.format(ride.fare.base)}
                </div>
              </div>
              <div>
                <div className={styles.summaryLabel}>Discount</div>
                <div className={styles.summaryValue}>
                  {CURRENCY.format(ride.fare.discount)}
                </div>
              </div>
              <div>
                <div className={styles.summaryLabel}>Total</div>
                <div className={styles.summaryValue}>
                  {CURRENCY.format(ride.fare.total)}
                </div>
              </div>
            </div>
          ) : (
            <div className={styles.emptyState}>No fare quote yet.</div>
          )}

          <div className={styles.sectionLabel}>Timeline</div>
          <div className={styles.timeline}>
            {timeline.map((step) => (
              <div key={step.label} className={styles.timelineRow}>
                <span className={styles.timelineLabel}>{step.label}</span>
                <span
                  className={
                    step.at
                      ? styles.timelineValue
                      : `${styles.timelineValue} ${styles.pending}`
                  }
                >
                  {step.at ? DATE_TIME.format(new Date(step.at)) : "—"}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </AppShell>
  );
}
