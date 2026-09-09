"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { CampaignForm } from "./CampaignForm";
import { getAdminProfile } from "@/lib/api/dashboard";
import { createCampaign, listCampaigns } from "@/lib/api/campaigns";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdminProfile, Campaign, CampaignRequest } from "@/lib/api/types";
import styles from "./CampaignsPage.module.css";

const PAGE_SIZE = 20;
const STATUSES = ["", "DRAFT", "ACTIVE", "PAUSED", "ENDED"];

function errorMessage(error: unknown): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) {
    if (error.code === "FORBIDDEN") {
      return "Your admin account does not have access to Offers/Coupons.";
    }
    return error.message;
  }
  return "Couldn't load campaigns. Try again.";
}

interface ListState {
  campaigns: Campaign[];
  totalPages: number;
  page: number;
}

export function CampaignsPage() {
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
      const result = await listCampaigns(searchStatus, page, PAGE_SIZE);
      setList({
        campaigns: result.items,
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
        const result = await listCampaigns("", 1, PAGE_SIZE);
        if (ignore) return;
        setList({
          campaigns: result.items,
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

  async function handleCreate(body: CampaignRequest) {
    const created = await createCampaign(body);
    setIsCreating(false);
    setCreatedNotice(
      `Created a DRAFT campaign "${created.name}" (ID ${created.campaign_id}).`,
    );
    await loadList(status, 1);
  }

  if (profileFailed) {
    return (
      <div className={styles.fullPageMessage}>
        <p>Something went wrong loading Offers/Coupons. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Offers/Coupons…</p>
      </div>
    );
  }

  return (
    <AppShell
      title="Offers / Coupons"
      subtitle="Author and manage redeemable campaigns"
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <div className={styles.headerRow}>
        <div className={styles.sectionLabel}>Campaigns</div>
        {!isCreating && (
          <button
            type="button"
            className={styles.primaryButton}
            onClick={() => {
              setCreatedNotice(null);
              setIsCreating(true);
            }}
          >
            + Create campaign
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
          <CampaignForm
            submitLabel="Create draft"
            onSubmit={handleCreate}
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
          Loading campaigns…
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
                <th>Name</th>
                <th>Code</th>
                <th>Category</th>
                <th>Discount</th>
                <th>Status</th>
                <th aria-hidden="true" />
              </tr>
            </thead>
            <tbody>
              {list.campaigns.length === 0 && (
                <tr>
                  <td colSpan={6} className={styles.emptyCell}>
                    No campaigns found.
                  </td>
                </tr>
              )}
              {list.campaigns.map((campaign) => (
                <tr key={campaign.campaign_id}>
                  <td>{campaign.name}</td>
                  <td className={styles.idCell}>{campaign.code ?? "—"}</td>
                  <td>{campaign.vehicle_category ?? "All"}</td>
                  <td>
                    {campaign.discount_type === "PERCENT"
                      ? `${campaign.discount_value}%`
                      : `₹${campaign.discount_value}`}
                  </td>
                  <td>
                    <Pill tone={toneForStatus(campaign.status)}>
                      {campaign.status}
                    </Pill>
                  </td>
                  <td className={styles.actionCell}>
                    <Link
                      href={`/offers-coupons/${campaign.campaign_id}`}
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
