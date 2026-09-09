"use client";

import { useState } from "react";
import { ApiError, NoSessionError } from "@/lib/api/client";
import type {
  Campaign,
  CampaignRequest,
  DiscountType,
  EligibleScope,
} from "@/lib/api/types";
import styles from "../fare-management/FareRulesPage.module.css";

const VEHICLE_CATEGORIES = ["", "BIKE", "AUTO", "CAB"];

/** `<input type="datetime-local">` wants "YYYY-MM-DDTHH:mm" in local
 * time, not the backend's UTC ISO string — converted both ways here
 * rather than showing a UTC timestamp in a control that looks local. */
function isoToDatetimeLocal(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

function datetimeLocalToIso(value: string): string | null {
  if (!value) return null;
  return new Date(value).toISOString();
}

function parseCustomerIds(raw: string): string[] {
  return raw
    .split(/[\n,]/)
    .map((id) => id.trim())
    .filter((id) => id.length > 0);
}

interface CampaignFormProps {
  initial?: Campaign;
  onSubmit: (body: CampaignRequest) => Promise<void>;
  onCancel: () => void;
  submitLabel: string;
}

/** Create Campaign (POST) and Edit Campaign (PATCH, DRAFT only —
 * enforced server-side) share this exact request shape (ADR-0041), so
 * one form covers both; the caller decides which API function
 * `onSubmit` calls. */
export function CampaignForm({
  initial,
  onSubmit,
  onCancel,
  submitLabel,
}: CampaignFormProps) {
  const [code, setCode] = useState(initial?.code ?? "");
  const [name, setName] = useState(initial?.name ?? "");
  const [vehicleCategory, setVehicleCategory] = useState(
    initial?.vehicle_category ?? "",
  );
  const [discountType, setDiscountType] = useState<DiscountType>(
    initial?.discount_type ?? "PERCENT",
  );
  const [discountValue, setDiscountValue] = useState(
    initial ? String(initial.discount_value) : "",
  );
  const [maxDiscountAmount, setMaxDiscountAmount] = useState(
    initial?.max_discount_amount != null
      ? String(initial.max_discount_amount)
      : "",
  );
  const [minimumFare, setMinimumFare] = useState(
    initial?.minimum_fare != null ? String(initial.minimum_fare) : "",
  );
  const [eligibleScope, setEligibleScope] = useState<EligibleScope>(
    initial?.eligible_scope ?? "ALL",
  );
  const [customerIds, setCustomerIds] = useState("");
  const [perCustomerUseLimit, setPerCustomerUseLimit] = useState(
    initial ? String(initial.per_customer_use_limit) : "1",
  );
  const [totalUsageLimit, setTotalUsageLimit] = useState(
    initial?.total_usage_limit != null ? String(initial.total_usage_limit) : "",
  );
  const [rideCountLimit, setRideCountLimit] = useState(
    initial?.ride_count_limit != null ? String(initial.ride_count_limit) : "",
  );
  const [startsAt, setStartsAt] = useState(
    isoToDatetimeLocal(initial?.starts_at ?? null),
  );
  const [endsAt, setEndsAt] = useState(
    isoToDatetimeLocal(initial?.ends_at ?? null),
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function messageFor(err: unknown): string {
    if (err instanceof NoSessionError) return err.message;
    if (err instanceof ApiError) return err.message;
    return "Couldn't save the campaign. Try again.";
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await onSubmit({
        code: code.trim() || null,
        name: name.trim(),
        vehicle_category: vehicleCategory || null,
        discount_type: discountType,
        discount_value: Number(discountValue),
        max_discount_amount: maxDiscountAmount ? Number(maxDiscountAmount) : null,
        minimum_fare: minimumFare ? Number(minimumFare) : null,
        eligible_scope: eligibleScope,
        per_customer_use_limit: Number(perCustomerUseLimit) || 1,
        total_usage_limit: totalUsageLimit ? Number(totalUsageLimit) : null,
        ride_count_limit: rideCountLimit ? Number(rideCountLimit) : null,
        starts_at: datetimeLocalToIso(startsAt) ?? new Date().toISOString(),
        ends_at: datetimeLocalToIso(endsAt),
        eligible_customer_ids:
          eligibleScope === "SELECTED" ? parseCustomerIds(customerIds) : null,
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
          <label htmlFor="campaign-name" className={styles.label}>
            Name
          </label>
          <input
            id="campaign-name"
            type="text"
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="campaign-code" className={styles.label}>
            Code (blank = auto-applied, no code)
          </label>
          <input
            id="campaign-code"
            type="text"
            value={code}
            onChange={(event) => setCode(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="campaign-category" className={styles.label}>
            Vehicle category
          </label>
          <select
            id="campaign-category"
            value={vehicleCategory}
            onChange={(event) => setVehicleCategory(event.target.value)}
            disabled={isSubmitting}
            className={styles.select}
          >
            {VEHICLE_CATEGORIES.map((value) => (
              <option key={value} value={value}>
                {value === "" ? "All categories" : value}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.field}>
          <label htmlFor="campaign-discount-type" className={styles.label}>
            Discount type
          </label>
          <select
            id="campaign-discount-type"
            value={discountType}
            onChange={(event) =>
              setDiscountType(event.target.value as DiscountType)
            }
            disabled={isSubmitting}
            className={styles.select}
          >
            <option value="PERCENT">PERCENT</option>
            <option value="FLAT">FLAT</option>
          </select>
        </div>
        <div className={styles.field}>
          <label htmlFor="campaign-discount-value" className={styles.label}>
            Discount value{discountType === "PERCENT" ? " (%)" : " (₹)"}
          </label>
          <input
            id="campaign-discount-value"
            type="number"
            min="0"
            step="0.01"
            required
            value={discountValue}
            onChange={(event) => setDiscountValue(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="campaign-max-discount" className={styles.label}>
            Max discount amount (₹, optional)
          </label>
          <input
            id="campaign-max-discount"
            type="number"
            min="0"
            step="0.01"
            value={maxDiscountAmount}
            onChange={(event) => setMaxDiscountAmount(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="campaign-minimum-fare" className={styles.label}>
            Minimum fare (₹, optional)
          </label>
          <input
            id="campaign-minimum-fare"
            type="number"
            min="0"
            step="0.01"
            value={minimumFare}
            onChange={(event) => setMinimumFare(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="campaign-scope" className={styles.label}>
            Eligible scope
          </label>
          <select
            id="campaign-scope"
            value={eligibleScope}
            onChange={(event) =>
              setEligibleScope(event.target.value as EligibleScope)
            }
            disabled={isSubmitting}
            className={styles.select}
          >
            <option value="ALL">ALL</option>
            <option value="SELECTED">SELECTED</option>
          </select>
        </div>
        <div className={styles.field}>
          <label htmlFor="campaign-per-customer" className={styles.label}>
            Per-customer use limit
          </label>
          <input
            id="campaign-per-customer"
            type="number"
            min="1"
            value={perCustomerUseLimit}
            onChange={(event) => setPerCustomerUseLimit(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="campaign-total-limit" className={styles.label}>
            Total usage limit (optional)
          </label>
          <input
            id="campaign-total-limit"
            type="number"
            min="1"
            value={totalUsageLimit}
            onChange={(event) => setTotalUsageLimit(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="campaign-ride-limit" className={styles.label}>
            Ride count limit (optional)
          </label>
          <input
            id="campaign-ride-limit"
            type="number"
            min="1"
            value={rideCountLimit}
            onChange={(event) => setRideCountLimit(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="campaign-starts" className={styles.label}>
            Starts at
          </label>
          <input
            id="campaign-starts"
            type="datetime-local"
            required
            value={startsAt}
            onChange={(event) => setStartsAt(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="campaign-ends" className={styles.label}>
            Ends at (optional)
          </label>
          <input
            id="campaign-ends"
            type="datetime-local"
            value={endsAt}
            onChange={(event) => setEndsAt(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>
      </div>

      {eligibleScope === "SELECTED" && (
        <div className={styles.field}>
          <label htmlFor="campaign-customer-ids" className={styles.label}>
            Eligible customer IDs (one per line or comma-separated)
          </label>
          <textarea
            id="campaign-customer-ids"
            value={customerIds}
            onChange={(event) => setCustomerIds(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
            rows={3}
          />
        </div>
      )}

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
          disabled={isSubmitting || !name.trim() || !discountValue || !startsAt}
        >
          {isSubmitting ? "Saving…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
