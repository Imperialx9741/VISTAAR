"use client";

import { useState } from "react";
import { ApiError, NoSessionError } from "@/lib/api/client";
import type { CreateFareRuleRequest, FareRuleVehicleCategory } from "@/lib/api/types";
import styles from "./FareRulesPage.module.css";

const CATEGORIES: FareRuleVehicleCategory[] = [
  "BIKE",
  "AUTO",
  "CAB_ECO",
  "CAB_PREMIUM",
  "CAB_PREMIUM_PLUS",
];

interface CreateFareRuleFormProps {
  onCreate: (body: CreateFareRuleRequest) => Promise<void>;
  onCancel: () => void;
}

function messageFor(error: unknown): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) return error.message;
  return "Couldn't create the fare rule. Try again.";
}

/** Create Draft Fare Rule (ADR-0042). Always starts DRAFT — Publish is
 * the only action that sets effective_from, so nothing here asks for
 * it. */
export function CreateFareRuleForm({
  onCreate,
  onCancel,
}: CreateFareRuleFormProps) {
  const [vehicleCategory, setVehicleCategory] =
    useState<FareRuleVehicleCategory>("CAB_ECO");
  const [baseFare, setBaseFare] = useState("");
  const [perKm, setPerKm] = useState("");
  const [perMinute, setPerMinute] = useState("0");
  const [waitingPerMinute, setWaitingPerMinute] = useState("0");
  const [minimumFare, setMinimumFare] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await onCreate({
        vehicle_category: vehicleCategory,
        base_fare: Number(baseFare),
        per_km: Number(perKm),
        per_minute: Number(perMinute),
        waiting_per_minute: Number(waitingPerMinute),
        minimum_fare: Number(minimumFare),
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
          <label htmlFor="fare-vehicle-category" className={styles.label}>
            Vehicle category
          </label>
          <select
            id="fare-vehicle-category"
            value={vehicleCategory}
            onChange={(event) =>
              setVehicleCategory(
                event.target.value as FareRuleVehicleCategory,
              )
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
          <label htmlFor="fare-base" className={styles.label}>
            Base fare (₹)
          </label>
          <input
            id="fare-base"
            type="number"
            min="0"
            step="0.01"
            required
            value={baseFare}
            onChange={(event) => setBaseFare(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="fare-per-km" className={styles.label}>
            Per km (₹)
          </label>
          <input
            id="fare-per-km"
            type="number"
            min="0"
            step="0.01"
            required
            value={perKm}
            onChange={(event) => setPerKm(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="fare-per-minute" className={styles.label}>
            Per minute (₹)
          </label>
          <input
            id="fare-per-minute"
            type="number"
            min="0"
            step="0.01"
            value={perMinute}
            onChange={(event) => setPerMinute(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="fare-waiting" className={styles.label}>
            Waiting, per minute (₹)
          </label>
          <input
            id="fare-waiting"
            type="number"
            min="0"
            step="0.01"
            value={waitingPerMinute}
            onChange={(event) => setWaitingPerMinute(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="fare-minimum" className={styles.label}>
            Minimum fare (₹)
          </label>
          <input
            id="fare-minimum"
            type="number"
            min="0"
            step="0.01"
            required
            value={minimumFare}
            onChange={(event) => setMinimumFare(event.target.value)}
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
          disabled={isSubmitting || !baseFare || !perKm || !minimumFare}
        >
          {isSubmitting ? "Creating…" : "Create draft"}
        </button>
      </div>
    </form>
  );
}
