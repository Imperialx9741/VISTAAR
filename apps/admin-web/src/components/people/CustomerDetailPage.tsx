"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import { getCustomer } from "@/lib/api/people";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdminProfile, CustomerDetail } from "@/lib/api/types";
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

export function CustomerDetailPage({ customerId }: { customerId: string }) {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [customer, setCustomer] = useState<CustomerDetail | null>(null);
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

    async function loadCustomerOnMount() {
      try {
        const data = await getCustomer(customerId);
        if (!ignore) setCustomer(data);
      } catch (error) {
        if (!ignore) setLoadError(errorMessage(error));
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    loadProfileOnMount();
    loadCustomerOnMount();
    return () => {
      ignore = true;
    };
  }, [customerId]);

  if (profileFailed) {
    return (
      <div className={styles.fullPageMessage}>
        <p>Something went wrong loading Customers. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Customers…</p>
      </div>
    );
  }

  return (
    <AppShell
      title="Customer profile"
      subtitle={customerId}
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <Link href="/customers" className={styles.backLink}>
        ← Back to Customers
      </Link>

      {loading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading customer…
        </div>
      )}

      {!loading && loadError && (
        <div className={styles.errorBanner} role="alert">
          {loadError}
        </div>
      )}

      {!loading && !loadError && customer && (
        <div className={styles.summaryCard}>
          <div>
            <div className={styles.summaryLabel}>Name</div>
            <div className={styles.summaryValue}>{customer.full_name}</div>
          </div>
          <div>
            <div className={styles.summaryLabel}>Phone</div>
            <div className={styles.summaryValue}>{customer.phone}</div>
          </div>
          <div>
            <div className={styles.summaryLabel}>Status</div>
            <Pill tone={toneForStatus(customer.status)}>{customer.status}</Pill>
          </div>
          <div>
            <div className={styles.summaryLabel}>Language</div>
            <div className={styles.summaryValue}>{customer.language}</div>
          </div>
          <div>
            <div className={styles.summaryLabel}>Joined</div>
            <div className={styles.summaryValue}>
              {DATE_TIME.format(new Date(customer.created_at))}
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
