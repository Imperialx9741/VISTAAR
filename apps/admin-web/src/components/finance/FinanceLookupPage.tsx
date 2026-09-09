"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import { getAdminProfile } from "@/lib/api/dashboard";
import type { AdminProfile } from "@/lib/api/types";
import styles from "./FinanceLookupPage.module.css";

/** Finance / Wallet (Admin Web §4.7) — there is no search-all-wallets
 * endpoint by design (a wallet is looked up by a known driver_id, not
 * browsed), so this landing screen is a single lookup that navigates
 * straight to that driver's wallet. */
export function FinanceLookupPage() {
  const router = useRouter();
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);
  const [driverId, setDriverId] = useState("");

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

    loadProfileOnMount();
    return () => {
      ignore = true;
    };
  }, []);

  if (profileFailed) {
    return (
      <div className={styles.fullPageMessage}>
        <p>Something went wrong loading Finance / Wallet. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Finance / Wallet…</p>
      </div>
    );
  }

  return (
    <AppShell
      title="Finance / Wallet"
      subtitle="Look up a driver's wallet balance and transaction history"
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <form
        className={styles.searchBar}
        onSubmit={(event) => {
          event.preventDefault();
          if (driverId) router.push(`/finance/${driverId}`);
        }}
      >
        <input
          type="text"
          value={driverId}
          onChange={(event) => setDriverId(event.target.value)}
          placeholder="Driver ID"
          aria-label="Driver ID"
          className={styles.searchInput}
        />
        <button
          type="submit"
          className={styles.searchButton}
          disabled={!driverId}
        >
          View wallet
        </button>
      </form>
    </AppShell>
  );
}
