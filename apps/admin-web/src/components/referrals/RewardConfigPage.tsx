"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import {
  createCustomerRewardRule,
  createDriverBonusRule,
  listCustomerRewardRules,
  listDriverBonusRules,
} from "@/lib/api/referrals";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type {
  AdminProfile,
  CustomerRewardRule,
  CustomerRewardType,
  DriverBonusRule,
} from "@/lib/api/types";
import styles from "./RewardConfigPage.module.css";

const PAGE_SIZE = 20;
const STATUSES = ["", "DRAFT", "IN_REVIEW", "PUBLISHED"];
const REWARD_TYPES: CustomerRewardType[] = [
  "REFERRAL_REFERRED",
  "REFERRAL_REFERRING",
];

function errorMessage(error: unknown, module: string): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) {
    if (error.code === "FORBIDDEN") {
      return `Your admin account does not have access to ${module}.`;
    }
    return error.message;
  }
  return `Couldn't load ${module.toLowerCase()}. Try again.`;
}

function DriverBonusSection() {
  const [status, setStatus] = useState("");
  const [rules, setRules] = useState<DriverBonusRule[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [referredAmount, setReferredAmount] = useState("");
  const [referrerAmount, setReferrerAmount] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadList = useCallback(async (searchStatus: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await listDriverBonusRules(searchStatus, 1, PAGE_SIZE);
      setRules(result.items);
    } catch (err) {
      setError(errorMessage(err, "Referrals"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let ignore = false;
    async function loadOnMount() {
      try {
        const result = await listDriverBonusRules("", 1, PAGE_SIZE);
        if (!ignore) setRules(result.items);
      } catch (err) {
        if (!ignore) setError(errorMessage(err, "Referrals"));
      } finally {
        if (!ignore) setLoading(false);
      }
    }
    loadOnMount();
    return () => {
      ignore = true;
    };
  }, []);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    setCreateError(null);
    setIsSubmitting(true);
    try {
      const created = await createDriverBonusRule(
        Number(referredAmount),
        Number(referrerAmount),
      );
      setIsCreating(false);
      setReferredAmount("");
      setReferrerAmount("");
      setNotice(`Created a DRAFT driver-bonus rule (ID ${created.rule_id}).`);
      await loadList(status);
    } catch (err) {
      setCreateError(errorMessage(err, "Referrals"));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className={styles.moduleSection}>
      <div className={styles.headerRow}>
        <div>
          <div className={styles.moduleHeading}>Driver Referral Bonus</div>
          <div className={styles.moduleSubtitle}>
            One global policy — the currently PUBLISHED row applies to every
            driver referral.
          </div>
        </div>
        {!isCreating && (
          <button
            type="button"
            className={styles.primaryButton}
            onClick={() => {
              setNotice(null);
              setIsCreating(true);
            }}
          >
            + Create draft
          </button>
        )}
      </div>

      {notice && (
        <div className={styles.successBanner} role="status">
          {notice}
        </div>
      )}

      {isCreating && (
        <div className={styles.panel}>
          <form className={styles.form} onSubmit={handleCreate}>
            <div className={styles.formGrid}>
              <div className={styles.field}>
                <label htmlFor="driver-bonus-referred" className={styles.label}>
                  Referred driver amount (₹)
                </label>
                <input
                  id="driver-bonus-referred"
                  type="number"
                  min="0"
                  step="0.01"
                  required
                  value={referredAmount}
                  onChange={(event) => setReferredAmount(event.target.value)}
                  disabled={isSubmitting}
                  className={styles.input}
                />
              </div>
              <div className={styles.field}>
                <label htmlFor="driver-bonus-referrer" className={styles.label}>
                  Referrer driver amount (₹)
                </label>
                <input
                  id="driver-bonus-referrer"
                  type="number"
                  min="0"
                  step="0.01"
                  required
                  value={referrerAmount}
                  onChange={(event) => setReferrerAmount(event.target.value)}
                  disabled={isSubmitting}
                  className={styles.input}
                />
              </div>
            </div>
            {createError && (
              <div className={styles.errorBanner} role="alert">
                {createError}
              </div>
            )}
            <div className={styles.actions}>
              <button
                type="button"
                className={styles.secondaryButton}
                onClick={() => setIsCreating(false)}
                disabled={isSubmitting}
              >
                Cancel
              </button>
              <button
                type="submit"
                className={styles.primaryButton}
                disabled={isSubmitting || !referredAmount || !referrerAmount}
              >
                {isSubmitting ? "Creating…" : "Create draft"}
              </button>
            </div>
          </form>
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
            void loadList(event.target.value);
          }}
          className={styles.statusSelect}
          aria-label="Filter driver-bonus rules by status"
        >
          {STATUSES.map((value) => (
            <option key={value} value={value}>
              {value === "" ? "Any status" : value}
            </option>
          ))}
        </select>
      </form>

      {loading && <div className={styles.stateMessage}>Loading…</div>}
      {!loading && error && (
        <div className={styles.errorBanner} role="alert">
          {error}
        </div>
      )}
      {!loading && !error && rules && (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Referred (₹)</th>
              <th>Referrer (₹)</th>
              <th>Status</th>
              <th aria-hidden="true" />
            </tr>
          </thead>
          <tbody>
            {rules.length === 0 && (
              <tr>
                <td colSpan={4} className={styles.emptyCell}>
                  No driver-bonus rules yet.
                </td>
              </tr>
            )}
            {rules.map((rule) => (
              <tr key={rule.rule_id}>
                <td>{rule.referred_amount}</td>
                <td>{rule.referrer_amount}</td>
                <td>
                  <Pill tone={toneForStatus(rule.status)}>{rule.status}</Pill>
                </td>
                <td className={styles.actionCell}>
                  <Link
                    href={`/referrals/rewards/driver-bonus/${rule.rule_id}`}
                    className={styles.viewLink}
                  >
                    View
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function CustomerRewardsSection() {
  const [rewardType, setRewardType] = useState("");
  const [status, setStatus] = useState("");
  const [rules, setRules] = useState<CustomerRewardRule[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [formRewardType, setFormRewardType] =
    useState<CustomerRewardType>("REFERRAL_REFERRED");
  const [discountPercent, setDiscountPercent] = useState("");
  const [totalUses, setTotalUses] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadList = useCallback(
    async (searchRewardType: string, searchStatus: string) => {
      setLoading(true);
      setError(null);
      try {
        const result = await listCustomerRewardRules(
          searchRewardType,
          searchStatus,
          1,
          PAGE_SIZE,
        );
        setRules(result.items);
      } catch (err) {
        setError(errorMessage(err, "Referrals"));
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    let ignore = false;
    async function loadOnMount() {
      try {
        const result = await listCustomerRewardRules("", "", 1, PAGE_SIZE);
        if (!ignore) setRules(result.items);
      } catch (err) {
        if (!ignore) setError(errorMessage(err, "Referrals"));
      } finally {
        if (!ignore) setLoading(false);
      }
    }
    loadOnMount();
    return () => {
      ignore = true;
    };
  }, []);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    setCreateError(null);
    setIsSubmitting(true);
    try {
      const created = await createCustomerRewardRule(
        formRewardType,
        Number(discountPercent),
        Number(totalUses),
      );
      setIsCreating(false);
      setDiscountPercent("");
      setTotalUses("");
      setNotice(
        `Created a DRAFT ${created.reward_type} rule (ID ${created.rule_id}).`,
      );
      await loadList(rewardType, status);
    } catch (err) {
      setCreateError(errorMessage(err, "Referrals"));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className={styles.moduleSection}>
      <div className={styles.headerRow}>
        <div>
          <div className={styles.moduleHeading}>Customer Referral Rewards</div>
          <div className={styles.moduleSubtitle}>
            One policy per reward type — REFERRAL_REFERRED (the new
            customer) and REFERRAL_REFERRING (the one who referred them).
          </div>
        </div>
        {!isCreating && (
          <button
            type="button"
            className={styles.primaryButton}
            onClick={() => {
              setNotice(null);
              setIsCreating(true);
            }}
          >
            + Create draft
          </button>
        )}
      </div>

      {notice && (
        <div className={styles.successBanner} role="status">
          {notice}
        </div>
      )}

      {isCreating && (
        <div className={styles.panel}>
          <form className={styles.form} onSubmit={handleCreate}>
            <div className={styles.formGrid}>
              <div className={styles.field}>
                <label htmlFor="customer-reward-type" className={styles.label}>
                  Reward type
                </label>
                <select
                  id="customer-reward-type"
                  value={formRewardType}
                  onChange={(event) =>
                    setFormRewardType(
                      event.target.value as CustomerRewardType,
                    )
                  }
                  disabled={isSubmitting}
                  className={styles.select}
                >
                  {REWARD_TYPES.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </div>
              <div className={styles.field}>
                <label htmlFor="customer-reward-discount" className={styles.label}>
                  Discount (%)
                </label>
                <input
                  id="customer-reward-discount"
                  type="number"
                  min="0"
                  max="100"
                  step="0.01"
                  required
                  value={discountPercent}
                  onChange={(event) => setDiscountPercent(event.target.value)}
                  disabled={isSubmitting}
                  className={styles.input}
                />
              </div>
              <div className={styles.field}>
                <label htmlFor="customer-reward-uses" className={styles.label}>
                  Total uses
                </label>
                <input
                  id="customer-reward-uses"
                  type="number"
                  min="1"
                  required
                  value={totalUses}
                  onChange={(event) => setTotalUses(event.target.value)}
                  disabled={isSubmitting}
                  className={styles.input}
                />
              </div>
            </div>
            {createError && (
              <div className={styles.errorBanner} role="alert">
                {createError}
              </div>
            )}
            <div className={styles.actions}>
              <button
                type="button"
                className={styles.secondaryButton}
                onClick={() => setIsCreating(false)}
                disabled={isSubmitting}
              >
                Cancel
              </button>
              <button
                type="submit"
                className={styles.primaryButton}
                disabled={isSubmitting || !discountPercent || !totalUses}
              >
                {isSubmitting ? "Creating…" : "Create draft"}
              </button>
            </div>
          </form>
        </div>
      )}

      <form
        className={styles.searchBar}
        onSubmit={(event) => event.preventDefault()}
      >
        <select
          value={rewardType}
          onChange={(event) => {
            setRewardType(event.target.value);
            void loadList(event.target.value, status);
          }}
          className={styles.statusSelect}
          aria-label="Filter by reward type"
        >
          <option value="">Any reward type</option>
          {REWARD_TYPES.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
        <select
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            void loadList(rewardType, event.target.value);
          }}
          className={styles.statusSelect}
          aria-label="Filter customer-reward rules by status"
        >
          {STATUSES.map((value) => (
            <option key={value} value={value}>
              {value === "" ? "Any status" : value}
            </option>
          ))}
        </select>
      </form>

      {loading && <div className={styles.stateMessage}>Loading…</div>}
      {!loading && error && (
        <div className={styles.errorBanner} role="alert">
          {error}
        </div>
      )}
      {!loading && !error && rules && (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Reward type</th>
              <th>Discount</th>
              <th>Total uses</th>
              <th>Status</th>
              <th aria-hidden="true" />
            </tr>
          </thead>
          <tbody>
            {rules.length === 0 && (
              <tr>
                <td colSpan={5} className={styles.emptyCell}>
                  No customer-reward rules yet.
                </td>
              </tr>
            )}
            {rules.map((rule) => (
              <tr key={rule.rule_id}>
                <td>{rule.reward_type}</td>
                <td>{rule.discount_percent}%</td>
                <td>{rule.total_uses}</td>
                <td>
                  <Pill tone={toneForStatus(rule.status)}>{rule.status}</Pill>
                </td>
                <td className={styles.actionCell}>
                  <Link
                    href={`/referrals/rewards/customer/${rule.rule_id}`}
                    className={styles.viewLink}
                  >
                    View
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

export function RewardConfigPage() {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

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

  return (
    <AppShell
      title="Referral Reward Configuration"
      subtitle="Two independent, versioned reward policies"
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <Link href="/referrals" className={styles.backLink}>
        ← Back to Referrals
      </Link>

      <DriverBonusSection />
      <CustomerRewardsSection />
    </AppShell>
  );
}
