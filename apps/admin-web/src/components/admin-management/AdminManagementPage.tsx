"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { CreateAdminForm } from "./CreateAdminForm";
import { getAdminProfile } from "@/lib/api/dashboard";
import { createAdmin, listAdmins } from "@/lib/api/admin-management";
import { ApiError, NoSessionError } from "@/lib/api/client";
import type {
  AdminAccount,
  AdminPermission,
  AdminProfile,
} from "@/lib/api/types";
import styles from "./AdminManagementPage.module.css";

const PAGE_SIZE = 20;

const DATE = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

interface ListState {
  admins: AdminAccount[];
  totalPages: number;
  page: number;
}

function listErrorMessage(error: unknown): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) {
    if (error.code === "FORBIDDEN") {
      return "Your admin account does not have access to Admin Management.";
    }
    return error.message;
  }
  return "Couldn't load employee admins. Try again.";
}

export function AdminManagementPage() {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [list, setList] = useState<ListState | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [isCreating, setIsCreating] = useState(false);
  const [createdNotice, setCreatedNotice] = useState<string | null>(null);

  const loadList = useCallback(async (page: number) => {
    setListLoading(true);
    setListError(null);
    try {
      const result = await listAdmins(page, PAGE_SIZE);
      setList({
        admins: result.items,
        totalPages: Math.max(1, result.pagination.total_pages),
        page: result.pagination.page,
      });
    } catch (error) {
      setListError(listErrorMessage(error));
    } finally {
      setListLoading(false);
    }
  }, []);

  // Initial load — two independent inline async IIFEs (the React docs'
  // own "Fetching data" pattern, same precedent as DashboardPage's own
  // loadOnMount), not calls to the loadList callback above: setState
  // reached synchronously (before any await) from an effect body is what
  // react-hooks/set-state-in-effect flags, so neither IIFE below touches
  // setState until after its own await — listLoading/listError's useState
  // initial values already cover the "loading, no error yet" starting
  // point, so nothing needs to be (re)set before that.
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
        const result = await listAdmins(1, PAGE_SIZE);
        if (ignore) return;
        setList({
          admins: result.items,
          totalPages: Math.max(1, result.pagination.total_pages),
          page: result.pagination.page,
        });
      } catch (error) {
        if (!ignore) setListError(listErrorMessage(error));
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

  async function handleCreate(phone: string, permissions: AdminPermission[]) {
    const created = await createAdmin(phone, permissions);
    setIsCreating(false);
    setCreatedNotice(
      `Created admin for ${phone} (ID ${created.admin_id}) with ` +
        `${created.permissions.length} module grant` +
        `${created.permissions.length === 1 ? "" : "s"}.`,
    );
    await loadList(1);
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

  return (
    <AppShell
      title="Admin Management"
      subtitle="Create and manage employee admin accounts and their module access"
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <div className={styles.headerRow}>
        <div className={styles.sectionLabel}>Employee admins</div>
        {!isCreating && (
          <button
            type="button"
            className={styles.primaryButton}
            onClick={() => {
              setCreatedNotice(null);
              setIsCreating(true);
            }}
          >
            + Create admin
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
          <CreateAdminForm
            onCreate={handleCreate}
            onCancel={() => setIsCreating(false)}
          />
        </div>
      )}

      {listLoading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading employee admins…
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
                <th>Admin ID</th>
                <th>Role</th>
                <th>Status</th>
                <th>Created</th>
                <th aria-hidden="true" />
              </tr>
            </thead>
            <tbody>
              {list.admins.length === 0 && (
                <tr>
                  <td colSpan={5} className={styles.emptyCell}>
                    No employee admins yet.
                  </td>
                </tr>
              )}
              {list.admins.map((admin) => (
                <tr key={admin.admin_id}>
                  <td className={styles.idCell}>{admin.admin_id}</td>
                  <td>
                    <Pill tone={admin.role === "SUPER_ADMIN" ? "gold" : "neutral"}>
                      {admin.role}
                    </Pill>
                  </td>
                  <td>
                    <Pill tone={admin.status === "ACTIVE" ? "success" : "danger"}>
                      {admin.status}
                    </Pill>
                  </td>
                  <td>{DATE.format(new Date(admin.created_at))}</td>
                  <td className={styles.actionCell}>
                    <Link
                      href={`/admin-management/${admin.admin_id}`}
                      className={styles.viewLink}
                    >
                      View / edit
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
              onClick={() => loadList(list.page - 1)}
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
              onClick={() => loadList(list.page + 1)}
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
