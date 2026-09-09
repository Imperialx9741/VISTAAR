"use client";

import { useState } from "react";
import { ApiError, NoSessionError } from "@/lib/api/client";
import type { CreatePlatformFeeRuleRequest, VehicleCategory } from "@/lib/api/types";
import styles from "./PlatformFeeRulesPage.module.css";

const CATEGORIES: VehicleCategory[] = ["BIKE", "AUTO", "CAB"];

interface CreatePlatformFeeRuleFormProps {
  onCreate: (body: CreatePlatformFeeRuleRequest) => Promise<void>;
  onCancel: () => void;
}

function messageFor(error: unknown): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) return error.message;
  return "Couldn't create the platform fee rule. Try again.";
}

/** Create Draft Platform Fee Rule (ADR-0045). Always starts DRAFT —
 * Publish is the only action that sets effective_from, so nothing here
 * asks for it. */
export function CreatePlatformFeeRuleForm({
  onCreate,
  onCancel,
}: CreatePlatformFeeRuleFormProps) {
  const [vehicleCategory, setVehicleCategory] =
    useState<VehicleCategory>("CAB");
  const [feeAmount, setFeeAmount] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await onCreate({
        vehicle_category: vehicleCategory,
        fee_amount: Number(feeAmount),
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
          <label htmlFor="platform-fee-vehicle-category" className={styles.label}>
            Vehicle category
          </label>
          <select
            id="platform-fee-vehicle-category"
            value={vehicleCategory}
            onChange={(event) =>
              setVehicleCategory(event.target.value as VehicleCategory)
            }
            disabled={isSubmitting}
            className={styles.select}
          >
            {CATEGORIES.map((category) => (
              <option key={category} value={category}>
                {category}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.field}>
          <label htmlFor="platform-fee-amount" className={styles.label}>
            Fee amount (₹)
          </label>
          <input
            id="platform-fee-amount"
            type="number"
            min="0"
            step="0.01"
            required
            value={feeAmount}
            onChange={(event) => setFeeAmount(event.target.value)}
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
          disabled={isSubmitting || !feeAmount}
        >
          {isSubmitting ? "Creating…" : "Create draft"}
        </button>
      </div>
    </form>
  );
}
