"use client";

import { useState, useSyncExternalStore } from "react";
import { logoutAdmin } from "@/lib/api/auth";
import { clearAdminSession, getAdminToken } from "@/lib/api/session";
import styles from "./TopBar.module.css";

// useSyncExternalStore, not useEffect+setState — the React-recommended
// way to read a value that only exists client-side (localStorage)
// without a hydration mismatch: getServerSnapshot below is what both
// the server render and the client's pre-hydration render use (always
// `false`, since there is no localStorage on the server), and
// getSnapshot is what the client reads afterward. `subscribe` listens
// for the `storage` event, which only fires for changes made in
// *another* tab/window — this tab's own sign-out already does a full
// navigation (see handleSignOut below), which reloads this component
// and reads a fresh snapshot on its own, so this listener is a real
// correctness improvement for a multi-tab admin, not load-bearing for
// the same-tab flow.
function subscribeToStorage(onChange: () => void) {
  window.addEventListener("storage", onChange);
  return () => window.removeEventListener("storage", onChange);
}

function getHasSessionSnapshot() {
  return getAdminToken() !== null;
}

function getHasSessionServerSnapshot() {
  return false;
}

interface TopBarProps {
  title: string;
  subtitle?: string;
  adminRole: string;
  adminInitials: string;
}

export function TopBar({
  title,
  subtitle,
  adminRole,
  adminInitials,
}: TopBarProps) {
  const [isSigningOut, setIsSigningOut] = useState(false);
  const hasSession = useSyncExternalStore(
    subscribeToStorage,
    getHasSessionSnapshot,
    getHasSessionServerSnapshot,
  );

  async function handleSignOut() {
    setIsSigningOut(true);
    try {
      await logoutAdmin();
    } catch {
      // Best-effort — the local session is cleared below regardless
      // (see logoutAdmin's own doc comment).
    }
    clearAdminSession();
    // A full navigation (not next/navigation's client-side router) —
    // deliberate for an auth boundary: it guarantees every component's
    // in-memory state resets along with the session, rather than
    // leaving some still-mounted component holding onto data fetched
    // under the old session. Also sidesteps needing a Next.js router
    // context in this component at all, which the existing test suite
    // (46 files, each already mocking `next/navigation` with only
    // `usePathname`) would otherwise all need updating for.
    window.location.href = "/login";
  }

  return (
    <header className={styles.topbar}>
      <div>
        <h1 className={styles.title}>{title}</h1>
        {subtitle && <div className={styles.subtitle}>{subtitle}</div>}
      </div>
      <div className={styles.adminChip}>
        <div className={styles.avatar} aria-hidden="true">
          {adminInitials}
        </div>
        <div className={styles.roleLabel}>
          {adminRole === "SUPER_ADMIN" ? "Super Admin" : "Admin"}
        </div>
        {hasSession ? (
          <button
            type="button"
            className={styles.sessionButton}
            onClick={handleSignOut}
            disabled={isSigningOut}
          >
            {isSigningOut ? "Signing out…" : "Sign out"}
          </button>
        ) : (
          <a href="/login" className={styles.sessionButton}>
            Sign in
          </a>
        )}
      </div>
    </header>
  );
}
