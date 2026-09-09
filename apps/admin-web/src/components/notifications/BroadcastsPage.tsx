"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { CreateBroadcastForm } from "./CreateBroadcastForm";
import { getAdminProfile } from "@/lib/api/dashboard";
import { createBroadcast, searchBroadcasts } from "@/lib/api/notifications";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdminProfile, Broadcast, CreateBroadcastRequest } from "@/lib/api/types";
import styles from "./BroadcastsPage.module.css";

const PAGE_SIZE = 20;
const STATUSES = ["", "SCHEDULED", "SENT"];

const DATE_TIME = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

function errorMessage(error: unknown): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) {
    if (error.code === "FORBIDDEN") {
      return "Your admin account does not have access to Notifications.";
    }
    return error.message;
  }
  return "Couldn't load broadcasts. Try again.";
}

interface ListState {
  broadcasts: Broadcast[];
  totalPages: number;
  page: number;
}

export function BroadcastsPage() {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [status, setStatus] = useState("");
  const [list, setList] = useState<ListState | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [isComposing, setIsComposing] = useState(false);
  const [createdNotice, setCreatedNotice] = useState<string | null>(null);

  const loadList = useCallback(async (searchStatus: string, page: number) => {
    setListLoading(true);
    setListError(null);
    try {
      const result = await searchBroadcasts(searchStatus, page, PAGE_SIZE);
      setList({
        broadcasts: result.items,
        totalPages: Math.max(1, result.pagination.total_pages),
        page: result.pagination.page,
      });
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

    async function loadListOnMount() {
      try {
        const result = await searchBroadcasts("", 1, PAGE_SIZE);
        if (ignore) return;
        setList({
          broadcasts: result.items,
          totalPages: Math.max(1, result.pagination.total_pages),
          page: result.pagination.page,
        });
      } catch (error) {
        if (!ignore) setListError(errorMessage(error));
      } finally {
        if (!ignore) setListLoading(false);
      }
    }

    loadProfileOnMount();
    loadListOnMount();
    return () => {
      ignore = true;
    };
  }, []);

  async function handleCreate(body: CreateBroadcastRequest) {
    const created = await createBroadcast(body);
    setIsComposing(false);
    setCreatedNotice(
      created.status === "SENT"
        ? `Sent to ${created.sent_count} recipient${created.sent_count === 1 ? "" : "s"} (${created.failed_count} failed).`
        : "Broadcast scheduled.",
    );
    await loadList(status, 1);
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

  return (
    <AppShell
      title="Broadcasts"
      subtitle="Compose and send a message to an audience"
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <div className={styles.headerRow}>
        <Link href="/notifications" className={styles.viewLink}>
          ← Delivery history
        </Link>
        {!isComposing && (
          <button
            type="button"
            className={styles.primaryButton}
            onClick={() => {
              setCreatedNotice(null);
              setIsComposing(true);
            }}
          >
            + Compose broadcast
          </button>
        )}
      </div>

      {createdNotice && (
        <div className={styles.successBanner} role="status">
          {createdNotice}
        </div>
      )}

      {isComposing && (
        <div className={styles.panel}>
          <CreateBroadcastForm
            onCreate={handleCreate}
            onCancel={() => setIsComposing(false)}
          />
        </div>
      )}

      <form
        className={styles.searchBar}
        onSubmit={(event) => event.preventDefault()}
      >
        <select
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            void loadList(event.target.value, 1);
          }}
          className={styles.statusSelect}
          aria-label="Filter by status"
        >
          {STATUSES.map((value) => (
            <option key={value} value={value}>
              {value === "" ? "Any status" : value}
            </option>
          ))}
        </select>
      </form>

      {listLoading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading broadcasts…
        </div>
      )}

      {!listLoading && listError && (
        <div className={styles.errorBanner} role="alert">
          {listError}
        </div>
      )}

      {!listLoading && !listError && list && (
        <>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Subject / body</th>
                <th>Channel</th>
                <th>Audience</th>
                <th>Status</th>
                <th>Sent / Failed</th>
                <th>Composed</th>
                <th aria-hidden="true" />
              </tr>
            </thead>
            <tbody>
              {list.broadcasts.length === 0 && (
                <tr>
                  <td colSpan={7} className={styles.emptyCell}>
                    No broadcasts found.
                  </td>
                </tr>
              )}
              {list.broadcasts.map((broadcast) => (
                <tr key={broadcast.broadcast_id}>
                  <td>{broadcast.subject ?? broadcast.body.slice(0, 60)}</td>
                  <td>{broadcast.channel}</td>
                  <td>{broadcast.audience_type}</td>
                  <td>
                    <Pill tone={toneForStatus(broadcast.status)}>
                      {broadcast.status}
                    </Pill>
                  </td>
                  <td>
                    {broadcast.status === "SENT"
                      ? `${broadcast.sent_count} / ${broadcast.failed_count}`
                      : "—"}
                  </td>
                  <td>{DATE_TIME.format(new Date(broadcast.created_at))}</td>
                  <td className={styles.actionCell}>
                    <Link
                      href={`/notifications/broadcasts/${broadcast.broadcast_id}`}
                      className={styles.viewLink}
                    >
                      View
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className={styles.pagination}>
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => loadList(status, list.page - 1)}
              disabled={list.page <= 1}
            >
              Previous
            </button>
            <span className={styles.pageIndicator}>
              Page {list.page} of {list.totalPages}
            </span>
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => loadList(status, list.page + 1)}
              disabled={list.page >= list.totalPages}
            >
              Next
            </button>
          </div>
        </>
      )}
    </AppShell>
  );
}
