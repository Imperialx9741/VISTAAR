"use client";

import { useState } from "react";
import { ApiError, NoSessionError } from "@/lib/api/client";
import type { CreateAdCampaignRequest } from "@/lib/api/types";
import styles from "./CampaignsPage.module.css";

interface CreateCampaignFormProps {
  onCreate: (body: CreateAdCampaignRequest) => Promise<void>;
  onCancel: () => void;
}

function messageFor(error: unknown): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) return error.message;
  return "Couldn't create the campaign. Try again.";
}

/** Create Campaign (ADR-0046). Always starts ACTIVE — no draft/approval
 * gate (ADR-0018 Decision 2, unchanged). driver_share_percent/
 * vistaar_share_percent default to the approved 80/20 split, exposed
 * as-is, not modified ("do not invent additional ad economics"). */
export function CreateCampaignForm({
  onCreate,
  onCancel,
}: CreateCampaignFormProps) {
  const [partnerName, setPartnerName] = useState("");
  const [payoutAmount, setPayoutAmount] = useState("");
  const [driverSharePercent, setDriverSharePercent] = useState("80");
  const [vistaarSharePercent, setVistaarSharePercent] = useState("20");
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await onCreate({
        partner_name: partnerName,
        payout_amount: Number(payoutAmount),
        driver_share_percent: Number(driverSharePercent),
        vistaar_share_percent: Number(vistaarSharePercent),
        starts_at: startsAt ? new Date(startsAt).toISOString() : undefined,
        ends_at: endsAt ? new Date(endsAt).toISOString() : undefined,
      });
    } catch (err) {
      setError(messageFor(err));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <div className={styles.formGrid}>
        <div className={styles.field}>
          <label htmlFor="campaign-partner-name" className={styles.label}>
            Partner name
          </label>
          <input
            id="campaign-partner-name"
            type="text"
            required
            value={partnerName}
            onChange={(event) => setPartnerName(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="campaign-payout-amount" className={styles.label}>
            Payout amount (₹)
          </label>
          <input
            id="campaign-payout-amount"
            type="number"
            min="0"
            step="0.01"
            required
            value={payoutAmount}
            onChange={(event) => setPayoutAmount(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="campaign-driver-share" className={styles.label}>
            Driver share (%)
          </label>
          <input
            id="campaign-driver-share"
            type="number"
            min="0"
            max="100"
            step="0.01"
            value={driverSharePercent}
            onChange={(event) => setDriverSharePercent(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="campaign-vistaar-share" className={styles.label}>
            VISTAAR share (%)
          </label>
          <input
            id="campaign-vistaar-share"
            type="number"
            min="0"
            max="100"
            step="0.01"
            value={vistaarSharePercent}
            onChange={(event) => setVistaarSharePercent(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="campaign-starts-at" className={styles.label}>
            Starts at (optional)
          </label>
          <input
            id="campaign-starts-at"
            type="datetime-local"
            value={startsAt}
            onChange={(event) => setStartsAt(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="campaign-ends-at" className={styles.label}>
            Ends at (optional)
          </label>
          <input
            id="campaign-ends-at"
            type="datetime-local"
            value={endsAt}
            onChange={(event) => setEndsAt(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>
      </div>

      {error && (
        <div className={styles.errorBanner} role="alert">
          {error}
        </div>
      )}

      <div className={styles.actions}>
        <button
          type="button"
          className={styles.secondaryButton}
          onClick={onCancel}
          disabled={isSubmitting}
        >
          Cancel
        </button>
        <button
          type="submit"
          className={styles.primaryButton}
          disabled={isSubmitting || !partnerName || !payoutAmount}
        >
          {isSubmitting ? "Creating…" : "Create campaign"}
        </button>
      </div>
    </form>
  );
}
