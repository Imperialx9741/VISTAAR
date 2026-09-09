"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { getAdminProfile } from "@/lib/api/dashboard";
import { listSettings, updateSetting } from "@/lib/api/settings";
import { ApiError, NoSessionError } from "@/lib/api/client";
import type { AdminProfile, Setting } from "@/lib/api/types";
import styles from "./SettingsPage.module.css";

const CATEGORIES = [
  "",
  "PROMOTION_DEFAULT",
  "OPERATIONAL_THRESHOLD",
  "FEATURE_FLAG",
  "GENERAL",
];

const DATE_TIME = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

/** Settings is a navigation surface over four already-dedicated,
 * versioned screens (ADR-0048 Decision 1) — never a second place to
 * edit the same data. */
const DEDICATED_SETTINGS_LINKS = [
  {
    label: "Fare settings",
    href: "/fare-management",
    target: "Fare Management",
  },
  {
    label: "Platform fees",
    href: "/fare-management/platform-fee",
    target: "Platform Fee Management",
  },
  {
    label: "Referral settings",
    href: "/referrals/rewards",
    target: "Referral Reward Configuration",
  },
  {
    label: "Notification settings",
    href: "/notifications/templates",
    target: "Notification Templates",
  },
];

function errorMessage(error: unknown): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) {
    if (error.code === "FORBIDDEN") {
      return "Your admin account does not have access to Settings.";
    }
    return error.message;
  }
  return "Couldn't load settings. Try again.";
}

export function SettingsPage() {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [category, setCategory] = useState("");
  const [settings, setSettings] = useState<Setting[] | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [editError, setEditError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [savedNotice, setSavedNotice] = useState<string | null>(null);

  const loadSettings = useCallback(async (searchCategory: string) => {
    setListLoading(true);
    setListError(null);
    try {
      const result = await listSettings(searchCategory);
      setSettings(result);
    } catch (error) {
      setListError(errorMessage(error));
    } finally {
      setListLoading(false);
    }
  }, []);

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

    async function loadSettingsOnMount() {
      try {
        const result = await listSettings("");
        if (!ignore) setSettings(result);
      } catch (error) {
        if (!ignore) setListError(errorMessage(error));
      } finally {
        if (!ignore) setListLoading(false);
      }
    }

    loadProfileOnMount();
    loadSettingsOnMount();
    return () => {
      ignore = true;
    };
  }, []);

  function startEdit(setting: Setting) {
    setSavedNotice(null);
    setEditError(null);
    setEditingKey(setting.key);
    setEditValue(JSON.stringify(setting.value, null, 2));
  }

  async function handleSave(key: string) {
    setEditError(null);
    let parsed: unknown;
    try {
      parsed = JSON.parse(editValue);
    } catch {
      setEditError("That's not valid JSON — check the value and try again.");
      return;
    }
    setIsSaving(true);
    try {
      await updateSetting(key, parsed);
      setEditingKey(null);
      setSavedNotice(`${key} updated.`);
      await loadSettings(category);
    } catch (error) {
      setEditError(errorMessage(error));
    } finally {
      setIsSaving(false);
    }
  }

  if (profileFailed) {
    return (
      <div className={styles.fullPageMessage}>
        <p>Something went wrong loading Settings. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Settings…</p>
      </div>
    );
  }

  return (
    <AppShell
      title="Settings"
      subtitle="Platform configuration — never API keys, passwords, or credentials"
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <div className={styles.sectionLabel}>Already has its own screen</div>
      <div className={styles.linksGrid}>
        {DEDICATED_SETTINGS_LINKS.map((link) => (
          <Link key={link.href} href={link.href} className={styles.linkCard}>
            <div className={styles.linkCardLabel}>{link.label}</div>
            <div className={styles.linkCardTarget}>{link.target} →</div>
          </Link>
        ))}
      </div>

      <div className={styles.headerRow}>
        <div className={styles.sectionLabel}>Platform settings</div>
      </div>

      {savedNotice && (
        <div className={styles.successBanner} role="status">
          {savedNotice}
        </div>
      )}

      <form
        className={styles.searchBar}
        onSubmit={(event) => event.preventDefault()}
      >
        <select
          value={category}
          onChange={(event) => {
            setCategory(event.target.value);
            void loadSettings(event.target.value);
          }}
          className={styles.statusSelect}
          aria-label="Filter by category"
        >
          {CATEGORIES.map((value) => (
            <option key={value} value={value}>
              {value === "" ? "Any category" : value}
            </option>
          ))}
        </select>
      </form>

      {listLoading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading settings…
        </div>
      )}

      {!listLoading && listError && (
        <div className={styles.errorBanner} role="alert">
          {listError}
        </div>
      )}

      {!listLoading && !listError && settings && (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Key</th>
              <th>Description</th>
              <th>Category</th>
              <th>Value</th>
              <th>Updated</th>
              <th aria-hidden="true" />
            </tr>
          </thead>
          <tbody>
            {settings.length === 0 && (
              <tr>
                <td colSpan={6} className={styles.emptyCell}>
                  No settings found.
                </td>
              </tr>
            )}
            {settings.map((setting) => (
              <tr key={setting.key}>
                <td className={styles.idCell}>{setting.key}</td>
                <td>{setting.description}</td>
                <td>
                  <span className={styles.categoryTag}>
                    {setting.category}
                  </span>
                </td>
                <td className={styles.valueCell}>
                  {editingKey === setting.key ? (
                    <>
                      <textarea
                        value={editValue}
                        onChange={(event) => setEditValue(event.target.value)}
                        disabled={isSaving}
                        className={styles.editArea}
                        aria-label={`Value for ${setting.key}`}
                      />
                      {editError && (
                        <div className={styles.errorBanner} role="alert">
                          {editError}
                        </div>
                      )}
                      <div className={styles.editActions}>
                        <button
                          type="button"
                          className={styles.secondaryButton}
                          disabled={isSaving}
                          onClick={() => setEditingKey(null)}
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          className={styles.primaryButton}
                          disabled={isSaving}
                          onClick={() => handleSave(setting.key)}
                        >
                          {isSaving ? "Saving…" : "Save"}
                        </button>
                      </div>
                    </>
                  ) : (
                    JSON.stringify(setting.value)
                  )}
                </td>
                <td>{DATE_TIME.format(new Date(setting.updated_at))}</td>
                <td className={styles.actionCell}>
                  {editingKey !== setting.key && (
                    <button
                      type="button"
                      className={styles.secondaryButton}
                      onClick={() => startEdit(setting)}
                    >
                      Edit
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </AppShell>
  );
}
