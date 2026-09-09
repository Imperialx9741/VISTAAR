"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { CampaignForm } from "./CampaignForm";
import { getAdminProfile } from "@/lib/api/dashboard";
import {
  activateCampaign,
  bulkAddEligibleCustomers,
  endCampaign,
  getCampaign,
  pauseCampaign,
  updateCampaign,
} from "@/lib/api/campaigns";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type {
  AdminProfile,
  BulkEligibleCustomersResult,
  Campaign,
  CampaignRequest,
} from "@/lib/api/types";
import styles from "./CampaignDetailPage.module.css";

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

export function CampaignDetailPage({ campaignId }: { campaignId: string }) {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [isEditing, setIsEditing] = useState(false);
  const [isWorking, setIsWorking] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadResult, setUploadResult] =
    useState<BulkEligibleCustomersResult | null>(null);

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

    async function loadCampaignOnMount() {
      try {
        const data = await getCampaign(campaignId);
        if (!ignore) setCampaign(data);
      } catch (error) {
        if (!ignore) setLoadError(errorMessage(error));
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    loadProfileOnMount();
    loadCampaignOnMount();
    return () => {
      ignore = true;
    };
  }, [campaignId]);

  async function handleEdit(body: CampaignRequest) {
    const updated = await updateCampaign(campaignId, body);
    setCampaign(updated);
    setIsEditing(false);
    setActionSuccess("Campaign updated.");
  }

  async function handleCsvUpload() {
    if (!csvFile) return;
    setIsUploading(true);
    setUploadError(null);
    setUploadResult(null);
    try {
      const result = await bulkAddEligibleCustomers(campaignId, csvFile);
      setUploadResult(result);
      setCsvFile(null);
    } catch (error) {
      setUploadError(errorMessage(error));
    } finally {
      setIsUploading(false);
    }
  }

  async function runAction(label: string, action: () => Promise<Campaign>) {
    setIsWorking(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const updated = await action();
      setCampaign(updated);
      setActionSuccess(label);
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setIsWorking(false);
    }
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

  const canEdit = campaign?.status === "DRAFT";
  const canActivate =
    campaign?.status === "DRAFT" || campaign?.status === "PAUSED";
  const canPause = campaign?.status === "ACTIVE";
  const canEnd = campaign != null && campaign.status !== "ENDED";

  return (
    <AppShell
      title="Campaign"
      subtitle={campaignId}
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <Link href="/offers-coupons" className={styles.backLink}>
        ← Back to Offers/Coupons
      </Link>

      {loading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading campaign…
        </div>
      )}

      {!loading && loadError && (
        <div className={styles.errorBanner} role="alert">
          {loadError}
        </div>
      )}

      {!loading && !loadError && campaign && !isEditing && (
        <>
          <div className={styles.summaryCard}>
            <div>
              <div className={styles.summaryLabel}>Name</div>
              <div className={styles.summaryValue}>{campaign.name}</div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Code</div>
              <div className={styles.summaryValue}>
                {campaign.code ?? "— (auto-applied)"}
              </div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Category</div>
              <div className={styles.summaryValue}>
                {campaign.vehicle_category ?? "All"}
              </div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Discount</div>
              <div className={styles.summaryValue}>
                {campaign.discount_type === "PERCENT"
                  ? `${campaign.discount_value}%`
                  : `₹${campaign.discount_value}`}
                {campaign.max_discount_amount != null &&
                  ` (max ₹${campaign.max_discount_amount})`}
              </div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Status</div>
              <Pill tone={toneForStatus(campaign.status)}>
                {campaign.status}
              </Pill>
            </div>
            <div>
              <div className={styles.summaryLabel}>Window</div>
              <div className={styles.summaryValue}>
                {DATE_TIME.format(new Date(campaign.starts_at))} –{" "}
                {campaign.ends_at
                  ? DATE_TIME.format(new Date(campaign.ends_at))
                  : "no end"}
              </div>
            </div>
            <div className={styles.summaryActions}>
              {canEdit && (
                <button
                  type="button"
                  className={styles.secondaryButton}
                  disabled={isWorking}
                  onClick={() => setIsEditing(true)}
                >
                  Edit
                </button>
              )}
              {canActivate && (
                <button
                  type="button"
                  className={styles.primaryButton}
                  disabled={isWorking}
                  onClick={() =>
                    runAction("Campaign activated.", () =>
                      activateCampaign(campaignId),
                    )
                  }
                >
                  Activate
                </button>
              )}
              {canPause && (
                <button
                  type="button"
                  className={styles.secondaryButton}
                  disabled={isWorking}
                  onClick={() =>
                    runAction("Campaign paused.", () =>
                      pauseCampaign(campaignId),
                    )
                  }
                >
                  Pause
                </button>
              )}
              {canEnd && (
                <button
                  type="button"
                  className={styles.dangerButton}
                  disabled={isWorking}
                  onClick={() =>
                    runAction("Campaign ended.", () => endCampaign(campaignId))
                  }
                >
                  End
                </button>
              )}
            </div>
          </div>

          {actionError && (
            <div className={styles.errorBanner} role="alert">
              {actionError}
            </div>
          )}
          {actionSuccess && (
            <div className={styles.successBanner} role="status">
              {actionSuccess}
            </div>
          )}

          {campaign.status === "DRAFT" &&
            campaign.eligible_scope === "SELECTED" && (
              <>
                <div className={styles.sectionLabel}>
                  Bulk-add eligible customers (CSV)
                </div>
                <div className={styles.panel}>
                  <div className={styles.reasonRow}>
                    <input
                      type="file"
                      accept=".csv,text/csv"
                      aria-label="CSV file"
                      disabled={isUploading}
                      onChange={(event) =>
                        setCsvFile(event.target.files?.[0] ?? null)
                      }
                    />
                    <button
                      type="button"
                      className={styles.primaryButton}
                      disabled={isUploading || !csvFile}
                      onClick={handleCsvUpload}
                    >
                      {isUploading ? "Uploading…" : "Upload"}
                    </button>
                  </div>
                  <p className={styles.emptyState}>
                    One column, header <code>phone</code>, one Indian phone
                    number per row. Additive — customers already eligible
                    are left untouched, not replaced.
                  </p>

                  {uploadError && (
                    <div className={styles.errorBanner} role="alert">
                      {uploadError}
                    </div>
                  )}

                  {uploadResult && (
                    <div className={styles.successBanner} role="status">
                      Added {uploadResult.added}, already eligible{" "}
                      {uploadResult.already_eligible}
                      {uploadResult.unmatched.length > 0 &&
                        `, ${uploadResult.unmatched.length} unmatched.`}
                    </div>
                  )}

                  {uploadResult && uploadResult.unmatched.length > 0 && (
                    <table className={styles.table}>
                      <thead>
                        <tr>
                          <th>Row</th>
                          <th>Phone</th>
                          <th>Reason</th>
                        </tr>
                      </thead>
                      <tbody>
                        {uploadResult.unmatched.map((row) => (
                          <tr key={row.row}>
                            <td>{row.row}</td>
                            <td>{row.phone}</td>
                            <td>{row.reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </>
            )}
        </>
      )}

      {!loading && !loadError && campaign && isEditing && (
        <div className={styles.panel}>
          <CampaignForm
            initial={campaign}
            submitLabel="Save changes"
            onSubmit={handleEdit}
            onCancel={() => setIsEditing(false)}
          />
        </div>
      )}
    </AppShell>
  );
}
