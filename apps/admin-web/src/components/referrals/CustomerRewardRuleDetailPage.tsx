"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import {
  getCustomerRewardRule,
  publishCustomerRewardRule,
  submitCustomerRewardRuleForReview,
} from "@/lib/api/referrals";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdminProfile, CustomerRewardRule } from "@/lib/api/types";
import styles from "./RewardRuleDetailPage.module.css";

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

export function CustomerRewardRuleDetailPage({ ruleId }: { ruleId: string }) {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [rule, setRule] = useState<CustomerRewardRule | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [showPublishField, setShowPublishField] = useState(false);
  const [isWorking, setIsWorking] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

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

    async function loadRuleOnMount() {
      try {
        const data = await getCustomerRewardRule(ruleId);
        if (!ignore) setRule(data);
      } catch (error) {
        if (!ignore) setLoadError(errorMessage(error));
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    loadProfileOnMount();
    loadRuleOnMount();
    return () => {
      ignore = true;
    };
  }, [ruleId]);

  async function runAction(
    label: string,
    action: () => Promise<CustomerRewardRule>,
  ) {
    setIsWorking(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const updated = await action();
      setRule(updated);
      setActionSuccess(label);
      setShowPublishField(false);
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setIsWorking(false);
    }
  }

  if (profileFailed) {
    return (
      <div className={styles.fullPageMessage}>
        <p>Something went wrong loading Referrals. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Referrals…</p>
      </div>
    );
  }

  const canSubmitForReview = rule?.status === "DRAFT";
  const canPublish = rule?.status === "DRAFT" || rule?.status === "IN_REVIEW";

  return (
    <AppShell
      title="Customer reward rule"
      subtitle={ruleId}
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <Link href="/referrals/rewards" className={styles.backLink}>
        ← Back to Reward Configuration
      </Link>

      {loading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading rule…
        </div>
      )}

      {!loading && loadError && (
        <div className={styles.errorBanner} role="alert">
          {loadError}
        </div>
      )}

      {!loading && !loadError && rule && (
        <>
          <div className={styles.summaryCard}>
            <div>
              <div className={styles.summaryLabel}>Reward type</div>
              <div className={styles.summaryValue}>{rule.reward_type}</div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Discount</div>
              <div className={styles.summaryValue}>
                {rule.discount_percent}%
              </div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Total uses</div>
              <div className={styles.summaryValue}>{rule.total_uses}</div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Status</div>
              <Pill tone={toneForStatus(rule.status)}>{rule.status}</Pill>
            </div>
            <div>
              <div className={styles.summaryLabel}>Effective from</div>
              <div className={styles.summaryValue}>
                {rule.effective_from
                  ? DATE_TIME.format(new Date(rule.effective_from))
                  : "—"}
              </div>
            </div>
            <div className={styles.summaryActions}>
              {canSubmitForReview && (
                <button
                  type="button"
                  className={styles.secondaryButton}
                  disabled={isWorking}
                  onClick={() =>
                    runAction("Submitted for review.", () =>
                      submitCustomerRewardRuleForReview(ruleId),
                    )
                  }
                >
                  Submit for review
                </button>
              )}
              {canPublish && (
                <button
                  type="button"
                  className={styles.primaryButton}
                  disabled={isWorking}
                  onClick={() => setShowPublishField((v) => !v)}
                >
                  Publish
                </button>
              )}
            </div>
          </div>

          {showPublishField && (
            <div className={styles.reasonRow}>
              <input
                type="datetime-local"
                value={effectiveFrom}
                onChange={(event) => setEffectiveFrom(event.target.value)}
                className={styles.reasonInput}
                aria-label="Effective from (leave blank for now)"
              />
              <button
                type="button"
                className={styles.primaryButton}
                disabled={isWorking}
                onClick={() =>
                  runAction("Rule published.", () =>
                    publishCustomerRewardRule(
                      ruleId,
                      effectiveFrom
                        ? new Date(effectiveFrom).toISOString()
                        : undefined,
                    ),
                  )
                }
              >
                Confirm publish
              </button>
            </div>
          )}

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
        </>
      )}
    </AppShell>
  );
}
