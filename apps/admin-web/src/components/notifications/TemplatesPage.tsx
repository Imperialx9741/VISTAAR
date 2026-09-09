"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { CreateTemplateForm } from "./CreateTemplateForm";
import { getAdminProfile } from "@/lib/api/dashboard";
import { createTemplate, listTemplates } from "@/lib/api/notifications";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type {
  AdminProfile,
  CreateTemplateRequest,
  NotificationTemplate,
} from "@/lib/api/types";
import styles from "./TemplatesPage.module.css";

const PAGE_SIZE = 20;
const STATUSES = ["", "DRAFT", "PUBLISHED", "ARCHIVED"];

function errorMessage(error: unknown): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) {
    if (error.code === "FORBIDDEN") {
      return "Your admin account does not have access to Notifications.";
    }
    return error.message;
  }
  return "Couldn't load templates. Try again.";
}

interface ListState {
  templates: NotificationTemplate[];
  totalPages: number;
  page: number;
}

export function TemplatesPage() {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [status, setStatus] = useState("");
  const [list, setList] = useState<ListState | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [isCreating, setIsCreating] = useState(false);
  const [createdNotice, setCreatedNotice] = useState<string | null>(null);

  const loadList = useCallback(async (searchStatus: string, page: number) => {
    setListLoading(true);
    setListError(null);
    try {
      const result = await listTemplates("", "", searchStatus, page, PAGE_SIZE);
      setList({
        templates: result.items,
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
        const result = await listTemplates("", "", "", 1, PAGE_SIZE);
        if (ignore) return;
        setList({
          templates: result.items,
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

  async function handleCreate(body: CreateTemplateRequest) {
    const created = await createTemplate(body);
    setIsCreating(false);
    setCreatedNotice(
      `Created ${created.template_key} (${created.channel}) v${created.version}, DRAFT.`,
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
      title="Notification Templates"
      subtitle="Draft and publish per-channel message copy"
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <div className={styles.headerRow}>
        <Link href="/notifications" className={styles.viewLink}>
          ← Delivery history
        </Link>
        {!isCreating && (
          <button
            type="button"
            className={styles.primaryButton}
            onClick={() => {
              setCreatedNotice(null);
              setIsCreating(true);
            }}
          >
            + Create template
          </button>
        )}
      </div>

      {createdNotice && (
        <div className={styles.successBanner} role="status">
          {createdNotice}
        </div>
      )}

      {isCreating && (
        <div className={styles.panel}>
          <CreateTemplateForm
            onCreate={handleCreate}
            onCancel={() => setIsCreating(false)}
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
          Loading templates…
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
                <th>Template key</th>
                <th>Channel</th>
                <th>Version</th>
                <th>Status</th>
                <th aria-hidden="true" />
              </tr>
            </thead>
            <tbody>
              {list.templates.length === 0 && (
                <tr>
                  <td colSpan={5} className={styles.emptyCell}>
                    No templates found.
                  </td>
                </tr>
              )}
              {list.templates.map((template) => (
                <tr key={template.template_id}>
                  <td>{template.template_key}</td>
                  <td>{template.channel}</td>
                  <td>{template.version}</td>
                  <td>
                    <Pill tone={toneForStatus(template.status)}>
                      {template.status}
                    </Pill>
                  </td>
                  <td className={styles.actionCell}>
                    <Link
                      href={`/notifications/templates/${template.template_id}`}
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
